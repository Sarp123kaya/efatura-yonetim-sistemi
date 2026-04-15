#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Run Logger Module
========================

Tracks agent execution history in database for monitoring and debugging.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
import logging
import json
import socket

from .db import db

logger = logging.getLogger(__name__)

# Agent version (update when releasing new version)
AGENT_VERSION = "2.1.1"


class AgentRunLogger:
    """Tracks agent run history in database"""
    
    def __init__(self, agent_name: str, run_id: str, version: Optional[str] = None):
        """
        Initialize agent run logger
        
        Args:
            agent_name: Name of the agent (e.g., 'incoming_agent')
            run_id: Unique run identifier
            version: Agent version (defaults to AGENT_VERSION)
        """
        self.agent_name = agent_name
        self.run_id = run_id
        self.db_id: Optional[int] = None
        self.host = socket.gethostname()
        self.version = version or AGENT_VERSION
    
    def start_run(self, metadata: Optional[Dict] = None) -> int:
        """
        Record start of agent run
        
        Args:
            metadata: Optional metadata (date range, config, etc.)
            
        Returns:
            Database ID of the run record
        """
        try:
            query = """
                INSERT INTO agent_runs (
                    agent_name, run_id, start_time, status, metadata, host, agent_version
                ) VALUES (%s, %s, NOW(), 'running', %s, %s, %s)
                RETURNING id
            """
            
            metadata_json = json.dumps(metadata or {})
            
            with db.get_connection(persistent=True, auto_commit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (self.agent_name, self.run_id, metadata_json, self.host, self.version))
                    self.db_id = cur.fetchone()[0]
            
            logger.info(f"📝 Run logged: {self.agent_name} ({self.run_id}) - ID: {self.db_id} - Host: {self.host} - Version: {self.version}")
            return self.db_id
            
        except Exception as e:
            logger.error(f"❌ Failed to log run start: {e}")
            # Don't fail agent if logging fails
            return -1
    
    def update_progress(self, 
                       insert_count: int = 0, 
                       update_count: int = 0,
                       nochange_count: int = 0,
                       error_count: int = 0,
                       total_fetched: int = 0,
                       batch_count: int = 0) -> bool:
        """
        Update run progress (can be called multiple times during run)
        
        Args:
            insert_count: Number of inserted records
            update_count: Number of updated records
            nochange_count: Number of unchanged records
            error_count: Number of errors
            total_fetched: Total fetched from API
            batch_count: Number of batches processed
            
        Returns:
            True if update successful
        """
        if not self.db_id or self.db_id < 0:
            return False
        
        try:
            query = """
                UPDATE agent_runs
                SET insert_count = %s,
                    update_count = %s,
                    nochange_count = %s,
                    error_count = %s,
                    total_fetched = %s,
                    batch_count = %s
                WHERE id = %s
            """
            
            db.execute(query, (
                insert_count, update_count, nochange_count, 
                error_count, total_fetched, batch_count, self.db_id
            ), persistent=True)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update progress: {e}")
            return False
    
    def complete_run(self, 
                    insert_count: int = 0,
                    update_count: int = 0,
                    nochange_count: int = 0,
                    error_count: int = 0,
                    total_fetched: int = 0,
                    batch_count: int = 0,
                    status: str = 'success',
                    error_message: Optional[str] = None) -> bool:
        """
        Mark run as complete
        
        Args:
            insert_count: Final insert count
            update_count: Final update count
            nochange_count: Final nochange count
            error_count: Final error count
            total_fetched: Total fetched from API
            batch_count: Number of batches processed
            status: 'success', 'failed', or 'partial'
            error_message: Error message if failed
            
        Returns:
            True if update successful
        """
        if not self.db_id or self.db_id < 0:
            return False
        
        try:
            query = """
                UPDATE agent_runs
                SET end_time = NOW(),
                    duration_sec = EXTRACT(EPOCH FROM (NOW() - start_time)),
                    insert_count = %s,
                    update_count = %s,
                    nochange_count = %s,
                    error_count = %s,
                    total_fetched = %s,
                    batch_count = %s,
                    status = %s,
                    error_message = %s
                WHERE id = %s
            """
            
            db.execute(query, (
                insert_count, update_count, nochange_count,
                error_count, total_fetched, batch_count, status, error_message,
                self.db_id
            ), persistent=True)
            
            logger.info(f"✅ Run completed: {self.run_id} - Status: {status}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to complete run: {e}")
            return False


# Monitoring helper functions

def get_recent_runs(agent_name: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent agent runs
    
    Args:
        agent_name: Filter by agent name (None for all)
        limit: Number of runs to return
        
    Returns:
        List of run records
    """
    if agent_name:
        query = """
            SELECT id, agent_name, run_id, start_time, end_time, duration_sec,
                   insert_count, update_count, nochange_count, error_count, total_fetched,
                   batch_count, status, error_message, host, agent_version
            FROM agent_runs
            WHERE agent_name = %s
            ORDER BY start_time DESC
            LIMIT %s
        """
        return db.query(query, (agent_name, limit))
    else:
        query = """
            SELECT id, agent_name, run_id, start_time, end_time, duration_sec,
                   insert_count, update_count, nochange_count, error_count, total_fetched,
                   batch_count, status, error_message, host, agent_version
            FROM agent_runs
            ORDER BY start_time DESC
            LIMIT %s
        """
        return db.query(query, (limit,))


def get_run_stats(agent_name: str, days: int = 7) -> Dict[str, Any]:
    """
    Get aggregated stats for an agent
    
    Args:
        agent_name: Agent name
        days: Number of days to look back
        
    Returns:
        Stats dictionary
    """
    query = """
        SELECT 
            COUNT(*) as total_runs,
            COUNT(*) FILTER (WHERE status = 'success') as successful_runs,
            COUNT(*) FILTER (WHERE status = 'failed') as failed_runs,
            COUNT(*) FILTER (WHERE status = 'partial') as partial_runs,
            SUM(insert_count) as total_inserts,
            SUM(update_count) as total_updates,
            SUM(error_count) as total_errors,
            AVG(duration_sec) as avg_duration_sec,
            AVG(batch_count) as avg_batch_count,
            MAX(end_time) as last_run_time
        FROM agent_runs
        WHERE agent_name = %s
          AND start_time > NOW() - INTERVAL '%s days'
    """
    
    result = db.query_one(query, (agent_name, days))
    return dict(result) if result else {}


def check_agent_health(agent_name: str) -> Dict[str, Any]:
    """
    Check if agent ran recently and successfully
    
    Args:
        agent_name: Agent name
        
    Returns:
        Health status dictionary
    """
    query = """
        SELECT id, run_id, start_time, end_time, status, error_message,
               insert_count, update_count, error_count, host, agent_version
        FROM agent_runs
        WHERE agent_name = %s
        ORDER BY start_time DESC
        LIMIT 1
    """
    
    last_run = db.query_one(query, (agent_name,))
    
    if not last_run:
        return {
            'healthy': False,
            'status': 'never_run',
            'message': f'{agent_name} has never run'
        }
    
    # Check if run is stuck (started but not ended)
    if last_run['status'] == 'running':
        # If started more than 1 hour ago, consider it stuck
        from datetime import timedelta
        if datetime.now(last_run['start_time'].tzinfo) - last_run['start_time'] > timedelta(hours=1):
            return {
                'healthy': False,
                'status': 'stuck',
                'message': f'{agent_name} appears stuck (started {last_run["start_time"]})',
                'last_run': dict(last_run)
            }
    
    # Check last run status
    if last_run['status'] == 'failed':
        return {
            'healthy': False,
            'status': 'failed',
            'message': f'{agent_name} last run failed: {last_run.get("error_message", "Unknown error")}',
            'last_run': dict(last_run)
        }
    
    # Check if ran recently (within 25 hours for daily agents)
    from datetime import timedelta
    time_since_run = datetime.now(last_run['end_time'].tzinfo) - last_run['end_time'] if last_run['end_time'] else timedelta(days=999)
    
    if time_since_run > timedelta(hours=25):
        return {
            'healthy': False,
            'status': 'stale',
            'message': f'{agent_name} has not run in {time_since_run.days} days',
            'last_run': dict(last_run)
        }
    
    return {
        'healthy': True,
        'status': 'ok',
        'message': f'{agent_name} is healthy',
        'last_run': dict(last_run)
    }
