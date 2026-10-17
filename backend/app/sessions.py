"""账号/会话：注册、登录、游客、开通独立数据库、过期清理。"""
import re
import secrets
import threading
import time

from . import auth, community
from .config import C
from .db import db_name_for, q_ident, root_conn


class AuthError(Exception):
    pass


# ---------- 启动引导 ----------

def wait_for_db(timeout: int = 90):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            conn = root_conn()
            conn.close()
            return
        except Exception as e:  # MySQL 还在启动
            last = e
            time.sleep(1)
    raise RuntimeError(f"MySQL 未能就绪: {last}")


def _init_meta():
    conn = root_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {q_ident(C.META_DB)} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.META_DB)}.accounts (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(64) NULL,
                    username_key VARCHAR(64) NULL UNIQUE,
                    kind VARCHAR(8) NOT NULL DEFAULT 'user',
                    pass_hash VARCHAR(256) NULL,
                    role VARCHAR(8) NOT NULL DEFAULT 'user',
                    db_name VARCHAR(64) NOT NULL UNIQUE,
                    mysql_user VARCHAR(64) NOT NULL UNIQUE,
                    mysql_pass VARCHAR(64) NOT NULL,
                    reg_ip VARCHAR(64) NULL,
                    last_ip VARCHAR(64) NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            for _col, _def in (("reg_ip", "VARCHAR(64) NULL"), ("last_ip", "VARCHAR(64) NULL")):
                try:
                    cur.execute(f"ALTER TABLE {q_ident(C.META_DB)}.accounts "
                                f"ADD COLUMN {_col} {_def}")
                except Exception:
                    pass
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.META_DB)}.dbs (
                    account_id BIGINT NOT NULL,
                    db_name VARCHAR(64) NOT NULL,
                    primary_db TINYINT(1) NOT NULL DEFAULT 0,
                    origin VARCHAR(16) NOT NULL DEFAULT 'own',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (db_name),
                    KEY idx_account (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            try:  # 旧库升级：补 origin 列
                cur.execute(f"ALTER TABLE {q_ident(C.META_DB)}.dbs "
                            "ADD COLUMN origin VARCHAR(16) NOT NULL DEFAULT 'own'")
            except Exception:
                pass
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.META_DB)}.imported_tables (
                    account_id BIGINT NOT NULL,
                    db_name VARCHAR(64) NOT NULL,
                    table_name VARCHAR(64) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (account_id, db_name, table_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.META_DB)}.py_files (
                    account_id BIGINT NOT NULL,
                    name VARCHAR(64) NOT NULL,
                    content MEDIUMTEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (account_id, name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.META_DB)}.sessions (
                    token VARCHAR(64) PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_account (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    finally:
        conn.close()


def _register_primary_db(cur, account_id: int, db_name: str):
    cur.execute(f"INSERT IGNORE INTO {q_ident(C.META_DB)}.dbs (account_id, db_name, primary_db) "
                "VALUES (%s,%s,1)", (account_id, db_name))


# ---------- 多数据库：列举 / 新建 / 删除 ----------

_DB_NAME_RE = re.compile(r"^[\w\u4e00-\u9fff]{1,32}$")
_RESERVED_DBS = {"meta", "community", "mysql", "information_schema", "performance_schema", "sys"}


def sanitize_db_name(name: str) -> str:
    n = re.sub(r"[^\w\u4e00-\u9fff]", "_", (name or "").strip())[:32].lower()
    if not n or not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", n):
        n = "db_" + n
    return n


def owned_dbs(account_id: int) -> list[str]:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT db_name FROM dbs WHERE account_id=%s", (account_id,))
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def remove_db_row(account_id: int, name: str):
    """学生用 SQL 自己 DROP 了导入库时，同步清理登记记录。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dbs WHERE account_id=%s AND db_name=%s AND primary_db=0",
                        (account_id, name))
            cur.execute("DELETE FROM imported_tables WHERE account_id=%s AND db_name=%s",
                        (account_id, name))
    finally:
        conn.close()


def list_dbs(account: dict) -> list[dict]:
    """我的数据库列表（含每库表数量）。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT db_name, primary_db, created_at FROM dbs
                           WHERE account_id=%s ORDER BY primary_db DESC, created_at ASC""",
                        (account["id"],))
            rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    conn = root_conn()
    try:
        with conn.cursor() as cur:
            for db_name, primary_db, created_at in rows:
                try:
                    cur.execute("SELECT COUNT(*) FROM information_schema.tables "
                                "WHERE table_schema=%s", (db_name,))
                    cnt = cur.fetchone()[0]
                except Exception:
                    cnt = 0
                out.append({"name": db_name, "primary": bool(primary_db),
                            "tables": cnt, "createdAt": str(created_at)})
    finally:
        conn.close()
    return out


def create_user_db(account: dict, name: str, origin: str = "own") -> str:
    safe = sanitize_db_name(name)
    if not safe or safe in _RESERVED_DBS:
        raise AuthError("库名不合法（不能使用系统库名）")
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id FROM dbs WHERE db_name=%s", (safe,))
            row = cur.fetchone()
            if row:
                raise AuthError(f"数据库名 {safe} 已被占用，换一个名字")
            cur.execute("INSERT INTO dbs (account_id, db_name, primary_db, origin) VALUES (%s,%s,0,%s)",
                        (account["id"], safe, origin))
    finally:
        conn.close()
    conn = root_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {q_ident(safe)} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(f"GRANT ALL PRIVILEGES ON {q_ident(safe)}.* TO %s@'%%'",
                        (account["mysql_user"],))
    finally:
        conn.close()
    return safe


def drop_user_db(account: dict, name: str):
    """删除自己名下的非默认数据库（含权限回收）。"""
    if name.lower() == account["db_name"].lower():
        raise AuthError("默认数据库不允许删除；要重置请找管理员")
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM dbs WHERE account_id=%s AND db_name=%s AND primary_db=0",
                        (account["id"], name))
            if not cur.fetchone():
                raise AuthError("这个数据库不在你的名下")
            cur.execute("DELETE FROM dbs WHERE account_id=%s AND db_name=%s",
                        (account["id"], name))
            cur.execute("DELETE FROM imported_tables WHERE account_id=%s AND db_name=%s",
                        (account["id"], name))
    finally:
        conn.close()
    conn = root_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {q_ident(name)}")
            cur.execute(f"REVOKE ALL PRIVILEGES ON {q_ident(name)}.* FROM %s@'%%'",
                        (account["mysql_user"],))
    finally:
        conn.close()


def create_user_db_unique(account: dict, base: str, origin: str = "own") -> str:
    """创建库，重名时自动加 _2/_3 后缀，返回实际库名。"""
    base = sanitize_db_name(base) or "db"
    candidate = base
    k = 2
    while True:
        try:
            return create_user_db(account, candidate, origin)
        except AuthError as e:
            if "已被占用" not in str(e) or k > 50:
                raise
            candidate = f"{base}_{k}"
            k += 1


def add_imported_tables(account_id: int, db_name: str, tables: list[str]):
    """记录「从社区导入的表」，这些表不能再原样发回社区。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            for t in tables:
                cur.execute("INSERT IGNORE INTO imported_tables "
                            "(account_id, db_name, table_name) VALUES (%s,%s,%s)",
                            (account_id, db_name, t))
    finally:
        conn.close()


def db_origin(account_id: int, db_name: str) -> str:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT origin FROM dbs WHERE account_id=%s AND db_name=%s",
                        (account_id, db_name))
            row = cur.fetchone()
    finally:
        conn.close()
    return row[0] if row else "own"


def table_from_community(account_id: int, table_name: str) -> bool:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM imported_tables WHERE account_id=%s AND table_name=%s",
                        (account_id, table_name))
            return cur.fetchone() is not None
    finally:
        conn.close()


def clear_imported_tables(account_id: int, db_name: str):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM imported_tables WHERE account_id=%s AND db_name=%s",
                        (account_id, db_name))
    finally:
        conn.close()


# ---------- Python 多文件 ----------

_PYFILE_RE = re.compile(r"^[\w\u4e00-\u9fff\-]{1,40}\.py$", re.I)
PYFILE_MAX = 256 * 1024
PYFILE_MAX_COUNT = 30

# 新账号的 main.py 初次内容：让学生点开 Python 页就能直接跑通，
# 顺便演示 query()/execute() 操作自己的数据库
PY_MAIN_SEED = '''\
# 欢迎来到 Python 练习区！点右上角「▶ 运行」即可执行。
# query(sql) 查你自己的 MySQL 数据库，execute(sql) 执行增删改

rows = query("SELECT ENAME, JOB, SAL FROM emp ORDER BY SAL DESC LIMIT 5")
print("工资前 5 名：")
for name, job, sal in rows:
    print(f"  {name:<8}{job:<10}{sal}")
'''


def normalize_pyfile_name(name: str) -> str | None:
    n = (name or "").strip()
    if n and not n.lower().endswith(".py"):
        n += ".py"
    n = n[:44]
    return n if _PYFILE_RE.match(n) else None


def pyfiles_list(account_id: int) -> list[dict]:
    conn = root_conn(C.META_DB)
    result = []
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT name, content, updated_at FROM py_files
                           WHERE account_id=%s ORDER BY name='main.py' DESC, name ASC""",
                        (account_id,))
            rows = cur.fetchall()
            if not rows:
                cur.execute("INSERT INTO py_files (account_id, name, content) VALUES (%s,'main.py',%s)",
                            (account_id, PY_MAIN_SEED))
                rows = [("main.py", PY_MAIN_SEED, "")]
            for name, content, updated_at in rows:
                result.append({"name": name, "size": len((content or "").encode("utf-8")),
                               "updatedAt": str(updated_at)})
    finally:
        conn.close()
    return result


def pyfiles_get(account_id: int, name: str) -> dict | None:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT content, updated_at FROM py_files WHERE account_id=%s AND name=%s",
                        (account_id, name))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"name": name, "content": row[0] or "", "updatedAt": str(row[1])}


def pyfiles_save(account_id: int, name: str, content: str):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO py_files (account_id, name, content) VALUES (%s,%s,%s)
                           ON DUPLICATE KEY UPDATE content=VALUES(content),
                           updated_at=CURRENT_TIMESTAMP""", (account_id, name, content))
    finally:
        conn.close()


def pyfiles_delete(account_id: int, name: str):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM py_files WHERE account_id=%s AND name=%s", (account_id, name))
    finally:
        conn.close()


def pyfiles_unique_name(account_id: int, base: str) -> str:
    name = normalize_pyfile_name(base) or "main.py"
    if name not in [f["name"] for f in pyfiles_list(account_id)]:
        return name
    stem = name[:-3]
    k = 2
    while k < 100:
        cand = f"{stem}_{k}.py"
        if cand not in [f["name"] for f in pyfiles_list(account_id)]:
            return cand
        k += 1
    return name


def ensure_admin():
    """按 .env 配置保证管理员账号存在（密码以环境变量为准）。"""
    key = C.ADMIN_USER.lower()
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, db_name, mysql_user, mysql_pass FROM accounts WHERE username_key=%s", (key,))
            row = cur.fetchone()
            if row is None:
                db_name = db_name_for(C.ADMIN_USER)
                mu = "m_" + secrets.token_hex(8)
                mp = secrets.token_urlsafe(12)
                cur.execute(
                    "INSERT INTO accounts (username, username_key, kind, pass_hash, role, db_name, mysql_user, mysql_pass)"
                    " VALUES (%s,%s,'user',%s,'admin',%s,%s,%s)",
                    (C.ADMIN_USER, key, auth.hash_password(C.ADMIN_PASSWORD), db_name, mu, mp))
                account_id = cur.lastrowid
                _register_primary_db(cur, account_id, db_name)
            else:
                account_id, db_name, mu, mp = row
                cur.execute("UPDATE accounts SET pass_hash=%s, role='admin' WHERE id=%s",
                            (auth.hash_password(C.ADMIN_PASSWORD), account_id))
    finally:
        conn.close()
    _provision(db_name, mu, mp)


# ---------- 开通：独立库 + 受限账号 ----------

def _provision(db_name: str, mysql_user: str, mysql_pass: str):
    """幂等开通：建库、建账号、授权（只授这一个库）。"""
    conn = root_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {q_ident(db_name)} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute("CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s", (mysql_user, mysql_pass))
            cur.execute("ALTER USER %s@'%%' IDENTIFIED BY %s", (mysql_user, mysql_pass))
            cur.execute(f"GRANT ALL PRIVILEGES ON {q_ident(db_name)}.* TO %s@'%%' "
                        "WITH MAX_USER_CONNECTIONS 5", (mysql_user,))
    finally:
        conn.close()


def _db_exists(db_name: str) -> bool:
    conn = root_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name=%s", (db_name,))
            return cur.fetchone() is not None
    finally:
        conn.close()


def ensure_account_ready(account: dict):
    """登录时保证默认库/账号存在；库若被清掉则重建并重新赠送内置表。"""
    fresh = not _db_exists(account["db_name"])
    _provision(account["db_name"], account["mysql_user"], account["mysql_pass"])
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            _register_primary_db(cur, account["id"], account["db_name"])
    finally:
        conn.close()
    if fresh:
        community.seed_account_builtins(account["db_name"])


# ---------- 注册 / 登录 / 游客 ----------

def register(username: str, password: str, ip: str = "") -> dict:
    ok, msg = auth.validate_username(username)
    if not ok:
        raise AuthError(msg)
    ok, msg = auth.validate_password(password, username)
    if not ok:
        raise AuthError(msg)
    key = username.lower()
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM accounts WHERE username_key=%s", (key,))
            if cur.fetchone():
                raise AuthError("这个账号已被注册，换一个或直接登录")
            db_name = db_name_for(username)
            mu = "m_" + secrets.token_hex(8)
            mp = secrets.token_urlsafe(12)
            cur.execute(
                "INSERT INTO accounts (username, username_key, kind, pass_hash, role, db_name,"
                " mysql_user, mysql_pass, reg_ip, last_ip)"
                " VALUES (%s,%s,'user',%s,'user',%s,%s,%s,%s,%s)",
                (username, key, auth.hash_password(password), db_name, mu, mp, ip, ip))
            account_id = cur.lastrowid
            _register_primary_db(cur, account_id, db_name)
    finally:
        conn.close()
    account = get_account(account_id)
    ensure_account_ready(account)
    return account


def authenticate(username: str, password: str, ip: str = "") -> dict:
    key = (username or "").lower()
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, pass_hash FROM accounts WHERE username_key=%s AND kind='user'", (key,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row or not auth.verify_password(password or "", row[1]):
        raise AuthError("账号或密码不对")
    if ip:
        try:
            c2 = root_conn(C.META_DB)
            with c2.cursor() as cur2:
                cur2.execute("UPDATE accounts SET last_ip=%s WHERE id=%s", (ip, row[0]))
            c2.close()
        except Exception:
            pass
    account = get_account(row[0])
    ensure_account_ready(account)
    return account


def create_guest(ip: str = "") -> dict:
    suffix = secrets.token_hex(2)
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            username = f"游客{suffix}"
            db_name = "g_" + secrets.token_hex(6)
            mu = "m_" + secrets.token_hex(8)
            mp = secrets.token_urlsafe(12)
            cur.execute(
                "INSERT INTO accounts (username, username_key, kind, db_name, mysql_user,"
                " mysql_pass, reg_ip, last_ip) VALUES (%s,NULL,'guest',%s,%s,%s,%s,%s)",
                (username, db_name, mu, mp, ip, ip))
            account_id = cur.lastrowid
            _register_primary_db(cur, account_id, db_name)
    finally:
        conn.close()
    account = get_account(account_id)
    _provision(db_name, mu, mp)
    community.seed_account_builtins(db_name)
    return account


def get_account(account_id: int) -> dict:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, username, kind, role, db_name, mysql_user, mysql_pass, created_at
                           FROM accounts WHERE id=%s""", (account_id,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        raise AuthError("账号不存在")
    return {
        "id": r[0], "username": r[1], "kind": r[2], "role": r[3],
        "db_name": r[4], "mysql_user": r[5], "mysql_pass": r[6],
        "display": r[1] or "游客", "created_at": str(r[7]),
    }


# ---------- 会话（token） ----------

_touch_cache: dict[str, float] = {}
_touch_lock = threading.Lock()


def create_session(account_id: int) -> str:
    token = secrets.token_urlsafe(24)
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO sessions (token, account_id) VALUES (%s,%s)", (token, account_id))
    finally:
        conn.close()
    return token


def get_session(token: str) -> dict | None:
    if not token or len(token) > 64:
        return None
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT s.token, s.account_id,
                                  a.id, a.username, a.kind, a.role, a.db_name, a.mysql_user, a.mysql_pass
                           FROM sessions s JOIN accounts a ON a.id = s.account_id
                           WHERE s.token=%s""", (token,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    account = {
        "id": row[2], "username": row[3], "kind": row[4], "role": row[5],
        "db_name": row[6], "mysql_user": row[7], "mysql_pass": row[8],
        "display": row[3] or "游客",
    }
    now = time.monotonic()
    with _touch_lock:
        last = _touch_cache.get(token, 0)
        need = now - last > 60
        if need:
            _touch_cache[token] = now
    if need:
        try:
            conn = root_conn(C.META_DB)
            with conn.cursor() as cur:
                cur.execute("UPDATE sessions SET last_seen=NOW() WHERE token=%s", (token,))
            conn.close()
        except Exception:
            pass
    return {"token": token, "account": account}


def destroy_session(token: str):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE token=%s", (token,))
    finally:
        conn.close()
    with _touch_lock:
        _touch_cache.pop(token, None)


# ---------- 定时清理 ----------

def cleanup_pass():
    """1) 删除过期登录态 2) 回收 7 天未用的游客库。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM sessions WHERE last_seen < NOW() - INTERVAL %d DAY"
                        % C.SESSION_TTL_DAYS)
            cur.execute(f"""
                SELECT a.id, a.db_name, a.mysql_user FROM accounts a
                WHERE a.kind='guest'
                  AND a.created_at < NOW() - INTERVAL 1 DAY
                  AND NOT EXISTS (SELECT 1 FROM sessions s
                                  WHERE s.account_id=a.id
                                    AND s.last_seen > NOW() - INTERVAL %d DAY)
            """ % C.GUEST_TTL_DAYS)
            stale = cur.fetchall()
    finally:
        conn.close()

    for account_id, db_name, mysql_user in stale:
        try:
            c = root_conn(C.META_DB)
            extra_dbs = []
            with c.cursor() as cur:
                cur.execute("SELECT db_name FROM dbs WHERE account_id=%s AND primary_db=0",
                            (account_id,))
                extra_dbs = [r[0] for r in cur.fetchall()]
            c.close()
        except Exception:
            extra_dbs = []
        try:
            c = root_conn()
            with c.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {q_ident(db_name)}")
                for dn in extra_dbs:
                    cur.execute(f"DROP DATABASE IF EXISTS {q_ident(dn)}")
                    try:
                        cur.execute(f"REVOKE ALL PRIVILEGES ON {q_ident(dn)}.* FROM %s@'%%'",
                                    (mysql_user,))
                    except Exception:
                        pass
                cur.execute("DROP USER IF EXISTS %s@'%%'", (mysql_user,))
                try:
                    cur.execute("DELETE FROM dbs WHERE account_id=%s", (account_id,))
                except Exception:
                    pass
            c.close()
        except Exception:
            continue
        try:
            c = root_conn(C.META_DB)
            with c.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE account_id=%s", (account_id,))
                cur.execute("DELETE FROM accounts WHERE id=%s", (account_id,))
            c.close()
        except Exception:
            continue


def admin_list_users(kind: str = "user") -> list[dict]:
    """管理后台列表：kind=user 注册用户 / kind=guest 游客。含 IP 与库统计。"""
    kind = "guest" if kind == "guest" else "user"
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT a.id, a.username, a.kind, a.role, a.db_name, a.created_at,
                       MAX(s.last_seen) AS last_seen, COUNT(DISTINCT s.token) AS tokens,
                       a.reg_ip, a.last_ip,
                       (SELECT COUNT(*) FROM {q_ident(C.META_DB)}.dbs d
                         WHERE d.account_id=a.id) AS db_count
                FROM accounts a LEFT JOIN sessions s ON s.account_id=a.id
                WHERE a.kind=%s
                GROUP BY a.id ORDER BY MAX(s.last_seen) DESC, a.id DESC LIMIT 500
            """, (kind,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{
        "id": r[0], "username": r[1] or "游客", "kind": r[2], "role": r[3],
        "db": r[4], "createdAt": str(r[5]), "lastSeen": str(r[6]) if r[6] else "-",
        "sessions": int(r[7] or 0), "regIp": r[8] or "-", "lastIp": r[9] or "-",
        "dbCount": int(r[10] or 0),
    } for r in rows]


def admin_reset_password(username: str, new_password: str):
    if not auth.valid_password(new_password):
        raise AuthError("密码至少 4 位")
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE accounts SET pass_hash=%s WHERE username_key=%s AND kind='user'",
                        (auth.hash_password(new_password), username.lower()))
            if cur.rowcount == 0:
                raise AuthError("没有这个账号（游客无法重置密码）")
    finally:
        conn.close()


def admin_delete_user(account_id: int):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, kind, role, db_name, mysql_user FROM accounts WHERE id=%s",
                        (account_id,))
            row = cur.fetchone()
            if not row:
                raise AuthError("没有这个账号")
            account_id, kind, role, db_name, mysql_user = row
            if role == "admin":
                raise AuthError("不能删除管理员账号")
            cur.execute("SELECT db_name FROM dbs WHERE account_id=%s AND primary_db=0", (account_id,))
            extra_dbs = [r[0] for r in cur.fetchall()]
            cur.execute("DELETE FROM sessions WHERE account_id=%s", (account_id,))
            cur.execute("DELETE FROM dbs WHERE account_id=%s", (account_id,))
            cur.execute("DELETE FROM accounts WHERE id=%s", (account_id,))
    finally:
        conn.close()
    try:
        c = root_conn()
        with c.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {q_ident(db_name)}")
            for dn in extra_dbs:
                cur.execute(f"DROP DATABASE IF EXISTS {q_ident(dn)}")
                try:
                    cur.execute(f"REVOKE ALL PRIVILEGES ON {q_ident(dn)}.* FROM %s@'%%'",
                                (mysql_user,))
                except Exception:
                    pass
            cur.execute("DROP USER IF EXISTS %s@'%%'", (mysql_user,))
            try:
                cur.execute("DELETE FROM meta.sources WHERE db_name=%s", (db_name,))
                for dn in extra_dbs:
                    cur.execute("DELETE FROM meta.sources WHERE db_name=%s", (dn,))
            except Exception:
                pass
        c.close()
    except Exception:
        pass
