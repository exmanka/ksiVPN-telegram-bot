BEGIN;

-- Убрать значение 'photo' из fileTypeEnum.
-- Postgres не умеет удалять значения из enum, поэтому пересоздаём тип.
-- Перед этим убеждаемся, что строк с file_type = 'photo' не осталось —
-- их должен был сконвертировать scripts/convert_photo_configs_to_link.py.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM configurations WHERE file_type = 'photo') THEN
        RAISE EXCEPTION 'configurations still contains rows with file_type = ''photo'' — run scripts/convert_photo_configs_to_link.py first';
    END IF;
END $$;

ALTER TYPE fileTypeEnum RENAME TO filetypeenum_old;
CREATE TYPE fileTypeEnum AS ENUM ('document', 'link');
ALTER TABLE configurations
    ALTER COLUMN file_type TYPE fileTypeEnum USING file_type::text::fileTypeEnum;
DROP TYPE filetypeenum_old;

COMMIT;
