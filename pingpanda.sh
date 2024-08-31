#!/bin/bash

# Read environment variables
LOG_DIR=${LOG_DIR:-/logs} # Default to /logs
LOG_FILE="$LOG_DIR/pingpanda.log" # Default to /logs/pingpanda.log
INTERVAL=${INTERVAL:-15} # Default to 15 seconds
VERBOSE=${VERBOSE:-false} # Default to non-verbose mode
MAX_LOG_SIZE=${MAX_LOG_SIZE:-1048576} # 1MB default max log size
LOG_BACKUP_COUNT=${LOG_BACKUP_COUNT:-5} # Default to keep 5 backup logs
LOG_TO_TERMINAL=${LOG_TO_TERMINAL:-true} # Default to log to terminal
LOG_TO_FILE=${LOG_TO_FILE:-true} # Default to log to file
ENABLE_PING=${ENABLE_PING:-true} # Default to enable ping checks
ENABLE_DNS=${ENABLE_DNS:-true} # Default to enable DNS checks
CHECK_WEBSITE=${CHECK_WEBSITE:-} # Default to no website check
ENABLE_WEBSITE_CHECK=${ENABLE_WEBSITE_CHECK:-false} # Default to disable website check
RETRY_COUNT=${RETRY_COUNT:-3} # Default to 3 retries
SUCCESS_HTTP_CODES=${SUCCESS_HTTP_CODES:-200} # Default to HTTP 200 as success
SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL:-} # Slack webhook URL for notifications
TEAMS_WEBHOOK_URL=${TEAMS_WEBHOOK_URL:-} # Teams webhook URL for notifications
DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL:-} # Discord webhook URL for notifications
ALERT_THRESHOLD=${ALERT_THRESHOLD:-3} # Number of consecutive failures before alerting
DOMAINS=${DOMAINS:-google.com} # Comma-separated list of domains to check DNS for
PING_IPS=${PING_IPS:-1.1.1.1} # Comma-separated list of IPs to ping
SSL_CHECK_DOMAINS=${SSL_CHECK_DOMAINS:-google.com} # Comma-separated list of domains to check SSL expiry

# Ensure log directory exists
mkdir -p $LOG_DIR

# Function to log messages
log() {
    local message=$1
    local level=${2:-INFO}
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    if [ "$LOG_TO_TERMINAL" = "true" ]; then
        echo "$timestamp - $level - $message"
    fi
    if [ "$LOG_TO_FILE" = "true" ]; then
        echo "$timestamp - $level - $message" >> $LOG_FILE
    fi
}

# Function to send notifications
send_notification() {
    local message=$1
    if [ -n "$SLACK_WEBHOOK_URL" ]; then
        curl -X POST -H 'Content-type: application/json' --data "{\"text\":\"$message\"}" $SLACK_WEBHOOK_URL
    fi
    if [ -n "$TEAMS_WEBHOOK_URL" ]; then
        curl -H 'Content-Type: application/json' -d "{\"text\":\"$message\"}" $TEAMS_WEBHOOK_URL
    fi
    if [ -n "$DISCORD_WEBHOOK_URL" ]; then
        curl -H 'Content-Type: application/json' -d "{\"content\":\"$message\"}" $DISCORD_WEBHOOK_URL
    fi
}

# Function to rotate logs
rotate_logs() {
    if [ "$LOG_TO_FILE" = "true" ] && [ -f "$LOG_FILE" ] && [ $(stat -c%s "$LOG_FILE") -ge $MAX_LOG_SIZE ]; then
        for ((i=$LOG_BACKUP_COUNT-1; i>=1; i--)); do
            if [ -f "$LOG_FILE.$i" ]; then
                mv "$LOG_FILE.$i" "$LOG_FILE.$((i+1))"
            fi
        done
        mv "$LOG_FILE" "$LOG_FILE.1"
        echo "$(date +"%Y-%m-%d %H:%M:%S") - Log rotated" > $LOG_FILE
    fi
}

# Function to check DNS resolution
check_dns() {
    local domains=(${DOMAINS//,/ })
    for domain in "${domains[@]}"; do
        if [ "$ENABLE_DNS" = "true" ]; then
            local start_time=$(date +%s%3N)
            for ((i=0; i<$RETRY_COUNT; i++)); do
                if dig +short $domain > /dev/null 2>&1; then
                    local end_time=$(date +%s%3N)
                    local duration=$((end_time - start_time))
                    log "DNS Resolution for $domain: PASS (Time: ${duration}ms)"
                    return
                else
                    [ "$VERBOSE" = "true" ] && log "DNS Resolution attempt $((i+1)) for $domain failed" "DEBUG"
                fi
            done
            local error=$(dig $domain 2>&1)
            log "DNS Resolution for $domain: FAIL - $error"
            send_notification "DNS Resolution for $domain: FAIL - $error"
        fi
    done
}

# Function to check ping
check_ping() {
    local ips=(${PING_IPS//,/ })
    for ip in "${ips[@]}"; do
        if [ "$ENABLE_PING" = "true" ]; then
            for ((i=0; i<$RETRY_COUNT; i++)); do
                if ping -c 1 $ip > /dev/null 2>&1; then
                    log "Ping to $ip: PASS"
                    return
                else
                    [ "$VERBOSE" = "true" ] && log "Ping attempt $((i+1)) to $ip failed" "DEBUG"
                fi
            done
            log "Ping to $ip: FAIL"
            send_notification "Ping to $ip: FAIL"
        fi
    done
}

# Function to check website for specified HTTP response codes
check_website() {
    if [ "$ENABLE_WEBSITE_CHECK" = "true" ] && [ -n "$CHECK_WEBSITE" ]; then
        local start_time=$(date +%s%3N)
        local http_status=$(curl -s -o /dev/null -w "%{http_code}" $CHECK_WEBSITE)
        local end_time=$(date +%s%3N)
        local duration=$((end_time - start_time))
        if [[ ",$SUCCESS_HTTP_CODES," == *",$http_status,"* ]]; then
            log "Website check for $CHECK_WEBSITE: PASS (HTTP Status: $http_status, Time: ${duration}ms)"
        else
            log "Website check for $CHECK_WEBSITE: FAIL (HTTP Status: $http_status, Time: ${duration}ms)"
            send_notification "Website check for $CHECK_WEBSITE: FAIL (HTTP Status: $http_status, Time: ${duration}ms)"
        fi
    fi
}

# Function to check SSL certificate expiry
check_ssl_expiry() {
    local domains=(${SSL_CHECK_DOMAINS//,/ })
    for domain in "${domains[@]}"; do
        local expiry_date=$(echo | openssl s_client -servername $domain -connect $domain:443 2>/dev/null | openssl x509 -noout -dates | grep 'notAfter' | cut -d= -f2)
        local expiry_timestamp=$(date -d "$expiry_date" +%s)
        local current_timestamp=$(date +%s)
        local days_left=$(( (expiry_timestamp - current_timestamp) / 86400 ))
        if [ $days_left -le 30 ]; then
            log "SSL certificate for $domain expires in $days_left days"
            send_notification "SSL certificate for $domain expires in $days_left days"
        else
            log "SSL certificate for $domain is valid for $days_left more days"
        fi
    done
}

# Function to handle graceful shutdown
graceful_shutdown() {
    log "Shutting down gracefully..."
    exit 0
}

# Ensure required commands are available
command -v nc >/dev/null 2>&1 || { echo >&2 "nc (netcat) is required but it's not installed. Aborting."; exit 1; }
command -v ping >/dev/null 2>&1 || { echo >&2 "ping is required but it's not installed. Aborting."; exit 1; }
command -v dig >/dev/null 2>&1 || { echo >&2 "dig is required but it's not installed. Aborting."; exit 1; }
command -v curl >/dev/null 2>&1 || { echo >&2 "curl is required but it's not installed. Aborting."; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo >&2 "openssl is required but it's not installed. Aborting."; exit 1; }

# Trap termination signals for graceful shutdown
trap graceful_shutdown SIGTERM SIGINT

# Main loop to perform checks and rotate logs
while true; do
    rotate_logs
    check_dns
    check_ping
    check_website
    check_ssl_expiry
    sleep $INTERVAL
done