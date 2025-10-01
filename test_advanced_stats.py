#!/usr/bin/env python3
"""Manual advanced statistics demonstration for PingPanda."""

import os
import time
import tempfile
from importlib import import_module

if os.environ.get("PYTEST_CURRENT_TEST"):
    pytest = import_module("pytest")
    pytest.skip("Manual integration demo; skipped during automated pytest runs.", allow_module_level=True)

from pingpanda import PingPanda

def test_advanced_stats():
    """Test the advanced statistics functionality."""
    
    # Create a temporary config for testing
    config = {
        'check_interval': 5,
        'prometheus_port': 8000,
        'dns_server': '8.8.8.8',
        'ping_targets': ['8.8.8.8', '1.1.1.1', '192.168.1.999'],  # Include one that will fail
        'websites': ['https://google.com', 'https://github.com'],
        'ssl_hosts': ['google.com:443', 'github.com:443'],
        'slack_webhook': '',
        'teams_webhook': '',
        'discord_webhook': '',
        
        # Advanced statistics configuration
        'enable_advanced_stats': True,
        'summary_interval': 30,  # Show summary every 30 seconds
        'enable_stats_logging': True,
        'stats_log_file': 'test_pingpanda_stats.csv',
        'stats_log_format': 'csv',
        'log_rotation_size': 1024*1024,  # 1MB
        'flapping_threshold': 3,
        'flapping_window': 300,  # 5 minutes
        'persist_stats': True,
        'stats_persistence_file': 'test_pingpanda_stats.pkl'
    }
    
    print("=== PingPanda Advanced Statistics Test ===")
    print("This test will:")
    print("1. Enable advanced ping statistics tracking")
    print("2. Show periodic summaries every 30 seconds")
    print("3. Log statistics to CSV file")
    print("4. Detect flapping (unstable) connections")
    print("5. Persist statistics across restarts")
    print()
    print("The test includes a deliberately failing IP (192.168.1.999) to demonstrate")
    print("downtime tracking and statistics.")
    print()
    print("Press Ctrl+C to stop the test and see final statistics...")
    print()
    
    # Create monitor with advanced stats
    monitor = PingPanda(config)
    
    try:
        # Run for a short test period
        monitor.run()
    except KeyboardInterrupt:
        print("\nTest completed!")
        
        # Show final statistics
        if hasattr(monitor, 'ip_stats') and monitor.ip_stats:
            print("\n=== Final Statistics Summary ===")
            for ip, stats in monitor.ip_stats.items():
                availability = (stats.total_uptime / (stats.total_uptime + stats.total_downtime)) * 100 if (stats.total_uptime + stats.total_downtime) > 0 else 100
                status_emoji = "🟢" if stats.current_status == "up" else "🔴"
                flap_indicator = " 🔄" if stats.is_flapping else ""
                
                print(f"{status_emoji} {ip}: {availability:.1f}% availability{flap_indicator}")
                print(f"   Uptime: {stats.total_uptime:.1f}s, Downtime: {stats.total_downtime:.1f}s")
                print(f"   Downtime events: {stats.downtime_events}")
        
        # Check if log files were created
        if os.path.exists(config['stats_log_file']):
            print(f"\n✅ Statistics log created: {config['stats_log_file']}")
        
        if os.path.exists(str(config['stats_persistence_file'])):
            print(f"✅ Statistics persistence file created: {config['stats_persistence_file']}")
        
        print("\nTest files created in current directory:")
        print("- test_pingpanda_stats.csv (statistics log)")
        print("- test_pingpanda_stats.pkl (persistence data)")
        print("\nYou can examine these files to see the detailed statistics data.")

if __name__ == "__main__":
    test_advanced_stats()
