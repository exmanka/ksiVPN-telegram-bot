import asyncpg
import datetime
import logging
from decimal import Decimal
from bot_init import POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB


logger = logging.getLogger(__name__)
conn: asyncpg.Connection


async def asyncpg_run() -> None:
    """Initialize asyncpg connection."""
    global conn
    conn = await asyncpg.connect(host='app-db', database=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)

    if conn:
        logger.info('Database has been successfully connected!')


async def asyncpg_close() -> None:
    """Close asyncpg connection."""
    await conn.close()

    if conn.is_closed():
        logger.info('Database has been successfully disconnected!')


async def is_user_registered(telegram_id: int) -> bool | None:
    """Check telegram_id exists in DB."""
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM clients
        WHERE telegram_id = $1;
        ''',
        telegram_id)


async def is_subscription_active(telegram_id: int) -> bool | None:
    """Check subcription's expiration date of client with specified telegram_id. Return TRUE if acive, None if inactive."""
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
    """Check admin hasn't send first client's configuration to activate subscription.

    Actually check subscription's expiration date before 1980 year (peculiarity of implementation of database architecture).
    """
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


async def is_subscription_blank(telegram_id: int) -> bool | None:
    """Check subscription was never paid or renewed.
    
    Actually check subscription's expiration date is 'EPOCH' = 1970-01-01 00:00 (peculiarity of implementation of database architecture)."""
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM clients_subscriptions AS cs
        JOIN clients AS c
        ON cs.client_id = c.id
        WHERE c.telegram_id = $1
        AND cs.expiration_date = TIMESTAMP 'EPOCH';
        ''',
        telegram_id)


async def is_subscription_free(telegram_id: int) -> bool | None:
    """Check client has free subscription."""
    return await conn.fetchval(
        '''
        SELECT
        CASE
            WHEN sub.price = 0 THEN TRUE
            ELSE FALSE
        END
        FROM subscriptions AS sub
        JOIN clients_subscriptions AS cs
        ON sub.id = cs.sub_id
        JOIN clients AS c
        ON cs.client_id = c.id
        WHERE c.telegram_id = $1;
        ''',
        telegram_id)


async def is_referral_promo(phrase: str) -> bool | None:
    """Check phrase is refferal promocode existing in DB."""
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM promocodes_ref
        WHERE phrase = $1;
        ''',
        phrase)


async def is_local_promo_accessible(client_id: int, local_promo_id: int) -> bool | None:
    """Check local promocode is available for client."""
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM clients_promo_local
        WHERE promocode_id = $1
        AND accessible_client_id = $2;
        ''',
        local_promo_id, client_id)


async def is_local_promo_already_entered(client_id: int, local_promo_id: int) -> bool | None:
    """Check local promocode was already entered by client before."""
    return await conn.fetchval(
        '''
        SELECT
        CASE
            WHEN date_of_entry IS NOT NULL THEN TRUE
        END
        FROM clients_promo_local
        WHERE promocode_id = $1
        AND accessible_client_id = $2;
        ''',
        local_promo_id, client_id)


async def is_local_promo_valid(local_promo_id: int) -> bool | None:
    """Check local promocode didn't expire."""
    return await conn.fetchrow(
        '''
        SELECT TRUE
        FROM promocodes_local
        WHERE id = $1
        AND expiration_date > NOW();
        ''',
        local_promo_id)


async def is_global_promo_has_remaining_activations(global_promo_id: int) -> bool | None:
    """Check global promocode was entered less than specified number of times."""
    return await conn.fetchval(
        '''
        SELECT
        CASE
            WHEN remaining_activations > 0 THEN TRUE
            ELSE FALSE
        END
        FROM promocodes_global
        WHERE id = $1;
        ''',
        global_promo_id
    )


async def is_global_promo_already_entered(client_id: int, global_promo_id: int) -> bool | None:
    """Check global promocode was already entered by client before."""
    return await conn.fetchval(
        '''
        SELECT TRUE
        FROM clients_promo_global
        WHERE client_id = $1
        AND promocode_id = $2;
        ''',
        client_id, global_promo_id)


async def is_global_promo_valid(global_promo_id: int) -> bool | None:
    """Check global promocode didn't expire."""
    return await conn.fetchrow(
        '''
        SELECT TRUE
        FROM promocodes_global
        WHERE id = $1
        AND expiration_date > NOW();
        ''',
        global_promo_id)


async def get_clientID_by_telegramID(telegram_id: int) -> int | None:
    """Return client_id by specified telegram_id."""
    return await conn.fetchval('''
        SELECT id
        FROM clients
        WHERE telegram_id = $1;
        ''',
                               telegram_id)


async def get_clientID_by_username(username: str) -> int | None:
    """Return client_id by specified @username."""
    return await conn.fetchval(
        '''
        SELECT id
        FROM clients
        WHERE username = $1;
        ''',
        username)


async def get_telegramID_by_clientID(client_id: str) -> int | None:
    """Return telegram_id by specified client_id."""
    return await conn.fetchval(
        '''
        SELECT telegram_id
        FROM clients
        WHERE id = $1;
        ''',
        client_id)


async def get_telegramID_by_username(username: str) -> int | None:
    """Return telegram_id by specified @username."""
    return await conn.fetchval(
        '''
        SELECT telegram_id
        FROM clients
        WHERE username = $1;
        ''',
        username)


async def get_client_info_by_telegramID(telegram_id: int) -> asyncpg.Record | None:
    """Return information about client by specified telegram_id.

    :param telegram_id:
    :return: asyncgp.Record object having (id, name, surname, username, register_date, TO_CHAR(register_date, 'FMDD TMMonth YYYY в HH24:MI'), used_ref_promo_id)
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT id, name, surname, username, register_date, TO_CHAR(register_date, 'FMDD TMMonth YYYY в HH24:MI'), used_ref_promo_id
        FROM clients
        WHERE telegram_id = $1;
        ''',
        telegram_id)


async def get_client_info_by_clientID(client_id: int) -> asyncpg.Record | None:
    """Return information about client by specified client_id.

    :param client_id:
    :return: asyncgp.Record object having (name, surname, username, telegram_id, register_date, TO_CHAR(register_date, 'FMDD TMMonth YYYY в HH24:MI'), used_ref_promo_id)
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT name, surname, username, telegram_id, register_date, TO_CHAR(register_date, 'FMDD TMMonth YYYY в HH24:MI'), used_ref_promo_id
        FROM clients
        WHERE id = $1;
        ''',
        client_id)


async def get_chatgpt_mode_status(client_id: int) -> bool | None:
    """Return TRUE if bot is answering unrecognized messages in ChatGPT mode else FALSE."""
    return await conn.fetchval(
        '''
        SELECT chatgpt_mode
        FROM settings
        WHERE client_id = $1;
        ''',
        client_id)


async def get_clients_ids() -> list[asyncpg.Record]:
    """Return all clients' ids from DB as list[asyncpg.Record]."""
    return await conn.fetch(
        '''
        SELECT id
        FROM clients;
        ''')


async def get_clients_telegram_ids() -> list[asyncpg.Record]:
    """Return all clients' telegram ids from DB as list[asyncpg.Record]."""
    return await conn.fetch(
        '''
        SELECT telegram_id
        FROM clients;
        ''')


async def get_subscription_info_by_clientID(client_id: int) -> asyncpg.Record | None:
    """Return information about subscription of client specified by client_id.

    :param client_id:
    :return: asyncgp.Record object having (sub_id, title, description, price)
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT sub.id, sub.title, sub.description, sub.price
        FROM clients_subscriptions AS clients_sub
        JOIN subscriptions AS sub
        ON sub.id = clients_sub.sub_id
        WHERE clients_sub.client_id = $1;
        ''',
        client_id)


async def get_clients_subscriptions_info_by_clientID(client_id: int) -> asyncpg.Record | None:
    """Return information about subscription's expiration date of client specified by client_id.

    :param client_id:
    :return: asyncgp.Record object having (sub_id, paid_months_counter, expiration_date, TO_CHAR(expiration_date,
    'FMDD TMMonth YYYY в HH24:MI'))
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT sub_id, paid_months_counter, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI')
        FROM clients_subscriptions
        WHERE client_id = $1;
        ''',
        client_id)


async def get_subscription_info_by_subID(subscription_id: int) -> asyncpg.Record | None:
    """Return information about subscription specified by sub_id.

    :param subscription_id:
    :return: asyncgp.Record object having (id, title, description, price)
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT id, title, description, price
        FROM subscriptions
        WHERE id = $1;
        ''',
        subscription_id)


async def get_subscription_expiration_date(telegram_id: int) -> str | None:
    """Return subsctiption's expiration date in string format."""
    return await conn.fetchval(
        '''
        SELECT TO_CHAR(cs.expiration_date, 'FMDD TMMonth YYYY в HH24:MI')
        FROM clients_subscriptions AS cs
        JOIN clients AS c
        ON cs.client_id = c.id
        WHERE c.telegram_id = $1;
        ''',
        telegram_id)


async def get_configurations_info(client_id: int) -> list[asyncpg.Record]:
    """Return information about all client's configurations.

    :param client_id:
    :return: list of asyncgp.Record objects having (file_type, TO_CHAR(date_of_receipt, 'FMDD TMMonth YYYY в HH24:MI'),
    os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)
    :rtype: list[asyncpg.Record]
    """
    return await conn.fetch(
        '''
        SELECT c.file_type, TO_CHAR(c.date_of_receipt, 'FMDD TMMonth YYYY в HH24:MI'), c.os,
        cl.is_chatgpt_available, cp.name, cl.country, cl.city, cl.bandwidth, cl.ping, c.telegram_file_id
        FROM configurations AS c
        JOIN configurations_protocols AS cp ON c.protocol_id = cp.id
        JOIN configurations_locations AS cl ON c.location_id = cl.id
        WHERE c.client_id = $1
        ORDER BY c.date_of_receipt;
        ''',
        client_id)


async def get_configurations_number(client_id: int) -> int | None:
    """Return number of client's configurations."""
    return await conn.fetchval(
        '''
        SELECT COUNT(*)
        FROM configurations
        WHERE client_id = $1;
        ''',
        client_id)


async def get_paymentIDs(client_id: int) -> list[asyncpg.Record]:
    """Return all payments ids created by client.

    :param client_id:
    :return: list of asyncgp.Record objects having (id)
    :rtype: list[asyncpg.Record]
    """
    return await conn.fetch(
        '''
        SELECT id
        FROM payments
        WHERE client_id = $1
        ORDER BY date_of_initiation DESC
        ''',
        client_id)


async def get_paymentIDs_last(client_id: int, minutes: int) -> list[asyncpg.Record]:
    """Return all created by client payments in last n minutes.

    :param client_id
    :param minutes: number of minutes for which ids are selected
    :return: list of asyncgp.Record objects having (id)
    :rtype: list[asyncpg.Record]
    """
    return await conn.fetch(
        '''
        SELECT id
        FROM payments
        WHERE client_id = $1
        AND date_of_initiation > CURRENT_TIMESTAMP - make_interval(mins => $2)
        ORDER BY date_of_initiation DESC;
        ''',
        client_id, minutes)


async def get_payments_successful_info(client_id: int) -> list[asyncpg.Record]:
    """Return information about successful payments by client.

    :param client_id:
    :return: list of asyncgp.Record objects having (p.id, s.title, p.price, p.months_number, TO_CHAR(p.date_of_initiation, 'FMDD TMMonth YYYY в HH24:MI'))
    :rtype: list[asyncpg.Record]
    """
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


async def get_payments_successful_number(client_id: int) -> int:
    """Return number of successful payments initiated by client."""
    return await conn.fetchval(
        '''
        SELECT COUNT(*)
        FROM payments
        WHERE client_id = $1
        AND is_successful = TRUE;
        ''',
        client_id)


async def get_payments_successful_sum(client_id: int) -> Decimal:
    """Return sum of successful payments initiated by client."""
    return await conn.fetchval(
        '''
        SELECT
        CASE
            WHEN SUM(price) IS NULL THEN 0.00
            ELSE SUM(price)
        END
        FROM payments
        WHERE client_id = $1
        AND is_successful = TRUE;
        ''',
        client_id)


async def get_payment_status(payment_id: int) -> bool | None:
    """Return TRUE if payment was successful else FALSE."""
    return await conn.fetchval(
        '''
        SELECT is_successful
        FROM payments
        WHERE id = $1;
        ''',
        payment_id)


async def get_payment_months_number(payment_id: int) -> int | None:
    """Return paid number of months for specified payment_id."""
    return await conn.fetchval(
        '''
        SELECT months_number
        FROM payments
        WHERE id = $1;
        ''',
        payment_id)


async def get_payment_last_message_id(client_id: int) -> asyncpg.Record | None:
    """Return telegram message id for last created payment."""
    return await conn.fetchval(
        '''
        SELECT telegram_message_id
        FROM payments
        WHERE client_id = $1
        ORDER BY date_of_initiation DESC
        LIMIT 1;
        ''',
        client_id)


async def get_referral_promo(telegram_id: int) -> str | None:
    """Return client's own referral promocode's phrase."""
    return await conn.fetchval(
        '''
        SELECT pf.phrase
        FROM clients AS c
        JOIN promocodes_ref AS pf
        ON c.id = pf.client_creator_id
        WHERE c.telegram_id = $1;
        ''',
        telegram_id)


async def get_local_promo_info(phrase: str) -> asyncpg.Record | None:
    """Return information about local promocode.

    :param phrase:
    :return: asyncgp.Record object having (id, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI')),
    bonus_time, TO_CHAR(bonus_time, 'FMDDD'), provided_sub_id)
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT id, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI'), bonus_time, TO_CHAR(bonus_time, 'FMDDD'), provided_sub_id
        FROM promocodes_local
        WHERE phrase = $1;
        ''',
        phrase)


async def get_global_promo_info(phrase: str) -> asyncpg.Record | None:
    """Return information about global promocode.

    :param phrase:
    :return: asyncgp.Record object having (id, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI'), remaining_activations,
    bonus_time, TO_CHAR(bonus_time, 'FMDDD'))
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT id, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI'), remaining_activations, bonus_time, TO_CHAR(bonus_time, 'FMDDD')
        FROM promocodes_global
        WHERE phrase = $1;
        ''',
        phrase)


async def get_client_entered_promos(client_id: int) -> tuple[asyncpg.Record | None, ...]:
    """Return information about entered by client promocodes.

    :param client_id:
    :return: tuple of entered (referral_promocode, global_promocodes, local_promocodes)
    :rtype: tuple[asyncpg.Record | None]
    """
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


async def get_settings_info(client_id: int) -> asyncpg.Record | None:
    """Return information about client's setting where TRUE means TURNED ON and FALSE means TURNED OFF.

    :param client_id:
    :return: asyncgp.Record object having (sub_expiration_in_1d, sub_expiration_in_3d, sub_expiration_in_7d, chatgpt_mode)
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT sub_expiration_in_1d, sub_expiration_in_3d, sub_expiration_in_7d, chatgpt_mode
        FROM settings
        WHERE client_id = $1;
        ''',
        client_id)


async def get_notifications_status() -> list[asyncpg.Record]:
    """Return information about subscription expiration for current 30 minutes.

    :return: list of asyncgp.Record objects having (telegram_id, subscription_expiration_date: str, is_subscription_expiration_now: bool, is_subscription_expiration_in_1d: bool,
    is_subscription_expiration_in_3d: bool, is_subscription_expiration_in_7d: bool)
    :rtype: list[asyncpg.Record]
    """
    return await conn.fetch(
        '''
        SELECT c.telegram_id,
        TO_CHAR(cs.expiration_date, 'FMDD TMMonth в HH24:MI') AS subscription_expiration_date,
        CURRENT_TIMESTAMP <= cs.expiration_date AND cs.expiration_date < CURRENT_TIMESTAMP + INTERVAL '30 minutes' AS is_subscription_expiration_now,
        s.sub_expiration_in_1d AND CURRENT_TIMESTAMP + INTERVAL '1 days' <= cs.expiration_date AND cs.expiration_date < CURRENT_TIMESTAMP + INTERVAL '1 days 30 minutes' AS is_subscription_expiration_in_1d,
        s.sub_expiration_in_3d AND CURRENT_TIMESTAMP + INTERVAL '3 days' <= cs.expiration_date AND cs.expiration_date < CURRENT_TIMESTAMP + INTERVAL '3 days 30 minutes' AS is_subscription_expiration_in_3d,
        s.sub_expiration_in_7d AND CURRENT_TIMESTAMP + INTERVAL '7 days' <= cs.expiration_date AND cs.expiration_date < CURRENT_TIMESTAMP + INTERVAL '7 days 30 minutes' AS is_subscription_expiration_in_7d
        FROM clients AS c
        JOIN settings AS s
        ON c.id = s.client_id
        JOIN clients_subscriptions AS cs
        ON s.client_id = cs.client_id;
        ''')


async def get_refferal_promo_info_by_phrase(phrase: str) -> asyncpg.Record | None:
    """Return information about referral promocode by specified promocode phrase.

    :param phrase:
    :return: asyncgp.Record object having (id, client_creator_id, provided_sub_id, bonus_time, TO_CHAR(bonus_time, 'FMDDD'))
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT id, client_creator_id, provided_sub_id, bonus_time, TO_CHAR(bonus_time, 'FMDDD')
        FROM promocodes_ref
        WHERE phrase = $1;
        ''',
        phrase)


async def get_refferal_promo_info_by_promoID(ref_promo_id: int) -> asyncpg.Record | None:
    """Return information about referral promocode by specified referral promocode id.

    :param phrase:
    :return: asyncgp.Record object having (phrase, client_creator_id, provided_sub_id, bonus_time, TO_CHAR(bonus_time, 'FMDDD'))
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT phrase, client_creator_id, provided_sub_id, bonus_time, TO_CHAR(bonus_time, 'FMDDD')
        FROM promocodes_ref
        WHERE id = $1;
        ''',
        ref_promo_id)


async def get_refferal_promo_info_by_clientCreatorID(client_creator_id: int) -> asyncpg.Record | None:
    """Return information about referral promocode by specified client creator of promocode id.

    :param phrase:
    :return: asyncgp.Record object having (id, phrase, provided_sub_id, bonus_time, TO_CHAR(bonus_time, 'FMDDD'))
    :rtype: asyncpg.Record | None
    """
    return await conn.fetchrow(
        '''
        SELECT id, phrase, provided_sub_id, bonus_time, TO_CHAR(bonus_time, 'FMDDD')
        FROM promocodes_ref
        WHERE client_creator_id = $1;
        ''',
        client_creator_id)


async def get_invited_by_client_info(telegram_id: int) -> asyncpg.Record | None:
    """Return information about client, who invited user with specified telegram_id.

    :param telegram_id:
    :return: asyncgp.Record object having (cc.name, cc.username)
    :rtype: asyncpg.Record | None
    """
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


async def get_invited_clients_list(telegram_id: int) -> list[asyncpg.Record]:
    """Return information about clients, invited by user with specified telegram_id.

    :param telegram_id:
    :return: list of asyncgp.Record objects having (c.name, c.username)
    :rtype: list[asyncpg.Record]
    """
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


async def get_earnings_per_month() -> Decimal:
    """Return sum of successful payments' prices per current month. Is used by administrator."""
    return await conn.fetchval(
        '''
        SELECT COALESCE(SUM(price), 0)
        FROM payments
        WHERE is_successful = TRUE
        AND date_of_initiation > date_trunc('month', CURRENT_TIMESTAMP);
        '''
    )


async def update_chatgpt_mode(client_id: int) -> bool | None:
    """Turn on/off ChatGPT bot mode in DB of client with specified telegram_id."""
    return await conn.fetchval(
        '''
        UPDATE settings
        SET chatgpt_mode = NOT chatgpt_mode
        WHERE client_id = $1
        RETURNING chatgpt_mode;
        ''',
        client_id)


async def insert_client(name: str,
                        telegram_id: int,
                        surname: str | None = None,
                        username: str | None = None,
                        used_ref_promo_id: int | None = None,
                        provided_sub_id: int | None = None,
                        bonus_time: datetime.timedelta | None = None,
                        ) -> None:
    """Add new client to DB."""
    if username:
        username = '@' + username

    if provided_sub_id is None:
        provided_sub_id = 1  # добавить глобальную константу

    if bonus_time is None:
        bonus_time = datetime.timedelta()    # zero days

    provided_ref_sub_id = provided_sub_id
    if provided_sub_id in [3, 4]:  # добавить глобальную константу
        provided_ref_sub_id = 1  # добавить глобальную константу

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
            INSERT INTO settings (client_id)
            VALUES ($1);
            ''',
            client_id)


async def insert_configuration(client_id: int,
                               protocol_id: int,
                               location_id: int,
                               os: str,
                               file_type: str,
                               telegram_file_id: str) -> None:
    """Add new configuration for client in DB."""
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
    """Add new payment for client in DB."""
    return await conn.fetchval(
        '''
        INSERT INTO payments (client_id, sub_id, price, months_number)
        VALUES($1, $2, $3, $4)
        RETURNING id;
        ''',
        client_id, sub_id, price, months_number)


async def insert_client_entered_local_promo(client_id: int, local_promo_id: int, local_promo_bonus_time) -> None:
    """Add information about entered local promocode and change subscription's expiration date for client."""
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
    """Add information about entered global promocode, reduce remaining activations of global promo, change subscription's expiration date for client."""
    async with conn.transaction():
        await conn.execute(
            '''
            INSERT INTO clients_promo_global (client_id, promocode_id)
            VALUES($1, $2);
            ''',
            client_id, global_promo_id)

        await conn.execute(
            '''
            UPDATE promocodes_global
            SET remaining_activations = remaining_activations - 1
            WHERE id = $1
            ''',
            global_promo_id)

        await conn.execute(
            '''
            UPDATE clients_subscriptions
            SET expiration_date = expiration_date + $1
            WHERE client_id = $2;
            ''',
            global_promo_bonus_time, client_id)


async def update_payment_successful(payment_id: int, client_id: int, paid_months: int) -> None:
    """Change status of payment specified by payment_id to successful and change subscription data."""
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
    """Add telegram message id for payment specified by payment_id."""
    await conn.execute(
        '''
        UPDATE payments
        SET telegram_message_id = $1
        WHERE id = $2;
        ''',
        telegram_message_id, payment_id)


async def update_client_subscription(client_id: int, new_sub_id: int) -> None:
    """Change client's subscription type."""
    await conn.execute(
        '''
        UPDATE clients_subscriptions
        SET sub_id = $1
        WHERE client_id = $2
        ''',
        new_sub_id, client_id)


async def update_notifications_1d(client_id: int) -> bool | None:
    """Change client's settings for sending notification one day before subscription expires where TRUE is send notification
    and FALSE is not send notification, return current settings."""
    return await conn.fetchval(
        '''
        UPDATE settings
        SET sub_expiration_in_1d = NOT sub_expiration_in_1d
        WHERE client_id = $1
        RETURNING sub_expiration_in_1d;
        ''',
        client_id)


async def update_notifications_3d(client_id: int) -> bool | None:
    """Change client's settings for sending notification three days before subscription expires where TRUE is send notification
    and FALSE is not send notification, return current settings."""
    return await conn.fetchval(
        '''
        UPDATE settings
        SET sub_expiration_in_3d = NOT sub_expiration_in_3d
        WHERE client_id = $1
        RETURNING sub_expiration_in_3d;
        ''',
        client_id)


async def update_notifications_7d(client_id: int) -> bool | None:
    """Change client's settings for sending notification seven day before subscription expires where TRUE is send notification
    and FALSE is not send notification, return current settings."""
    return await conn.fetchval(
        '''
        UPDATE settings
        SET sub_expiration_in_7d = NOT sub_expiration_in_7d
        WHERE client_id = $1
        RETURNING sub_expiration_in_7d;
        ''',
        client_id)


async def add_subscription_period(client_id: int, days: int) -> None:
    """Add interval for subscription expiration date."""
    await conn.execute(
        '''
        UPDATE clients_subscriptions
        SET expiration_date = expiration_date + make_interval(days => $1)
        WHERE client_id = $2;
        ''',
        days, client_id)
