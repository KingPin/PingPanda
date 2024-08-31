#!/bin/bash

# Read environment variables
LOG_DIR=${LOG_DIR:-/logs} # Default to /logs
LOG_FILE="$LOG_DIR/pingpanda.log" # Default to /logs/pingpanda.log
DOMAIN=${DOMAIN:-google.com} # Default to google.com
PING_IP=${PING_IP:-1.1.1.1} # Default to Cloudflare DNS
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

# Ensure log directory exists
mkdir -p $LOG_DIR

# Function to log messages
log() {
    local message=$1
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    if [ "$LOG_TO_TERMINAL" = "true" ]; then
        echo "$timestamp - $message"
    fi
    if [ "$LOG_TO_FILE" = "true" ]; then
        echo "$timestamp - $message" >> $LOG_FILE
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
    if [ "$ENABLE_DNS" = "true" ]; then
        local start_time=$(date +%s%3N)
        for ((i=0; i<$RETRY_COUNT; i++)); do
            if dig +short $DOMAIN > /dev/null 2>&1; then
                local end_time=$(date +%s%3N)
                local duration=$((end_time - start_time))
                log "DNS Resolution for $DOMAIN: PASS (Time: ${duration}ms)"
                return
            fi
        done
        local error=$(dig $DOMAIN 2>&1)
        log "DNS Resolution for $DOMAIN: FAIL - $error"
    fi
}

# Function to check ping
check_ping() {
    if [ "$ENABLE_PING" = "true" ]; then
        for ((i=0; i<$RETRY_COUNT; i++)); do
            if ping -c 1 $PING_IP > /dev/null 2>&1; then
                log "Ping to $PING_IP: PASS"
                return
            fi
        done
        log "Ping to $PING_IP: FAIL"
    fi
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
        fi
    fi
}

# Function to start a detailed HTTP health check server
start_health_check_server() {
    while true; do
        local dns_status="UNKNOWN"
        local ping_status="UNKNOWN"
        local website_status="UNKNOWN"
        
        if [ "$ENABLE_DNS" = "true" ]; then
            if dig +short $DOMAIN > /dev/null 2>&1; then
                dns_status="PASS"
            else
                dns_status="FAIL"
            fi
        fi
        
        if [ "$ENABLE_PING" = "true" ]; then
            if ping -c 1 $PING_IP > /dev/null 2>&1; then
                ping_status="PASS"
            else
                ping_status="FAIL"
            fi
        fi
        
        if [ "$ENABLE_WEBSITE_CHECK" = "true" ] && [ -n "$CHECK_WEBSITE" ]; then
            local http_status=$(curl -s -o /dev/null -w "%{http_code}" $CHECK_WEBSITE)
            if [[ ",$SUCCESS_HTTP_CODES," == *",$http_status,"* ]]; then
                website_status="PASS"
            else
                website_status="FAIL"
            fi
        fi
        
        { 
            echo -ne "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n"
            echo -ne "{\"dns_status\":\"$dns_status\",\"ping_status\":\"$ping_status\",\"website_status\":\"$website_status\"}"
        } | nc -l -p 8080 -q 1 > /dev/null 2>&1
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

# Trap termination signals for graceful shutdown
trap graceful_shutdown SIGTERM SIGINT

# Start health check server in the background
start_health_check_server &

# Main loop to perform checks and rotate logs
while true; do
    rotate_logs
    check_dns
    check_ping
    check_website
    sleep $INTERVAL
done