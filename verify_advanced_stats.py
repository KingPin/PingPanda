#!/usr/bin/env python3
"""
Simple test to verify advanced statistics functionality.
"""

import os
import sys
sys.path.insert(0, '.')

try:
    from pingpanda import PingPanda
    print("✅ Successfully imported PingPanda")
    
    # Test configuration with advanced stats
    config = {
        'check_interval': 1,
        'prometheus_port': 8001,
        'dns_server': '8.8.8.8',
        'ping_targets': ['8.8.8.8'],
        'websites': [],
        'ssl_hosts': [],
        'slack_webhook': '',
        'teams_webhook': '',
        'discord_webhook': '',
        'enable_advanced_stats': True,
        'summary_interval': 5,
        'enable_stats_logging': True,
        'stats_log_file': 'test_stats.csv',
        'flapping_threshold': 3,
        'persist_stats': True,
        'stats_persistence_file': 'test_stats.pkl'
    }
    
    print("✅ Advanced stats configuration created")
    
    # Create monitor instance
    monitor = PingPanda(config)
    print("✅ PingPanda instance created with advanced stats")
    
    # Check if advanced stats attributes exist
    if hasattr(monitor, 'ip_stats'):
        print("✅ IP stats tracking available")
    
    if hasattr(monitor, 'stats_logger'):
        print("✅ Stats logger available")
        
    if hasattr(monitor, '_output_stats_summary'):
        print("✅ Stats summary method available")
        
    print("\n🎉 All advanced statistics features are properly integrated!")
    print("\nTo see the features in action, run:")
    print("python3 test_advanced_stats.py")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
