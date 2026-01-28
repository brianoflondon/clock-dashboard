"""Clock & weather dashboard for a Linux TTY.

This module provides a curses-based dashboard that shows:
- A large ASCII-art clock on the left
- A large ASCII-art day+month block next to it
- Plain-text seconds between the time and date, aligned with the bottom
- A brief, one-line weather summary at the bottom of the visible region

All content is constrained to the top VIEWPORT_RATIO of the terminal so
it works well when only the top portion of the physical screen is visible.

The console entry point ``clock`` is configured in ``pyproject.toml`` as
``clock = "clock:main"``, which runs ``main()`` below.
"""

from __future__ import annotations

import curses
import time
import textwrap
import urllib.error
import urllib.request
from typing import Iterable, List, Optional

from pyfiglet import Figlet

# Fraction of terminal height (0 < VIEWPORT_RATIO <= 1.0) to use for drawing.
# With 0.33 we only use the top ~33% of the screen. Adjust as needed.
VIEWPORT_RATIO: float = 0.33

# Minimum number of rows we require for the dashboard area
MIN_HEIGHT: int = 8

# How often to refresh weather info (in seconds)
WEATHER_REFRESH_SECONDS: int = 600

# Simple text weather endpoint (one-line summary) for Ramat Hasharon, Israel
WEATHER_URL: str = "https://wttr.in/Ramat+Hasharon?format=3"


def get_weather() -> str:
    """Fetch a one-line weather summary, or a fallback message on error."""

    try:
        req = urllib.request.Request(
            WEATHER_URL,
            headers={"User-Agent": "curl/7.79.1"},  # wttr.in likes curl-style UA
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8", errors="ignore").strip()
            return data or "Weather: unavailable"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return "Weather: unavailable"


def _pad_lines(lines: Iterable[str]) -> List[str]:
    """Return a list of lines padded to equal width."""

    lines_list = list(lines)
    if not lines_list:
        return []
    width = max(len(line) for line in lines_list)
    return [line.ljust(width) for line in lines_list]


def _trim_empty_border(lines: Iterable[str]) -> List[str]:
    """Trim completely empty rows from top and bottom of ASCII art."""

    out = list(lines)
    # Trim top
    while out and not out[0].strip():
        out.pop(0)
    # Trim bottom
    while out and not out[-1].strip():
        out.pop()
    return out or [""]


def _draw_ascii_clock_and_date(
    stdscr: "curses._CursesWindow", *, usable_h: int, width: int
) -> Optional[int]:  # type: ignore[name-defined]
    """Draw a large ASCII-art clock, seconds, and day+month.

    Layout (horizontally):
        [ CLOCK ASCII ]  [ seconds ]  [ DATE ASCII ]

    Returns the last row index used by the art (``art_bottom_y``) or ``None``
    if nothing was drawn. This is used to position the weather.
    """

    now_struct = time.localtime()
    time_str = time.strftime("%H:%M", now_struct)
    seconds_str = time.strftime("%S", now_struct)
    date_block_str = time.strftime("%d %b", now_struct).upper()  # e.g. 28 JAN

    # Figlet instances
    clock_fig = Figlet(font="big")
    date_fig = Figlet(font="standard")

    clock_art = clock_fig.renderText(time_str)
    date_art = date_fig.renderText(date_block_str)

    clock_lines = _trim_empty_border(clock_art.splitlines())
    date_lines = _trim_empty_border(date_art.splitlines())

    clock_lines = _pad_lines(clock_lines)
    date_lines = _pad_lines(date_lines)

    clock_h = len(clock_lines)
    date_h = len(date_lines)
    art_height = max(clock_h, date_h)

    if art_height <= 0:
        return None

    # Draw starting at the very top (row 0). Weather and header will be below.
    art_top = 0
    max_art_rows = max(1, usable_h - art_top - 2)  # leave at least 2 rows

    draw_rows = min(art_height, max_art_rows)

    # Horizontal layout
    left_width = max(len(line) for line in clock_lines) if clock_lines else 0
    right_width = max(len(line) for line in date_lines) if date_lines else 0
    sec_text = f":{seconds_str}"
    sec_width = len(sec_text)

    left_x = 1
    sec_x = left_x + left_width + 2
    date_x = sec_x + sec_width + 3

    total_width_needed = left_width + 2 + sec_width + 3 + right_width

    # If not enough space, fall back to centered plain text
    if total_width_needed + 2 > width:
        plain_time = time.strftime("%H:%M:%S", now_struct)
        plain_date = time.strftime("%A, %Y-%m-%d", now_struct)

        inner_top = 0  # no top space
        inner_bottom = max(inner_top, usable_h - 3)
        inner_height = max(1, inner_bottom - inner_top + 1)

        time_y = inner_top + inner_height // 2 - 1
        if time_y < inner_top:
            time_y = inner_top
        date_y = min(usable_h - 3, time_y + 1)

        time_x = max(0, (width - len(plain_time)) // 2)
        date_x2 = max(0, (width - len(plain_date)) // 2)

        try:
            stdscr.addstr(time_y, time_x, plain_time, curses.A_BOLD)
        except curses.error:
            pass
        try:
            stdscr.addstr(date_y, date_x2, plain_date)
        except curses.error:
            pass
        return date_y

    last_y: Optional[int] = None

    for i in range(draw_rows):
        y = art_top + i
        if y >= usable_h - 2:
            break

        clock_line = clock_lines[i] if i < clock_h else "".ljust(left_width)
        date_line = date_lines[i] if i < date_h else "".ljust(right_width)

        # Draw clock block
        if left_x < width:
            try:
                stdscr.addstr(y, left_x, clock_line[: max(0, width - left_x)])
            except curses.error:
                pass

        # Draw date block
        if date_x < width:
            try:
                stdscr.addstr(y, date_x, date_line[: max(0, width - date_x)])
            except curses.error:
                pass

        last_y = y

    # Draw seconds as plain text aligned with the bottom row of the art
    if last_y is not None and sec_x < width:
        try:
            stdscr.addstr(last_y, sec_x, sec_text[: max(0, width - sec_x)])
        except curses.error:
            pass

    return last_y


def _draw(stdscr: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
    """Main curses drawing loop.

    This is wrapped by :func:`curses.wrapper` in :func:`main`.
    """

    # Basic curses setup (no color manipulation; terminal keeps its defaults)
    try:
        curses.curs_set(0)  # hide cursor
    except curses.error:
        # Not all terminals support cursor visibility changes
        pass

    stdscr.nodelay(True)  # non-blocking getch
    stdscr.timeout(200)  # getch timeout in ms

    last_weather_time = 0.0
    weather = "Loading weather..."

    while True:
        now = time.time()

        # Periodically refresh weather
        if now - last_weather_time > WEATHER_REFRESH_SECONDS:
            weather = get_weather()
            last_weather_time = now

        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Compute usable height based on VIEWPORT_RATIO
        usable_h = int(h * VIEWPORT_RATIO)
        if usable_h < MIN_HEIGHT:
            usable_h = MIN_HEIGHT
        if usable_h > h:
            usable_h = h

        # Safety guard: if terminal is extremely small
        if usable_h <= 1 or w <= 10:
            try:
                stdscr.addstr(0, 0, "Terminal too small")
            except curses.error:
                pass
            stdscr.refresh()
            time.sleep(0.5)
            ch = stdscr.getch()
            if ch in (ord("q"), ord("Q")):
                break
            continue

        # Large ASCII-art clock + seconds + date block
        art_bottom = _draw_ascii_clock_and_date(stdscr, usable_h=usable_h, width=w)

        # Weather near the bottom of the usable region, with ~2-line gap
        header_text = "Clock dashboard q to quit"
        header_y = usable_h - 1

        if weather:
            max_width = max(10, w - 4)
            wrapped = textwrap.wrap(weather, max_width)
            max_weather_lines = 2
            wrapped = wrapped[:max_weather_lines]

            if art_bottom is not None:
                # 2 blank lines between art and first weather line
                start_y = art_bottom + 3
            else:
                start_y = header_y - len(wrapped)

            # Ensure weather fits above the header; if not, shift up
            if start_y + len(wrapped) > header_y:
                start_y = max(1, header_y - len(wrapped))

            for i, line in enumerate(wrapped):
                y = start_y + i
                if y >= header_y:  # never draw over the header line
                    break
                try:
                    stdscr.addstr(y, 2, line[: max(0, w - 4)])
                except curses.error:
                    pass

        # Header in the bottom-right corner of the usable region
        header_x = max(0, w - len(header_text) - 1)
        try:
            stdscr.addstr(header_y, header_x, header_text[: max(0, w - header_x)])
        except curses.error:
            pass

        stdscr.refresh()

        # Handle keypresses (non-blocking)
        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            break

        time.sleep(0.2)


def main() -> None:
    """Entry point for the ``clock`` console script.

    Runs the curses-based dashboard on the current TTY.
    """

    curses.wrapper(_draw)


__all__ = [
    "main",
    "get_weather",
    "VIEWPORT_RATIO",
    "MIN_HEIGHT",
    "WEATHER_REFRESH_SECONDS",
    "WEATHER_URL",
]
