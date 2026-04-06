BEGIN;

-- Переименовать столбец telegram_file_id -> link.
-- В этом столбце де-факто хранятся как telegram file_id, так и vless:// ссылки,
-- поэтому name telegram_file_id вводит в заблуждение. UNIQUE-индекс и NOT NULL
-- переедут вместе с колонкой автоматически.
ALTER TABLE configurations RENAME COLUMN telegram_file_id TO link;

COMMIT;
