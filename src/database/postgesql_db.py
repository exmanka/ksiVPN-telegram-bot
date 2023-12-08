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

    return cur.fetchall()

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
def is_subscription_active(telegram_id: int):
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
                SELECT bonus_time, TO_CHAR(bonus_time, 'FMDDD')
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