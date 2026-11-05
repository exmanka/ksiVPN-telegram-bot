# Database layer

All SQL lives here — one module per domain. Callers import modules, not functions:
`from src.database import payments_db` → `await payments_db.claim_payment_finalize(...)`.

| Module | Tables / responsibility |
|---|---|
| `connection.py` | asyncpg pool (`asyncpg_run`, `asyncpg_close`, `acquire`) and the dedicated LISTEN connection (`create_listener_connection`) |
| `clients_db.py` | `clients`: lookups by telegram_id / client_id, registration (`insert_client`) |
| `subscriptions_db.py` | `subscriptions`, `clients_subscriptions`: subscription types, state, expiration date |
| `promocodes_db.py` | `promocodes_ref`, `promocodes_local`, `promocodes_global` and entered-promo tables; referral graph |
| `payments_db.py` | `payments`: creation, idempotent finalize (`claim_payment_finalize`), provider state, history, stats |
| `client_settings_db.py` | `settings`: notification toggles, ChatGPT mode |
| `subscription_events_db.py` | `subscription_events`: consumer side of the trigger-owned expiration schedule |
| `remnawave_db.py` | `clients_remnawave`, `remnawave_internal_squads` |

Rules:

- Parameterized SQL only.
- A transaction that spans tables lives in the module of the domain that starts it.
- Reach the pool only through `connection.acquire()`; never import the pool object itself.
