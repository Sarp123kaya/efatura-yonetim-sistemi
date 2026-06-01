-- Aynı çek numarası tek kayıt: önce mükerrerleri temizleyin (panel: Çekler → Mükerrerleri Birleştir)
-- veya: python3 -c "from backend.core.check_dedupe import dedupe_checks_by_check_no; print(dedupe_checks_by_check_no())"

CREATE UNIQUE INDEX IF NOT EXISTS uq_checks_check_no_trim
ON checks (TRIM(check_no))
WHERE TRIM(check_no) <> '';
