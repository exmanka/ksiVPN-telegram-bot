import asyncpg
from datetime import datetime, timedelta
from bot_init import POSTGRES_PW


conn: asyncpg.Connection


async def asyncpg_run() -> None:
    global conn
    conn = await asyncpg.connect(host='localhost', database='tgbot_postgres_db', user='postgres', password=POSTGRES_PW)

    if conn:
        print('DB is successfully connected!')

async def is_user_registered(telegram_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM clients
        WHERE telegram_id = $1;
        ''',
        telegram_id)

async def is_subscription_active(telegram_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM clients_subscriptions AS cs
        JOIN clients AS c
        ON cs.client_id = c.id
        WHERE c.telegram_id = $1
        AND cs.expiration_date > NOW();
        ''',
        telegram_id)

async def is_subscription_not_started(telegram_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM clients_subscriptions AS cs
        JOIN clients AS c
        ON cs.client_id = c.id
        WHERE c.telegram_id = $1
        AND cs.expiration_date < TIMESTAMP 'EPOCH' + INTERVAL '10 years';
        ''',
        telegram_id)

async def is_referral_promo(phrase: str) -> bool | None:
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM promocodes_ref
        WHERE phrase = $1;
        ''',
        phrase)

async def is_promo_ref(phrase: str) -> bool | None:
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM promocodes_ref
        WHERE phrase = $1;
        ''',
        phrase)

async def is_local_promo_accessible(client_id: int, local_promo_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM clients_promo_local
        WHERE promocode_id = $1
        AND accessible_client_id = $2;
        ''',
        local_promo_id, client_id)

async def is_local_promo_already_entered(client_id: int, local_promo_id: int) -> datetime | None:
    return await conn.fetchval(
        '''
        SELECT date_of_entry
        FROM clients_promo_local
        WHERE promocode_id = $1
        AND accessible_client_id = $2;
        ''',
        local_promo_id, client_id) 

async def is_global_promo_already_entered(client_id: int, global_promo_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM clients_promo_global
        WHERE client_id = $1
        AND promocode_id = $2;
        ''',
        client_id, global_promo_id) 

async def is_local_promo_valid(local_promo_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT bonus_time, TO_CHAR(bonus_time, 'FMDDD'), provided_sub_id
        FROM promocodes_local
        WHERE id = $1
        AND expiration_date > NOW();
        ''',
        local_promo_id)

async def is_global_promo_valid(global_promo_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT bonus_time, TO_CHAR(bonus_time, 'FMDDD')
        FROM promocodes_global
        WHERE id = $1
        AND expiration_date > NOW();
        ''',
        global_promo_id)

async def get_clientID_by_telegramID(telegram_id: int) -> int | None:
    return await conn.fetchval('''
        SELECT id
        FROM clients
        WHERE telegram_id = $1;
        ''',
        telegram_id)

async def get_clientID_by_username(username: str) -> int | None:
    return await conn.fetchval(
        '''
        SELECT id
        FROM clients
        WHERE username = $1;
        ''',
        username)

async def get_telegramID_by_clientID(client_id: str) -> int | None:
    return await conn.fetchval(
        '''
        SELECT telegram_id
        FROM clients
        WHERE id = $1;
        ''',
        client_id)

async def get_telegramID_by_username(username: str) -> int | None:
    return await conn.fetchval(
        '''
        SELECT telegram_id
        FROM clients
        WHERE username = $1;
        ''',
        username)

async def get_paymentIDs(client_id: int) -> list[asyncpg.Record]:
    '''
    Return all clients's created payments id for all the time
    '''
        
    return await conn.fetch(
        '''
        SELECT id
        FROM payments
        WHERE client_id = $1
        ORDER BY date_of_initiation DESC
        ''',
        client_id)

async def get_paymentIDs_last(client_id: int, minutes: int) -> list[asyncpg.Record]:
    '''
    Return all clients's created payments id for the last n minutes
    '''

    return await conn.fetch(
        '''
        SELECT id
        FROM payments
        WHERE client_id = $1
        AND date_of_initiation > CURRENT_TIMESTAMP - make_interval(mins => $2)
        ORDER BY date_of_initiation DESC;
        ''',
        client_id, minutes)

async def get_client_info_by_telegramID(telegram_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT id, name, surname, username, register_date, TO_CHAR(register_date, 'FMDD TMMonth YYYY в HH24:MI'), used_ref_promo_id, bot_chatgpt_mode
        FROM clients
        WHERE telegram_id = $1;
        ''',
        telegram_id)

async def get_client_info_by_clientID(client_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT name, surname, username, telegram_id, register_date, TO_CHAR(register_date, 'FMDD TMMonth YYYY в HH24:MI'), used_ref_promo_id, bot_chatgpt_mode
        FROM clients
        WHERE id = $1;
        ''',
        client_id)

async def get_subscription_info_by_clientID(client_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT sub.id, sub.title, sub.description, sub.price
        FROM clients_subscriptions AS clients_sub
        JOIN subscriptions AS sub
        ON sub.id = clients_sub.sub_id
        WHERE clients_sub.client_id = $1;
        ''',
        client_id)

async def get_subscription_info_by_subID(subscription_id) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT id, title, description, price
        FROM subscriptions
        WHERE id = $1;
        ''',
        subscription_id)

async def get_subscription_expiration_date(telegram_id: int) -> str | None:
    return await conn.fetchval(
        '''
        SELECT TO_CHAR(cs.expiration_date, 'FMDD TMMonth YYYY в HH24:MI')
        FROM clients_subscriptions AS cs
        JOIN clients AS c
        ON cs.client_id = c.id
        WHERE c.telegram_id = $1;
        ''',
        telegram_id)

async def get_payments_successful_info(client_id: int) -> list[asyncpg.Record]:
    '''
    Return user's created payments info for all the time
    '''

    return await conn.fetch(
        '''
        SELECT p.id, s.title, p.price, p.months_number, TO_CHAR(p.date_of_initiation, 'FMDD TMMonth YYYY в HH24:MI')
        FROM payments AS p
        JOIN subscriptions AS s
        ON p.sub_id = s.id
        WHERE p.client_id = $1
        AND p.is_successful = TRUE;
        ''',
        client_id)

async def get_configurations_info(client_id: int) -> list[asyncpg.Record]:
    return await conn.fetch(
        '''
        SELECT c.file_type, TO_CHAR(c.date_of_receipt, 'FMDD TMMonth YYYY в HH24:MI'), c.os, cl.is_chatgpt_available, cp.name, cl.country, cl.city, cl.bandwidth, cl.ping, c.telegram_file_id
        FROM configurations AS c
        JOIN configurations_protocols AS cp ON c.protocol_id = cp.id
        JOIN configurations_locations AS cl ON c.location_id = cl.id
        WHERE c.client_id = $1
        ORDER BY c.date_of_receipt;
        ''',
        client_id)

async def get_configurations_number(client_id: int) -> int | None:
    return await conn.fetchval(
        '''
        SELECT COUNT(*) FROM configurations
        WHERE client_id = $1;
        ''',
        client_id)

async def get_payment_status(payment_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        SELECT is_successful
        FROM payments
        WHERE id = $1;
        ''',
        payment_id)

async def get_payment_months_number(payment_id: int) -> int | None:
    return await conn.fetchval(
        '''
        SELECT months_number
        FROM payments
        WHERE id = $1;
        ''',
        payment_id)

async def get_payment_last_message_id(client_id: int) -> asyncpg.Record | None:
    '''
    Return last user's created payment's telegram message id
    '''

    return await conn.fetchval(
        '''
        SELECT telegram_message_id
        FROM payments
        WHERE client_id = $1
        ORDER BY date_of_initiation DESC
        LIMIT 1;
        ''',
        client_id)

async def get_referral_promocode(telegram_id: int) -> str | None:
    return await conn.fetchval(
        '''
        SELECT pf.phrase
        FROM clients AS c
        JOIN promocodes_ref AS pf
        ON c.id = pf.client_creator_id
        WHERE c.telegram_id = $1;
        ''',
        telegram_id)    

async def get_invited_by_client_info(telegram_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT cc.name, cc.username
        FROM clients AS c
        JOIN promocodes_ref AS pr
        ON c.used_ref_promo_id = pr.id
        JOIN clients AS cc
        ON pr.client_creator_id = cc.id
        WHERE c.telegram_id = $1;
        ''',
        telegram_id)    

async def get_invited_users_list(telegram_id: int) -> list[asyncpg.Record]:
    return await conn.fetch(
        '''
        SELECT c.name, c.username
        FROM clients AS c
        JOIN promocodes_ref AS pr
        ON c.used_ref_promo_id = pr.id
        JOIN clients AS cc
        ON pr.client_creator_id = cc.id
        WHERE cc.telegram_id = $1;
        ''',
        telegram_id) 

async def get_local_promo_id(phrase: str) -> int | None:
    return await conn.fetchval(
        '''
        SELECT id
        FROM promocodes_local
        WHERE phrase = $1;
        ''',
        phrase) 

async def get_local_promo_info(phrase: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT id, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI'), bonus_time, TO_CHAR(bonus_time, 'FMDDD'), provided_sub_id
        FROM promocodes_local
        WHERE phrase = $1;
        ''',
        phrase)

async def get_global_promo_info(phrase: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT id, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI'), bonus_time, TO_CHAR(bonus_time, 'FMDDD')
        FROM promocodes_global
        WHERE phrase = $1;
        ''',
        phrase)

async def get_global_promo_id(phrase: int) -> int | None:
    return await conn.fetchval(
        '''
        SELECT id
        FROM promocodes_global
        WHERE phrase = $1;
        ''',
        phrase) 

async def get_client_entered_promos(client_id: int) -> tuple[asyncpg.Record | None]:
    async with conn.transaction():

        # referral promocodes
        promos_ref = await conn.fetchrow(
            '''
            SELECT pf.phrase, cc.name
            FROM clients AS c
            JOIN promocodes_ref AS pf
            ON c.used_ref_promo_id = pf.id
            JOIN clients AS cc
            ON pf.client_creator_id = cc.id
            WHERE c.id = $1;
            ''',
            client_id)

        # global promocodes
        promos_global = await conn.fetch(
            '''
            SELECT pg.phrase, TO_CHAR(pg.bonus_time, 'FMDDD'), TO_CHAR(cpg.date_of_entry, 'FMDD TMMonth YYYY в HH24:MI')
            FROM clients_promo_global AS cpg
            JOIN promocodes_global AS pg
            ON cpg.promocode_id = pg.id
            WHERE cpg.client_id = $1;
            ''',
            client_id)
        
        # local promocodes
        promos_local = await conn.fetch(
            '''
            SELECT pl.phrase, TO_CHAR(pl.bonus_time, 'FMDDD'), TO_CHAR(cpl.date_of_entry, 'FMDD TMMonth YYYY в HH24:MI')
            FROM clients_promo_local AS cpl
            JOIN promocodes_local AS pl
            ON cpl.promocode_id = pl.id
            WHERE cpl.accessible_client_id = $1
            AND cpl.date_of_entry IS NOT NULL;
            ''',
            client_id)

        return (promos_ref, promos_global, promos_local)

async def get_clients_telegram_ids() -> list[asyncpg.Record]:
    return await conn.fetch(
        '''
        SELECT telegram_id
        FROM clients;
        ''')

async def get_notifications_info(client_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT sub_expiration_in_1d, sub_expiration_in_3d, sub_expiration_in_7d
        FROM sub_notifications_settings
        WHERE client_id = $1;
        ''',
        client_id)

async def get_notifications_status() -> list[asyncpg.Record]:
    return await conn.fetch(
        '''
        SELECT c.telegram_id,
        TO_CHAR(cs.expiration_date, 'FMDD TMMonth в HH24:MI') AS subscription_expiration_date,
        CURRENT_TIMESTAMP <= cs.expiration_date AND cs.expiration_date < CURRENT_TIMESTAMP + INTERVAL '30 minutes' AS is_subscription_expiration_now,
        sns.sub_expiration_in_1d AND CURRENT_TIMESTAMP + INTERVAL '1 days' <= cs.expiration_date AND cs.expiration_date < CURRENT_TIMESTAMP + INTERVAL '1 days 30 minutes' AS is_subscription_expiration_in_1d,
        sns.sub_expiration_in_3d AND CURRENT_TIMESTAMP + INTERVAL '3 days' <= cs.expiration_date AND cs.expiration_date < CURRENT_TIMESTAMP + INTERVAL '3 days 30 minutes' AS is_subscription_expiration_in_3d,
        sns.sub_expiration_in_7d AND CURRENT_TIMESTAMP + INTERVAL '7 days' <= cs.expiration_date AND cs.expiration_date < CURRENT_TIMESTAMP + INTERVAL '7 days 30 minutes' AS is_subscription_expiration_in_7d
        FROM clients AS c
        JOIN sub_notifications_settings AS sns
        ON c.id = sns.client_id
        JOIN clients_subscriptions AS cs
        ON sns.client_id = cs.client_id;
        ''')

async def get_chatgpt_mode_status(telegram_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        SELECT bot_chatgpt_mode
        FROM clients
        WHERE telegram_id = $1;
        ''',
        telegram_id)

async def get_promo_ref_info(phrase: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT id, client_creator_id, provided_sub_id, bonus_time
        FROM promocodes_ref
        WHERE phrase = $1;
        ''',
        phrase)

async def get_promo_ref_info_parsed(phrase: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT id, client_creator_id, provided_sub_id, TO_CHAR(bonus_time, 'FMDDD')
        FROM promocodes_ref
        WHERE phrase = $1;
        ''',
        phrase)

async def get_ref_promo_info_by_clientCreatorID(client_creator_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT id, phrase, provided_sub_id, bonus_time, TO_CHAR(bonus_time, 'FMDDD')
        FROM promocodes_ref
        WHERE client_creator_id = $1;
        ''',
        client_creator_id)

async def get_ref_promo_info(ref_promo_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT phrase, client_creator_id, provided_sub_id, bonus_time
        FROM promocodes_ref
        WHERE id = $1;
        ''',
        ref_promo_id)

async def get_clientsSubscriptions_info_by_clientID(client_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT sub_id, paid_months_counter, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI')
        FROM clients_subscriptions
        WHERE client_id = $1;
        ''',
        client_id)

async def update_chatgpt_mode(telegram_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        UPDATE clients
        SET bot_chatgpt_mode = NOT bot_chatgpt_mode
        WHERE telegram_id = $1
        RETURNING bot_chatgpt_mode;
        ''',
        telegram_id)
    
async def insert_client(name: str,
                  telegram_id: int,
                  surname: str | None = None,
                  username: str | None = None,
                  used_ref_promo_id: int | None = None,
                  provided_sub_id: int | None = None,
                  bonus_time: timedelta | None = None,
                  ) -> None:
    
    if username:
        username = '@' + username
    
    if provided_sub_id is None:
        provided_sub_id = 1 # добавить глобальную константу

    if bonus_time is None:
        bonus_time = timedelta()    # zero days

    provided_ref_sub_id = provided_sub_id
    if provided_sub_id in [3, 4]: # добавить глобальную константу
        provided_ref_sub_id = 1 # добавить глобальную константу

    async with conn.transaction():
        client_id: int = await conn.fetchval(
            '''
            INSERT INTO clients (name, surname, username, telegram_id, used_ref_promo_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id;
            ''',
            name, surname, username, telegram_id, used_ref_promo_id)
        
        await conn.execute(
            '''
            INSERT INTO clients_subscriptions (client_id, sub_id, expiration_date)
            VALUES ($1, $2, TIMESTAMP 'EPOCH' + $3);
            ''',
            client_id, provided_sub_id, bonus_time)
        
        await conn.execute(
            '''
            INSERT INTO promocodes_ref (client_creator_id, provided_sub_id)
            VALUES ($1, $2);
            ''',
            client_id, provided_ref_sub_id)
        
        await conn.execute(
            '''
            INSERT INTO sub_notifications_settings (client_id)
            VALUES ($1);
            ''',
            client_id)

async def insert_configuration(client_id: int,
                         protocol_id: int,
                         location_id: int,
                         os: str,
                         file_type: str,
                         telegram_file_id: str) -> None:
    
    async with conn.transaction():
        await conn.execute(
            '''
            INSERT INTO configurations (client_id, protocol_id, location_id, os, file_type, telegram_file_id)
            VALUES ($1, $2, $3, $4, $5, $6);
            ''',
            client_id, protocol_id, location_id, os, file_type, telegram_file_id)
        
        # execute only for new clients
        await conn.execute(
            '''
            UPDATE clients_subscriptions
            SET expiration_date = NOW() + (expiration_date - 'EPOCH')
            WHERE client_id = $1
            AND expiration_date < TIMESTAMP 'EPOCH' + INTERVAL '10 years';
            ''',
            client_id)

async def insert_payment(client_id: int, sub_id: int, price: float, months_number: int) -> int | None:
    return await conn.fetchval(
        '''
        INSERT INTO payments (client_id, sub_id, price, months_number)
        VALUES($1, $2, $3, $4)
        RETURNING id;
        ''',
        client_id, sub_id, price, months_number)

async def insert_client_entered_local_promo(client_id: int, local_promo_id: int, local_promo_bonus_time) -> None:
    async with conn.transaction():
        await conn.execute(
            '''
            UPDATE clients_promo_local
            SET date_of_entry = NOW()
            WHERE promocode_id = $1
            AND accessible_client_id = $2;
            ''',
            local_promo_id, client_id)
        
        await conn.execute(
            '''
            UPDATE clients_subscriptions
            SET expiration_date = expiration_date + $1
            WHERE client_id = $2;
            ''',
            local_promo_bonus_time, client_id)

async def insert_client_entered_global_promo(client_id: int, global_promo_id: int, global_promo_bonus_time) -> None:
    async with conn.transaction():
        await conn.execute(
            '''
            INSERT INTO clients_promo_global (client_id, promocode_id)
            VALUES($1, $2);
            ''',
            client_id, global_promo_id)
        
        await conn.execute(
            '''
            UPDATE clients_subscriptions
            SET expiration_date = expiration_date + $1
            WHERE client_id = $2;
            ''',
            global_promo_bonus_time, client_id)
    
async def update_payment_successful(payment_id: int, client_id: int, paid_months: int) -> None:
    async with conn.transaction():
        await conn.execute(
            '''
            UPDATE payments
            SET is_successful = TRUE
            WHERE id = $1;
            ''',
            payment_id)
        
        await conn.execute(
            '''
            UPDATE clients_subscriptions
            SET paid_months_counter = paid_months_counter + $1,
            expiration_date = expiration_date + make_interval(months => $2)
            WHERE client_id = $3;
            ''',
            paid_months, paid_months, client_id)

async def update_payment_telegram_message_id(payment_id: int, telegram_message_id: int) -> None:
    await conn.execute(
        '''
        UPDATE payments
        SET telegram_message_id = $1
        WHERE id = $2;
        ''',
        telegram_message_id, payment_id)

async def update_client_subscription(client_id: int, new_sub_id: int) -> None:
    await conn.execute(
        '''
        UPDATE clients_subscriptions
        SET sub_id = $1
        WHERE client_id = $2
        ''',
        new_sub_id, client_id)
    
async def update_notifications_1d(client_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        UPDATE sub_notifications_settings
        SET sub_expiration_in_1d = NOT sub_expiration_in_1d
        WHERE client_id = $1
        RETURNING sub_expiration_in_1d;
        ''',
        client_id)

async def update_notifications_3d(client_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        UPDATE sub_notifications_settings
        SET sub_expiration_in_3d = NOT sub_expiration_in_3d
        WHERE client_id = $1
        RETURNING sub_expiration_in_3d;
        ''',
        client_id)

async def update_notifications_7d(client_id: int) -> bool | None:
    return await conn.fetchval(
        '''
        UPDATE sub_notifications_settings
        SET sub_expiration_in_7d = NOT sub_expiration_in_7d
        WHERE client_id = $1
        RETURNING sub_expiration_in_7d;
        ''',
        client_id)

async def add_subscription_time(client_id: int, days: int) -> None:
    await conn.execute(
        '''
        UPDATE clients_subscriptions
        SET expiration_date = expiration_date + make_interval(days => $1)
        WHERE client_id = $2;
        ''',
        days, client_id)