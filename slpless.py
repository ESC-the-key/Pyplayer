# slpless - suckless player for less code
# this is not actual suckless software, just inspired
import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = '1'
import sys, curses, pygame
from pathlib import Path
import tomllib
from rapidfuzz import process, fuzz
from typing import Dict, List, Any

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
        "playing_bg":   [200, 160, 220], # darker than b7bdf8
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

def get_song_time(path):
    if TinyTag:
        try:
            tag = TinyTag.get(str(path))
            return tag.duration
        except:
            pass
    return None

def draw_status_bar(stdscr, vol: float, playing: Path | None, names: List[str], files: List[Path], y: int, w: int):
    if playing is None:
        status = "--"
    else:
        try:
            idx = files.index(playing)
            status = names[idx]
        except ValueError:
            status = playing.name
    max_status_len = w - 50
    if len(status) > max_status_len:
        status = status[:max_status_len] + "..."
    time_text = ""
    if playing:
        pos = pygame.mixer.music.get_pos()
        cur = 0 if pos < 0 else pos // 1000
        total = get_song_time(playing)

        if total:
            time_text = f"{cur//60:02}:{cur%60:02}/{int(total)//60:02}:{int(total)%60:02}"
        else:
            time_text = f"{cur//60:02}:{cur%60:02}"
    vol_text = f"{int(vol*100):3d}% {int(vol*20)*'█'}{(20-int(vol*20))*'░'}"
    line = f"{status:<{max_status_len + 10}} {time_text:>12}  {vol_text}"
    stdscr.addstr(y, max(-2, w//2 - len(line)//2), line, curses.color_pair(3))

def handle_keybind(key, state):
    if key in (ord('q'), 27):
        state["quit"] = True

    elif key == ord(' '):
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
        else:
            pygame.mixer.music.unpause()

    elif key == curses.KEY_LEFT:
        state["volume"] = max(state["vol_min"], round(state["volume"] - state["vol_step"], 2))
        pygame.mixer.music.set_volume(state["volume"])

    elif key == curses.KEY_RIGHT:
        state["volume"] = min(state["vol_max"], round(state["volume"] + state["vol_step"], 2))
        pygame.mixer.music.set_volume(state["volume"])
    return state
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
    repeat = False
    vol_step = config["volume"]["step"]
    search_mode = False
    search_query = ""
    search_results = []
    search_cursor = 0
    state = {
        "quit": False,
        "volume": current_volume,
        "vol_step": vol_step,
        "vol_min": config["volume"]["min"],
        "vol_max": config["volume"]["max"]
    }
    def run_search():
        nonlocal search_results, search_cursor

        if not search_query.strip():
            search_results = list(range(len(names)))
            search_cursor = min(search_cursor, len(search_results)-1) if search_results else 0
            return

        results = process.extract(
            search_query,
            names,
            scorer=fuzz.WRatio,
            limit=100
        )

        search_results = [idx for _, score, idx in results if score > 45]
        search_cursor = 0
    while True:
        h, w = stdscr.getmaxyx()
        stdscr.clear()
        header = f"  {folder.name}  ({len(files)} tracks)"
        stdscr.addstr(0, 0, header.center(w)[:w], curses.A_BOLD | curses.A_REVERSE)
        if search_mode:
            stdscr.addstr(1, 2, f"/{search_query}"[:w-4], curses.A_BOLD)
        list_h = h - 6
        max_name_len = w - 6
        if search_mode:
            display_ind = search_results
            cursor_pos = search_cursor
        else:
            display_ind = list(range(len(files)))
            cursor_pos = current_idx
        list_len = len(display_ind)
        if list_len > list_h:
            ideal_offset = max(0, cursor_pos - list_h // 4)
            scroll_offset = min(ideal_offset, list_len - list_h)
        else:
            scroll_offset = 0
        for rel_row in range(list_h):
            abs_idx = scroll_offset + rel_row
            if abs_idx >= list_len:
                break
            real_idx = display_ind[abs_idx]
            y = rel_row + 2
            name = names[real_idx][:max_name_len]
            if len(names[real_idx]) > max_name_len:
                name = name[:-3] + '...'
            line = f" {name:<{max_name_len}} "
            is_cursor = (abs_idx == cursor_pos)
            is_playing = (playing is not None and files[real_idx] == playing)
            if is_cursor:
                attr = curses.color_pair(1) | curses.A_BOLD
            elif is_playing:
                attr = curses.color_pair(2) | curses.A_BOLD
            else:
                attr = 0
            stdscr.addstr(y, 2, line, attr)
        draw_status_bar(stdscr, current_volume, playing, names, files, h-4, w)
        repeat_text = "repeat one" if repeat else "repeat all"
        help_text = f"↑↓ select  ⏎ play  SPACE pause  ←→ volume  r repeat  q quit  [{repeat_text}]"
        stdscr.addstr(h-2, 2, help_text[:w-4], curses.A_DIM)
        stdscr.refresh()

        key = stdscr.getch()
        if not search_mode:
            state = handle_keybind(key, state)
        if key == curses.KEY_UP:
            if search_mode:
                search_cursor = (search_cursor - 1) % max(1, len(search_results))
            else:
                current_idx = (current_idx - 1) % len(files)

        elif key == curses.KEY_DOWN:
            if search_mode:
                search_cursor = (search_cursor + 1) % max(1, len(search_results))
            else:
                current_idx = (current_idx + 1) % len(files)

        elif key in (10, curses.KEY_ENTER) and not search_mode:
            path = files[current_idx]
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play(-1 if repeat else 0)
            play_pos = 0.0
            playing = path  

        elif key == ord('/') and not search_mode:
            search_mode = True
            search_query = ""
            run_search()
        elif key == ord('r') and not search_mode:
            repeat = not repeat

        elif search_mode:

            if key == 27:
                search_mode = False
                search_query = ""
                run_search()

            elif key in (10, curses.KEY_ENTER):

                idx = search_results[search_cursor]
                path = files[idx]

                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play(-1 if repeat else 0)
                play_pos = 0.0

                playing = path
                current_idx = idx

                search_mode = False
                search_query = ""
            elif key in (curses.KEY_BACKSPACE, 127):
                search_query = search_query[:-1]
                run_search()

            elif 32 <= key <= 126:
                search_query += chr(key)
                run_search()

        if state["quit"]:
            break

        current_volume = state["volume"]
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 slpless.py <folder>")
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
