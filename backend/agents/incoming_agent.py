#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Incoming Invoice Agent v2.0 (Production-Ready)
===============================================

Stateful ingestion of incoming invoices with:
- Lookback/watermark for late-arriving invoices
- Non-interactive auth via .env
- Batch upsert for performance
- Change type tracking
- Retry logic with exponential backoff
- Comprehensive logging
"""

import sys
import json
import hashlib
import time
import uuid as uuid_lib
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import logging

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.core.config import config
from backend.core.db import db
from backend.core.agent_state import get_state, set_state, get_start_date_with_lookback
from backend.core.normalize import normalize_despatch_ids_from_incoming, extract_despatch_ids_from_summary
from backend.core.agent_run_logger import AgentRunLogger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class IncomingInvoiceAgent:
    """Production-ready incoming invoice ingestion agent"""
    
    def __init__(self, run_id: Optional[str] = None, refresh_xml_cache: bool = False):
        self.run_id = run_id or f"incoming_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid_lib.uuid4().hex[:8]}"
        self.agent_name = 'incoming_agent'
        self.refresh_xml_cache = refresh_xml_cache
        self.stats = {
            'insert': 0,
            'update': 0,
            'nochange': 0,
            'error': 0,
            'total_fetched': 0,
            'batch_count': 0
        }
        self.start_time = None
        self.end_time = None
        self.run_logger = AgentRunLogger(self.agent_name, self.run_id)
    
    def compute_row_hash(self, raw_json: Dict) -> str:
        """Compute SHA256 hash of raw JSON for change detection"""
        json_str = json.dumps(raw_json, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
    
    def extract_despatch_ids(self, invoice: Dict) -> List[str]:
        """Extract and normalize despatch IDs from invoice"""
        # Try despatch_documents first (from XML parsing)
        despatch_docs = invoice.get('despatch_documents', [])
        if despatch_docs:
            full_ids = [d.get('despatch_id_full', '') for d in despatch_docs if d.get('despatch_id_full')]
            return normalize_despatch_ids_from_incoming(full_ids)
        
        # Try despatch_ids_summary
        summary = invoice.get('despatch_ids_summary')
        if summary:
            return extract_despatch_ids_from_summary(summary)
        
        return []
    
    def upsert_invoice_batch(self, invoices: List[Dict]) -> Dict[str, int]:
        """
        Batch upsert invoices with change tracking
        
        Returns:
            Dict with counts: {insert: N, update: N, nochange: N, error: N, batch_count: N}
        """
        counts = {'insert': 0, 'update': 0, 'nochange': 0, 'error': 0, 'batch_count': 0}
        
        if not invoices:
            return counts
        
        # Build lookup of existing invoices
        invoice_ids = [str(inv.get('invoiceId', '')) for inv in invoices if inv.get('invoiceId')]
        if not invoice_ids:
            return counts
        
        placeholders = ','.join(['%s'] * len(invoice_ids))
        existing_query = f"SELECT invoice_id, row_hash FROM incoming_invoices WHERE invoice_id IN ({placeholders})"
        existing = {row['invoice_id']: row['row_hash'] for row in db.query(existing_query, tuple(invoice_ids), persistent=True)}
        
        # Separate into insert/update/nochange
        to_insert = []
        to_update = []
        
        for invoice in invoices:
            try:
                invoice_id = str(invoice.get('invoiceId', ''))
                uuid_val = str(invoice.get('uuId', ''))
                
                if not invoice_id or not uuid_val:
                    counts['error'] += 1
                    continue
                
                # Parse issue_date
                issue_date_str = invoice.get('issueDate', '')
                try:
                    if 'T' in issue_date_str:
                        issue_date = datetime.fromisoformat(issue_date_str.replace('Z', '+00:00'))
                    else:
                        issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d')
                except:
                    issue_date = datetime.now()
                
                # Extract fields
                supplier = invoice.get('supplier', '')
                supplier_tckn_vkn = str(invoice.get('supplierTcknVkn', ''))
                amount = invoice.get('amount', 0.0)
                total_vat_base = invoice.get('totalVatBase', 0.0)
                currency = invoice.get('currency', 'TRY')
                despatch_ids = self.extract_despatch_ids(invoice)
                row_hash = self.compute_row_hash(invoice)
                
                if invoice_id in existing:
                    # Exists - check if changed
                    if existing[invoice_id] != row_hash:
                        to_update.append((
                            uuid_val, issue_date, supplier, supplier_tckn_vkn,
                            amount, total_vat_base, currency,
                            json.dumps(despatch_ids), json.dumps(invoice), row_hash,
                            'update', datetime.now(), datetime.now(),
                            invoice_id
                        ))
                        counts['update'] += 1
                    else:
                        counts['nochange'] += 1
                else:
                    # New invoice
                    to_insert.append((
                        invoice_id, uuid_val, issue_date, supplier, supplier_tckn_vkn,
                        amount, total_vat_base, currency,
                        json.dumps(despatch_ids), json.dumps(invoice), row_hash,
                        'insert', datetime.now(), datetime.now(), datetime.now()
                    ))
                    counts['insert'] += 1
                    
            except Exception as e:
                logger.error(f"❌ Error processing invoice {invoice.get('invoiceId')}: {e}")
                counts['error'] += 1
        
        # Track batch count
        batch_count = 0
        
        # Batch insert with transaction per batch
        if to_insert:
            num_insert_batches = (len(to_insert) + config.BATCH_SIZE - 1) // config.BATCH_SIZE
            batch_count += num_insert_batches
            logger.info(f"💾 Inserting {len(to_insert)} new invoices ({num_insert_batches} batches of {config.BATCH_SIZE})...")
            insert_query = """
                INSERT INTO incoming_invoices (
                    invoice_id, uuid, issue_date, supplier, supplier_tckn_vkn,
                    amount, total_vat_base, currency, despatch_ids, raw_json, row_hash,
                    change_type, last_change_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (invoice_id) DO NOTHING
            """
            # Each batch gets BEGIN -> UPSERT -> COMMIT
            db.execute_batch(insert_query, to_insert, batch_size=config.BATCH_SIZE, persistent=True)
        
        # Batch update with transaction per batch
        if to_update:
            num_update_batches = (len(to_update) + config.BATCH_SIZE - 1) // config.BATCH_SIZE
            batch_count += num_update_batches
            logger.info(f"🔄 Updating {len(to_update)} changed invoices ({num_update_batches} batches of {config.BATCH_SIZE})...")
            update_query = """
                UPDATE incoming_invoices
                SET uuid = %s,
                    issue_date = %s,
                    supplier = %s,
                    supplier_tckn_vkn = %s,
                    amount = %s,
                    total_vat_base = %s,
                    currency = %s,
                    despatch_ids = %s,
                    raw_json = %s,
                    row_hash = %s,
                    change_type = %s,
                    last_change_at = %s,
                    updated_at = %s
                WHERE invoice_id = %s
            """
            # Each batch gets BEGIN -> UPDATE -> COMMIT
            db.execute_batch(update_query, to_update, batch_size=config.BATCH_SIZE, persistent=True)
        
        # Store batch count in counts dict
        counts['batch_count'] = batch_count
        
        return counts
    
    def fetch_with_retry(self, extractor, max_retries: int = None) -> List[Dict]:
        """Fetch invoices with retry logic"""
        max_retries = max_retries or config.MAX_RETRIES
        retry_delay = config.RETRY_DELAY
        
        for attempt in range(max_retries):
            try:
                success, invoices_data = extractor.fetch_incoming_invoices_with_pagination()
                if success:
                    return invoices_data
                else:
                    logger.warning(f"⚠️  Fetch failed (attempt {attempt + 1}/{max_retries})")
            except Exception as e:
                logger.error(f"❌ Fetch error (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                sleep_time = retry_delay * (2 ** attempt)  # Exponential backoff
                logger.info(f"💤 Retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)
        
        logger.error(f"❌ All {max_retries} fetch attempts failed")
        return []
    
    def run(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
        """Run incoming invoice agent"""
        self.start_time = datetime.now()
        
        logger.info("=" * 70)
        logger.info(f"🚀 INCOMING INVOICE AGENT v2.0 - RUN ID: {self.run_id}")
        logger.info("=" * 70)
        
        # Log run start to database
        metadata = {
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'refresh_xml_cache': self.refresh_xml_cache
        }
        self.run_logger.start_run(metadata=metadata)
        
        try:
            # Test database connection
            logger.info("🔌 Testing database connection...")
            if not db.test_connection():
                raise Exception("Database connection failed")
            logger.info("✅ Database connected")
            
            # Get agent state with lookback
            if start_date is None:
                start_date = get_start_date_with_lookback(self.agent_name)
            
            if end_date is None:
                end_date = datetime.now()
            
            logger.info(f"📅 Date range: {start_date.date()} to {end_date.date()}")
            
            # Import extractor (late import to avoid circular dependencies)
            from ingestion.api_incoming_invoices_extractor import IsbasiAPIIncomingInvoicesExtractor
            
            # Initialize extractor with non-interactive auth
            logger.info("🔧 Initializing API extractor...")
            extractor = IsbasiAPIIncomingInvoicesExtractor(refresh_xml_cache=self.refresh_xml_cache)
            
            # Override password if in .env (non-interactive mode)
            if config.ISBASI_PASSWORD:
                logger.info("🔑 Using password from .env (non-interactive mode)")
                extractor.password = config.ISBASI_PASSWORD
                # Set access token from environment if available
                if hasattr(extractor, 'session'):
                    # Pre-login to avoid interactive prompt
                    login_data = {
                        "username": config.ISBASI_USERNAME,
                        "password": config.ISBASI_PASSWORD
                    }
                    try:
                        response = extractor.session.post(
                            f"{extractor.base_url}{extractor.endpoints['login']}",
                            json=login_data,
                            timeout=extractor.timeout,
                            verify=extractor.verify_ssl
                        )
                        if response.status_code == 200:
                            response_data = response.json()
                            data = response_data.get('data', {})
                            extractor.access_token = data.get('accessToken')
                            extractor.user_id = data.get('id') or data.get('userId')
                            extractor.user_email = data.get('email') or config.ISBASI_USERNAME
                            extractor.tenant_id = data.get('tenantId')
                            extractor.user_name = data.get('userName') or data.get('name')
                            
                            if extractor.access_token:
                                extractor.session.headers.update({
                                    'Authorization': f'Bearer {extractor.access_token}'
                                })
                                if extractor.user_id:
                                    extractor.session.headers.update({'UserId': str(extractor.user_id)})
                                if extractor.user_email:
                                    extractor.session.headers.update({'UserEmail': extractor.user_email})
                                if extractor.tenant_id:
                                    extractor.session.headers.update({'tenantId': str(extractor.tenant_id)})
                                if extractor.user_name:
                                    extractor.session.headers.update({'UserName': extractor.user_name})
                                
                                logger.info("✅ Non-interactive login successful")
                        else:
                            logger.warning("⚠️  Non-interactive login failed, falling back to interactive")
                    except Exception as e:
                        logger.warning(f"⚠️  Non-interactive login error: {e}, falling back to interactive")
            else:
                # Interactive login
                logger.info("🔐 Interactive login required...")
                if not extractor.secure_login():
                    raise Exception("API login failed")
            
            # Fetch invoices with retry
            logger.info("📥 Fetching invoices from API...")
            invoices_data = self.fetch_with_retry(extractor)
            
            if not invoices_data:
                logger.warning("⚠️  No invoices fetched")
                self.end_time = datetime.now()
                self._print_summary()
                return
            
            self.stats['total_fetched'] = len(invoices_data)
            logger.info(f"✅ Fetched {len(invoices_data)} invoices")
            
            # Filter by date range
            filtered = []
            max_issue_date = start_date
            
            for invoice in invoices_data:
                issue_date_str = invoice.get('issueDate', '')
                try:
                    if 'T' in issue_date_str:
                        issue_date = datetime.fromisoformat(issue_date_str.replace('Z', '+00:00'))
                    else:
                        issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d')
                    
                    if issue_date >= start_date and issue_date <= end_date:
                        filtered.append(invoice)
                        if issue_date > max_issue_date:
                            max_issue_date = issue_date
                except:
                    filtered.append(invoice)
            
            logger.info(f"📊 {len(filtered)} invoices in date range")
            
            # Batch upsert
            logger.info("💾 Upserting to database...")
            batch_counts = self.upsert_invoice_batch(filtered)
            
            for key in ['insert', 'update', 'nochange', 'error', 'batch_count']:
                self.stats[key] += batch_counts[key]
            
            # Update agent state
            logger.info(f"📅 Updating agent state (max_issue_date: {max_issue_date})")
            set_state(self.agent_name, max_issue_date)
            
            # Close persistent connection
            db.close_persistent_connection()
            
            self.end_time = datetime.now()
            
            # Log successful completion
            status = 'success' if self.stats['error'] == 0 else 'partial'
            self.run_logger.complete_run(
                insert_count=self.stats['insert'],
                update_count=self.stats['update'],
                nochange_count=self.stats['nochange'],
                error_count=self.stats['error'],
                total_fetched=self.stats['total_fetched'],
                batch_count=self.stats['batch_count'],
                status=status
            )
            
            self._print_summary()
            
        except Exception as e:
            self.end_time = datetime.now()
            logger.error(f"❌ Agent failed: {e}", exc_info=True)
            
            # Log failed run
            self.run_logger.complete_run(
                insert_count=self.stats['insert'],
                update_count=self.stats['update'],
                nochange_count=self.stats['nochange'],
                error_count=self.stats['error'],
                total_fetched=self.stats['total_fetched'],
                batch_count=self.stats['batch_count'],
                status='failed',
                error_message=str(e)
            )
            
            self._print_summary()
            raise
    
    def _print_summary(self):
        """Print run summary"""
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else 0
        
        logger.info("=" * 70)
        logger.info(f"📊 INCOMING AGENT SUMMARY - {self.run_id}")
        logger.info("=" * 70)
        logger.info(f"⏱️  Duration: {duration:.1f}s")
        logger.info(f"📥 Fetched: {self.stats['total_fetched']}")
        logger.info(f"✅ Inserted: {self.stats['insert']}")
        logger.info(f"🔄 Updated: {self.stats['update']}")
        logger.info(f"⚪ Unchanged: {self.stats['nochange']}")
        logger.info(f"❌ Errors: {self.stats['error']}")
        logger.info(f"📦 Batches: {self.stats['batch_count']}")
        logger.info(f"🖥️  Host: {self.run_logger.host}")
        logger.info(f"🏷️  Version: {self.run_logger.version}")
        logger.info("=" * 70)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Run incoming invoice ingestion agent')
    parser.add_argument(
        '--refresh-xml',
        action='store_true',
        help='Cache olsa bile gelen fatura XML içeriklerini yeniden çek'
    )
    args = parser.parse_args()

    try:
        agent = IncomingInvoiceAgent(refresh_xml_cache=args.refresh_xml)
        agent.run()
    except KeyboardInterrupt:
        logger.info("\n❌ Agent interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
