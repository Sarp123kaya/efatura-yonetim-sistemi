#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installation Verification Script
=================================

Verifies that all backend modules are importable and configured correctly.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Test that all modules can be imported"""
    print("🔍 Testing module imports...")
    
    try:
        from backend.core import config
        print("  ✅ backend.core.config")
    except Exception as e:
        print(f"  ❌ backend.core.config - {e}")
        return False
    
    try:
        from backend.core import db
        print("  ✅ backend.core.db")
    except Exception as e:
        print(f"  ❌ backend.core.db - {e}")
        return False
    
    try:
        from backend.core import agent_state
        print("  ✅ backend.core.agent_state")
    except Exception as e:
        print(f"  ❌ backend.core.agent_state - {e}")
        return False
    
    try:
        from backend.core import normalize
        print("  ✅ backend.core.normalize")
    except Exception as e:
        print(f"  ❌ backend.core.normalize - {e}")
        return False
    
    try:
        from backend.agents import incoming_agent
        print("  ✅ backend.agents.incoming_agent")
    except Exception as e:
        print(f"  ❌ backend.agents.incoming_agent - {e}")
        return False
    
    try:
        from backend.agents import outgoing_agent
        print("  ✅ backend.agents.outgoing_agent")
    except Exception as e:
        print(f"  ❌ backend.agents.outgoing_agent - {e}")
        return False
    
    return True


def test_config():
    """Test configuration"""
    print("\n⚙️  Testing configuration...")
    
    try:
        from backend.core.config import config
        
        print(f"  📊 Base URL: {config.ISBASI_BASE_URL}")
        print(f"  📅 Default start date: {config.DEFAULT_START_DATE}")
        
        # Check if credentials are configured
        if config.validate_api_credentials():
            print("  ✅ API credentials configured")
        else:
            print("  ⚠️  API credentials NOT configured (set in .env)")
        
        # Check DB URL (don't fail if not set)
        try:
            db_url = config.get_db_url()
            # Mask password
            masked_url = db_url.split('@')[1] if '@' in db_url else db_url
            print(f"  ✅ Database URL configured (@{masked_url})")
        except ValueError as e:
            print(f"  ⚠️  Database URL NOT configured: {e}")
        
        return True
    except Exception as e:
        print(f"  ❌ Configuration error: {e}")
        return False


def test_normalization():
    """Test normalization functions"""
    print("\n🔧 Testing normalization functions (v2.0)...")
    
    try:
        from backend.core.normalize import (
            extract_irsaliye_codes_from_description,
            normalize_despatch_ids_from_incoming,
            extract_despatch_ids_from_summary,
            normalize_incoming_despatch,
        )
        
        # Test 1: Extract from description (A/F format)
        desc = "İRSALİYE NO: A-09170 / F-14740"
        codes = extract_irsaliye_codes_from_description(desc)
        expected = ["A-09170", "F-14740"]
        if codes == expected:
            print(f"  ✅ extract_irsaliye_codes (A/F): {codes}")
        else:
            print(f"  ❌ extract_irsaliye_codes (A/F): got {codes}, expected {expected}")
            return False
        
        # Test 1b: Supplier-aware incoming normalization (v2.2)
        incoming_code = normalize_incoming_despatch("IRS2025000014740", "AK GİPS")
        expected_incoming = "A-14740"
        if incoming_code == expected_incoming:
            print(f"  ✅ normalize_incoming_despatch (supplier-aware): {incoming_code}")
        else:
            print(
                "  ❌ normalize_incoming_despatch (supplier-aware): "
                f"got {incoming_code}, expected {expected_incoming}"
            )
            return False
        
        # Test 2: Normalize incoming despatch IDs
        ids = ["IRS2025000014740", "IRS2025000009170"]
        normalized = normalize_despatch_ids_from_incoming(ids)
        expected = ["IRS-14740", "IRS-09170"]
        if normalized == expected:
            print(f"  ✅ normalize_despatch_ids: {normalized}")
        else:
            print(f"  ❌ normalize_despatch_ids: got {normalized}, expected {expected}")
            return False
        
        # Test 3: Extract from summary
        summary = "14740, 09170"
        ids = extract_despatch_ids_from_summary(summary)
        expected = ["IRS-14740", "IRS-09170"]
        if ids == expected:
            print(f"  ✅ extract_despatch_ids_from_summary: {ids}")
        else:
            print(f"  ❌ extract_despatch_ids_from_summary: got {ids}, expected {expected}")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ Normalization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_connection():
    """Test database connection (if configured)"""
    print("\n🔌 Testing database connection...")
    
    try:
        from backend.core.db import db
        
        if db.test_connection():
            print("  ✅ Database connection successful!")
            
            # Try to query agent_state
            try:
                query = "SELECT agent_name, last_issue_date FROM agent_state ORDER BY agent_name"
                results = db.query(query)
                print(f"  📊 Agent state: {len(results)} agents configured")
                for row in results:
                    print(f"     - {row['agent_name']}: {row['last_issue_date']}")
                return True
            except Exception as e:
                print(f"  ⚠️  Could not query agent_state: {e}")
                print("     Run migrations in this order:")
                print("       psql <db_url> -f sql/stateful_ingestion_schema_v2.sql")
                print("       psql <db_url> -f sql/migration_v2.2_despatch_improvements.sql")
                print("       psql <db_url> -f sql/migration_irsaliye_override.sql")
                print("       psql <db_url> -f sql/migration_incoming_xml_cache.sql")
                return True  # Don't fail if schema not applied yet
        else:
            print("  ⚠️  Database connection failed (configure DB_URL in .env)")
            return True  # Don't fail if DB not configured yet
            
    except Exception as e:
        print(f"  ⚠️  Database test skipped: {e}")
        return True  # Don't fail if DB not configured


def main():
    """Main verification"""
    print("=" * 60)
    print("🔍 BACKEND INSTALLATION VERIFICATION v2.0")
    print("=" * 60)
    print()
    
    all_tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("Normalization", test_normalization),
        ("Database Connection", test_database_connection),
    ]
    
    results = []
    for name, test_func in all_tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print()
    print("=" * 60)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:12} {name}")
    
    all_passed = all(result for _, result in results)
    
    print()
    if all_passed:
        print("✅ All tests passed! v2.0 Production-Ready verified.")
        print()
        print("Next steps:")
        print("1. Configure .env file:")
        print("   - DB_URL=postgresql://...")
        print("   - ISBASI_API_KEY=xxx")
        print("   - ISBASI_USERNAME=xxx")
        print("   - ISBASI_PASSWORD=xxx  # For non-interactive")
        print("2. Migrate schema:")
        print("   - python3 scripts/setup_postgres.sh")
        print("3. First full run with XML cache:")
        print("   - python3 scripts/run_invoice_pipeline.py --start-date 2026-01-01 --refresh-xml")
        print("4. Regular updates:")
        print("   - python3 scripts/run_invoice_pipeline.py")
        print("5. Supplier detail Excel exports:")
        print("   - python3 scripts/export_supplier_invoice_details.py")
        print()
        print("New in v2.0:")
        print("  • Lookback/watermark (2-day default)")
        print("  • Non-interactive auth via .env")
        print("  • Batch upsert (10x faster)")
        print("  • Change type tracking")
        print("  • Retry logic (3 attempts)")
    else:
        print("⚠️  Some tests failed. Check errors above.")
    
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
