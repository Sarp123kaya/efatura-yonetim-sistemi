#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the web panel background worker."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.web.worker import main


if __name__ == "__main__":
    main()
