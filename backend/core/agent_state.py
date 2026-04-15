#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent State Management Module
==============================

Manages stateful ingestion by tracking last processed issue_date for each agent.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import logging

from .db import db
from .config import config

logger = logging.getLogger(__name__)


def get_state(agent_name: str) -> Tuple[datetime, int]:
    """
    Get last processed issue_date and lookback_days for an agent
    
    Args:
        agent_name: Name of the agent (e.g., 'incoming_agent', 'outgoing_agent')
        
    Returns:
        Tuple of (last_issue_date, lookback_days)
    """
    try:
        query = "SELECT last_issue_date, lookback_days FROM agent_state WHERE agent_name = %s"
        result = db.query_one(query, (agent_name,))
        
        if result:
            last_date = result['last_issue_date']
            lookback_days = result.get('lookback_days', config.DEFAULT_LOOKBACK_DAYS)
            logger.info(f"📅 {agent_name}: last_issue_date = {last_date}, lookback_days = {lookback_days}")
            return last_date, lookback_days
        else:
            # Agent not found, use defaults
            default_date = datetime.strptime(config.DEFAULT_START_DATE, "%Y-%m-%d")
            logger.warning(f"⚠️  {agent_name} not found in agent_state, using defaults: {default_date}, lookback={config.DEFAULT_LOOKBACK_DAYS}")
            return default_date, config.DEFAULT_LOOKBACK_DAYS
            
    except Exception as e:
        logger.error(f"❌ Error getting state for {agent_name}: {e}")
        # Fallback to defaults
        default_date = datetime.strptime(config.DEFAULT_START_DATE, "%Y-%m-%d")
        logger.warning(f"⚠️  Falling back to defaults: {default_date}, lookback={config.DEFAULT_LOOKBACK_DAYS}")
        return default_date, config.DEFAULT_LOOKBACK_DAYS


def get_start_date_with_lookback(agent_name: str) -> datetime:
    """
    Get effective start date with lookback applied
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Start date = last_issue_date - lookback_days
    """
    last_issue_date, lookback_days = get_state(agent_name)
    start_date = last_issue_date - timedelta(days=lookback_days)
    logger.info(f"🔙 {agent_name}: effective start_date = {start_date} (lookback {lookback_days} days)")
    return start_date


def set_state(agent_name: str, last_issue_date: datetime) -> bool:
    """
    Update last processed issue_date for an agent
    
    Args:
        agent_name: Name of the agent
        last_issue_date: New last issue_date to save
        
    Returns:
        True if successful
    """
    try:
        query = """
            INSERT INTO agent_state (agent_name, last_issue_date, last_run_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (agent_name) 
            DO UPDATE SET 
                last_issue_date = EXCLUDED.last_issue_date,
                last_run_at = NOW()
        """
        
        db.execute(query, (agent_name, last_issue_date))
        logger.info(f"✅ {agent_name}: updated last_issue_date = {last_issue_date}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error setting state for {agent_name}: {e}")
        return False


def get_last_run_at(agent_name: str) -> Optional[datetime]:
    """
    Get last run timestamp for an agent
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Last run timestamp or None
    """
    try:
        query = "SELECT last_run_at FROM agent_state WHERE agent_name = %s"
        result = db.query_one(query, (agent_name,))
        return result['last_run_at'] if result else None
    except Exception as e:
        logger.error(f"❌ Error getting last_run_at for {agent_name}: {e}")
        return None
