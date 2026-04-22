CREATE TABLE clients_remnawave (
	client_id INT UNIQUE NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	remnawave_uuid UUID UNIQUE NOT NULL,
	remnawave_subscription_url TEXT NOT NULL,
	created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX clients_remnawave_client_id_idx
ON clients_remnawave(client_id);
