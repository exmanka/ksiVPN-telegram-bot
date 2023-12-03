import string
import random


max_id = 43
promocode_random_part_length = 7
for i in range(max_id):
    print(f"INSERT INTO promocodes_ref(phrase, ref_client_id) VALUES(\'{'REF' + ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(promocode_random_part_length))}\', {i + 1});")