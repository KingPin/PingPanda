# Adaptive Backoff and Circuit Breaker

This document contains extended notes and examples for PingPanda's adaptive backoff and circuit breaker behavior.

(Original content moved from project root.)

> See README.md for a short summary; this file contains expanded examples, configuration options, and rationale.

## Purpose
Adaptive backoff reduces load against targets that are failing and prevents noisy logs and wasted retries. The circuit breaker opens after a configurable number of failures and stops checks for a cooldown period.

## How It Works

### Exponential Backoff
When a check fails, an exponential backoff is applied before the next attempt:
- After 1st failure: `min_backoff * 2` (e.g., 20s with default 10s min)
- After 2nd failure: `min_backoff * 4` (e.g., 40s)
- After 3rd failure: `min_backoff * 8` (e.g., 80s)
- The multiplier caps at 32x to prevent excessively long waits

This gradual backpressure helps distinguish transient failures from sustained outages.

### Circuit Breaker
When consecutive failures reach the threshold (default: 5), the circuit "opens":
- All checks for that target are blocked during the cooldown period
- After cooldown, the circuit enters "half-open" state and allows one check
- If that check succeeds, the circuit closes and normal operation resumes
- If it fails, the circuit opens again for another cooldown period

## Configuration
- `ENABLE_ADAPTIVE_BACKOFF` (default: true) - Enable/disable the entire backoff system
- `BACKOFF_MIN_SECONDS` (default: 10) - Base backoff time in seconds
- `BACKOFF_MAX_SECONDS` (default: 300) - Maximum backoff time (caps the exponential growth)
- `CIRCUIT_BREAKER_THRESHOLD` (default: 5) - Failures before circuit opens
- `CIRCUIT_BREAKER_COOLDOWN_SECONDS` (default: 60) - How long circuit stays open

## Example Timeline

Given defaults (min=10s, threshold=5, cooldown=60s):

| Time | Event | Backoff Multiplier | Next Check Allowed |
|------|-------|-------------------|-------------------|
| 0s | Check fails (1st) | 2x | After 20s |
| 20s | Check fails (2nd) | 4x | After 40s |
| 60s | Check fails (3rd) | 8x | After 80s |
| 140s | Check fails (4th) | 16x | After 160s |
| 300s | Check fails (5th) | N/A | Circuit OPEN - blocked for 60s |
| 360s | Circuit half-open | 1x | Immediate retry allowed |

## Notes for Developers
- Implementation lives in `pingpanda_core/backoff.py`.
- Tests live in `tests/test_backoff.py` and include timing-sensitive assertions; keep sleep durations conservative in tests.
- The backoff multiplier resets to 1.0 when a check succeeds or when circuit closes after cooldown.
