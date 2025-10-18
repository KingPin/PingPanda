# PingPanda Filtering Features

This file expands on the filtering options briefly described in the root README.

(Original content moved from project root.)

## Environment Variables

- `SHOW_ONLY_SUCCESS=true` — show only successful check results
- `SHOW_ONLY_FAILURE=true` — show only failed check results

## Command Line Arguments

- `--show-only-success` — show only successful results
- `--show-only-failure` — show only failed results

## Behaviour

- Default: shows both success and failure
- If both `SHOW_ONLY_SUCCESS` and `SHOW_ONLY_FAILURE` are enabled, a warning is shown and no results displayed
- Filtering only affects output formatting; metrics and notifications still work

## Notes for Developers

- Implementation lives in `pingpanda_core/checks.py` and `pingpanda_core/app.py`
- Tests may rely on `DummyApp` patterns under `tests/`
