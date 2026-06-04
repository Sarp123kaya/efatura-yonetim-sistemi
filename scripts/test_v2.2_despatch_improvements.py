#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Script for v2.2 Despatch Improvements
Tests normalize functions and extractor integration
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_normalize_incoming_despatch():
    """Test supplier-based incoming despatch normalization"""
    from backend.core.normalize import normalize_incoming_despatch
    
    print("\n" + "=" * 80)
    print("TEST 1: normalize_incoming_despatch (Supplier-based)")
    print("=" * 80)
    
    test_cases = [
        # (raw_id, supplier, expected)
        ("IRS2025000014740", "AK GİPS YAPI KİMYASALLARI", "A-14740"),
        ("IRS2025000009170", "FULLBOARD YAPI ELEMANLARI A.Ş", "F-09170"),
        ("IRS2025000012345", "AKBANK", "A-12345"),
        ("IRS2025000067890", "FULLTÜRK", "F-67890"),
        ("IRS2025000098765", "OTHER SUPPLIER", "98765"),
        ("12345", "AK COMPANY", "A-12345"),
        ("98765", "FULL COMPANY", "F-98765"),
        ("12345", "RANDOM COMPANY", "12345"),
        (None, "AK GİPS", None),
        ("", "FULLBOARD", None),
    ]
    
    passed = 0
    failed = 0
    
    for raw_id, supplier, expected in test_cases:
        result = normalize_incoming_despatch(raw_id, supplier)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status} normalize_incoming_despatch('{raw_id}', '{supplier}') = '{result}' (expected: '{expected}')")
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_clean_description():
    """Test description cleaning (IBAN removal)"""
    from backend.core.normalize import clean_description
    
    print("\n" + "=" * 80)
    print("TEST 2: clean_description (IBAN/Bank Info Removal)")
    print("=" * 80)
    
    test_cases = [
        (
            "İRSALİYE NO: A-09170\nGARANTİBANK A.Ş. - TR35 0006 2001 1670 0006 2939 21",
            "İRSALİYE NO: A-09170"
        ),
        (
            "F/14740 (İSTANBUL)\nBanka Bilgileri\nAKBANK - TR12 3456 7890 1234 5678 9012 34",
            "F/14740 (İSTANBUL)"
        ),
        (
            "Normal invoice description without IBAN",
            "Normal invoice description without IBAN"
        ),
        ("", ""),
        (None, ""),
    ]
    
    passed = 0
    failed = 0
    
    for desc, expected in test_cases:
        result = clean_description(desc)
        # Trim whitespace for comparison
        result = result.strip()
        expected = expected.strip()
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        else:
            failed += 1
        desc_preview = (desc or "")[:50] + "..." if desc and len(desc) > 50 else (desc or "")
        print(f"{status} clean_description('{desc_preview}') = '{result}' (expected: '{expected}')")
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_extract_despatch_from_description():
    """Test despatch extraction from description"""
    from backend.core.normalize import extract_despatch_from_description
    
    print("\n" + "=" * 80)
    print("TEST 3: extract_despatch_from_description (Pattern Matching)")
    print("=" * 80)
    
    test_cases = [
        ("İRSALİYE NO: A-09170", "A-09170"),
        ("F / 14740 (İSTANBUL)", "F-14740"),
        ("A 1234", "A-1234"),
        ("F-98765 TEST", "F-98765"),
        ("a-12345", "A-12345"),  # Case insensitive
        ("f/67890", "F-67890"),
        ("No despatch code here", None),
        ("", None),
        (None, None),
        # With IBAN (should be cleaned first)
        ("A-09170\nGARANTİBANK - TR35 0006 2001 1670 0006 2939 21", "A-09170"),
    ]
    
    passed = 0
    failed = 0
    
    for desc, expected in test_cases:
        result = extract_despatch_from_description(desc)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        else:
            failed += 1
        desc_preview = (desc or "")[:50] + "..." if desc and len(desc) > 50 else (desc or "")
        print(f"{status} extract_despatch_from_description('{desc_preview}') = '{result}' (expected: '{expected}')")
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_extractor_integration():
    """Test if extractors can import and use the new functions"""
    print("\n" + "=" * 80)
    print("TEST 4: Extractor Integration")
    print("=" * 80)
    
    # Test incoming extractor
    try:
        from ingestion.api_incoming_invoices_extractor import IsbasiAPIIncomingInvoicesExtractor
        print("✅ Incoming extractor imported successfully")
        
        # Check if parse_despatch_documents_from_xml has supplier parameter
        import inspect
        sig = inspect.signature(IsbasiAPIIncomingInvoicesExtractor.parse_despatch_documents_from_xml)
        params = list(sig.parameters.keys())
        if 'supplier' in params:
            print("✅ parse_despatch_documents_from_xml has 'supplier' parameter")
        else:
            print("❌ parse_despatch_documents_from_xml missing 'supplier' parameter")
            return False
    except Exception as e:
        print(f"❌ Incoming extractor import failed: {e}")
        return False
    
    # Test outgoing extractor
    try:
        from ingestion.api_data_extractor import IsbasiAPIDataExtractor
        print("✅ Outgoing extractor imported successfully")
        
        # Check if new methods exist
        if hasattr(IsbasiAPIDataExtractor, 'extract_despatch_id_from_description'):
            print("✅ extract_despatch_id_from_description method exists")
        else:
            print("❌ extract_despatch_id_from_description method missing")
            return False
    except Exception as e:
        print(f"❌ Outgoing extractor import failed: {e}")
        return False
    
    return True


def main():
    print("\n" + "=" * 80)
    print("🔍 TESTING v2.2 DESPATCH IMPROVEMENTS")
    print("=" * 80)
    
    all_passed = True
    
    # Run tests
    try:
        all_passed &= test_normalize_incoming_despatch()
    except Exception as e:
        print(f"\n❌ Test 1 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        all_passed &= test_clean_description()
    except Exception as e:
        print(f"\n❌ Test 2 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        all_passed &= test_extract_despatch_from_description()
    except Exception as e:
        print(f"\n❌ Test 3 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        all_passed &= test_extractor_integration()
    except Exception as e:
        print(f"\n❌ Test 4 failed with exception: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    # Summary
    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("=" * 80)
        print("\n✅ Ready to use:")
        print("   1. Run migration: psql invoices -f sql/migration_v2.2_despatch_improvements.sql")
        print("   2. Run agents: python backend/agents/incoming_agent.py")
        print("   3. Export data: python scripts/export_to_excel.py")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("=" * 80)
        print("\nPlease fix the issues before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
