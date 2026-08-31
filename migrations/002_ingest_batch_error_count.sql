-- 002: E5 报表闭合——ingest_batch 增加行级错误计数
-- 口径：inserted + duplicates + quarantined + rejected + extraction_failed + error_count = total
ALTER TABLE ingest_batch ADD COLUMN IF NOT EXISTS error_count INT NOT NULL DEFAULT 0;
