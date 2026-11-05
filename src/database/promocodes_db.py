"""Referral, local and global promo codes and the referral graph."""
import asyncpg
import datetime

from src.database.connection import acquire
from src.database.subscriptions_db import get_ref_provided_sub_id


async def is_referral_promo(phrase: str) -> bool | None:
    """Check phrase is refferal promocode existing in DB."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT TRUE
            FROM promocodes_ref
            WHERE phrase = $1;
            ''',
            phrase)


async def is_local_promo_accessible(client_id: int, local_promo_id: int) -> bool | None:
    """Check local promocode is available for client."""
    async with acquire() as conn:
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
    async with acquire() as conn:
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
    async with acquire() as conn:
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
    async with acquire() as conn:
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
    async with acquire() as conn:
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
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT TRUE
            FROM promocodes_global
            WHERE id = $1
            AND expiration_date > NOW();
            ''',
            global_promo_id)


async def get_referral_promo(telegram_id: int) -> str | None:
    """Return client's own referral promocode's phrase."""
    async with acquire() as conn:
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
    :return: asyncgp.Record object having (id, expiration_date, bonus_time, provided_sub_id)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT id, expiration_date, bonus_time, provided_sub_id
            FROM promocodes_local
            WHERE phrase = $1;
            ''',
            phrase)


async def get_global_promo_info(phrase: str) -> asyncpg.Record | None:
    """Return information about global promocode.

    :param phrase:
    :return: asyncgp.Record object having (id, expiration_date, remaining_activations, bonus_time)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT id, expiration_date, remaining_activations, bonus_time
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
    async with acquire() as conn:
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
                SELECT pg.phrase, pg.bonus_time, cpg.date_of_entry
                FROM clients_promo_global AS cpg
                JOIN promocodes_global AS pg
                ON cpg.promocode_id = pg.id
                WHERE cpg.client_id = $1;
                ''',
                client_id)

            # local promocodes
            promos_local = await conn.fetch(
                '''
                SELECT pl.phrase, pl.bonus_time, cpl.date_of_entry
                FROM clients_promo_local AS cpl
                JOIN promocodes_local AS pl
                ON cpl.promocode_id = pl.id
                WHERE cpl.accessible_client_id = $1
                AND cpl.date_of_entry IS NOT NULL;
                ''',
                client_id)

            return (promos_ref, promos_global, promos_local)


async def get_refferal_promo_info_by_phrase(phrase: str) -> asyncpg.Record | None:
    """Return information about referral promocode by specified promocode phrase.

    :param phrase:
    :return: asyncgp.Record object having (id, client_creator_id, provided_sub_id, bonus_time)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT id, client_creator_id, provided_sub_id, bonus_time
            FROM promocodes_ref
            WHERE phrase = $1;
            ''',
            phrase)


async def get_refferal_promo_info_by_promoID(ref_promo_id: int) -> asyncpg.Record | None:
    """Return information about referral promocode by specified referral promocode id.

    :param phrase:
    :return: asyncgp.Record object having (phrase, client_creator_id, provided_sub_id, bonus_time)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT phrase, client_creator_id, provided_sub_id, bonus_time
            FROM promocodes_ref
            WHERE id = $1;
            ''',
            ref_promo_id)


async def get_refferal_promo_info_by_clientCreatorID(client_creator_id: int) -> asyncpg.Record | None:
    """Return information about referral promocode by specified client creator of promocode id.

    :param phrase:
    :return: asyncgp.Record object having (id, phrase, provided_sub_id, bonus_time)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT id, phrase, provided_sub_id, bonus_time
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
    async with acquire() as conn:
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
    async with acquire() as conn:
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


async def can_enter_ref_promo_as_authorized(client_id: int) -> bool:
    """Return True if the authorized client is eligible to enter a referral promo code.

    Conditions:
    - registered within the last 7 days (registration window for referral codes)
    - has not yet used any referral promo (used_ref_promo_id IS NULL)
    """
    async with acquire() as conn:
        return bool(await conn.fetchval(
            '''
            SELECT TRUE
            FROM clients
            WHERE id = $1
              AND register_date > NOW() - INTERVAL '7 days'
              AND used_ref_promo_id IS NULL;
            ''',
            client_id))


async def apply_ref_promo_to_existing_client(
    client_id: int,
    ref_promo_id: int,
    provided_sub_id: int | None,
    bonus_time: datetime.timedelta,
) -> None:
    """Apply a referral promo code to an already-registered authorized client.

    In one transaction:
    - sets clients.used_ref_promo_id
    - updates clients_subscriptions.sub_id when provided_sub_id is given
    - updates the client's own promocodes_ref.provided_sub_id to propagate inheritance
    - extends expiration_date (for blank/EPOCH subscriptions counts from NOW())
    """
    # Resolve what subscription type the client's OWN invitees will receive.
    # Uses subscriptions.ref_provided_sub_id — no magic numbers.
    new_ref_sub_id: int | None = None
    if provided_sub_id is not None:
        new_ref_sub_id = await get_ref_provided_sub_id(provided_sub_id)

    async with acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                'UPDATE clients SET used_ref_promo_id = $1 WHERE id = $2;',
                ref_promo_id, client_id)

            if provided_sub_id is not None:
                await conn.execute(
                    'UPDATE clients_subscriptions SET sub_id = $1 WHERE client_id = $2;',
                    provided_sub_id, client_id)
                # Propagate inheritance: update the client's own referral promo so
                # that people they invite in turn receive the correct subscription type.
                await conn.execute(
                    'UPDATE promocodes_ref SET provided_sub_id = $1 WHERE client_creator_id = $2;',
                    new_ref_sub_id, client_id)

            await conn.execute(
                '''
                UPDATE clients_subscriptions
                SET expiration_date = CASE
                    WHEN expiration_date <= CURRENT_TIMESTAMP
                    THEN CURRENT_TIMESTAMP + $1
                    ELSE expiration_date + $1
                END
                WHERE client_id = $2;
                ''',
                bonus_time, client_id)


async def insert_client_entered_local_promo(client_id: int, local_promo_id: int, local_promo_bonus_time) -> None:
    """Add information about entered local promocode and change subscription's expiration date for client."""
    async with acquire() as conn:
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
                SET expiration_date = CASE
                    WHEN expiration_date <= CURRENT_TIMESTAMP
                    THEN CURRENT_TIMESTAMP + $1
                    ELSE expiration_date + $1
                END
                WHERE client_id = $2;
                ''',
                local_promo_bonus_time, client_id)


async def insert_client_entered_global_promo(client_id: int, global_promo_id: int, global_promo_bonus_time) -> None:
    """Add information about entered global promocode, reduce remaining activations of global promo, change subscription's expiration date for client."""
    async with acquire() as conn:
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
                SET expiration_date = CASE
                    WHEN expiration_date <= CURRENT_TIMESTAMP
                    THEN CURRENT_TIMESTAMP + $1
                    ELSE expiration_date + $1
                END
                WHERE client_id = $2;
                ''',
                global_promo_bonus_time, client_id)
