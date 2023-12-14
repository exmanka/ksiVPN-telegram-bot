import psycopg2 as ps
from aiogram import types
from bot_init import bot, POSTGRES_PW

def sql_start():
    global conn, cur
    conn = ps.connect(host="localhost", database="tgbot_postgres_db", user="postgres", password=POSTGRES_PW)
    cur = conn.cursor()
    
    if conn:
        print('DB is successfully connected!')

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ 
def find_clientID_by_telegramID(telegram_id: int):
    cur.execute('''
                SELECT id FROM clients
                WHERE telegram_id = %s;
                ''',
                (telegram_id,))
    
    conn.commit()
    
    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ 
def find_clientID_by_username(username: str):
    cur.execute('''
                SELECT id FROM clients
                WHERE username = %s;
                ''',
                (username,))
    
    conn.commit()
    
    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ 
def get_telegramID_by_username(username: str):
    cur.execute('''
                SELECT telegram_id FROM clients
                WHERE username = %s;
                ''',
                (username,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def insert_user_payment(client_id: int, sub_id: int, price: float, months_number: int):
    cur.execute('''
                INSERT INTO payments (client_id, sub_id, price, months_number)
                VALUES(%s, %s, %s, %s);
                ''',
                (client_id, sub_id, price, months_number))
    
    cur.execute('''
                SELECT id FROM payments
                WHERE client_id = %s
                ORDER BY date_of_initiation DESC
                LIMIT 1;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ  
def get_last_user_payments_ids(client_id: int, minutes: int):
    '''
    Return user's created payments id for the last n minutes
    '''

    cur.execute('''
                SELECT id FROM payments
                WHERE client_id = %s
                AND date_of_initiation > CURRENT_TIMESTAMP - INTERVAL '%s minutes'
                ORDER BY date_of_initiation DESC
                ''',
                (client_id, minutes))
    
    conn.commit()

    return cur.fetchall()

def get_user_payments(client_id: int):
    '''
    Return user's created payments info for all the time
    '''

    cur.execute('''
                SELECT p.id, s.title, p.price, p.months_number, TO_CHAR(p.date_of_initiation, 'FMDD TMMonth YYYY в HH24:MI')
                FROM payments AS p
                JOIN subscriptions AS s
                ON p.sub_id = s.id
                WHERE p.client_id = %s
                AND p.is_successful = TRUE;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchall()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ 
def get_user_payments_ids(client_id: int):
    '''
    Return user's created payments id for all the time
    '''

    cur.execute('''
                SELECT id FROM payments
                WHERE client_id = %s
                ORDER BY date_of_initiation DESC
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchall()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ 
def get_payment_status(payment_id: int):
    cur.execute('''
                SELECT is_successful FROM payments
                WHERE id = %s;
                ''',
                (payment_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ 
def get_payment_months_number(payment_id: int):
    cur.execute('''
                SELECT months_number FROM payments
                WHERE id = %s;
                ''',
                (payment_id,))
    
    conn.commit()

    return cur.fetchone()

def get_last_user_payment_message_id(client_id: int):
    '''
    Return last user's created payment's telegram message id
    '''

    cur.execute('''
                SELECT telegram_message_id FROM payments
                WHERE client_id = %s
                ORDER BY date_of_initiation DESC
                LIMIT 1;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchone()
    

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ 
def update_payment_successful(payment_id: int, client_id: int, paid_months: int):
    cur.execute('''
                UPDATE payments
                SET is_successful = TRUE
                WHERE id = %s;
                ''',
                (payment_id,))
    
    cur.execute('''
                UPDATE clients_subscriptions
                SET paid_months_counter = paid_months_counter + %s,
                expiration_date = expiration_date + INTERVAL '%s months'
                WHERE client_id = %s;
                ''',
                (paid_months, paid_months, client_id))
    
    conn.commit()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ 
def update_payment_telegram_message_id(payment_id: int, telegram_message_id: int):
    cur.execute('''
                UPDATE payments
                SET telegram_message_id = %s
                WHERE id = %s;
                ''',
                (telegram_message_id, payment_id))
    
    conn.commit()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ  
def show_user_info(telegram_id: int):
    cur.execute('''
                SELECT name, surname, username, telegram_id, TO_CHAR(register_date, 'FMDD TMMonth YYYY в HH24:MI') FROM clients
                WHERE telegram_id = %s;
                ''',
                (telegram_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def get_user_info_by_clientID(client_id: int):
    cur.execute('''
                SELECT name, surname, username, telegram_id, TO_CHAR(register_date, 'FMDD TMMonth YYYY в HH24:MI') FROM clients
                WHERE id = %s;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchone()

def get_user_parsed_tuple_by_telegramID(telegram_id: int):
    cur.execute('''
                SELECT id, name, surname, username, TO_CHAR(register_date, 'FMDD TMMonth YYYY в HH24:MI') FROM clients
                WHERE telegram_id = %s;
                ''',
                (telegram_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def is_user_registered(telegram_id: int):
    cur.execute('''
                SELECT * FROM clients
                WHERE telegram_id = %s;
                ''',
                (telegram_id,))
    
    conn.commit()
    
    return True if cur.fetchall() else False

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def show_subscription_info(client_id: int):
    cur.execute('''
                SELECT sub.id, sub.title, sub.description, sub.price
                FROM clients_subscriptions AS clients_sub
                JOIN subscriptions AS sub
                ON sub.id = clients_sub.sub_id
                WHERE clients_sub.client_id = %s;
                ''',
                (client_id,))
    
    conn.commit()
    
    return cur.fetchall()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def get_subscription_info_by_subID(subscription_id):
    cur.execute('''
                SELECT id, title, description, price
                FROM subscriptions
                WHERE id = %s;
                ''',
                (subscription_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def show_configurations_info(client_id: int):
    cur.execute('''
                SELECT c.file_type, TO_CHAR(c.date_of_receipt, 'FMDD TMMonth YYYY в HH24:MI'), c.os, cl.is_chatgpt_available, cp.name, cl.country, cl.city, cl.bandwidth, cl.ping, c.telegram_file_id
                FROM configurations AS c
                JOIN configurations_protocols AS cp ON c.protocol_id = cp.id
                JOIN configurations_locations AS cl ON c.location_id = cl.id
                WHERE c.client_id = %s
                ORDER BY c.date_of_receipt;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchall()

def show_configurations_number(client_id: int):
    cur.execute('''
                SELECT COUNT(*) FROM configurations
                WHERE client_id = %s;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def is_subscription_active(telegram_id: int) -> bool:
    cur.execute('''
                SELECT * FROM clients_subscriptions AS cs
                JOIN clients AS c
                ON cs.client_id = c.id
                WHERE c.telegram_id = %s
                AND cs.expiration_date > NOW();
                ''',
                (telegram_id,))
    
    conn.commit()
    
    return True if cur.fetchall() else False

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def is_subscription_not_started(telegram_id: int) -> bool:
    cur.execute('''
                SELECT * FROM clients_subscriptions AS cs
                JOIN clients AS c
                ON cs.client_id = c.id
                WHERE c.telegram_id = %s
                AND cs.expiration_date < TIMESTAMP 'EPOCH' + INTERVAL '5 years';
                ''',
                (telegram_id,))
    
    conn.commit()
    
    return True if cur.fetchall() else False

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def show_subscription_expiration_date(telegram_id: int):
    cur.execute('''
                SELECT TO_CHAR(cs.expiration_date, 'FMDD TMMonth YYYY в HH24:MI') FROM clients_subscriptions AS cs
                JOIN clients AS c
                ON cs.client_id = c.id
                WHERE c.telegram_id = %s;
                ''',
                (telegram_id,))
    
    conn.commit()
    
    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def show_referral_promocode(telegram_id: int):
    cur.execute('''
                SELECT pf.phrase
                FROM clients AS c
                JOIN promocodes_ref AS pf
                ON c.id = pf.client_creator_id
                WHERE c.telegram_id = %s;
                ''',
                (telegram_id,))
    
    conn.commit()
    
    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def show_invited_by_user_info(telegram_id: int):
    cur.execute('''
                SELECT cc.name, cc.username
                FROM clients AS c
                JOIN promocodes_ref AS pr
                ON c.used_ref_promo_id = pr.id
                JOIN clients AS cc
                ON pr.client_creator_id = cc.id
                WHERE c.telegram_id = %s;
                ''',
                (telegram_id,))
    
    conn.commit()
    
    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def show_invited_users_list(telegram_id: int):
    cur.execute('''
                SELECT c.name, c.username
                FROM clients AS c
                JOIN promocodes_ref AS pr
                ON c.used_ref_promo_id = pr.id
                JOIN clients AS cc
                ON pr.client_creator_id = cc.id
                WHERE cc.telegram_id = %s;
                ''',
                (telegram_id,))
    
    conn.commit()
    
    return cur.fetchall()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def check_referral_promo(phrase):
    cur.execute('''
                SELECT client_creator_id
                FROM promocodes_ref
                WHERE phrase = %s;
                ''',
                (phrase,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def check_local_promo_exists(phrase):
    cur.execute('''
                SELECT id
                FROM promocodes_local
                WHERE phrase = %s;
                ''',
                (phrase,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def get_local_promo_parsed_tuple_by_phrase(phrase: str) -> tuple[int, str, str, str, str, int]:
    cur.execute('''
                SELECT id, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI'), bonus_time, TO_CHAR(bonus_time, 'FMDDD'), provided_sub_id
                FROM promocodes_local
                WHERE phrase = %s;
                ''',
                (phrase,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def update_client_subscription(client_id: int, new_sub_id: int):
    cur.execute('''
                UPDATE clients_subscriptions
                SET sub_id = %s
                WHERE client_id = %s
                ''',
                (new_sub_id, client_id))
    
    conn.commit()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def get_global_promo_parsed_tuple_by_phrase(phrase: str) -> tuple[int, str, str, str, str]:
    cur.execute('''
                SELECT id, expiration_date, TO_CHAR(expiration_date, 'FMDD TMMonth YYYY в HH24:MI'), bonus_time, TO_CHAR(bonus_time, 'FMDDD')
                FROM promocodes_global
                WHERE phrase = %s;
                ''',
                (phrase,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def check_global_promo_exists(phrase):
    cur.execute('''
                SELECT id
                FROM promocodes_global
                WHERE phrase = %s;
                ''',
                (phrase,))
    
    conn.commit()
    
    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def check_local_promo_accessible(client_id: int, local_promo_id: int):
    cur.execute('''
                SELECT date_of_entry
                FROM clients_promo_local
                WHERE promocode_id = %s
                AND accessible_client_id = %s;
                ''',
                (local_promo_id, client_id))
    
    conn.commit()
    
    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def is_global_promo_already_entered(client_id: int, global_promo_id: int):
    cur.execute('''
                SELECT *
                FROM clients_promo_global
                WHERE client_id = %s
                AND promocode_id = %s;
                ''',
                (client_id, global_promo_id))
    
    conn.commit()
    
    return True if cur.fetchall() else False

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def check_local_promo_valid(local_promo_id: int):
    cur.execute('''
                SELECT bonus_time, TO_CHAR(bonus_time, 'FMDDD'), provided_sub_id
                FROM promocodes_local
                WHERE id = %s
                AND expiration_date > NOW();
                ''',
                (local_promo_id,))
    
    conn.commit()
    
    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def check_global_promo_valid(global_promo_id: int):
    cur.execute('''
                SELECT bonus_time, TO_CHAR(bonus_time, 'FMDDD')
                FROM promocodes_global
                WHERE id = %s
                AND expiration_date > NOW();
                ''',
                (global_promo_id,))
    
    conn.commit()
    
    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def insert_user_entered_local_promo(client_id: int, local_promo_id: int, local_promo_bonus_time):
    cur.execute('''
                UPDATE clients_promo_local
                SET date_of_entry = NOW()
                WHERE promocode_id = %s
                AND accessible_client_id = %s;
                ''',
                (local_promo_id, client_id))
    
    cur.execute('''
                UPDATE clients_subscriptions
                SET expiration_date = expiration_date + %s
                WHERE client_id = %s;
                ''',
                (local_promo_bonus_time, client_id))
    
    conn.commit()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def insert_user_entered_global_promo(client_id: int, global_promo_id: int, global_promo_bonus_time):
    cur.execute('''
                INSERT INTO clients_promo_global (client_id, promocode_id)
                VALUES(%s, %s);
                ''',
                (client_id, global_promo_id))
    
    cur.execute('''
                UPDATE clients_subscriptions
                SET expiration_date = expiration_date + %s
                WHERE client_id = %s;
                ''',
                (global_promo_bonus_time, client_id))
    
    conn.commit()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def show_entered_promos(client_id: int):
    promos_dict = {}
    
    # referral promocodes
    cur.execute('''
                SELECT pf.phrase, cc.name
                FROM clients AS c
                JOIN promocodes_ref AS pf
                ON c.used_ref_promo_id = pf.id
                JOIN clients AS cc
                ON pf.client_creator_id = cc.id
                WHERE c.id = %s;
                ''',
                (client_id,))
    promos_dict['ref'] = cur.fetchone()

    # global promocodes
    cur.execute('''
                SELECT pg.phrase, TO_CHAR(pg.bonus_time, 'FMDDD'), TO_CHAR(cpg.date_of_entry, 'FMDD TMMonth YYYY в HH24:MI')
                FROM clients_promo_global AS cpg
                JOIN promocodes_global AS pg
                ON cpg.promocode_id = pg.id
                WHERE cpg.client_id = %s;
                ''',
                (client_id,))
    promos_dict['global'] = cur.fetchall()

    # local promocodes
    cur.execute('''
            SELECT pl.phrase, TO_CHAR(pl.bonus_time, 'FMDDD'), TO_CHAR(cpl.date_of_entry, 'FMDD TMMonth YYYY в HH24:MI')
            FROM clients_promo_local AS cpl
            JOIN promocodes_local AS pl
            ON cpl.promocode_id = pl.id
            WHERE cpl.accessible_client_id = %s
            AND cpl.date_of_entry IS NOT NULL;
            ''',
            (client_id,))
    promos_dict['local'] = cur.fetchall()

    conn.commit()

    return promos_dict

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def get_clients_telegram_ids():
    cur.execute('''
                SELECT telegram_id FROM clients;
                ''')
    
    conn.commit()

    return cur.fetchall()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def get_notifications_info(client_id: int):
    cur.execute('''
                SELECT sub_expiration_in_1d, sub_expiration_in_3d, sub_expiration_in_7d
                FROM sub_notifications_settings
                WHERE client_id = %s;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ 
def get_notifications_status():
    cur.execute('''
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

    conn.commit()

    return cur.fetchall()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def update_notifications_1d(client_id: int):
    cur.execute('''
                UPDATE sub_notifications_settings
                SET sub_expiration_in_1d = NOT sub_expiration_in_1d
                WHERE client_id = %s
                RETURNING sub_expiration_in_1d;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def update_notifications_3d(client_id: int):
    cur.execute('''
                UPDATE sub_notifications_settings
                SET sub_expiration_in_3d = NOT sub_expiration_in_3d
                WHERE client_id = %s
                RETURNING sub_expiration_in_3d;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def update_notifications_7d(client_id: int):
    cur.execute('''
                UPDATE sub_notifications_settings
                SET sub_expiration_in_7d = NOT sub_expiration_in_7d
                WHERE client_id = %s
                RETURNING sub_expiration_in_7d;
                ''',
                (client_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def get_chatgpt_mode_status(telegram_id: int):
    cur.execute('''
                SELECT bot_chatgpt_mode
                FROM clients
                WHERE telegram_id = %s;
                ''',
                (telegram_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def update_chatgpt_mode(telegram_id: int):
    cur.execute('''
                UPDATE clients
                SET bot_chatgpt_mode = NOT bot_chatgpt_mode
                WHERE telegram_id = %s
                RETURNING bot_chatgpt_mode;
                ''',
                (telegram_id,))
    
    conn.commit()

    return cur.fetchone()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def is_promo_ref(phrase: str) -> bool:
    cur.execute('''
                SELECT TRUE
                FROM promocodes_ref
                WHERE phrase = %s;
                ''',
                (phrase,))
    
    conn.commit()

    return True if cur.fetchone() else False

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def insert_client(name: str,
                  telegram_id: int,
                  surname: str | None = None,
                  username: str | None = None,
                  used_ref_promo_id: int | None = None,
                  provided_sub_id: int | None = None,
                  bonus_time: str | None = None,
                  ):
    
    if username:
        username = '@' + username
    
    if provided_sub_id is None:
        provided_sub_id = 1 # добавить глобальную константу

    if bonus_time is None:
        bonus_time = '0 days'

    provided_ref_sub_id = provided_sub_id
    if provided_sub_id in [3, 4]: # добавить глобальную константу
        provided_ref_sub_id = 1 # добавить глобальную константу
    
    cur.execute('''
                INSERT INTO clients (name, surname, username, telegram_id, used_ref_promo_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
                ''',
                (name, surname, username, telegram_id, used_ref_promo_id))
    
    client_id: int = cur.fetchone()[0]

    cur.execute('''
                INSERT INTO clients_subscriptions (client_id, sub_id, expiration_date)
                VALUES (%s, %s, TIMESTAMP 'EPOCH' + INTERVAL %s);
                ''',
                (client_id, provided_sub_id, bonus_time))

    cur.execute('''
                INSERT INTO promocodes_ref (client_creator_id, provided_sub_id)
                VALUES (%s, %s);
                ''',
                (client_id, provided_ref_sub_id))
    
    cur.execute('''
                INSERT INTO sub_notifications_settings (client_id)
                VALUES (%s);
                ''',
                (client_id,))
    
    conn.commit()

# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def insert_configuration(client_id: int,
                         protocol_id: int,
                         location_id: int,
                         os: str,
                         file_type: str,
                         telegram_file_id: str) -> tuple[int]:
    
    cur.execute('''
                INSERT INTO configurations (client_id, protocol_id, location_id, os, file_type, telegram_file_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id;
                ''',
                (client_id, protocol_id, location_id, os, file_type, telegram_file_id))
    
    cur.execute('''
                UPDATE clients_subscriptions
                SET expiration_date = NOW() + (expiration_date - 'EPOCH')
                WHERE client_id = %s;
                ''',
                (client_id,))

    conn.commit()
    
# ДОПИСАТЬ АСИНХРОННУЮ ФУНКЦИЮ
def get_promo_ref_info(phrase: str):
    cur.execute('''
                SELECT id, client_creator_id, provided_sub_id, bonus_time
                FROM promocodes_ref
                WHERE phrase = %s;
                ''',
                (phrase,))
    
    conn.commit()

    return cur.fetchone()

def get_promo_ref_info_parsed(phrase: str):
    cur.execute('''
                SELECT id, client_creator_id, provided_sub_id, TO_CHAR(bonus_time, 'FMDDD')
                FROM promocodes_ref
                WHERE phrase = %s;
                ''',
                (phrase,))
    
    conn.commit()

    return cur.fetchone()
