"""Clock & weather dashboard for a Linux TTY.

This module provides a curses-based dashboard that shows:
- A large ASCII-art clock on the left
- A large ASCII-art day+month block next to it
- Plain-text seconds between the time and date, aligned with the bottom
- Large ASCII-art temperatures for now, +2h, +4h to the right of the date
  with labels/conditions below

All content is constrained to the top VIEWPORT_RATIO of the terminal so
it works well when only the top portion of the physical screen is visible.

The console entry point ``clock`` is configured in ``pyproject.toml`` as
``clock = "clock:main"`, which runs ``main()`` below.
"""

from __future__ import annotations

import curses
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
from typing import Iterable, List, Optional, Sequence, Tuple

from pyfiglet import Figlet
from zoneinfo import ZoneInfo

# Fraction of terminal height (0 < VIEWPORT_RATIO <= 1.0) to use for drawing.
# With 0.33 we only use the top ~33% of the screen. Adjust as needed.
VIEWPORT_RATIO: float = 0.33

# Minimum number of rows we require for the dashboard area
MIN_HEIGHT: int = 8

# How often to refresh weather info (in seconds)
WEATHER_REFRESH_SECONDS: int = 600

# JSON weather endpoint for Ramat Hasharon, Israel
WEATHER_URL: str = "https://wttr.in/Ramat+Hasharon?format=j1"

# Timezone for Ramat Hasharon
TZ = ZoneInfo("Asia/Jerusalem")


@dataclass
class WeatherInfo:
    """Structured weather info for display in the dashboard."""

    now_temp_c: str
    now_desc: str
    plus2_temp_c: Optional[str]
    plus4_temp_c: Optional[str]


def _ascii(text: str) -> str:
    """Return ASCII-only version of *text* (drop non-ASCII chars like emoji)."""

    return text.encode("ascii", "ignore").decode("ascii", "ignore")


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


def _parse_hourly_points(data: dict) -> Sequence[Tuple[datetime, str]]:
    """Extract (local_datetime, tempC) points from wttr.in JSON.

    Times are interpreted in the Asia/Jerusalem timezone.
    """

    points: List[Tuple[datetime, str]] = []
    weather_days = data.get("weather") or []
    for day in weather_days:
        date_str = day.get("date")
        if not date_str:
            continue
        try:
            day_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        for h in day.get("hourly") or []:
            t_str = str(h.get("time", "0")).strip()
            if not t_str:
                continue
            # wttr uses "0", "300", "600" ... for local times
            try:
                t_val = int(t_str)
            except ValueError:
                continue
            hour = t_val // 100
            minute = t_val % 100
            try:
                dt_local = datetime.combine(day_date, dtime(hour=hour, minute=minute), TZ)
            except ValueError:
                continue

            temp_c = str(h.get("tempC") or h.get("temp_C") or "").strip()
            if not temp_c:
                continue
            points.append((dt_local, temp_c))

    return points


def _nearest_temp(points: Sequence[Tuple[datetime, str]], target: datetime) -> Optional[str]:
    """Return tempC for the hourly point nearest to *target* local time."""

    if not points:
        return None

    best_temp: Optional[str] = None
    best_delta: Optional[float] = None

    for dt, temp_c in points:
        delta = abs((dt - target).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_temp = temp_c

    return best_temp


def get_weather() -> Optional[WeatherInfo]:
    """Fetch structured weather info, or None on error.

    Uses wttr.in JSON (format=j1) and returns current temp/conditions, plus
    approximate temps for +2h and +4h ahead.
    """

    try:
        req = urllib.request.Request(
            WEATHER_URL,
            headers={"User-Agent": "curl/7.79.1"},  # wttr.in likes curl-style UA
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    try:
        current = (data.get("current_condition") or [{}])[0]
    except (TypeError, IndexError):
        current = {}

    now_temp = str(current.get("temp_C") or current.get("tempC") or "").strip()
    if not now_temp:
        now_temp = "?"

    desc_val = ""
    for item in current.get("weatherDesc") or []:
        if isinstance(item, dict) and item.get("value"):
            desc_val = str(item["value"])
            break
    now_desc = _ascii(desc_val).strip() or "Unknown"

    # Build hourly forecast points for +2h and +4h temps
    now_local = datetime.now(TZ)
    points = _parse_hourly_points(data)

    plus2 = _nearest_temp(points, now_local + timedelta(hours=2))
    plus4 = _nearest_temp(points, now_local + timedelta(hours=4))

    return WeatherInfo(
        now_temp_c=now_temp,
        now_desc=now_desc,
        plus2_temp_c=plus2,
        plus4_temp_c=plus4,
    )


def _draw_ascii_clock_and_date(
    stdscr: "curses._CursesWindow", *, usable_h: int, width: int, weather: Optional[WeatherInfo]
) -> Optional[int]:  # type: ignore[name-defined]
    """Draw a large ASCII-art clock, seconds, date, and large temps.

    Layout (top band, horizontally):
        [ CLOCK ASCII ]  [ seconds ]  [ DATE ASCII ]  [ TEMP ASCII blocks ]

    Returns the last row index used by the main art (``art_bottom_y``) or
    ``None`` if nothing was drawn.
    """

    now_struct = time.localtime()
    time_str = time.strftime("%H:%M", now_struct)
    seconds_str = time.strftime("%S", now_struct)
    date_block_str = time.strftime("%d %b", now_struct).upper()  # e.g. 28 JAN
    weekday_str = time.strftime("%A", now_struct)

    # Figlet instances
    clock_fig = Figlet(font="big")
    date_fig = Figlet(font="standard")
    temp_fig = Figlet(font="standard")

    clock_art = clock_fig.renderText(time_str)
    date_art = date_fig.renderText(date_block_str)

    clock_lines = _pad_lines(_trim_empty_border(clock_art.splitlines()))
    date_lines = _pad_lines(_trim_empty_border(date_art.splitlines()))

    clock_h = len(clock_lines)
    date_h = len(date_lines)

    # Prepare temp ASCII blocks if we have weather data
    now_temp_lines: List[str] = []
    plus2_temp_lines: List[str] = []
    plus4_temp_lines: List[str] = []

    if weather is not None:
        now_text = f"{weather.now_temp_c}C"
        now_temp_lines = _pad_lines(
            _trim_empty_border(temp_fig.renderText(now_text).splitlines())
        )

        if weather.plus2_temp_c:
            t2_text = f"{weather.plus2_temp_c}C"
            plus2_temp_lines = _pad_lines(
                _trim_empty_border(temp_fig.renderText(t2_text).splitlines())
            )
        if weather.plus4_temp_c:
            t4_text = f"{weather.plus4_temp_c}C"
            plus4_temp_lines = _pad_lines(
                _trim_empty_border(temp_fig.renderText(t4_text).splitlines())
            )

    temp_heights = [len(now_temp_lines), len(plus2_temp_lines), len(plus4_temp_lines)]
    temp_height = max(temp_heights) if any(temp_heights) else 0

    art_height = max(clock_h, date_h, temp_height)
    if art_height <= 0:
        return None

    # Draw starting at the very top (row 0). Header will be below.
    art_top = 0
    max_art_rows = max(1, usable_h - art_top - 3)  # leave some rows below for labels + header

    draw_rows = min(art_height, max_art_rows)

    # Horizontal layout for clock/date/seconds
    left_width = max(len(line) for line in clock_lines) if clock_lines else 0
    right_width = max(len(line) for line in date_lines) if date_lines else 0
    sec_text = f":{seconds_str}"
    sec_width = len(sec_text)

    left_x = 1
    sec_x = left_x + left_width + 2
    date_x = sec_x + sec_width + 3

    # Compute temp block widths
    now_w = max((len(line) for line in now_temp_lines), default=0)
    plus2_w = max((len(line) for line in plus2_temp_lines), default=0)
    plus4_w = max((len(line) for line in plus4_temp_lines), default=0)

    temps_base_x = date_x + right_width + 4
    plus2_offset = 5

    now_x = temps_base_x
    plus2_x = now_x + now_w + plus2_offset if now_w else temps_base_x
    plus4_x = plus2_x + plus2_w + 5 if plus2_w else plus2_x

    # Rough width check including temps; if too wide, drop future temps first
    total_needed = now_x + now_w
    if plus2_w:
        total_needed = max(total_needed, plus2_x + plus2_w)
    if plus4_w:
        total_needed = max(total_needed, plus4_x + plus4_w)

    # If not enough space, progressively disable plus4 and plus2
    if total_needed + 2 > width:
        plus4_temp_lines = []
        plus4_w = 0
        plus4_x = plus2_x
        total_needed = now_x + now_w
        if plus2_w:
            total_needed = max(total_needed, plus2_x + plus2_w)
        if total_needed + 2 > width:
            plus2_temp_lines = []
            plus2_w = 0
            plus2_x = now_x

    last_y: Optional[int] = None

    for i in range(draw_rows):
        y = art_top + i
        if y >= usable_h - 3:
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

        # Draw temp ASCII blocks
        if weather is not None:
            if now_temp_lines:
                line = now_temp_lines[i] if i < len(now_temp_lines) else "".ljust(now_w)
                if now_x < width:
                    try:
                        stdscr.addstr(y, now_x, line[: max(0, width - now_x)])
                    except curses.error:
                        pass
            if plus2_temp_lines:
                line = plus2_temp_lines[i] if i < len(plus2_temp_lines) else "".ljust(plus2_w)
                if plus2_x < width:
                    try:
                        stdscr.addstr(y, plus2_x, line[: max(0, width - plus2_x)])
                    except curses.error:
                        pass
            if plus4_temp_lines:
                line = plus4_temp_lines[i] if i < len(plus4_temp_lines) else "".ljust(plus4_w)
                if plus4_x < width:
                    try:
                        stdscr.addstr(y, plus4_x, line[: max(0, width - plus4_x)])
                    except curses.error:
                        pass

        last_y = y

    # Draw seconds as plain text aligned with the bottom row of the art
    if last_y is not None and sec_x < width:
        try:
            stdscr.addstr(last_y, sec_x, sec_text[: max(0, width - sec_x)])
        except curses.error:
            pass

    # Draw weekday under the date, and labels/conditions under temp blocks
    if last_y is not None:
        label_y = last_y + 1
        if label_y < usable_h - 1:
            # Weekday centered under the date block
            weekday_x = date_x + max(0, (right_width - len(weekday_str)) // 2)
            if weekday_x < width:
                try:
                    stdscr.addstr(label_y, weekday_x, weekday_str[: max(0, width - weekday_x)])
                except curses.error:
                    pass

            if weather is not None:
                if now_temp_lines and now_x < width:
                    now_label = f"Now: {weather.now_desc}"[: max(0, width - now_x)]
                    try:
                        stdscr.addstr(label_y, now_x, now_label)
                    except curses.error:
                        pass
                if plus2_temp_lines and plus2_x < width:
                    plus2_label = "+2h"[: max(0, width - plus2_x)]
                    try:
                        stdscr.addstr(label_y, plus2_x, plus2_label)
                    except curses.error:
                        pass
                if plus4_temp_lines and plus4_x < width:
                    plus4_label = "+4h"[: max(0, width - plus4_x)]
                    try:
                        stdscr.addstr(label_y, plus4_x, plus4_label)
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
    weather: Optional[WeatherInfo] = None
    last_good_weather: Optional[WeatherInfo] = None

    while True:
        now = time.time()

        # Periodically refresh weather
        if now - last_weather_time > WEATHER_REFRESH_SECONDS:
            new_weather = get_weather()
            last_weather_time = now
            if new_weather is not None:
                weather = new_weather
                last_good_weather = new_weather
            else:
                # On error, keep showing the last good reading if we have one
                if last_good_weather is not None:
                    weather = last_good_weather

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

        # Large ASCII-art clock + seconds + date + temp blocks at the top
        _draw_ascii_clock_and_date(stdscr, usable_h=usable_h, width=w, weather=weather)

        # Header in the bottom-right corner of the usable region
        header_text = "Clock dashboard q to quit"
        header_y = usable_h - 1
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
