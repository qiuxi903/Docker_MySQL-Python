"""数据库底层工具：root 连接、标识符转义、值序列化。"""
import datetime
import decimal
import re

import pymysql

from .config import C


def root_conn(db: str | None = None) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=C.DB_HOST,
        port=C.DB_PORT,
        user="root",
        password=C.ROOT_PW,
        database=db,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )


def user_conn(db_name: str, user: str, password: str) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=C.DB_HOST,
        port=C.DB_PORT,
        user=user,
        password=password,
        database=db_name,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )


def q_ident(name: str) -> str:
    """反引号转义标识符（表名/列名），内部反引号翻倍。"""
    return "`" + str(name).replace("`", "``") + "`"


# 学生可自建任意表名，这里校验"表名/列名"是否为安全字符（中文/字母/数字/下划线/短横线）
_IDENT_RE = re.compile(r"^[\w\u4e00-\u9fff-]{1,64}$", re.UNICODE)


def valid_ident(name: str) -> bool:
    return bool(name) and bool(_IDENT_RE.match(str(name)))


def db_name_for(username: str) -> str:
    """账号 → 独立数据库名。ASCII 安全用户名直接用，否则哈希，保证全是合法标识符。"""
    key = username.lower()
    if re.fullmatch(r"[a-z][a-z0-9_]{2,31}", key):
        return "u_" + key
    import hashlib

    return "u_h" + hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def mysql_user_for(seed: str) -> str:
    import hashlib

    return "m_" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:16]


def conv_value(v):
    """把 MySQL 返回值转成可 JSON 序列化的形式。"""
    if v is None:
        return None
    if isinstance(v, (str, int)):
        return v
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return str(v)
        return v
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, datetime.datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, (datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, datetime.timedelta):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return "0x" + bytes(v).hex()
    return str(v)
