# Transaction Per Batch - Veri Bütünlüğü Garantisi

## 🎯 Amaç

Batch upsert işlemlerinde yarım veri kalmasını önlemek için **her batch için ayrı transaction** kullanılır.

## 📊 Öncesi vs Sonrası

### Öncesi (Riskli)
```python
BEGIN
  INSERT 100 rows  # Batch 1
  INSERT 100 rows  # Batch 2
  INSERT 100 rows  # Batch 3 ❌ FAIL here
ROLLBACK  # Tüm 300 row kaybedilir!
```

**Sorun:** Batch 3'te hata olursa, önceki 200 row da geri alınır.

### Sonrası (Güvenli) ✅
```python
# Batch 1
BEGIN
  INSERT 100 rows
COMMIT ✅ 100 row kaydedildi

# Batch 2  
BEGIN
  INSERT 100 rows
COMMIT ✅ 100 row kaydedildi

# Batch 3
BEGIN
  INSERT 100 rows ❌ FAIL
ROLLBACK  # Sadece batch 3 geri alınır

# Sonuç: 200 row başarıyla kaydedildi, 100 row failed
```

**Avantaj:** Batch 3 fail olsa bile, önceki 200 row güvende.

---

## 🔧 Implementation

### backend/core/db.py

```python
def execute_batch(self, query: str, params_list: List[Tuple], 
                  batch_size: int = 100, persistent: bool = True) -> int:
    """
    Transaction per batch:
    - Batch 1: BEGIN -> UPSERT -> COMMIT
    - Batch 2: BEGIN -> UPSERT -> COMMIT
    - etc.
    """
    num_batches = (len(params_list) + batch_size - 1) // batch_size
    
    with self.get_connection(persistent=persistent) as conn:
        for batch_idx in range(num_batches):
            batch_params = params_list[start_idx:end_idx]
            
            try:
                # BEGIN (implicit)
                with conn.cursor() as cur:
                    psycopg2.extras.execute_batch(cur, query, batch_params)
                
                # COMMIT (explicit per batch)
                conn.commit()
                
                logger.debug(f"Batch {batch_idx + 1} committed: {len(batch_params)} rows")
                
            except Exception as e:
                # ROLLBACK this batch only
                conn.rollback()
                logger.error(f"Batch {batch_idx + 1} failed: {e}")
                raise  # Stop processing
```

**Key Points:**
- `conn.commit()` her batch sonrası
- Hata olursa `conn.rollback()` sadece o batch için
- Önceki batch'ler zaten commit edilmiş

---

## 📊 Örnek Senaryo

### Senaryo: 250 Invoice Upsert (batch_size=100)

```
Batch 1: Rows 1-100
  BEGIN
    INSERT invoice_1 ... invoice_100
  COMMIT ✅
  Status: 100 rows committed

Batch 2: Rows 101-200
  BEGIN
    INSERT invoice_101 ... invoice_200
  COMMIT ✅
  Status: 200 rows committed (total)

Batch 3: Rows 201-250
  BEGIN
    INSERT invoice_201 ... invoice_250
    ❌ ERROR: Duplicate key violation on invoice_225
  ROLLBACK
  Status: 200 rows committed, 50 rows failed
```

**Sonuç:**
- ✅ 200 invoice başarıyla kaydedildi
- ❌ 50 invoice failed (batch 3)
- Agent log: `insert: 200, error: 50`

---

## 🔍 Logging

Agent'lar her batch için log üretir:

```
💾 Inserting 250 new invoices (batches of 100)...
DEBUG: Batch 1/3 committed: 100 rows
DEBUG: Batch 2/3 committed: 100 rows
DEBUG: Batch 3/3 committed: 50 rows

✅ Inserted: 250
```

Hata durumunda:
```
💾 Inserting 250 new invoices (batches of 100)...
DEBUG: Batch 1/3 committed: 100 rows
DEBUG: Batch 2/3 committed: 100 rows
ERROR: Batch 3/3 failed: duplicate key value violates unique constraint

✅ Inserted: 200
❌ Errors: 50
```

---

## ⚙️ Configuration

Batch size .env'den ayarlanabilir:

```bash
# .env
BATCH_SIZE=100  # Default
# BATCH_SIZE=500  # Daha az transaction, daha hızlı (ama hata riski yükselir)
# BATCH_SIZE=50   # Daha fazla transaction, daha güvenli (ama biraz yavaş)
```

**Trade-off:**
- **Küçük batch (50):** Daha fazla transaction, daha güvenli, biraz yavaş
- **Büyük batch (500):** Daha az transaction, daha hızlı, hata olursa daha çok kayıp

**Öneri:** 100-200 arası optimal (production için)

---

## 🧪 Test

### Test 1: Normal Case (Tüm Batch'ler Başarılı)

```python
# 250 invoice, batch_size=100
agent = IncomingInvoiceAgent()
agent.run()

# Beklenen:
# - Batch 1: 100 rows COMMIT
# - Batch 2: 100 rows COMMIT
# - Batch 3: 50 rows COMMIT
# Total: 250 inserted
```

### Test 2: Partial Failure (3. Batch Fail)

```python
# 250 invoice, batch_size=100
# invoice_225'te duplicate key hatası enjekte et

agent = IncomingInvoiceAgent()
agent.run()

# Beklenen:
# - Batch 1: 100 rows COMMIT ✅
# - Batch 2: 100 rows COMMIT ✅
# - Batch 3: ROLLBACK ❌ (duplicate key)
# Total: 200 inserted, 50 failed
```

### Test 3: İlk Batch Fail

```python
# 250 invoice, batch_size=100
# invoice_50'de hata

agent = IncomingInvoiceAgent()
agent.run()

# Beklenen:
# - Batch 1: ROLLBACK ❌ (error at row 50)
# - Agent stops (raise exception)
# Total: 0 inserted
```

**Not:** Batch fail olursa agent durur (raise exception), sonraki batch'ler işlenmez.

---

## 📈 Performance Impact

### Transaction Overhead

```
Batch Size | Transactions | Performance | Reliability
-----------|--------------|-------------|------------
10         | 25 (for 250) | Slower      | Very Safe
50         | 5 (for 250)  | Medium      | Safe
100        | 3 (for 250)  | Fast        | Balanced ✅
200        | 2 (for 250)  | Faster      | Risky
500        | 1 (for 250)  | Fastest     | Very Risky
```

**Öneri:** BATCH_SIZE=100 (balanced)

### Commit Latency

Her commit ~1-5ms (network + disk)
- Batch 100: ~3 commits → ~15ms overhead
- Batch 10: ~25 commits → ~125ms overhead

**100-200 arası optimal trade-off.**

---

## 🛡️ Veri Bütünlüğü Garantileri

### 1. Atomicity (Her Batch İçin)
✅ Batch içindeki tüm row'lar ya commit edilir ya rollback

### 2. Consistency
✅ Constraints (PK, UNIQUE, FK) her batch commit öncesi kontrol edilir

### 3. Isolation
✅ Batch transaction sırasında başka process'ler yarım veri görmez

### 4. Durability
✅ COMMIT sonrası veriler kalıcı (crash olsa bile)

### 5. Partial Success
✅ Batch 3 fail olsa bile Batch 1-2 güvende

---

## 🔍 Monitoring

### Database Tarafında

```sql
-- Active transactions
SELECT pid, state, query_start, query
FROM pg_stat_activity
WHERE state = 'active';

-- Transaction duration
SELECT NOW() - xact_start AS duration, *
FROM pg_stat_activity
WHERE xact_start IS NOT NULL;
```

### Application Logs

```
2026-02-10 14:30:22,123 - INFO - 💾 Inserting 250 new invoices (batches of 100)...
2026-02-10 14:30:22,156 - DEBUG - Batch 1/3 committed: 100 rows
2026-02-10 14:30:22,189 - DEBUG - Batch 2/3 committed: 100 rows
2026-02-10 14:30:22,222 - DEBUG - Batch 3/3 committed: 50 rows
2026-02-10 14:30:22,223 - INFO - ✅ Inserted: 250
```

---

## 🚨 Error Handling

### Retry Strategy

```python
# Agent level retry (3 attempts)
for attempt in range(3):
    try:
        agent.run()
        break
    except BatchFailureException:
        if attempt < 2:
            time.sleep(2 ** attempt)  # Exponential backoff
```

**Not:** Batch internal retry yok (fail olursa stop), ama agent level'da retry var.

---

## ✅ Sonuç

**Transaction-per-batch garantileri:**
- ✅ Yarım veri kalmaz
- ✅ Partial success mümkün
- ✅ ACID compliance
- ✅ Production-safe
- ✅ Performans dengesi (100-200 batch)

**Status:** ✅ IMPLEMENTED  
**Version:** 2.0.1  
**Date:** 2026-02-10
