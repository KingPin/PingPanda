# PingPanda Filtering Features

The PingPanda monitoring tool now supports filtering options to show only successful or failed check results.

## Environment Variables

Add these environment variables to control filtering:

```bash
# Show only successful check results
SHOW_ONLY_SUCCESS=true

# Show only failed check results  
SHOW_ONLY_FAILURE=true
```

## Command Line Arguments

Use these command-line flags for dynamic filtering:

```bash
# Show only successful results
python pingpanda.py --show-only-success

# Show only failed results
python pingpanda.py --show-only-failure

# Show verbose output with filtering
python pingpanda.py --verbose --show-only-failure
```

## Docker Example

```bash
# Run with environment variable filtering
docker run -e SHOW_ONLY_FAILURE=true pingpanda

# Run with command line filtering
docker run pingpanda --show-only-success
```

## Filtering Behavior

- **Default**: Shows all check results (both success and failure)
- **SHOW_ONLY_SUCCESS=true**: Only displays successful check results
- **SHOW_ONLY_FAILURE=true**: Only displays failed check results  
- **Both enabled**: Displays warning message and shows no results (conflicting filters)

## Use Cases

1. **Production Monitoring**: Use `SHOW_ONLY_FAILURE=true` to focus on issues
2. **Health Verification**: Use `SHOW_ONLY_SUCCESS=true` to confirm services are working
3. **Development/Testing**: Use default (show all) for comprehensive visibility

## Notes

- Filtering only affects log output display
- Prometheus metrics are always updated regardless of filtering
- Notifications are still sent based on alert thresholds
- Status tracking continues to work normally with filtering enabled
