# Briner File Organizer

Briner is a Windows-friendly Python app that organizes files by scanning a target folder periodically. It is designed for low-resource background use: the default mode is interval scanning, while realtime monitoring with `watchdog` remains available as an optional mode.

## Features

- Periodic folder scans, recommended every hour.
- Optional realtime monitoring.
- Deterministic rules before LLM classification.
- Gemini support through `GOOGLE_API_KEY` or `GEMINI_API_KEY`.
- Dry-run mode for safe simulation.
- SQLite audit/state database.
- Windows `.exe` packaging with PyInstaller.
- Optional startup shortcut for running at login.

## Quick Start

```powershell
cd briner_agent
python -m pip install -r requirements.txt
python main.py --setup
python main.py
```

During setup, choose the folder to organize, the scan interval in seconds, and whether to enable dry-run.

## AI Configuration

Copy the example environment file and add your key:

```powershell
copy briner_agent\.env.example briner_agent\.env
```

Edit `.env`:

```text
GOOGLE_API_KEY=your_google_or_gemini_api_key_here
```

Do not commit `.env`.

## Common Commands

Run once:

```powershell
python briner_agent\main.py --once
```

Simulate without moving files:

```powershell
python briner_agent\main.py --once --dry-run
```

Show metrics:

```powershell
python briner_agent\main.py --metrics
```

Force setup again:

```powershell
python briner_agent\main.py --setup
```

## Windows Packaging

See [README_WINDOWS.md](README_WINDOWS.md) for the PyInstaller and auto-start guide.

## User Manual

See [MANUAL_USO.md](MANUAL_USO.md) for the Spanish usage manual.

## Tests

```powershell
cd briner_agent
python -m pytest -q
```

