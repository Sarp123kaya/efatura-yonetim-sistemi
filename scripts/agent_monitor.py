#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Monitor Script
====================

View agent run history and health status from database.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import argparse

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.core.agent_run_logger import (
    get_recent_runs, 
    get_run_stats, 
    check_agent_health
)


def format_duration(seconds):
    """Format duration in seconds to human-readable string"""
    if not seconds:
        return "N/A"
    
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def format_timestamp(ts):
    """Format timestamp"""
    if not ts:
        return "N/A"
    
    # Convert to local time for display
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def print_recent_runs(agent_name=None, limit=10):
    """Print recent agent runs"""
    runs = get_recent_runs(agent_name, limit)
    
    if not runs:
        print("📭 No runs found")
        return
    
    print(f"\n📋 Recent Runs ({len(runs)} total)")
    print("=" * 140)
    
    # Header
    header = f"{'Agent':<15} {'Start':<20} {'Dur':<8} {'I':<6} {'U':<6} {'E':<6} {'B':<5} {'Host':<12} {'Ver':<8} {'Status':<8}"
    print(header)
    print("-" * 140)
    
    # Rows
    for run in runs:
        status_icon = {
            'success': '✅',
            'failed': '❌',
            'partial': '⚠️',
            'running': '⏳'
        }.get(run['status'], '❓')
        
        # Truncate host if too long
        host_short = (run.get('host') or 'N/A')[:12]
        version_short = (run.get('agent_version') or 'N/A')[:8]
        
        print(f"{run['agent_name']:<15} "
              f"{format_timestamp(run['start_time']):<20} "
              f"{format_duration(run['duration_sec']):<8} "
              f"{run['insert_count']:<6} "
              f"{run['update_count']:<6} "
              f"{run['error_count']:<6} "
              f"{run.get('batch_count', 0):<5} "
              f"{host_short:<12} "
              f"{version_short:<8} "
              f"{status_icon} {run['status']:<8}")
        
        # Show error message if failed
        if run['error_message'] and run['status'] == 'failed':
            print(f"  └─ Error: {run['error_message'][:100]}")
    
    print("=" * 140)
    print("Legend: I=Inserted, U=Updated, E=Errors, B=Batches")


def print_stats(agent_name, days=7):
    """Print aggregated stats for an agent"""
    stats = get_run_stats(agent_name, days)
    
    if not stats or stats.get('total_runs', 0) == 0:
        print(f"\n📭 No runs found for {agent_name} in last {days} days")
        return
    
    print(f"\n📊 Stats for {agent_name} (Last {days} days)")
    print("=" * 60)
    print(f"Total Runs:       {stats['total_runs']}")
    print(f"  ✅ Successful:  {stats['successful_runs']}")
    print(f"  ❌ Failed:      {stats['failed_runs']}")
    print(f"  ⚠️  Partial:    {stats['partial_runs']}")
    print()
    print(f"Total Inserts:    {stats['total_inserts']:,}")
    print(f"Total Updates:    {stats['total_updates']:,}")
    print(f"Total Errors:     {stats['total_errors']:,}")
    print()
    print(f"Avg Duration:     {format_duration(stats['avg_duration_sec'])}")
    print(f"Avg Batch Count:  {stats.get('avg_batch_count', 0):.1f}")
    print(f"Last Run:         {format_timestamp(stats['last_run_time'])}")
    print("=" * 60)


def print_health(agent_name=None):
    """Print health status for agent(s)"""
    agents = [agent_name] if agent_name else ['incoming_agent', 'outgoing_agent']
    
    print("\n🏥 Agent Health Status")
    print("=" * 80)
    
    for agent in agents:
        health = check_agent_health(agent)
        
        icon = '✅' if health['healthy'] else '❌'
        print(f"\n{icon} {agent.upper()}")
        print(f"   Status: {health['status']}")
        print(f"   Message: {health['message']}")
        
        if 'last_run' in health:
            last_run = health['last_run']
            print(f"   Last Run: {format_timestamp(last_run.get('start_time'))}")
            print(f"   Result: {last_run.get('status')} "
                  f"(I:{last_run.get('insert_count', 0)}, "
                  f"U:{last_run.get('update_count', 0)}, "
                  f"E:{last_run.get('error_count', 0)})")
    
    print("=" * 80)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Monitor agent runs')
    parser.add_argument('--agent', choices=['incoming', 'outgoing', 'all'], 
                       default='all', help='Agent to monitor')
    parser.add_argument('--command', choices=['recent', 'stats', 'health'], 
                       default='health', help='Command to run')
    parser.add_argument('--limit', type=int, default=10, 
                       help='Number of recent runs to show')
    parser.add_argument('--days', type=int, default=7, 
                       help='Number of days for stats')
    
    args = parser.parse_args()
    
    # Map agent name
    agent_map = {
        'incoming': 'incoming_agent',
        'outgoing': 'outgoing_agent',
        'all': None
    }
    agent_name = agent_map[args.agent]
    
    print("=" * 80)
    print("🔍 AGENT MONITOR")
    print("=" * 80)
    
    if args.command == 'recent':
        print_recent_runs(agent_name, args.limit)
    
    elif args.command == 'stats':
        if agent_name:
            print_stats(agent_name, args.days)
        else:
            print_stats('incoming_agent', args.days)
            print()
            print_stats('outgoing_agent', args.days)
    
    elif args.command == 'health':
        print_health(agent_name)


if __name__ == "__main__":
    main()
