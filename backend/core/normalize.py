#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Normalization Module
====================

Extracts and normalizes irsaliye/despatch codes from various sources.
"""

import re
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


def extract_irsaliye_codes_from_description(description: str) -> List[str]:
    """
    Extract and normalize irsaliye codes from description text.
    Preserves the original prefix (A/F/T) for supplier-aware matching.
    
    Supported prefixes:
        A = AK GİPS
        F = FULLBOARD
        T = TERMATECH
    
    Examples:
        - "A-604"              -> ["A-00604"]
        - "F-956"              -> ["F-00956"]
        - "T-86 / T-92"       -> ["T-00086", "T-00092"]
        - "A-940 / A-941"     -> ["A-00940", "A-00941"]
        - "A-1183"            -> ["A-01183"]
        - "F-0071 / F-0179"   -> ["F-00071", "F-00179"]
    
    Args:
        description: Description text (from outgoing invoice)
        
    Returns:
        List of normalized irsaliye codes (X-XXXXX format, prefix preserved)
    """
    if not description:
        return []
    
    normalized_codes = []
    
    # Pattern: [AFT] prefix followed by digits
    pattern = r'([AFT])\s*[-/]\s*(\d+)'
    matches = re.findall(pattern, description, re.IGNORECASE)
    for prefix, digits in matches:
        if len(digits) > 5:
            digits = digits[-5:]
        padded_digits = digits.zfill(5)
        normalized_codes.append(f"{prefix.upper()}-{padded_digits}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_codes = []
    for code in normalized_codes:
        if code not in seen:
            seen.add(code)
            unique_codes.append(code)
    
    if unique_codes:
        logger.debug(f"Extracted {len(unique_codes)} irsaliye codes from description")
    
    return unique_codes


def normalize_despatch_ids_from_incoming(despatch_ids: List[str]) -> List[str]:
    """
    Normalize despatch IDs from incoming invoice XML data
    
    Incoming invoices contain despatch IDs like:
        - "IRS2025000014740" -> ["IRS-14740"]
        - "IRS2025000009170" -> ["IRS-09170"]
    
    Extract last 5 digits and normalize to IRS-XXXXX format.
    
    Args:
        despatch_ids: List of despatch ID strings (full format from XML)
        
    Returns:
        List of normalized despatch IDs (IRS-XXXXX format)
    """
    if not despatch_ids:
        return []
    
    normalized_ids = []
    
    for despatch_id in despatch_ids:
        if not despatch_id:
            continue
        
        despatch_id = str(despatch_id).strip()
        
        # Extract last 5 digits
        if len(despatch_id) >= 5:
            last_five = despatch_id[-5:]
            # Verify they are digits
            if last_five.isdigit():
                normalized_id = f"IRS-{last_five}"
                normalized_ids.append(normalized_id)
            else:
                logger.warning(f"⚠️  Invalid despatch_id format (last 5 chars not digits): {despatch_id}")
        else:
            # Short format, pad with zeros
            if despatch_id.isdigit():
                padded = despatch_id.zfill(5)
                normalized_id = f"IRS-{padded}"
                normalized_ids.append(normalized_id)
            else:
                logger.warning(f"⚠️  Invalid despatch_id format: {despatch_id}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_ids = []
    for despatch_id in normalized_ids:
        if despatch_id not in seen:
            seen.add(despatch_id)
            unique_ids.append(despatch_id)
    
    if unique_ids:
        logger.debug(f"Normalized {len(unique_ids)} despatch IDs from incoming invoice")
    
    return unique_ids


def extract_despatch_ids_from_summary(despatch_summary: Optional[str]) -> List[str]:
    """
    Extract despatch IDs from comma-separated summary string
    
    Args:
        despatch_summary: Comma-separated string like "14740, 09170"
        
    Returns:
        List of normalized despatch IDs (IRS-XXXXX format)
    """
    if not despatch_summary:
        return []
    
    # Split by comma and normalize each
    parts = [p.strip() for p in str(despatch_summary).split(',') if p.strip()]
    
    normalized_ids = []
    for part in parts:
        # Remove non-digits
        digits = re.sub(r'\D', '', part)
        if digits:
            # Zero-pad to 5 digits
            padded = digits.zfill(5)
            normalized_id = f"IRS-{padded}"
            normalized_ids.append(normalized_id)
    
    # Remove duplicates
    return list(dict.fromkeys(normalized_ids))


# ============================================================================
# NEW: Supplier-based normalization (v2.2)
# ============================================================================

def normalize_incoming_despatch(raw_id: str, supplier: str) -> Optional[str]:
    """
    Normalize incoming despatch ID based on supplier name
    
    Rules:
        - Supplier contains "AK" -> A-XXXX format
        - Supplier contains "FULL" -> F-XXXX format
        - Otherwise -> return digits only
        - Extract last 5 digits from raw_id (standard format)
        
    Examples:
        - normalize_incoming_despatch("IRS2025000014740", "AK GİPS") -> "A-14740"
        - normalize_incoming_despatch("IRS2025000009170", "FULLBOARD") -> "F-09170"
        - normalize_incoming_despatch("12345", "OTHER SUPPLIER") -> "12345"
        
    Args:
        raw_id: Raw despatch ID from XML/API (e.g., "IRS2025000014740")
        supplier: Supplier name (e.g., "AK GİPS YAPI KİMYASALLARI")
        
    Returns:
        Normalized despatch ID or None if invalid
    """
    if not raw_id:
        return None
    
    raw_id_str = str(raw_id).strip()
    
    # Extract all digits
    all_digits = re.sub(r'\D', '', raw_id_str)
    if not all_digits:
        return None
    
    # Take last 5 digits (standard irsaliye format)
    if len(all_digits) >= 5:
        code = all_digits[-5:]
    else:
        # If less than 5 digits, use as-is (no padding for short codes)
        code = all_digits
    
    # Determine prefix based on supplier
    supplier_upper = (supplier or "").upper()
    
    if "AK" in supplier_upper:
        return f"A-{code}"
    
    if "FULL" in supplier_upper:
        return f"F-{code}"
    
    if "TERMA" in supplier_upper:
        return f"T-{code}"
    
    return code


def clean_description(desc: str) -> str:
    """
    Clean description by removing IBAN and bank info
    
    Removes lines like:
        - "AKBANK A.Ş. - TR12 3456 7890 1234 5678 9012 34"
        - "Banka Bilgileri"
        - "GARANTİ BANKASI A.Ş. - TR98 7654 3210 9876 5432 1098 76"
        - "GARANTİBANK A.Ş. - TR35 0006 2001 1670 0006 2939 21"
        
    Args:
        desc: Description text
        
    Returns:
        Cleaned description without IBAN/bank info
    """
    if not desc:
        return ""
    
    # Normalize line endings
    desc = desc.replace('\r\n', '\n').replace('\r', '\n')
    
    # Remove "Banka Bilgileri" text (case variations)
    desc = re.sub(r'(?i)banka\s+bilgileri', '', desc)
    
    # Remove bank IBAN lines (Turkish bank names + TR IBAN)
    desc = re.sub(r'[A-ZÇĞİÖŞÜa-zçğıöşü\s\.]+\s*-\s*TR\s*\d[\d\s]+', '', desc, flags=re.MULTILINE)
    
    # Remove standalone IBAN (TR followed by 24 digits/spaces)
    desc = re.sub(r'TR\s*\d{2}[\s\d]{20,}', '', desc, flags=re.MULTILINE)
    
    # Clean up multiple newlines and whitespace
    desc = re.sub(r'\n\s*\n', '\n', desc)
    
    return desc.strip()


def extract_despatch_from_description(desc: str) -> Optional[str]:
    """
    Extract single despatch ID from outgoing invoice description
    
    First cleans IBAN/bank info, then extracts despatch code.
    
    Patterns:
        - "A-09170" -> "A-09170"
        - "F / 14740" -> "F-14740"
        - "A 1234" -> "A-1234" (space instead of dash)
        
    Args:
        desc: Description text (may contain IBAN/bank info)
        
    Returns:
        Normalized despatch ID (A-XXXX or F-XXXX) or None
        
    Examples:
        >>> extract_despatch_from_description("İRSALİYE NO: A-09170\\nAKBANK - TR12...")
        'A-09170'
        >>> extract_despatch_from_description("F / 14740 (İSTANBUL)")
        'F-14740'
    """
    if not desc:
        return None
    
    # Clean IBAN/bank info first
    cleaned = clean_description(desc)
    
    match = re.search(r'([AFT])\s*[-/\s]\s*(\d+)', cleaned, re.IGNORECASE)
    
    if match:
        prefix = match.group(1).upper()
        digits = match.group(2)
        return f"{prefix}-{digits}"
    
    return None
