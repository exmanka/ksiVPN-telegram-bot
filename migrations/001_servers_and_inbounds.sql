BEGIN;

-- 1. Таблица servers (замена configurations_locations)
CREATE TABLE servers (
    id VARCHAR(64) PRIMARY KEY,
    alias VARCHAR(16) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    country VARCHAR(32) NOT NULL,
    city VARCHAR(32) NOT NULL,
    description VARCHAR(256) NOT NULL,
    bandwidth SMALLINT NOT NULL,
    ping SMALLINT NOT NULL,
    available_services TEXT[] NOT NULL DEFAULT '{}',
    api_url TEXT DEFAULT NULL,
    api_login TEXT DEFAULT NULL,
    api_password TEXT DEFAULT NULL
);

-- 2. Мигрировать данные (hostname'ы, alias'ы и имена уточнить перед применением!)
INSERT INTO servers (id, alias, name, country, city, description, bandwidth, ping, available_services)
SELECT
    CASE old.id
        WHEN 1 THEN 'ksivpn-netherlands-2p'
        WHEN 2 THEN 'ksivpn-latvia-1p'
        WHEN 3 THEN 'ksivpn-germany-0p'
        WHEN 4 THEN 'ksivpn-usa-1p'
    END,
    CASE old.id
        WHEN 1 THEN 'nl02'
        WHEN 2 THEN 'lv02'
        WHEN 3 THEN 'de00'
        WHEN 4 THEN 'us01'
    END,
    CASE old.id
        WHEN 1 THEN '🇳🇱 Нидерланды #2'
        WHEN 2 THEN '🇱🇻 Латвия #1'
        WHEN 3 THEN '🇩🇪 Германия #0'
        WHEN 4 THEN '🇺🇸 США #1'
    END,
    old.country, old.city, old.description, old.bandwidth, old.ping,
    CASE WHEN old.is_chatgpt_available THEN ARRAY['ChatGPT'] ELSE '{}' END
FROM configurations_locations AS old;

-- 3. FK в configurations: location_id → server_id
ALTER TABLE configurations ADD COLUMN server_id VARCHAR(64);
UPDATE configurations SET server_id = CASE location_id
    WHEN 1 THEN 'ksivpn-netherlands-2p'
    WHEN 2 THEN 'ksivpn-latvia-1p'
    WHEN 3 THEN 'ksivpn-germany-0p'
    WHEN 4 THEN 'ksivpn-usa-1p'
END;
ALTER TABLE configurations ALTER COLUMN server_id SET NOT NULL;
ALTER TABLE configurations ADD CONSTRAINT configurations_server_id_fkey
    FOREIGN KEY (server_id) REFERENCES servers(id) ON UPDATE CASCADE ON DELETE CASCADE;
ALTER TABLE configurations DROP COLUMN location_id;
DROP TABLE configurations_locations;

-- 4. Добавить alias в configurations_protocols (уточнить alias'ы перед применением!)
ALTER TABLE configurations_protocols ADD COLUMN alias VARCHAR(16) UNIQUE;
UPDATE configurations_protocols SET alias = CASE id
    WHEN 1 THEN 'wg'
    WHEN 2 THEN 'x'
    WHEN 3 THEN 'ss'
END;
ALTER TABLE configurations_protocols ALTER COLUMN alias SET NOT NULL;

-- 5. Таблица server_inbounds
CREATE TABLE server_inbounds (
    id SMALLSERIAL PRIMARY KEY,
    server_id VARCHAR(64) NOT NULL REFERENCES servers(id) ON UPDATE CASCADE ON DELETE CASCADE,
    protocol_id SMALLINT NOT NULL REFERENCES configurations_protocols(id) ON DELETE CASCADE,
    inbound_id INT NOT NULL,
    UNIQUE (server_id, protocol_id)
);

-- 6. Вставка дополнительных серверов в servers
INSERT INTO public.servers (id, alias, name, country, city, description, bandwidth, ping, available_services)
VALUES ('ksivpn-germany-1p', 'de01', '🇩🇪 Германия #1', 'Германия', 'Франкфурт', '—', 10000, 50, ARRAY['Telegram', 'WhatsApp', 'Instagram', 'YouTube', 'TikTok', 'ChatGPT', 'Netflix']);
INSERT INTO public.servers (id, alias, name, country, city, description, bandwidth, ping, available_services)
VALUES ('ksivpn-germany-2p', 'de02', '🇩🇪 Германия #2', 'Германия', 'Франкфурт', '—', 10000, 50, ARRAY['Telegram', 'WhatsApp', 'Instagram', 'YouTube', 'TikTok', 'ChatGPT', 'Netflix']);
INSERT INTO public.servers (id, alias, name, country, city, description, bandwidth, ping, available_services)
VALUES ('ksivpn-germany-3p', 'de03', '🇩🇪 Германия #3', 'Германия', 'Франкфурт', '—', 2000, 50, ARRAY['Telegram', 'WhatsApp', 'Instagram', 'YouTube', 'TikTok', 'ChatGPT', 'Netflix', 'Gemini', 'Reddit Guest']);
INSERT INTO public.servers (id, alias, name, country, city, description, bandwidth, ping, available_services)
VALUES ('ksivpn-germany-4p', 'de04', '🇩🇪 Германия #4', 'Германия', 'Франкфурт', '—', 2000, 50, ARRAY['Telegram', 'WhatsApp', 'Instagram', 'YouTube', 'TikTok', 'ChatGPT', 'Netflix', 'Gemini', 'Reddit Guest']);
INSERT INTO public.servers (id, alias, name, country, city, description, bandwidth, ping, available_services)
VALUES ('ksivpn-spain-1p', 'es01', '🇪🇸 Испания #1', 'Испания', 'Мадрид', '—', 500, 70, ARRAY['Telegram', 'WhatsApp', 'Instagram', 'YouTube', 'TikTok', 'ChatGPT', 'Netflix']);

UPDATE public.servers
SET available_services = ARRAY['Telegram', 'WhatsApp', 'Instagram', 'YouTube', 'TikTok', 'ChatGPT', 'Netflix']
WHERE id IN ('ksivpn-germany-0p', 'ksivpn-netherlands-2p', 'ksivpn-usa-1p', 'ksivpn-spain-1p');

UPDATE public.servers
SET available_services = ARRAY['Telegram', 'WhatsApp', 'Instagram', 'YouTube', 'TikTok', 'ChatGPT', 'Netflix', 'Gemini', 'Reddit Guest']
WHERE id = 'ksivpn-latvia-1p';

COMMIT;
