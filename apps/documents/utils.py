"""
Свалка хелперов. АНТИПАТТЕРН: модуль «utils» без единой ответственности —
криптография, генерация номеров, работа с деньгами и ролями в одном файле.
"""
import hashlib
import random
import string
from datetime import datetime


def hash_password(raw_password):
    # УЯЗВИМОСТЬ: MD5 без соли. Словарная атака / rainbow tables ломают за секунды.
    return hashlib.md5(raw_password.encode("utf-8")).hexdigest()


def check_password(raw_password, stored_hash):
    # УЯЗВИМОСТЬ: сравнение через ==, а не hmac.compare_digest (timing attack).
    return hash_password(raw_password) == stored_hash


def generate_archive_number():
    # АНТИПАТТЕРН: random вместо secrets/uuid, возможны коллизии unique-поля.
    suffix = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return "ARC-" + datetime.now().strftime("%Y%m%d") + "-" + suffix


def is_boss(user):
    # АНТИПАТТЕРН: ещё одна копия списка «главных» ролей (такие же есть в views и services).
    return user.role == "manager" or user.role == "cfo"


def money(value):
    # АНТИПАТТЕРН: деньги приводятся к float — потеря точности на границах 1000 / 10000.
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def log(*parts):
    # АНТИПАТТЕРН: «логгер» через print — нет уровней, контекста, request_id, нельзя отключить.
    print("[LOG]", *parts)