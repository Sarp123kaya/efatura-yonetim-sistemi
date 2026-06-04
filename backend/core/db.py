#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Helper Module
======================

Production-ready psycopg2-based database helpers with:
- Persistent connection support
- Batch upsert operations
- Transaction management
"""

import psycopg2
import psycopg2.extras
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
import logging

from .config import config

logger = logging.getLogger(__name__)


class DatabaseHelper:
    """Production-ready database helper using psycopg2"""
    
    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize database helper
        
        Args:
            db_url: PostgreSQL connection URL (defaults to config.get_db_url())
        """
        self._db_url = db_url
        self._persistent_conn = None
    
    @property
    def db_url(self) -> str:
        """Get database URL (lazy evaluation)"""
        if self._db_url is None:
            self._db_url = config.get_db_url()
        return self._db_url
    
    @contextmanager
    def get_connection(self, persistent: bool = False, auto_commit: bool = False):
        """
        Context manager for database connections
        
        Args:
            persistent: If True, reuse connection across calls
            auto_commit: If True, auto-commit on success (False for manual transaction control)
        
        Yields:
            psycopg2 connection
        """
        conn = None
        should_close = True
        
        try:
            if persistent and self._persistent_conn:
                conn = self._persistent_conn
                should_close = False
            else:
                conn = psycopg2.connect(self.db_url)
                if persistent:
                    self._persistent_conn = conn
                    should_close = False
            
            yield conn
            
            # Only auto-commit if requested (for non-batch operations)
            if auto_commit:
                conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if should_close and conn:
                conn.close()
    
    def close_persistent_connection(self):
        """Close persistent connection if open"""
        if self._persistent_conn:
            try:
                self._persistent_conn.close()
            except:
                pass
            self._persistent_conn = None
    
    def execute(self, query: str, params: Optional[Tuple] = None, persistent: bool = False) -> int:
        """
        Execute a SQL command (INSERT, UPDATE, DELETE)
        Auto-commits the transaction.
        
        Args:
            query: SQL query string
            params: Query parameters tuple
            persistent: Use persistent connection
            
        Returns:
            Number of rows affected
        """
        with self.get_connection(persistent=persistent, auto_commit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                return cur.rowcount
    
    def query(self, query: str, params: Optional[Tuple] = None, persistent: bool = False) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results as list of dicts
        Read-only, no commit needed.
        
        Args:
            query: SQL query string
            params: Query parameters tuple
            persistent: Use persistent connection
            
        Returns:
            List of rows as dictionaries
        """
        with self.get_connection(persistent=persistent, auto_commit=False) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params or ())
                return [dict(row) for row in cur.fetchall()]
    
    def query_one(self, query: str, params: Optional[Tuple] = None, persistent: bool = False) -> Optional[Dict[str, Any]]:
        """
        Execute a SELECT query and return first row as dict
        Read-only, no commit needed.
        
        Args:
            query: SQL query string
            params: Query parameters tuple
            persistent: Use persistent connection
            
        Returns:
            First row as dictionary or None
        """
        results = self.query(query, params, persistent=persistent)
        return results[0] if results else None
    
    def execute_batch(self, query: str, params_list: List[Tuple], batch_size: int = 100, persistent: bool = True) -> int:
        """
        Execute a SQL command with multiple parameter sets (batch insert/update)
        Uses execute_batch for better performance with transaction per batch
        
        Each batch gets its own transaction (BEGIN/COMMIT) for data integrity:
        - Batch 1: BEGIN -> UPSERT 100 rows -> COMMIT
        - Batch 2: BEGIN -> UPSERT 100 rows -> COMMIT
        - etc.
        
        If a batch fails, previous batches are committed (partial success).
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
            batch_size: Number of rows per batch
            persistent: Use persistent connection
            
        Returns:
            Total number of rows affected
        """
        if not params_list:
            return 0
        
        total_rows = 0
        
        # Split into batches
        num_batches = (len(params_list) + batch_size - 1) // batch_size
        
        # Manual transaction control (no auto_commit)
        with self.get_connection(persistent=persistent, auto_commit=False) as conn:
            for batch_idx in range(num_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(params_list))
                batch_params = params_list[start_idx:end_idx]
                
                try:
                    # BEGIN (implicit with connection context)
                    with conn.cursor() as cur:
                        psycopg2.extras.execute_batch(cur, query, batch_params, page_size=len(batch_params))
                        total_rows += cur.rowcount
                    # COMMIT (explicit for each batch)
                    conn.commit()
                    
                    logger.debug(f"Batch {batch_idx + 1}/{num_batches} committed: {len(batch_params)} rows")
                    
                except Exception as e:
                    # ROLLBACK this batch (previous batches already committed)
                    conn.rollback()
                    logger.error(f"Batch {batch_idx + 1}/{num_batches} failed: {e}")
                    raise  # Re-raise to stop processing
        
        return total_rows
    
    def execute_values(self, query: str, params_list: List[Tuple], template: str = None, batch_size: int = 100, persistent: bool = True) -> int:
        """
        Execute batch INSERT using execute_values (fastest for bulk inserts)
        Uses transaction per batch for data integrity
        
        Args:
            query: SQL query with VALUES placeholder
            params_list: List of parameter tuples
            template: SQL template for each row
            batch_size: Number of rows per batch
            persistent: Use persistent connection
            
        Returns:
            Number of rows affected
        """
        if not params_list:
            return 0
        
        total_rows = 0
        num_batches = (len(params_list) + batch_size - 1) // batch_size
        
        # Manual transaction control (no auto_commit)
        with self.get_connection(persistent=persistent, auto_commit=False) as conn:
            for batch_idx in range(num_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(params_list))
                batch_params = params_list[start_idx:end_idx]
                
                try:
                    # BEGIN -> EXECUTE_VALUES -> COMMIT
                    with conn.cursor() as cur:
                        psycopg2.extras.execute_values(cur, query, batch_params, template=template)
                        total_rows += cur.rowcount
                    conn.commit()
                    
                    logger.debug(f"Batch {batch_idx + 1}/{num_batches} committed: {len(batch_params)} rows")
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Batch {batch_idx + 1}/{num_batches} failed: {e}")
                    raise
        
        return total_rows
    
    def test_connection(self) -> bool:
        """
        Test database connection
        
        Returns:
            True if connection successful
        """
        try:
            with self.get_connection(auto_commit=False) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    return result[0] == 1
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


# Create singleton instance
db = DatabaseHelper()
