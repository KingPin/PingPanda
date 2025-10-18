# Adaptive Backoff and Circuit Breaker

This document contains extended notes and examples for PingPanda's adaptive backoff and circuit breaker behavior.

(Original content moved from project root.)

> See README.md for a short summary; this file contains expanded examples, configuration options, and rationale.

## Purpose
Adaptive backoff reduces load against targets that are failing and prevents noisy logs and wasted retries. The circuit breaker opens after a configurable number of failures and stops checks for a cooldown period.

## Configuration
- ENABLE_ADAPTIVE_BACKOFF (default: true)
- BACKOFF_MIN_SECONDS (default: 10)
- BACKOFF_MAX_SECONDS (default: 300)
- CIRCUIT_BREAKER_THRESHOLD (default: 5)
- CIRCUIT_BREAKER_COOLDOWN_SECONDS (default: 60)

## Example
- See the README for the short example behaviour timeline.

## Notes for Developers
- Implementation lives in `pingpanda_core/backoff.py`.
- Tests live in `tests/test_backoff.py` and include timing-sensitive assertions; keep sleep durations conservative in tests.
