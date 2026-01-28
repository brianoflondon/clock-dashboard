#!/usr/bin/env python3
import curses
import time
import textwrap
import urllib.request
import urllib.error

# Fraction of terminal height (0 < VIEWPORT_RATIO <= 1.0) to use for drawing.
# With 0.33 we only use the top ~33% of the screen. Adjust as needed.
VIEWPORT_RATIO = 0.33

# Minimum number of rows we require for the dashboard area
MIN_HEIGHT = 8

# How often to refresh weather info (in seconds)
WEATHER_REFRESH_SECONDS = 600

# Simple text weather endpoint (one-line summary)
WEATHER_URL = "https://wttr.in/?format=3"


def get_weather():
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


def draw(stdscr):
    # Basic curses setup
    try:
        curses.curs_set(0)  # hide cursor
    except curses.error:
        pass

    stdscr.nodelay(True)     # non-blocking getch
    stdscr.timeout(200)      # getch timeout in ms

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

        # Header line at top-left of usable region
        header_text = "Clock dashboard (press 'q' to quit)"
        try:
            stdscr.addstr(0, 0, header_text[: max(0, w - 1)])
        except curses.error:
            pass

        # Time and date strings
        time_str = time.strftime("%H:%M:%S")
        date_str = time.strftime("%A, %Y-%m-%d")

        # Center the time within the usable region
        # Reserve top row for header and bottom rows for weather
        # So we place clock roughly in the middle of rows [1, usable_h - 3]
        inner_top = 1
        inner_bottom = max(inner_top, usable_h - 3)
        inner_height = max(1, inner_bottom - inner_top + 1)

        time_y = inner_top + inner_height // 2 - 1
        if time_y < inner_top:
            time_y = inner_top
        date_y = min(usable_h - 3, time_y + 1)

        time_x = max(0, (w - len(time_str)) // 2)
        date_x = max(0, (w - len(date_str)) // 2)

        try:
            stdscr.addstr(time_y, time_x, time_str, curses.A_BOLD)
        except curses.error:
            pass

        try:
            stdscr.addstr(date_y, date_x, date_str)
        except curses.error:
            pass

        # Weather near the bottom of the usable region
        if weather:
            max_width = max(10, w - 4)
            wrapped = textwrap.wrap(weather, max_width)
            max_weather_lines = 2
            wrapped = wrapped[:max_weather_lines]

            start_y = usable_h - len(wrapped)
            if start_y < inner_top:
                start_y = inner_top

            for i, line in enumerate(wrapped):
                y = start_y + i
                if y >= usable_h:
                    break
                try:
                    stdscr.addstr(y, 2, line[: max(0, w - 4)])
                except curses.error:
                    pass

        stdscr.refresh()

        # Handle keypresses (non-blocking)
        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            break

        time.sleep(0.2)


def main():
    curses.wrapper(draw)


if __name__ == "__main__":
    main()
