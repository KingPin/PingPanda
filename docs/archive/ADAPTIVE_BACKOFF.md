# Adaptive Backoff and Circuit Breaker

PingPanda includes intelligent failure handling that prevents unnecessary resource usage when targets are down.

## Features

### 1. Adaptive Backoff
When a target (domain, IP, website, SSL cert) fails, PingPanda automatically increases the time between subsequent checks using exponential backoff:

- **First failure**: Wait 10 seconds (configurable)
- **Second failure**: Wait 20 seconds
- **Third failure**: Wait 40 seconds
- **Continues doubling** up to maximum backoff time (default: 5 minutes)

When the target recovers, backoff resets immediately.

### 2. Circuit Breaker
After repeated failures (default: 5), the circuit breaker "opens" and stops checking the target for a cooldown period (default: 60 seconds). This prevents:

- Wasting network bandwidth on known-down targets
- Excessive retry attempts
- Log spam from repeated failures

After cooldown, the circuit enters a "half-open" state and allows one check attempt. If successful, the circuit closes and normal checking resumes.

### 3. Cross-Check Deduplication
Targets are tracked with prefixes (`dns:`, `ping:`, `website:`, `ssl:`) to enable intelligent coordination:

- If DNS resolution fails for `example.com`, you can extend this to skip SSL checks for the same domain
- Prevents redundant checks for the same underlying resource

## Configuration

Add these environment variables or config file entries:

```bash
# Enable/disable adaptive backoff (default: true)
ENABLE_ADAPTIVE_BACKOFF=true

# Minimum backoff time in seconds (default: 10)
BACKOFF_MIN_SECONDS=10

# Maximum backoff time in seconds (default: 300)
BACKOFF_MAX_SECONDS=300

# Number of consecutive failures before circuit opens (default: 5)
CIRCUIT_BREAKER_THRESHOLD=5

# Cooldown period before circuit tries to close (default: 60)
CIRCUIT_BREAKER_COOLDOWN_SECONDS=60
```

## Example Behavior

### Scenario: Database Server Down

```
00:00 - Check #1 fails → Wait 10s
00:10 - Check #2 fails → Wait 20s  
00:30 - Check #3 fails → Wait 40s
01:10 - Check #4 fails → Wait 80s
02:30 - Check #5 fails → Circuit opens, wait 60s
03:30 - Circuit half-open, check #6 attempts
03:30 - Check #6 succeeds → Circuit closes, backoff resets
03:45 - Check #7 runs normally (15s interval)
```

### Benefits

✅ **Reduced load** on failing targets  
✅ **Faster recovery** detection with adaptive timing  
✅ **Cleaner logs** without repeated failure spam  
✅ **Better resource usage** - CPU, network, and thread efficiency  
✅ **Smart cross-check** coordination

## Monitoring

Check the status summary at startup to see backoff settings:

```
=== PingPanda Status Summary ===
...
Adaptive backoff: ENABLED (min: 10s, max: 300s)
Circuit breaker: threshold=5 failures, cooldown=60s
===============================
```

When verbose logging is enabled (`VERBOSE=true`), you'll see:

```
DEBUG - Skipping DNS check for example.com (in backoff/circuit open)
```

## Disabling

To disable adaptive backoff entirely:

```bash
ENABLE_ADAPTIVE_BACKOFF=false
```

This restores the original behavior of checking every target on every cycle.
