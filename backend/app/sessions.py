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
                    can_publish TINYINT(1) NOT NULL DEFAULT 0,
                    disabled TINYINT(1) NOT NULL DEFAULT 0,
                    last_login_at DATETIME NULL,
                    password_changed_at DATETIME NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            try:  # 旧库升级：发布到题库的权限
                cur.execute(f"ALTER TABLE {q_ident(C.META_DB)}.accounts "
                            "ADD COLUMN can_publish TINYINT(1) NOT NULL DEFAULT 0")
            except Exception:
                pass
            for _col, _def in (("disabled", "TINYINT(1) NOT NULL DEFAULT 0"),
                               ("last_login_at", "DATETIME NULL"),
                               ("password_changed_at", "DATETIME NULL"),
                               ("reg_ip", "VARCHAR(64) NULL"), ("last_ip", "VARCHAR(64) NULL")):
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
                CREATE TABLE IF NOT EXISTS {q_ident(C.META_DB)}.py_projects (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    name VARCHAR(32) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_account_name (account_id, name),
                    KEY idx_account (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.META_DB)}.py_files (
                    project_id BIGINT NOT NULL,
                    account_id BIGINT NOT NULL,
                    name VARCHAR(64) NOT NULL,
                    content MEDIUMTEXT,
                    uploaded TINYINT NOT NULL DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (project_id, name),
                    KEY idx_account (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 老库升级：补 project_id 列
            try:
                cur.execute(f"ALTER TABLE {q_ident(C.META_DB)}.py_files "
                            "ADD COLUMN project_id BIGINT NOT NULL DEFAULT 0")
            except Exception:
                pass
            try:
                cur.execute(f"ALTER TABLE {q_ident(C.META_DB)}.py_files "
                            "ADD COLUMN uploaded TINYINT NOT NULL DEFAULT 0")
            except Exception:
                pass
            # 把还没有项目的老文件放进各自的「默认项目」
            cur.execute(f"""SELECT DISTINCT account_id FROM {q_ident(C.META_DB)}.py_files
                             WHERE project_id=0""")
            for (acc_id,) in cur.fetchall():
                cur.execute(f"""SELECT id FROM {q_ident(C.META_DB)}.py_projects
                                 WHERE account_id=%s ORDER BY id LIMIT 1""", (acc_id,))
                prow = cur.fetchone()
                if prow:
                    pid = int(prow[0])
                else:
                    cur.execute(f"""INSERT INTO {q_ident(C.META_DB)}.py_projects
                                    (account_id, name) VALUES (%s,'默认项目')""", (acc_id,))
                    pid = int(cur.lastrowid)
                cur.execute(f"""UPDATE {q_ident(C.META_DB)}.py_files SET project_id=%s
                                 WHERE account_id=%s AND project_id=0""", (pid, acc_id))
            # 主键从 (account_id,name) 改为 (project_id,name)，不同项目可以同名
            try:
                cur.execute(f"""ALTER TABLE {q_ident(C.META_DB)}.py_files
                                DROP PRIMARY KEY,
                                ADD PRIMARY KEY (project_id, name),
                                ADD KEY idx_account (account_id)""")
            except Exception:
                pass
            # 以前版本给新账号预置过一段示例代码；现在编辑器一律空白，
            # 只清掉「一字未改的旧示例」，不影响学生自己写过的文件
            try:
                cur.execute(f"UPDATE {q_ident(C.META_DB)}.py_files SET content='' "
                            "WHERE content=%s", (PY_MAIN_SEED_OLD,))
            except Exception:
                pass
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
            # origin='drill' 是练习题的沙箱库，不在「我的数据库」里显示
            cur.execute("""SELECT db_name, primary_db, created_at FROM dbs
                           WHERE account_id=%s AND origin<>'drill'
                           ORDER BY primary_db DESC, created_at ASC""",
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
PYPROJECT_MAX = 10
PYPROJECT_NAME_MAX = 24

# 新账号的 main.py 只建一个空文件：编辑器不预填任何命令，全部由学生自己输入。
PY_MAIN_SEED = ""
# 旧版本预置过的示例原文，仅用于升级时把「没改过的示例」清空
PY_MAIN_SEED_OLD = '''\
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


def normalize_pyproject_name(name: str) -> str | None:
    s = re.sub(r"[\x00-\x1f\x7f]", "", str(name or ""))
    s = re.sub(r"\s+", " ", s).strip()
    if not s or len(s) > PYPROJECT_NAME_MAX:
        return None
    return s


def _project_row(cur, account_id: int, project_id: int | None = None):
    """取项目（不传则取第一个；没有就建默认项目），并校验归属。"""
    if project_id:
        cur.execute("SELECT id, name FROM py_projects WHERE id=%s AND account_id=%s",
                    (project_id, account_id))
        row = cur.fetchone()
        if not row:
            raise AuthError("Python 项目不存在")
        return row
    cur.execute("SELECT id, name FROM py_projects WHERE account_id=%s ORDER BY id LIMIT 1",
                (account_id,))
    row = cur.fetchone()
    if row:
        return row
    try:
        cur.execute("INSERT INTO py_projects (account_id, name) VALUES (%s,'默认项目')",
                    (account_id,))
        return (cur.lastrowid, "默认项目")
    except Exception:
        cur.execute("SELECT id, name FROM py_projects WHERE account_id=%s ORDER BY id LIMIT 1",
                    (account_id,))
        row = cur.fetchone()
        if not row:
            raise AuthError("Python 项目初始化失败")
        return row


def ensure_default_project(account_id: int) -> dict:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            row = _project_row(cur, account_id)
            return {"id": int(row[0]), "name": row[1]}
    finally:
        conn.close()


def resolve_project(account_id: int, project_id: int | None = None) -> int:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            return int(_project_row(cur, account_id, project_id)[0])
    finally:
        conn.close()


def pyprojects_list(account_id: int) -> list[dict]:
    conn = root_conn(C.META_DB)
    out = []
    try:
        with conn.cursor() as cur:
            _project_row(cur, account_id)     # 至少保证有一个项目
            cur.execute("""SELECT p.id, p.name, p.created_at, COUNT(f.name),
                                  COALESCE(MAX(f.updated_at), p.created_at)
                             FROM py_projects p
                             LEFT JOIN py_files f ON f.project_id=p.id
                            WHERE p.account_id=%s
                            GROUP BY p.id
                            ORDER BY p.id ASC""", (account_id,))
            for pid, name, created, cnt, updated in cur.fetchall():
                out.append({"id": int(pid), "name": name or "未命名项目",
                            "fileCount": int(cnt or 0),
                            "createdAt": str(created), "updatedAt": str(updated)})
    finally:
        conn.close()
    return out


def pyprojects_create(account_id: int, name: str) -> dict:
    nm = normalize_pyproject_name(name)
    if not nm:
        raise AuthError(f"项目名称不能为空，且最多 {PYPROJECT_NAME_MAX} 个字")
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM py_projects WHERE account_id=%s", (account_id,))
            if int(cur.fetchone()[0]) >= PYPROJECT_MAX:
                raise AuthError(f"最多创建 {PYPROJECT_MAX} 个项目")
            cur.execute("SELECT id FROM py_projects WHERE account_id=%s AND name=%s",
                        (account_id, nm))
            if cur.fetchone():
                raise AuthError("已经有同名项目了")
            cur.execute("INSERT INTO py_projects (account_id, name) VALUES (%s,%s)",
                        (account_id, nm))
            pid = int(cur.lastrowid)
            cur.execute("""INSERT IGNORE INTO py_files
                           (project_id, account_id, name, content)
                           VALUES (%s,%s,'main.py',%s)""", (pid, account_id, PY_MAIN_SEED))
    finally:
        conn.close()
    return {"id": pid, "name": nm, "fileCount": 1}


def pyprojects_rename(account_id: int, project_id: int, name: str) -> dict:
    nm = normalize_pyproject_name(name)
    if not nm:
        raise AuthError(f"项目名称不能为空，且最多 {PYPROJECT_NAME_MAX} 个字")
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM py_projects WHERE id=%s AND account_id=%s",
                        (project_id, account_id))
            if not cur.fetchone():
                raise AuthError("Python 项目不存在")
            cur.execute("""SELECT id FROM py_projects
                            WHERE account_id=%s AND name=%s AND id<>%s""",
                        (account_id, nm, project_id))
            if cur.fetchone():
                raise AuthError("已经有同名项目了")
            cur.execute("UPDATE py_projects SET name=%s, updated_at=NOW() WHERE id=%s",
                        (nm, project_id))
    finally:
        conn.close()
    return {"id": project_id, "name": nm}


def pyprojects_delete(account_id: int, project_id: int) -> dict:
    conn = root_conn(C.META_DB)
    row = None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM py_projects WHERE id=%s AND account_id=%s",
                        (project_id, account_id))
            if not cur.fetchone():
                raise AuthError("Python 项目不存在")
            cur.execute("DELETE FROM py_files WHERE project_id=%s AND account_id=%s",
                        (project_id, account_id))
            cur.execute("DELETE FROM py_projects WHERE id=%s", (project_id,))
            cur.execute("SELECT id, name FROM py_projects WHERE account_id=%s ORDER BY id LIMIT 1",
                        (account_id,))
            row = cur.fetchone()
            if not row:
                cur.execute("INSERT INTO py_projects (account_id, name) VALUES (%s,'默认项目')",
                            (account_id,))
                row = (cur.lastrowid, "默认项目")
    finally:
        conn.close()
    return {"ok": True, "nextProjectId": int(row[0]), "nextProjectName": row[1]}


def pyfiles_list(account_id: int, project_id: int | None = None) -> list[dict]:
    conn = root_conn(C.META_DB)
    result = []
    try:
        with conn.cursor() as cur:
            pid = int(_project_row(cur, account_id, project_id)[0])
            cur.execute("""SELECT name, content, updated_at, uploaded FROM py_files
                           WHERE project_id=%s
                           ORDER BY updated_at DESC, name ASC""", (pid,))
            rows = cur.fetchall()
            if not rows:
                cur.execute("""INSERT IGNORE INTO py_files
                               (project_id, account_id, name, content)
                               VALUES (%s,%s,'main.py',%s)""", (pid, account_id, PY_MAIN_SEED))
                cur.execute("""SELECT name, content, updated_at, uploaded FROM py_files
                               WHERE project_id=%s
                               ORDER BY updated_at DESC, name ASC""", (pid,))
                rows = cur.fetchall()
            for name, content, updated_at, uploaded in rows:
                result.append({"name": name, "size": len((content or "").encode("utf-8")),
                               "updatedAt": str(updated_at), "uploaded": bool(uploaded),
                               "projectId": pid})
    finally:
        conn.close()
    return result


def pyfiles_get(account_id: int, name: str, project_id: int | None = None) -> dict | None:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            pid = int(_project_row(cur, account_id, project_id)[0])
            cur.execute("""SELECT content, updated_at FROM py_files
                            WHERE project_id=%s AND name=%s""", (pid, name))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"name": name, "content": row[0] or "", "updatedAt": str(row[1])}


def pyfiles_contents(account_id: int, project_id: int | None = None) -> dict[str, str]:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            pid = int(_project_row(cur, account_id, project_id)[0])
            cur.execute("SELECT name, content FROM py_files WHERE project_id=%s", (pid,))
            return {name: content or "" for name, content in cur.fetchall()}
    finally:
        conn.close()


def pyfiles_save(account_id: int, name: str, content: str, uploaded: bool = False,
                 project_id: int | None = None):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            pid = int(_project_row(cur, account_id, project_id)[0])
            # 更新已有文件时不改动 uploaded 标记：编辑上传的临时文件不会把它变成永久文件
            cur.execute("""INSERT INTO py_files
                           (project_id, account_id, name, content, uploaded)
                           VALUES (%s,%s,%s,%s,%s)
                           ON DUPLICATE KEY UPDATE content=VALUES(content),
                           updated_at=CURRENT_TIMESTAMP""",
                        (pid, account_id, name, content, 1 if uploaded else 0))
    finally:
        conn.close()


def pyfiles_delete_uploaded(account_id: int, project_id: int | None = None) -> int:
    """删除临时 py 文件；传项目只清该项目，否则清该账号所有项目。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            if project_id:
                pid = int(_project_row(cur, account_id, project_id)[0])
                cur.execute("DELETE FROM py_files WHERE project_id=%s AND uploaded=1", (pid,))
            else:
                cur.execute("DELETE FROM py_files WHERE account_id=%s AND uploaded=1", (account_id,))
            return cur.rowcount
    finally:
        conn.close()


def pyfiles_delete(account_id: int, name: str, project_id: int | None = None):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            pid = int(_project_row(cur, account_id, project_id)[0])
            cur.execute("DELETE FROM py_files WHERE project_id=%s AND name=%s", (pid, name))
    finally:
        conn.close()


def pyfiles_unique_name(account_id: int, base: str, existing: set[str] | None = None,
                        project_id: int | None = None) -> str:
    name = normalize_pyfile_name(base) or "main.py"
    if existing is None:
        existing = {f["name"].casefold() for f in pyfiles_list(account_id, project_id)}
    if name.casefold() not in existing:
        return name
    stem = name[:-3]
    k = 2
    while True:
        suffix = f"_{k}.py"
        cand = f"{stem[:40 - len(suffix)]}{suffix}"
        if cand.casefold() not in existing:
            return cand
        k += 1


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
    try:
        from . import users as _users
        _users.log(account_id, username, ip, "register", True)
    except Exception:
        pass
    return account


def authenticate(username: str, password: str, ip: str = "") -> dict:
    key = (username or "").lower()
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, pass_hash, disabled FROM accounts"
                        " WHERE username_key=%s AND kind='user'", (key,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row or not auth.verify_password(password or "", row[1]):
        try:
            from . import users as _users
            _users.log(row[0] if row else None, username, ip, "login_fail", False,
                       "账号或密码不对")
        except Exception:
            pass
        raise AuthError("账号或密码不对")
    if row[2]:
        try:
            from . import users as _users
            _users.log(row[0], username, ip, "login_fail", False, "账号已被禁用")
        except Exception:
            pass
        raise AuthError("账号已被禁用，请联系老师")
    if ip:
        try:
            c2 = root_conn(C.META_DB)
            with c2.cursor() as cur2:
                cur2.execute("UPDATE accounts SET last_ip=%s, last_login_at=NOW() WHERE id=%s",
                             (ip, row[0]))
            c2.close()
        except Exception:
            pass
    else:
        try:
            c3 = root_conn(C.META_DB)
            with c3.cursor() as cur3:
                cur3.execute("UPDATE accounts SET last_login_at=NOW() WHERE id=%s", (row[0],))
            c3.close()
        except Exception:
            pass
    try:
        from . import users as _users
        _users.log(row[0], username, ip, "login_ok", True)
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
            cur.execute("""SELECT id, username, kind, role, db_name, mysql_user, mysql_pass,
                                  created_at, can_publish, disabled
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
        "can_publish": bool(r[8]), "disabled": bool(r[9]),
    }


# ---------- 会话（token） ----------

_touch_cache: dict[str, float] = {}
_touch_lock = threading.Lock()


MAX_SESSIONS_PER_ACCOUNT = 10   # 同一账号最多保留的并发登录（超出踢最旧）


def create_session(account_id: int) -> str:
    token = secrets.token_urlsafe(24)
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO sessions (token, account_id) VALUES (%s,%s)", (token, account_id))
            # 防止会话无限堆积：只保留最近 N 个（其他设备会被登出）
            cur.execute("""DELETE FROM sessions WHERE account_id=%s AND token NOT IN (
                               SELECT token FROM (
                                   SELECT token FROM sessions WHERE account_id=%s
                                   ORDER BY last_seen DESC, created_at DESC, token DESC
                                   LIMIT %s
                               ) AS keep
                           )""", (account_id, account_id, MAX_SESSIONS_PER_ACCOUNT))
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
                                  a.id, a.username, a.kind, a.role, a.db_name, a.mysql_user, a.mysql_pass,
                                  a.can_publish, a.disabled
                           FROM sessions s JOIN accounts a ON a.id = s.account_id
                           WHERE s.token=%s
                             AND a.disabled=0
                             AND (a.kind <> 'guest' OR s.created_at >= NOW() - INTERVAL %s DAY)""",
                        (token, C.GUEST_SESSION_TTL_DAYS))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    account = {
        "id": row[2], "username": row[3], "kind": row[4], "role": row[5],
        "db_name": row[6], "mysql_user": row[7], "mysql_pass": row[8],
        "can_publish": bool(row[9]), "disabled": bool(row[10]),
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


def kill_other_sessions(account_id: int, keep_token: str = "") -> int:
    """把该账号除 keep_token 之外的所有会话删掉，返回删除数量。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            if keep_token:
                cur.execute("DELETE FROM sessions WHERE account_id=%s AND token<>%s",
                            (account_id, keep_token))
            else:
                cur.execute("DELETE FROM sessions WHERE account_id=%s", (account_id,))
            n = cur.rowcount
    finally:
        conn.close()
    return int(n or 0)


def destroy_session(token: str):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE token=%s", (token,))
    finally:
        conn.close()
    with _touch_lock:
        _touch_cache.pop(token, None)


def logout_cleanup(token: str):
    """登出：先清掉该会话账号上传的临时 py 文件，再销毁会话。"""
    if not token or len(token) > 64:
        return
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id FROM sessions WHERE token=%s", (token,))
            row = cur.fetchone()
            if row:
                cur.execute("DELETE FROM py_files WHERE account_id=%s AND uploaded=1", (row[0],))
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
            cur.execute("""DELETE s FROM sessions s
                           JOIN accounts a ON a.id=s.account_id
                           WHERE a.kind='guest'
                             AND s.created_at < NOW() - INTERVAL %s DAY""",
                        (C.GUEST_SESSION_TTL_DAYS,))
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
                cur.execute("DELETE FROM py_files WHERE account_id=%s", (account_id,))
                cur.execute("DELETE FROM py_projects WHERE account_id=%s", (account_id,))
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
                       a.can_publish,
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
        "db": r[4], "createdAt": str(r[5]), "canPublish": bool(r[6]),
        "lastSeen": str(r[7]) if r[7] else "-",
        "sessions": int(r[8] or 0), "regIp": r[9] or "-", "lastIp": r[10] or "-",
        "dbCount": int(r[11] or 0),
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


def set_publish_permission(account_id: int, allow: bool):
    """管理员给/收回「发布到题库」的权限。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM accounts WHERE id=%s", (account_id,))
            row = cur.fetchone()
            if not row:
                raise AuthError("没有这个账号")
            if row[0] == "admin":
                raise AuthError("管理员默认就有发布权限，不用单独开通")
            cur.execute("UPDATE accounts SET can_publish=%s WHERE id=%s",
                        (1 if allow else 0, account_id))
    finally:
        conn.close()
    return {"id": account_id, "canPublish": bool(allow)}


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
            cur.execute("DELETE FROM py_files WHERE account_id=%s", (account_id,))
            cur.execute("DELETE FROM py_projects WHERE account_id=%s", (account_id,))
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
