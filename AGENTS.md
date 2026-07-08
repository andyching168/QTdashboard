# Repository Guidelines

## Project Structure & Module Organization

This is a Python/PyQt6 digital dashboard for a Luxgen M7. The real vehicle environment is Raspberry Pi 4 running Raspberry Pi OS. `main.py` is the application entry point for UI, vehicle data, navigation, Spotify, MQTT, and hardware integrations. UI components live in `ui/`; shared helpers in `core/`; CAN/OBD logic in `vehicle/`; GPIO code in `hardware/`; GPS and speed-limit logic in `navigation/`; Spotify code in `spotify/`; WiFi helpers in `wifi/`; deployment scripts in `deploy/` and `scripts/`. Tests are in `tests/test_*.py`. Static assets and speed-limit CSV data are under `assets/`.

## Build, Test, and Development Commands

- `python3 -m venv venv && source venv/bin/activate`: create and enter a local virtual environment.
- `pip install -r requirements.txt`: install runtime dependencies.
- `python main.py`: run the dashboard with automatic hardware detection.
- `python main.py --mode demo`: run without vehicle hardware using simulated data.
- `pytest`: run the full test suite.
- `pytest tests/test_speed_limit.py`: run one focused test module.
- `./deploy/auto_start.sh`: exercise the Raspberry Pi startup flow.

## Coding Style & Naming Conventions

Use Python 3.8+ syntax and 4-space indentation. Keep modules focused by domain and prefer small helpers when extending large UI classes. Use `snake_case` for functions, variables, files, and tests; `PascalCase` for Qt widgets/classes; and the existing `signal_...` pattern for Qt signals. Preserve bilingual comments when they explain vehicle, UI, or hardware behavior.

## Testing Guidelines

Tests use `pytest` and live in `tests/`. Name files `test_<feature>.py` and functions `test_<behavior>()`. For UI or hardware-adjacent changes, prefer tests around parsing, state transitions, or signal handling rather than physical devices. Run a focused test first, then `pytest`.

## Commit & Pull Request Guidelines

Recent history uses short imperative summaries, sometimes with prefixes such as `feat(...)` or `perf:`. Keep commits focused, for example `feat(music_card): dim bright album art` or `Reduce dashboard update overhead`. Pull requests should describe the change, list tests run, note hardware requirements or skipped hardware validation, and include screenshots or videos for visible UI changes.

## Security & Configuration Tips

Do not commit real credentials, tokens, or local runtime state. Use `spotify/spotify_config.json.example`, `mqtt_config_example.json`, and `telegram_config_example.json`. Treat scripts that call `sudo`, reboot, reset USB, or alter systemd services as Raspberry Pi 4 / Raspberry Pi OS production operations; document permission changes in the PR.
