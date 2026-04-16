# PingPanda Compose Examples

Drop-in `docker compose` files for common PingPanda setups. Each one uses the published image [`ghcr.io/kingpin/pingpanda:latest`](https://ghcr.io/kingpin/pingpanda) — no build step required.

Pick a file and run it with:

```bash
docker compose -f examples/<file>.yml up -d
```

For files that reference `${VAR}`, either export the variable in your shell or create a `.env` file next to the compose file:

```bash
echo "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ" > .env
docker compose -f examples/notify-slack.yml --env-file .env up -d
```

## Index

### Tiered (start here)

| File | What it does | Good for |
|------|--------------|----------|
| [`minimal.yml`](minimal.yml) | DNS + ping only, no alerts | First run / smoke test |
| [`standard.yml`](standard.yml) | DNS + ping + website + SSL, Slack + Prometheus | Home lab / small team |
| [`full.yml`](full.yml) | Every feature enabled (stats, flap detection, backoff, fan-out alerts) | Reference / tuning starting point |

### By notification provider

| File | Sends alerts to |
|------|-----------------|
| [`notify-slack.yml`](notify-slack.yml) | Slack (with channel override + emoji) |
| [`notify-teams.yml`](notify-teams.yml) | Microsoft Teams |
| [`notify-discord.yml`](notify-discord.yml) | Discord (with custom avatar/username) |
| [`notify-multi.yml`](notify-multi.yml) | Slack + Teams + Discord simultaneously |

### By check type

Use these when you only care about one probe category — each file disables all other check types.

| File | Probes | Notes |
|------|--------|-------|
| [`checks-dns.yml`](checks-dns.yml) | DNS resolution | Handy for internal resolvers or propagation checks |
| [`checks-ping.yml`](checks-ping.yml) | ICMP ping | Requires `NET_RAW` capability (already set) |
| [`checks-website.yml`](checks-website.yml) | HTTP/HTTPS status codes | Customize `SUCCESS_HTTP_CODES` per endpoint |
| [`checks-ssl.yml`](checks-ssl.yml) | TLS certificate expiry | Long interval — certs don't change often |

### Integrations

| File | Description |
|------|-------------|
| [`prometheus-stack.yml`](prometheus-stack.yml) | PingPanda + a Prometheus container, pre-wired for scraping |

## Mixing & matching

The examples are intentionally focused. To combine features (e.g. SSL-only checks with Teams alerts and Prometheus), copy `standard.yml` as your base and strip/add the blocks you need — all the knobs are documented in the [main README](../README.md#configuration).

## ICMP note

Any compose file that enables `ENABLE_PING=true` includes `cap_add: [NET_RAW]`. If you're running a hardened host that blocks capability grants, either disable ping (`ENABLE_PING=false`) or run the container as root.
