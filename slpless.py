# slpless - suckless player for less code
# this is not actual suckless software, just inspired
import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = '1'
import sys
import curses
import pygame
import warnings
from pathlib import Path
from typing import List, Tuple, Dict, Any
import tomllib

try:
    from tinytag import TinyTag
except ImportError:
    TinyTag = None
DEFAULT_CONFIG = {
    "volume": {
        "default": 0.80,
        "step": 0.05,
        "min": 0.0,
        "max": 1.0
    },
    "colors": {
        "selection_fg": "black",
        "selection_bg": [183, 189, 248],   #b7bdf8
        "playing_fg":   "black",
        "playing_bg":   [200, 160, 220],
    },
    "ui": {
        "show_full_path": False
    }
}

SUPPORTED = ('.mp3', '.wav', '.ogg', '.flac')

def load_config() -> Dict[str, Any]:
    if sys.platform == "win32":
        config_dir = Path(__file__).parent
    else:
        config_dir = Path.home() / ".config" / "slpless"

    config_path = config_dir / "slpless.toml"
    if not config_path.is_file():
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            with config_path.open("w", encoding="utf-8") as f:
                f.write("""\
# slpless.toml - configuration file

[volume]
default = 0.80
step    = 0.05
min     = 0.0
max     = 1.0

[colors]
selection_fg = "black"
selection_bg = [183, 189, 248]
playing_fg   = "black"
playing_bg   = [200, 160, 220]

[ui]
show_full_path = false
""")
            print(f"Created default config: {config_path}", file=sys.stderr)
        except Exception as e:
            print(f"Cannot create config {config_path}: {e}", file=sys.stderr)
    if config_path.is_file():
        try:
            with config_path.open("rb") as f:
                data = tomllib.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            for k in ("volume", "colors", "ui"):
                if k in data:
                    merged[k].update(data[k])
            return merged
        except Exception as e:
            print(f"Config error in {config_path}: {e}", file=sys.stderr)
    return DEFAULT_CONFIG

def get_display_name(path: Path, show_full: bool = False) -> str:
    if TinyTag:
        try:
            tag = TinyTag.get(str(path))
            artist = tag.artist or "Unknown"
            title = tag.title or path.stem
            return f"{artist} - {title}"
        except:
            pass
    return str(path) if show_full else path.name

def init_curses(config: Dict):
    stdscr = curses.initscr()
    curses.noecho()
    curses.cbreak()
    curses.curs_set(0)
    stdscr.keypad(True)
    curses.start_color()
    curses.use_default_colors()

    sel_bg = config["colors"]["selection_bg"]
    play_bg = config["colors"]["playing_bg"]
    if curses.can_change_color():
        curses.init_color(10, *(int(c*1000//255) for c in sel_bg))   # 10 select bg
        curses.init_color(11, *(int(c*1000//255) for c in play_bg))  # 11 current track bg
    curses.init_pair(1, curses.COLOR_BLACK, 10)     # selection
    curses.init_pair(2, curses.COLOR_BLACK, 11)     # playing track
    curses.init_pair(3, 10, -1) # vol
    return stdscr

def cleanup():
    curses.nocbreak()
    curses.echo()
    curses.curs_set(1)
    curses.endwin()
    pygame.mixer.quit()

def draw_status_bar(stdscr, vol: float, playing: Path | None, names: List[str], files: List[Path], y: int, w: int):
    if playing is None:
        status = "Nothing playing"
    else:
        try:
            idx = files.index(playing)
            status = names[idx]
        except ValueError:
            status = playing.name
    max_status_len = w - 50
    if len(status) > max_status_len:
        status = status[:max_status_len] + "..."
    vol_text = f"{int(vol*100):3d}% {int(vol*20)*'█'}{(20-int(vol*20))*'░'}"
    line = f"{status:<{max_status_len + 20}}  {vol_text}"
    stdscr.addstr(y, max(-2, w//2 - len(line)//2), line, curses.color_pair(3))

def main(stdscr, folder: str):
    config = load_config()
    folder = Path(folder).resolve()
    if not folder.is_dir():
        print(f"Not a directory: {folder}", file=sys.stderr)
        return 1
    files: List[Path] = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED
    )
    if not files:
        print("No supported audio files found.", file=sys.stderr)
        return 1
    names = [get_display_name(p, config["ui"]["show_full_path"]) for p in files]
    current_idx = 0
    playing: Path | None = None
    scroll_offset = 0
    pygame.mixer.pre_init(44100, -16, 2, 4096)
    pygame.mixer.init()
    pygame.mixer.music.set_volume(config["volume"]["default"])
    current_volume = config["volume"]["default"]
    vol_step = config["volume"]["step"]
    current_track_name = ""
    track_dur = 0
    track_start_time = 0
    while True:
        h, w = stdscr.getmaxyx()
        list_area_h = h - 5
        if len(files) > list_area_h: # centering
            ideal_offset = current_idx - list_area_h // 5
            scroll_offset = max(0, min(ideal_offset, len(files) - list_area_h + 2))
        else:
            scroll_offset = 0
        stdscr.clear()
        header = f"  {folder.name}  ({len(files)} tracks)"
        stdscr.addstr(0, 0, header.center(w)[:w], curses.A_BOLD | curses.A_REVERSE)
        max_name_len = w - 6
        for i in range(scroll_offset, scroll_offset + list_area_h):
            if i >= len(files):
                break
            y = i - scroll_offset + 2
            name = names[i][:max_name_len]
            if len(names[i]) > max_name_len:
                name = name[:-3] + "..."
            line = f" {name:<{max_name_len}} "

            if i == current_idx:
                attr = curses.color_pair(1) | curses.A_BOLD
            elif playing and files[i] == playing:
                attr = curses.color_pair(2) | curses.A_BOLD
            else:
                attr = 0

            stdscr.addstr(y, 2, line, attr)
        draw_status_bar(stdscr, current_volume, playing, names, files, h-4, w)
        help_text = "↑↓ select  ⏎ play/loop  SPACE pause  ←→ volume  q quit"
        stdscr.addstr(h-2, 2, help_text[:w-4], curses.A_DIM)
        stdscr.refresh()

        try:
            key = stdscr.getch()
        except KeyboardInterrupt:
            key = ord('q')
        if key in (ord('q'), 27):
            break
        elif key == ord(' '):
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
            else:
                pygame.mixer.music.unpause()
        elif key == curses.KEY_UP:
            current_idx = (current_idx - 1) % len(files)
        elif key == curses.KEY_DOWN:
            current_idx = (current_idx + 1) % len(files)
        elif key in (ord('\n'), 10, curses.KEY_ENTER):
            path = files[current_idx]
            try:
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play(-1)   # TODO: playback other than inf reset
                playing = path
                current_track_name = get_display_name(path, config["ui"]["show_full_path"])
                try:
                    if TinyTag:
                        tag = TinyTag.get(str(path))
                        track_dur = tag.duration or 0
                    else:
                        track_dur = 0
                except:
                    track_dur = 0
                track_start_time = pygame.time.get_ticks()
            except pygame.error as e:
                err = f"Cannot play: {e}"
                stdscr.addstr(h//2, max(0, w//2 - len(err)//2), err,
                              curses.A_BOLD | curses.color_pair(1))
                stdscr.refresh()
                stdscr.getch()
        elif key == curses.KEY_LEFT:
            current_volume = max(config["volume"]["min"], current_volume - vol_step)
            pygame.mixer.music.set_volume(current_volume)
        elif key == curses.KEY_RIGHT:
            current_volume = min(config["volume"]["max"], current_volume + vol_step)
            pygame.mixer.music.set_volume(current_volume)
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: slpless.py <folder>")
        sys.exit(1)
    folder = sys.argv[1]
    config = load_config()
    try:
        stdscr = init_curses(config)
        ret = main(stdscr, folder)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        ret = 1
    finally:
        cleanup()
    sys.exit(ret)
