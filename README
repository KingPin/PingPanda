# PingPanda

PingPanda is a Dockerized script that performs periodic checks for DNS resolution, ping responses, and website availability. It logs the results to a specified directory and can be configured to log to the terminal as well.

## Features

- DNS resolution checks
- Ping checks
- Website availability checks
- Configurable logging to file and terminal
- Log rotation

## Prerequisites

- Docker
- Docker Compose

## Getting Started

### Download the Docker Compose File

You can download the `docker-compose.yml` file using `wget` or `curl`:

Using `wget`:
```bash
wget https://raw.githubusercontent.com/KingPin/PingPanda/main/docker-compose.yml
```

Using `curl`:
```bash
curl -O https://raw.githubusercontent.com/KingPin/PingPanda/main/docker-compose.yml
```

### Configuration

The script can be configured using environment variables. Below is a list of the available environment variables and their default values:

- `DOMAIN`: The domain to check DNS resolution for (default: `google.com`)
- `PING_IP`: The IP address to ping (default: `1.1.1.1`)
- `LOG_DIR`: The directory to store logs (default: `/logs`)
- `LOG_TO_TERMINAL`: Whether to log to the terminal (default: `true`)
- `LOG_TO_FILE`: Whether to log to a file (default: `true`)
- `INTERVAL`: The interval in seconds between checks (default: `15`)
- `VERBOSE`: Enable verbose logging (default: `false`)
- `MAX_LOG_SIZE`: Maximum log size in bytes before rotation (default: `1048576`)
- `LOG_BACKUP_COUNT`: Number of backup logs to keep (default: `5`)
- `ENABLE_PING`: Enable ping checks (default: `true`)
- `ENABLE_DNS`: Enable DNS checks (default: `true`)
- `ENABLE_WEBSITE_CHECK`: Enable website availability checks (default: `false`)
- `CHECK_WEBSITE`: The website URL to check (default: empty)
- `RETRY_COUNT`: Number of retries for checks (default: `3`)
- `SUCCESS_HTTP_CODES`: Comma-separated list of HTTP status codes considered successful (default: `200`)

### Running the Service

To start the PingPanda service, run the following command in the folder you downloaded the docker-compose.yml above:

```bash
docker-compose up -d
```

This will start the PingPanda service in detached mode. Logs will be stored in the `./logs` directory on your host machine.

### Stopping the Service

To stop the PingPanda service run the following command in the folder you downloaded the docker-compose.yml above:

```bash
docker-compose down
```

## Logs

Logs are stored in the directory specified by the `LOG_DIR` environment variable. By default, this is the `./logs` directory on your host machine. The logs are rotated when they reach the size specified by the `MAX_LOG_SIZE` environment variable.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the GNU General Public License v3.0. See the [LICENSE](LICENSE) file for details.
