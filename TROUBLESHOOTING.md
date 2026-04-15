# Troubleshooting Guide

**Last Updated:** 2026-02-10  
**Version:** 2.1.1

---

## 🐛 Common Issues After Restructuring

### Issue 1: ModuleNotFoundError: No module named 'src' ✅ FIXED

**Error:**
```
ModuleNotFoundError: No module named 'src'
File: ingestion/api_incoming_invoices_extractor.py, line 68
```

**Cause:** Extractor files had old imports pointing to `src.api.api_database`

**Fix Applied:**
```python
# OLD (broken after restructuring)
from src.api.api_database import APIDatabase

# NEW (fixed)
from archive.legacy_src.api_database import APIDatabase
```

**Files Updated:**
- ✅ `ingestion/api_data_extractor.py`
- ✅ `ingestion/api_incoming_invoices_extractor.py`
- ✅ `archive/__init__.py` (created)

**Status:** ✅ RESOLVED

---

### Issue 2: ModuleNotFoundError: No module named 'psycopg2' ⚠️ DEPENDENCY ISSUE

**Error:**
```
ModuleNotFoundError: No module named 'psycopg2'
File: backend/core/db.py, line 13
```

**Cause:** Missing Python dependency (psycopg2 not installed in virtual environment)

**Fix:**

```bash
# Option 1: Install psycopg2-binary (recommended)
pip install psycopg2-binary

# Option 2: Reinstall all requirements
pip install -r requirements.txt

# Option 3: Use correct virtual environment
# Check if you're in the right venv:
which python
# Should show: /Users/sp383/Desktop/gelen efaturalar deneme kopyası/.venv/bin/python

# If not, activate it:
source .venv/bin/activate  # or create new one
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Verify installation:**
```bash
python -c "import psycopg2; print(psycopg2.__version__)"
# Should print: 2.9.x (or similar)
```

**Note:** The terminal output shows you're using a different venv:
```
/Users/sp383/Desktop/gelen efaturalar deneme/.venv/
                                              ↑ Wrong folder (no "kopyası")
```

You need to use:
```
/Users/sp383/Desktop/gelen efaturalar deneme kopyası/.venv/
                                              ↑ Correct folder
```

**Status:** ⚠️ USER ACTION REQUIRED

---

### Issue 3: zsh: no matches found: COUNT(*) ⚠️ SHELL SYNTAX

**Error:**
```
zsh: no matches found: COUNT(*)
```

**Cause:** ZSH shell tries to expand `*` as a glob pattern

**Fix:** Quote or escape SQL queries in terminal

**Correct usage:**

```bash
# Option 1: Single quotes (best)
sqlite3 data/db/akgips.db "SELECT COUNT(*) FROM despatch_documents"

# Option 2: Escape asterisk
sqlite3 data/db/akgips.db "SELECT COUNT(\*) FROM despatch_documents"

# Option 3: Double quotes
sqlite3 data/db/akgips.db 'SELECT COUNT(*) FROM despatch_documents'

# ❌ WRONG (will fail in zsh)
sqlite3 data/db/akgips.db SELECT COUNT(*) FROM despatch_documents
```

**Status:** 💡 USER SYNTAX ERROR

---

## ✅ Quick Fix Checklist

After restructuring, run this checklist:

### 1. Verify Virtual Environment

```bash
# Check which Python you're using
which python

# Should output:
# /Users/sp383/Desktop/gelen efaturalar deneme kopyası/.venv/bin/python

# If not, activate correct venv:
cd "/Users/sp383/Desktop/gelen efaturalar deneme kopyası"
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
# Ensure all dependencies installed
pip install -r requirements.txt

# Verify key packages
python -c "import psycopg2, pandas, requests; print('✅ All imports OK')"
```

### 3. Test Imports

```bash
# Test agent imports
python -c "from backend.agents.incoming_agent import IncomingInvoiceAgent; print('✅ Agent OK')"

# Test extractor imports
python -c "from ingestion.api_data_extractor import IsbasiAPIDataExtractor; print('✅ Extractor OK')"

# Test core imports
python -c "from backend.core.db import db; print('✅ DB OK')"
```

### 4. Verify Structure

```bash
# Check all required folders exist
ls -d backend/ ingestion/ sql/ scripts/ docs/ archive/
# Should show all 6 folders without errors
```

---

## 🔧 Environment Setup (Fresh Start)

If you're having persistent issues, start fresh:

```bash
# 1. Navigate to project
cd "/Users/sp383/Desktop/gelen efaturalar deneme kopyası"

# 2. Remove old venv (if exists)
rm -rf .venv

# 3. Create new venv
python3 -m venv .venv

# 4. Activate venv
source .venv/bin/activate

# 5. Upgrade pip
pip install --upgrade pip

# 6. Install dependencies
pip install -r requirements.txt

# 7. Verify installation
python scripts/verify_installation.py
```

---

## 🐛 Debugging Import Issues

### Check Python Path

```bash
python -c "import sys; print('\n'.join(sys.path))"
```

Should include:
- `/Users/sp383/Desktop/gelen efaturalar deneme kopyası`
- `.venv/lib/python3.x/site-packages`

### Check Module Structure

```bash
# Check if __init__.py files exist
find . -name "__init__.py" -type f | grep -E "^\./(backend|ingestion|archive)"

# Should show:
# ./backend/__init__.py
# ./backend/core/__init__.py
# ./backend/agents/__init__.py
# ./ingestion/__init__.py
# ./archive/__init__.py
# ./archive/legacy_src/__init__.py
```

### Test Import from Python REPL

```python
# Start Python
python

# Test imports step by step
>>> import backend
>>> from backend.core import db
>>> from ingestion import api_data_extractor
>>> from archive.legacy_src import api_database
>>> print("✅ All imports successful!")
```

---

## 📊 Requirements.txt Check

Ensure `requirements.txt` includes all necessary packages:

```txt
# Core dependencies
psycopg2-binary>=2.9.0
python-dotenv>=0.19.0
requests>=2.26.0

# Data processing
pandas>=1.3.0
openpyxl>=3.0.9
xlsxwriter>=3.0.0

# Optional
cryptography>=3.4.8
```

**Verify:**
```bash
grep -E "psycopg2|pandas|requests" requirements.txt
```

---

## 🚨 Known Issues & Workarounds

### OpenSSL Warning (Non-Critical)

**Warning:**
```
NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, 
currently the 'ssl' module is compiled with 'LibreSSL 2.8.3'
```

**Impact:** Non-critical warning, requests still work

**Workaround (if it bothers you):**
```bash
# Downgrade urllib3
pip install 'urllib3<2.0'
```

### ImportError: cannot import name 'SomeModule'

**Cause:** Circular imports or missing `__init__.py`

**Fix:**
1. Check `__init__.py` exists in all package folders
2. Avoid circular imports (e.g., A imports B, B imports A)
3. Use absolute imports: `from backend.core.db import db`

---

## 🎯 Post-Restructuring Verification

Run this complete test:

```bash
#!/bin/bash
# save as: test_restructuring.sh

echo "🔍 Testing restructuring..."

# Test 1: Folder structure
echo "1. Checking folders..."
for folder in backend ingestion sql scripts docs archive; do
    if [ -d "$folder" ]; then
        echo "  ✅ $folder"
    else
        echo "  ❌ $folder MISSING!"
        exit 1
    fi
done

# Test 2: Python imports
echo "2. Testing imports..."
python -c "from backend.core.db import db; print('  ✅ backend.core.db')" || exit 1
python -c "from ingestion.api_data_extractor import IsbasiAPIDataExtractor; print('  ✅ ingestion.api_data_extractor')" || exit 1
python -c "from archive.legacy_src.api_database import APIDatabase; print('  ✅ archive.legacy_src.api_database')" || exit 1

# Test 3: Dependencies
echo "3. Checking dependencies..."
python -c "import psycopg2; print('  ✅ psycopg2')" || echo "  ⚠️  psycopg2 not installed"
python -c "import pandas; print('  ✅ pandas')" || echo "  ⚠️  pandas not installed"

echo ""
echo "✅ Restructuring verification complete!"
```

**Run:**
```bash
chmod +x test_restructuring.sh
./test_restructuring.sh
```

---

## 📞 Still Having Issues?

### 1. Check This File First
- `PROJECT_STRUCTURE.md` - Detailed structure guide

### 2. Review Changelogs
- `docs/CHANGELOG_v2.1.1.md` - Latest changes
- `RESTRUCTURING_COMPLETE.md` - What was moved

### 3. Common Fixes

**"Can't find module X"**
→ Check if you're in correct venv and installed requirements

**"Import error from src.*"**
→ We already fixed this (update to `archive.legacy_src.*`)

**"Database connection failed"**
→ Check `.env` file has correct `DB_URL`

**"Agent won't run"**
→ Ensure `.env` has API credentials

---

## 🔄 Rollback (Emergency)

If restructuring broke something critically:

```bash
# Git rollback (if you committed before)
git log --oneline  # find commit before restructuring
git reset --hard <commit-hash>

# Manual fix: Check what imports are broken
python backend/agents/incoming_agent.py
# Read error, fix import path
```

---

**Status:** 📝 Living document - update as issues are discovered

**Questions?** Check:
- `PROJECT_STRUCTURE.md` for structure details
- `README.md` for usage guide
- `docs/V2_PRODUCTION_READY.md` for system overview
