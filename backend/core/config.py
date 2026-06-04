#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Module
====================

Loads configuration from environment variables and .env file.
"""

import os
from pathlib import Path
from typing import Optional

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_dotenv_if_present(dotenv_path: Path) -> None:
    """
    Minimal .env loader (no python-dotenv dependency).
    - Only sets keys that are NOT already present in os.environ
    - Ignores blank lines and comments
    """
    try:
        if not dotenv_path.exists():
            return
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            key, val = s.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception as e:
        print(f"⚠️ .env okunamadı ({dotenv_path}): {e}")


# Load .env file
_load_dotenv_if_present(PROJECT_ROOT / ".env")


class Config:
    """Application configuration"""
    
    # Database
    DB_URL: str = os.getenv("DB_URL", "").strip()
    PG_DSN: str = os.getenv("PG_DSN", "").strip()  # Alternative name
    
    # Isbasi API credentials
    ISBASI_API_KEY: str = os.getenv("ISBASI_API_KEY", "").strip()
    ISBASI_USERNAME: str = os.getenv("ISBASI_USERNAME", "").strip()
    ISBASI_PASSWORD: str = os.getenv("ISBASI_PASSWORD", "").strip()  # Non-interactive password
    ISBASI_BASE_URL: str = os.getenv("ISBASI_BASE_URL", "https://mw-jplatform.isbasi.com").rstrip("/")
    ISBASI_VERIFY_SSL: bool = os.getenv("ISBASI_VERIFY_SSL", "true").strip().lower() in ("1", "true", "yes", "y", "on")
    
    # Optional user info (for headers)
    ISBASI_USER_ID: str = os.getenv("ISBASI_USER_ID", "").strip()
    ISBASI_USER_EMAIL: str = os.getenv("ISBASI_USER_EMAIL", "").strip()
    ISBASI_TENANT_ID: str = os.getenv("ISBASI_TENANT_ID", "").strip()
    
    # Agent defaults
    DEFAULT_START_DATE: str = "2026-01-01"
    DEFAULT_LOOKBACK_DAYS: int = 2
    
    # Performance settings
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "100"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: float = float(os.getenv("RETRY_DELAY", "2.0"))
    
    @classmethod
    def get_db_url(cls) -> str:
        """Get database URL with fallback"""
        url = cls.DB_URL or cls.PG_DSN
        if not url:
            raise ValueError(
                "Database URL not configured. Set DB_URL or PG_DSN in .env file.\n"
                "Example: DB_URL=postgresql://user:password@localhost:5432/invoices"
            )
        return url
    
    @classmethod
    def validate_api_credentials(cls) -> bool:
        """Check if API credentials are configured"""
        return bool(cls.ISBASI_API_KEY and cls.ISBASI_USERNAME)


# Create singleton instance
config = Config()
