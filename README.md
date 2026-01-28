# TTY Clock & Weather Dashboard

This project provides a small TTY dashboard that shows a large digital clock and current weather on a Linux virtual console (e.g. `tty1`).
It is designed for machines that usually run headless, where only the top portion of the physical screen is visible.

## Features

- Large ASCII-art clock (`HH:MM`) on the left
- Large ASCII-art day + month (e.g. `28 JAN`) on the right
- Seconds (`:SS`) shown as plain text between the time and date, aligned with the bottom of the clock
- Weather for **Ramat Hasharon, Israel** via `wttr.in`
- All content constrained to the top configurable fraction of the terminal (default: top 33%)
- Runs on a text console (no GUI required)
- Managed as a Python package using **uv**, with a `clock` console entry point
- Can be set up to start automatically on `tty1` via `systemd`

## Project Layout

- `pyproject.toml` – project metadata and uv build configuration
- `src/clock/__init__.py` – main implementation of the curses-based dashboard
- `README.md` – this file
- `dist/` – built artifacts (wheel and source distribution) after running `uv build`
- `show-clock-tty1.sh` – helper script to launch the dashboard on a given TTY using `openvt`

## Requirements

- Linux system with virtual consoles (e.g. `tty1`)
- Python (configured via uv; `pyproject.toml` targets Python 3.12+)
- `uv` package manager installed for the `bol` user
- `pyfiglet` (added as a dependency via `uv add pyfiglet`)
- `curl` or network access for fetching weather from `wttr.in`

## Installing Dependencies with uv

This project is already initialized as a uv-managed package. To ensure dependencies are installed:

```bash
uv sync
```

This will create/refresh the virtual environment and install the `clock` package and its dependencies (including `pyfiglet`).

## Running the Dashboard (SSH or Local Terminal)

From the project directory:

```bash
uv run clock
```

Controls:

- `q` – quit the dashboard

This runs the curses-based dashboard in the current terminal (e.g. over SSH) without affecting any TTYs.

## Controlling the Visible Screen Area

The dashboard only uses the top portion of the terminal, which is useful if the physical display only shows part of the screen.

In `src/clock/__init__.py`:

```python
VIEWPORT_RATIO: float = 0.33
```

- `VIEWPORT_RATIO` is a float between 0 and 1
- `0.33` means "use the top 33% of the terminal height"
- To adjust, edit the value and restart the dashboard (or the systemd service)

## Weather Source

Weather is fetched from:

```python
WEATHER_URL: str = "https://wttr.in/Ramat+Hasharon?format=3"
```

This returns a one-line summary, e.g. `Ramat Hasharon: +15°C, Rainy`. The dashboard caches the value and refreshes it periodically (every 600 seconds by default).

## Launching on tty1 Manually

The helper script `show-clock-tty1.sh` can launch the dashboard on a specific TTY (default `tty1`) using `openvt`.

Example:

```bash
cd ~/clock
sudo ./show-clock-tty1.sh
```

What this does:

- Unblanks `/dev/tty1`
- Starts the dashboard on that virtual terminal via `openvt`
- Switches the active console to `tty1`

You can pass a different TTY if needed:

```bash
sudo ./show-clock-tty1.sh /dev/tty2
```

## Systemd Service for Automatic Start on tty1

A `systemd` service can run the dashboard automatically on `tty1` at boot.

Example unit file (`/etc/systemd/system/clock-dashboard.service`):

```ini
[Unit]
Description=Clock & Weather Dashboard on tty1
After=systemd-user-sessions.service getty@tty1.service
Conflicts=getty@tty1.service

[Service]
User=bol
WorkingDirectory=/home/bol/clock
ExecStart=/home/bol/.local/bin/uv run clock
StandardInput=tty
StandardOutput=tty
TTYPath=/dev/tty1
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

### Enabling the Service

After creating the unit file:

```bash
sudo systemctl daemon-reload
sudo systemctl disable --now getty@tty1.service
sudo systemctl enable --now clock-dashboard.service
```

Check status:

```bash
systemctl status clock-dashboard.service
```

Logs:

```bash
sudo journalctl -u clock-dashboard.service
```

On the next boot, `tty1` will automatically show the clock dashboard instead of a login prompt.

## Customization

You can customize several aspects in `src/clock/__init__.py`:

- **Viewport height**: change `VIEWPORT_RATIO`
- **Weather location**: update `WEATHER_URL` to another `wttr.in` location
- **Refresh interval**: adjust `WEATHER_REFRESH_SECONDS`
- **ASCII-art fonts**: change the `Figlet` font names used for the clock and date

After making changes:

```bash
uv run clock                 # test in your current terminal
sudo systemctl restart clock-dashboard.service  # if running as a systemd service
```

## Development Notes

- The dashboard uses Python's `curses` library; no GUI dependencies are required.
- Colors are not modified explicitly; the terminal's current foreground/background are respected.
- The dashboard is intended to be resilient to small terminal sizes; if the space is too small, it will show a minimal message instead of crashing.

