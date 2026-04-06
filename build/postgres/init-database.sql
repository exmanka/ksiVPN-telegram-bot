CREATE TABLE clients (
	id SERIAL PRIMARY KEY,
	name VARCHAR(64) NOT NULL,
	surname VARCHAR(64),
	username VARCHAR(33),
	telegram_id BIGINT NOT NULL UNIQUE,
	register_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	used_ref_promo_id INT
);
INSERT INTO clients (name, surname, username, telegram_id, register_date)
VALUES('Михаил','Ким', '@exmanka', 467321357, 'EPOCH');


CREATE INDEX clients_idx
ON clients(telegram_id);


CREATE TABLE subscriptions (
	id SMALLSERIAL PRIMARY KEY,
	price INT NOT NULL,
	title VARCHAR(32) NOT NULL,
	description VARCHAR(128),
	max_configurations SMALLINT NOT NULL DEFAULT 5
);
INSERT INTO subscriptions (price, title, description, max_configurations)
VALUES(200, 'Standard subscription', 'Here is subscription description.', 3);


CREATE TABLE clients_subscriptions (
	client_id INT UNIQUE NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	sub_id SMALLINT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
	paid_months_counter INT NOT NULL DEFAULT 0,
	expiration_date TIMESTAMP NOT NULL
);
INSERT INTO clients_subscriptions(client_id, sub_id, paid_months_counter, expiration_date)
VALUES(1, 1, 10, TIMESTAMP '2030-01-01 00:00');


CREATE OR REPLACE FUNCTION create_ref_promocode() RETURNS text
AS $$
DECLARE
    ref_promo text;
    done boolean;
BEGIN
    done := false;
    WHILE NOT done LOOP
        ref_promo := 'REF'||upper(substring(md5(''||now()::text||random()::text) for 7));
        done := NOT exists(SELECT 1 FROM promocodes_ref WHERE phrase=ref_promo);
    END LOOP;
    RETURN ref_promo;
END;
$$ LANGUAGE PLPGSQL VOLATILE;


CREATE TABLE promocodes_ref (
	id SERIAL PRIMARY KEY,
	phrase VARCHAR(10) UNIQUE NOT NULL DEFAULT create_ref_promocode(),
	client_creator_id INT UNIQUE NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	provided_sub_id SMALLINT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
	bonus_time INTERVAL NOT NULL DEFAULT '1 month'
);
INSERT INTO promocodes_ref(client_creator_id, provided_sub_id)
VALUES(1, 1);


CREATE TABLE promocodes_global (
	id SMALLSERIAL PRIMARY KEY,
	phrase VARCHAR(32) UNIQUE NOT NULL,
	expiration_date TIMESTAMP NOT NULL,
	remaining_activations INT NOT NULL,
	bonus_time INTERVAL NOT NULL
);
INSERT INTO promocodes_global(phrase, expiration_date, remaining_activations, bonus_time)
VALUES('GLOBAL_PROMO_EXAMPLE', TIMESTAMP '2025-01-01', 3, INTERVAL '1 month');


CREATE TABLE clients_promo_global (
	client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	promocode_id SMALLINT NOT NULL REFERENCES promocodes_global(id) ON DELETE CASCADE,
	date_of_entry TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE promocodes_local (
	id SMALLSERIAL PRIMARY KEY,
	phrase VARCHAR(32) UNIQUE NOT NULL,
	expiration_date TIMESTAMP NOT NULL,
	provided_sub_id SMALLINT REFERENCES subscriptions(id) ON DELETE CASCADE,
	bonus_time INTERVAL NOT NULL
);
INSERT INTO promocodes_local(phrase, expiration_date, bonus_time)
VALUES('LOCAL_PROMO_EXAMPLE', TIMESTAMP '2025-01-01', INTERVAL '1 month');


CREATE TABLE clients_promo_local (
	accessible_client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	promocode_id SMALLINT NOT NULL REFERENCES promocodes_local(id) ON DELETE CASCADE,
	date_of_entry TIMESTAMP DEFAULT NULL
);
INSERT INTO clients_promo_local(accessible_client_id, promocode_id)
VALUES(1, 1);


CREATE TABLE configurations_protocols (
	id SMALLSERIAL PRIMARY KEY,
	alias VARCHAR(16) UNIQUE NOT NULL,
	name VARCHAR(32) NOT NULL UNIQUE,
	description VARCHAR(64) NOT NULL
);
INSERT INTO configurations_protocols(alias, name, description)
VALUES('x', 'XRay VLESS XTLS-Reality', 'Here is protocol description. Still love WireGuard!');


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
INSERT INTO servers(id, alias, name, country, city, description, bandwidth, ping, available_services)
VALUES('ksivpn-netherlands-1p', 'nl1', '🇳🇱 Netherlands #1', 'Country of your awesome server', 'City of your awesome server', 'Here is your awesome server description.', 1000, 30, ARRAY['Instagram', 'YouTube', 'ChatGPT']);


CREATE TYPE osEnum AS ENUM ('Android', 'IOS', 'Windows', 'macOS', 'Linux');
CREATE TYPE fileTypeEnum AS ENUM('photo', 'document', 'link');
CREATE TABLE configurations (
	id SERIAL PRIMARY KEY,
	client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	protocol_id SMALLINT NOT NULL REFERENCES configurations_protocols(id) ON DELETE CASCADE,
	server_id VARCHAR(64) NOT NULL REFERENCES servers(id) ON UPDATE CASCADE ON DELETE CASCADE,
	os osEnum NOT NULL,
	file_type fileTypeEnum NOT NULL,
	telegram_file_id VARCHAR(512) UNIQUE NOT NULL,
	date_of_receipt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO configurations(client_id, protocol_id, server_id, os, file_type, telegram_file_id, date_of_receipt)
VALUES(1, 1, 'ksivpn-netherlands-1p', 'Android', 'link', 'vless://link_or_telegram_file_id_here', 'EPOCH');


CREATE TABLE server_inbounds (
	id SMALLSERIAL PRIMARY KEY,
	server_id VARCHAR(64) NOT NULL REFERENCES servers(id) ON UPDATE CASCADE ON DELETE CASCADE,
	protocol_id SMALLINT NOT NULL REFERENCES configurations_protocols(id) ON DELETE CASCADE,
	inbound_id INT NOT NULL,
	UNIQUE (server_id, protocol_id)
);


CREATE TABLE payments (
	id BIGSERIAL PRIMARY KEY,
	client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	sub_id SMALLINT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
	price DECIMAL(6, 2) NOT NULL,
	months_number SMALLINT NOT NULL,
	is_successful BOOLEAN NOT NULL DEFAULT FALSE,
	telegram_message_id INT,
	date_of_initiation TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE settings (
	client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	sub_expiration_in_1d BOOLEAN NOT NULL DEFAULT TRUE,
	sub_expiration_in_3d BOOLEAN NOT NULL DEFAULT TRUE,
	sub_expiration_in_7d BOOLEAN NOT NULL DEFAULT TRUE,
	chatgpt_mode BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO settings(client_id)
VALUES(1);