#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for removing old generated Excel reports before writing new ones."""
from pathlib import Path
from typing import Iterable, Union


def cleanup_old_reports(output_dir: Union[str, Path], patterns: Iterable[str]) -> int:
    """Delete old report files matching known generated filename patterns."""
    output_path = Path(output_dir)
    if not output_path.exists():
        return 0

    deleted = 0
    for pattern in patterns:
        for file_path in output_path.glob(pattern):
            if not file_path.is_file():
                continue
            try:
                file_path.unlink()
                deleted += 1
            except OSError as exc:
                print(f"⚠️ Eski rapor silinemedi: {file_path} ({exc})")

    if deleted:
        print(f"🧹 {deleted} eski Excel raporu silindi.")

    return deleted
