#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick Data Viewer - View agent results in Excel-like format
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backend.core.db import db
from backend.core.config import config
import json
from datetime import datetime

def format_jsonb(data):
    """Format JSONB data nicely"""
    if not data:
        return ""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            return data
    if isinstance(data, list):
        return ", ".join(str(x) for x in data)
    return str(data)

def view_incoming_invoices(limit=10):
    """View recent incoming invoices"""
    print("\n" + "=" * 120)
    print("📥 INCOMING INVOICES (Most Recent)")
    print("=" * 120)
    
    query = """
        SELECT 
            invoice_id,
            issue_date,
            supplier,
            amount,
            currency,
            despatch_ids,
            change_type,
            last_change_at,
            created_at
        FROM incoming_invoices
        ORDER BY issue_date DESC, created_at DESC
        LIMIT %s
    """
    
    rows = db.query(query, (limit,))
    
    if not rows:
        print("❌ No data found in incoming_invoices table")
        return
    
    print(f"\n📊 Found {len(rows)} records\n")
    
    # Header
    print(f"{'Invoice ID':<25} {'Date':<12} {'Supplier':<30} {'Amount':<12} {'Currency':<8} {'Despatch IDs':<20} {'Type':<8}")
    print("-" * 120)
    
    # Rows
    for row in rows:
        invoice_id = row.get('invoice_id', '')[:24]
        issue_date = row.get('issue_date', '')
        if isinstance(issue_date, datetime):
            issue_date = issue_date.strftime('%Y-%m-%d')
        supplier = (row.get('supplier', '') or '')[:29]
        amount = f"{row.get('amount', 0):,.2f}" if row.get('amount') else '0.00'
        currency = row.get('currency', '')[:7]
        despatch_ids = format_jsonb(row.get('despatch_ids', []))[:19]
        change_type = row.get('change_type', '')[:7]
        
        print(f"{invoice_id:<25} {issue_date:<12} {supplier:<30} {amount:>12} {currency:<8} {despatch_ids:<20} {change_type:<8}")
    
    print("\n")

def view_outgoing_invoices(limit=10):
    """View recent outgoing invoices"""
    print("\n" + "=" * 120)
    print("📤 OUTGOING INVOICES (Most Recent)")
    print("=" * 120)
    
    query = """
        SELECT 
            invoice_no,
            issue_date,
            firm_name,
            total_tl,
            COALESCE(irsaliye_codes_override, irsaliye_codes) AS irsaliye_codes,
            change_type,
            last_change_at,
            created_at
        FROM outgoing_invoices
        ORDER BY issue_date DESC, created_at DESC
        LIMIT %s
    """
    
    rows = db.query(query, (limit,))
    
    if not rows:
        print("❌ No data found in outgoing_invoices table")
        return
    
    print(f"\n📊 Found {len(rows)} records\n")
    
    # Header
    print(f"{'Invoice No':<20} {'Date':<12} {'Firm Name':<35} {'Total (TL)':<15} {'İrsaliye':<25} {'Type':<8}")
    print("-" * 120)
    
    # Rows
    for row in rows:
        invoice_no = row.get('invoice_no', '')[:19]
        issue_date = row.get('issue_date', '')
        if isinstance(issue_date, datetime):
            issue_date = issue_date.strftime('%Y-%m-%d')
        firm_name = (row.get('firm_name', '') or '')[:34]
        total_tl = f"{row.get('total_tl', 0):,.2f}" if row.get('total_tl') else '0.00'
        irsaliye = format_jsonb(row.get('irsaliye_codes', []))[:24]
        change_type = row.get('change_type', '')[:7]
        
        print(f"{invoice_no:<20} {issue_date:<12} {firm_name:<35} {total_tl:>15} {irsaliye:<25} {change_type:<8}")
    
    print("\n")

def view_agent_runs(limit=5):
    """View recent agent runs"""
    print("\n" + "=" * 120)
    print("🤖 AGENT RUNS (Most Recent)")
    print("=" * 120)
    
    query = """
        SELECT 
            agent_name,
            run_id,
            start_time,
            duration_sec,
            insert_count,
            update_count,
            nochange_count,
            error_count,
            batch_count,
            status,
            host,
            agent_version
        FROM agent_runs
        ORDER BY start_time DESC
        LIMIT %s
    """
    
    rows = db.query(query, (limit,))
    
    if not rows:
        print("❌ No agent runs found")
        return
    
    print(f"\n📊 Found {len(rows)} runs\n")
    
    # Header
    print(f"{'Agent':<16} {'Start Time':<20} {'Dur':<7} {'I':<5} {'U':<5} {'E':<5} {'B':<5} {'Status':<10} {'Host':<15} {'Ver':<6}")
    print("-" * 120)
    
    # Rows
    for row in rows:
        agent = row.get('agent_name', '')[:15]
        start = row.get('start_time', '')
        if isinstance(start, datetime):
            start = start.strftime('%Y-%m-%d %H:%M:%S')[:19]
        dur = f"{row.get('duration_sec', 0):.1f}s"
        ins = str(row.get('insert_count', 0))
        upd = str(row.get('update_count', 0))
        err = str(row.get('error_count', 0))
        bat = str(row.get('batch_count', 0))
        status = row.get('status', '')[:9]
        host = (row.get('host', '') or 'N/A')[:14]
        ver = (row.get('agent_version', '') or 'N/A')[:5]
        
        # Status icon
        status_icon = {'success': '✅', 'failed': '❌', 'partial': '⚠️', 'running': '⏳'}.get(status, '❓')
        
        print(f"{agent:<16} {start:<20} {dur:<7} {ins:<5} {upd:<5} {err:<5} {bat:<5} {status_icon} {status:<9} {host:<15} {ver:<6}")
    
    print("\n")

def view_statistics():
    """View overall statistics"""
    print("\n" + "=" * 120)
    print("📊 DATABASE STATISTICS")
    print("=" * 120)
    print()
    
    # Count queries
    stats = {
        'incoming_total': db.query_one("SELECT COUNT(*) as count FROM incoming_invoices"),
        'incoming_inserts': db.query_one("SELECT COUNT(*) as count FROM incoming_invoices WHERE change_type = 'insert'"),
        'incoming_updates': db.query_one("SELECT COUNT(*) as count FROM incoming_invoices WHERE change_type = 'update'"),
        'outgoing_total': db.query_one("SELECT COUNT(*) as count FROM outgoing_invoices"),
        'outgoing_inserts': db.query_one("SELECT COUNT(*) as count FROM outgoing_invoices WHERE change_type = 'insert'"),
        'outgoing_updates': db.query_one("SELECT COUNT(*) as count FROM outgoing_invoices WHERE change_type = 'update'"),
        'agent_runs': db.query_one("SELECT COUNT(*) as count FROM agent_runs"),
        'successful_runs': db.query_one("SELECT COUNT(*) as count FROM agent_runs WHERE status = 'success'"),
    }
    
    print(f"📥 Incoming Invoices:")
    print(f"   Total:      {stats['incoming_total'].get('count', 0):>6,}")
    print(f"   Inserted:   {stats['incoming_inserts'].get('count', 0):>6,}")
    print(f"   Updated:    {stats['incoming_updates'].get('count', 0):>6,}")
    print()
    print(f"📤 Outgoing Invoices:")
    print(f"   Total:      {stats['outgoing_total'].get('count', 0):>6,}")
    print(f"   Inserted:   {stats['outgoing_inserts'].get('count', 0):>6,}")
    print(f"   Updated:    {stats['outgoing_updates'].get('count', 0):>6,}")
    print()
    print(f"🤖 Agent Runs:")
    print(f"   Total:      {stats['agent_runs'].get('count', 0):>6,}")
    print(f"   Successful: {stats['successful_runs'].get('count', 0):>6,}")
    print()

if __name__ == "__main__":
    try:
        import argparse
        parser = argparse.ArgumentParser(description='View agent data in Excel-like format')
        parser.add_argument('--limit', type=int, default=10, help='Number of records to show')
        parser.add_argument('--type', choices=['incoming', 'outgoing', 'runs', 'stats', 'all'], 
                          default='all', help='Type of data to view')
        args = parser.parse_args()
        
        print("\n" + "=" * 120)
        print("🔍 DATA VIEWER - Agent Results")
        print("=" * 120)
        
        if args.type in ['all', 'stats']:
            view_statistics()
        
        if args.type in ['all', 'runs']:
            view_agent_runs(args.limit)
        
        if args.type in ['all', 'incoming']:
            view_incoming_invoices(args.limit)
        
        if args.type in ['all', 'outgoing']:
            view_outgoing_invoices(args.limit)
        
        print("=" * 120)
        print("✅ Done!")
        print("=" * 120)
        print()
        print("💡 Tips:")
        print("  - View more: python view_data.py --limit 20")
        print("  - Only incoming: python view_data.py --type incoming")
        print("  - Only runs: python view_data.py --type runs")
        print("  - Export to Excel: python scripts/export_to_excel.py")
        print()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
