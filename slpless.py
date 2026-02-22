import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = '1'
import sys, curses, pygame, warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pygame.pkgdata")
from pathlib import Path
from typing import List, Tuple
try:
    from tinytag import TinyTag
except ImportError:
    TinyTag = None
paused = None
SUPPORTED = ('.mp3', '.wav') # TODO: поддержка форматов кроме мп3 и вав
def get_display_name(path: Path) -> str: # красивое название
    if TinyTag:
        try:
            tag = TinyTag.get(str(path))
            return f"{tag.artist or 'Unknown'} - {tag.title or p.stem}"
        except Exception:
            pass
    return path.name
def init_curses():
    stdscr = curses.initscr()
    curses.noecho(); curses.cbreak(); curses.curs_set(0)
    stdscr.keypad(True)
    curses.start_color()
    curses.use_default_colors()
    if curses.can_change_color():
        curses.init_color(curses.COLOR_MAGENTA, 183*1000//255, 189*1000//255, 248*1000//255)
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_MAGENTA)   # выделение
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_MAGENTA)
    return stdscr
def cleanup():
    curses.nocbreak(); curses.echo(); curses.curs_set(1); curses.endwin()
    pygame.mixer.quit()
def main(stdscr, folder: str):
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
    names = [get_display_name(p) for p in files]
    current_idx = 0
    playing: Path | None = None
    scroll_offset = 0
    pygame.mixer.init()
    pygame.mixer.music.set_volume(0.9)
    while True:
        h, w = stdscr.getmaxyx()
        list_area_h = h - 4  # заголовок
        if list_area_h < 1:
            list_area_h = 1
        if len(files) > list_area_h:  # скроллинг
            ideal_offset = current_idx - list_area_h // 2
            scroll_offset = max(0, min(ideal_offset, len(files) - list_area_h))
        else:
            scroll_offset = 0
        stdscr.clear()
        header = f"  {folder.name}  ({len(files)} tracks)" # заголовок с папкой
        stdscr.addstr(0, 0, header.center(w)[:w], curses.A_BOLD | curses.A_REVERSE)
        max_name_len = w
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
        help_text = "↑↓ select   ⏎ play/loop  SPACE stop  q quit"
        stdscr.addstr(h-1, 2, help_text[:w-4], curses.A_DIM)
        stdscr.refresh()
        try:         # клавиатура
            key = stdscr.getch()
        except KeyboardInterrupt:
            key = ord('q')
        if key in (ord('q'), 27):  # выход 
            break
        elif key == ord(' '):
            if playing:
                pygame.mixer.music.stop()
                playing = None
        elif key == curses.KEY_UP:
            current_idx = (current_idx - 1) % len(files)
        elif key == curses.KEY_DOWN:
            current_idx = (current_idx + 1) % len(files)
        elif key in (ord('\n'), 10, curses.KEY_ENTER):
            path = files[current_idx]
            try:
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play(-1)  # TODO: сделать поддержу не бесконечного проигрыша
                playing = path
            except pygame.error as e:
                err_msg = f"Cannot play: {e}"
                stdscr.addstr(h//2, max(0, w//2 - len(err_msg)//2), err_msg, curses.A_BOLD | curses.color_pair(1))
                stdscr.refresh()
                stdscr.getch() # TODO: пауза
    return 0
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Err: folder name needed")
        sys.exit(1)
    folder = sys.argv[1]
    try:
        stdscr = init_curses()
        ret = main(stdscr, folder)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        ret = 1
    finally:
        cleanup()# мощно вдохновился минимализмом, поэтому вот саклесс плеер на pygame
    sys.exit(ret)
