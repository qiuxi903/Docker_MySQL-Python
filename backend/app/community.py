"""社区：以「数据库」为单元的资源共享。

条目类型（kind）：
  db  — 一个数据库：内置教学库（bjpowernode 三表）、学生发布的表（单表库）、
        上传的 .sql 整库脚本（解析出表清单，点开详情可见）
  py  — Python 代码文件（.py，可打开到编辑器 / 下载）
  csv / xlsx — 表格文件（一键导入成表）

db 条目分两种数据形态：
  结构化（内置/发布）：data_gz = JSON {tables: [{name, ddl, rows}]}   → 可整库导入，也可按表导入
  脚本（.sql 上传）  ：data_gz = 原始脚本字节                           → 整库导入（执行脚本）
"""
import base64
import json
import re
import secrets
import zlib
from pathlib import Path

import pymysql

from . import config as C
from .db import conv_value, q_ident, root_conn, user_conn
from .sqlrun import split_sql

SEED_FILE = Path(__file__).parent / "seed" / "bjpowernode.sql"
SCRATCH_DB = "community_seed_tmp"

KIND_LABEL = {"db": "数据库", "py": "Python代码", "csv": "表格", "xlsx": "Excel"}
FILE_CAPS = {"py": 256 * 1024, "sql": 8 * 1024 * 1024, "csv": 8 * 1024 * 1024, "xlsx": 8 * 1024 * 1024}


class CommunityError(Exception):
    pass


# ---------- 存储初始化 ----------

def _init_store():
    conn = root_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)}.items (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    kind VARCHAR(16) NOT NULL,
                    title VARCHAR(128) NOT NULL,
                    name VARCHAR(64) NOT NULL DEFAULT '',
                    filename VARCHAR(255) NOT NULL DEFAULT '',
                    uploader VARCHAR(64) NOT NULL DEFAULT '内置',
                    builtin TINYINT(1) NOT NULL DEFAULT 0,
                    size INT NOT NULL DEFAULT 0,
                    rows_count INT NOT NULL DEFAULT 0,
                    cols_json TEXT,
                    data_gz LONGTEXT,
                    downloads INT NOT NULL DEFAULT 0,
                    listed TINYINT(1) NOT NULL DEFAULT 1,
                    share_code VARCHAR(16) NULL,
                    share_name VARCHAR(64) NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_kind (kind),
                    KEY idx_created (created_at),
                    UNIQUE KEY uk_code (share_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            try:  # 旧库升级
                cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.items "
                            "ADD COLUMN listed TINYINT(1) NOT NULL DEFAULT 1")
            except Exception:
                pass
            try:  # 旧库升级：补分享两列
                cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.items "
                            "ADD COLUMN share_code VARCHAR(16) NULL")
                cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.items "
                            "ADD COLUMN share_name VARCHAR(64) NULL")
                cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.items "
                            "ADD UNIQUE KEY uk_code (share_code)")
            except Exception:
                pass
    finally:
        conn.close()


def _pack(data: bytes) -> str:
    return base64.b64encode(zlib.compress(data)).decode("ascii")


def _unpack(payload: str) -> bytes:
    return zlib.decompress(base64.b64decode(payload))


# ---------- 内置教学数据库种子 ----------

def ensure_builtin_seed():
    """首次启动：bjpowernode.sql 在临时库真实执行，快照成一个内置「教学数据库」。"""
    _init_store()
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM items WHERE builtin=1")
            if cur.fetchone()[0] > 0:
                return
    finally:
        conn.close()

    sql_text = SEED_FILE.read_text(encoding="utf-8")
    conn = root_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {q_ident(SCRATCH_DB)}")
            cur.execute(f"CREATE DATABASE {q_ident(SCRATCH_DB)} CHARACTER SET utf8mb4")
        conn.select_db(SCRATCH_DB)
        tables = []
        with conn.cursor() as cur:
            for stmt in split_sql(sql_text):
                cur.execute(stmt)
            cur.execute("SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema=%s ORDER BY table_name", (SCRATCH_DB,))
            names = [r[0] for r in cur.fetchall()]
            for name in names:
                cur.execute("SHOW CREATE TABLE " + q_ident(name))
                ddl = cur.fetchone()[1]
                cur.execute(f"SELECT * FROM {q_ident(name)}")
                cols = [d[0] for d in cur.description]
                rows = [[conv_value(v) for v in r] for r in cur.fetchall()]
                tables.append({
                    "name": name,
                    "ddl": ddl,
                    "cols": cols,
                    "rows": rows,
                })
        with root_conn(C.COMMUNITY_DB).cursor() as cur:
            _put_db(cur, title="教学数据库（bjpowernode）", name="bjpowernode",
                    uploader="内置", builtin=1, tables=tables, share_name="bjpowernode")
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {q_ident(SCRATCH_DB)}")
        except Exception:
            pass
        conn.close()


def _put_db(cur, *, title, name="", filename="", uploader="内置", builtin=0,
            tables=None, script=None, share_name=None, share_code=None, listed=1):
    """写入 kind=db 条目。tables=结构化表清单；script=原始 .sql 字节（二选一）。"""
    if script is not None:
        payload = _pack(script)
        names = parse_script_tables(script.decode("utf-8", "replace"))
        summary = json.dumps([{"name": n, "rows": None} for n in names], ensure_ascii=False)
        rows_count = len(names)
    else:
        payload = _pack(json.dumps({"tables": tables or []}, ensure_ascii=False, default=str).encode("utf-8"))
        summary = json.dumps([{"name": t["name"], "rows": len(t.get("rows") or [])}
                              for t in (tables or [])], ensure_ascii=False)
        rows_count = len(tables or [])
    cur.execute(f"""
        INSERT INTO {q_ident(C.COMMUNITY_DB)}.items
            (kind, title, name, filename, uploader, builtin, size, rows_count, cols_json, data_gz,
             share_code, share_name, listed)
        VALUES ('db',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (title, name, filename, uploader, builtin, rows_count, rows_count,
          summary, payload, share_code or secrets.token_hex(4), share_name, listed))


def _put_file(cur, *, kind, title, filename, uploader, data: bytes):
    cur.execute(f"""
        INSERT INTO {q_ident(C.COMMUNITY_DB)}.items
            (kind, title, filename, uploader, size, data_gz)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (kind, title, filename, uploader, len(data), _pack(data)))


# ---------- 新账号自动送内置表 ----------

def seed_account_builtins(db_name: str):
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT data_gz FROM items WHERE builtin=1 AND kind='db'")
            builtins = cur.fetchall()
    finally:
        conn.close()

    tconn = root_conn(db_name)
    try:
        with tconn.cursor() as cur:
            cur.execute("SHOW TABLES")
            existing = {r[0] for r in cur.fetchall()}
            for (data_gz,) in builtins:
                data = json.loads(_unpack(data_gz).decode("utf-8"))
                for t in data.get("tables", []):
                    if t["name"] in existing:
                        continue
                    cur.execute(t["ddl"])
                    rows = t.get("rows") or []
                    if rows:
                        cols = t.get("cols") or []
                        ph = ", ".join(["%s"] * len(cols))
                        for i in range(0, len(rows), 500):
                            cur.executemany(f"INSERT INTO {q_ident(t['name'])} VALUES ({ph})",
                                            rows[i : i + 500])
        tconn.commit()
    finally:
        tconn.close()


# ---------- 浏览 ----------

def list_items() -> list[dict]:
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, kind, title, name, filename, uploader, builtin,
                                  size, rows_count, cols_json, downloads, created_at,
                                  share_name
                           FROM items WHERE listed=1
                           ORDER BY builtin DESC,
                                    IF(builtin=1, id, 1000000000 - id) ASC
                           LIMIT 200""")
            out = []
            for r in cur.fetchall():
                out.append({
                    "id": r[0], "kind": r[1], "title": r[2], "name": r[3],
                    "filename": r[4], "uploader": r[5], "builtin": bool(r[6]),
                    "size": r[7], "rows": r[8],
                    "tables": json.loads(r[9] or "[]"),
                    "downloads": r[10], "createdAt": str(r[11]),
                    "shareName": r[12],
                })
            return out
    finally:
        conn.close()


def _get_item(cur, item_id: int) -> dict:
    cur.execute("""SELECT id, kind, title, name, filename, uploader, builtin,
                          data_gz, rows_count, cols_json, share_name, share_code
                   FROM items WHERE id=%s""", (item_id,))
    r = cur.fetchone()
    if not r:
        raise CommunityError("这份资源不存在或已被删除")
    return {
        "id": r[0], "kind": r[1], "title": r[2], "name": r[3], "filename": r[4],
        "uploader": r[5], "builtin": bool(r[6]), "data_gz": r[7],
        "rows_count": r[8], "tables": json.loads(r[9] or "[]"),
        "shareName": r[10] or r[3], "shareCode": r[11],
    }


def get_detail(item_id: int) -> dict:
    """数据库条目的详情：包含哪些表。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            it = _get_item(cur, item_id)
    finally:
        conn.close()
    structured = it["kind"] == "db" and it["filename"] == ""
    is_script = it["kind"] == "db" and it["filename"] != ""
    return {
        "id": it["id"], "kind": it["kind"], "title": it["title"], "name": it["name"],
        "uploader": it["uploader"], "builtin": it["builtin"],
        "structured": structured,
        "isScript": is_script,
        "tables": it["tables"] if it["kind"] == "db" else None,
        "filename": it["filename"], "size": it["rows_count"],
        "shareName": it["shareName"], "shareCode": it["shareCode"],
    }


def get_by_code(code: str) -> dict:
    """通过分享码取数据库详情（分享链接入口）。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM items WHERE share_code=%s AND kind='db'", (code,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        raise CommunityError("分享链接不存在或已失效")
    return get_detail(r[0])


# ---------- 发布 / 上传 ----------

def publish_table(db_name: str, mysql_user: str, mysql_pass: str, table: str, uploader: str,
                  account_id: int | None = None) -> dict:
    """把自己空间里的一张表发布为社区的单表数据库。"""
    from .db import valid_ident

    if account_id is not None:
        from . import sessions as _sessions

        if _sessions.table_from_community(account_id, table):
            raise CommunityError(
                f"表 {table} 来自社区下载，不能原样回传社区。"
                f"可以分享你自己创作的表。")
    if not valid_ident(table):
        raise CommunityError("表名不合法")
    uconn = user_conn(db_name, mysql_user, mysql_pass)
    try:
        with uconn.cursor() as cur:
            cur.execute("SHOW TABLES")
            if table not in {r[0] for r in cur.fetchall()}:
                raise CommunityError(f"表 `{table}` 不存在")
            cur.execute("SHOW CREATE TABLE " + q_ident(table))
            ddl = cur.fetchone()[1]
            cur.execute(f"SELECT * FROM {q_ident(table)} LIMIT %s", (C.SHARE_ROWS_MAX,))
            cols = [d[0] for d in cur.description]
            rows = [[conv_value(v) for v in r] for r in cur.fetchall()]
            cur.execute(f"SELECT COUNT(*) FROM {q_ident(table)}")
            total = cur.fetchone()[0]
    finally:
        uconn.close()
    if len(rows) >= C.SHARE_ROWS_MAX and total > C.SHARE_ROWS_MAX:
        raise CommunityError(f"表太大（{total} 行），社区最多分享 {C.SHARE_ROWS_MAX} 行")

    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM items WHERE uploader=%s", (uploader,))
            if cur.fetchone()[0] >= 50:
                raise CommunityError("每人最多分享 50 份资源，可先删除旧的")
            cur.execute("SELECT id, share_code FROM items WHERE uploader=%s AND kind='db' AND name=%s",
                        (uploader, table))
            old = cur.fetchone()
            if old:
                cur.execute("DELETE FROM items WHERE id=%s", (old[0],))
            _put_db(cur, title=table, name=table, uploader=uploader,
                    tables=[{"name": table, "ddl": ddl, "cols": cols, "rows": rows}],
                    share_name=table, share_code=old[1] if old else None)
        conn.commit()
    finally:
        conn.close()
    return {"name": table, "tables": 1}


def upload_file(uploader: str, filename: str, data: bytes, title: str = "") -> dict:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in FILE_CAPS:
        raise CommunityError("仅支持 .sql / .py / .csv / .xlsx 文件")
    if len(data) > FILE_CAPS[ext]:
        cap = FILE_CAPS[ext] // 1024
        raise CommunityError(f"文件超过 {cap}KB 上限")
    if len(data) == 0:
        raise CommunityError("文件是空的")
    kind = "db" if ext == "sql" else ext  # .sql 上传即为「数据库」条目
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM items WHERE uploader=%s", (uploader,))
            if cur.fetchone()[0] >= 50:
                raise CommunityError("每人最多分享 50 份资源，可先删除旧的")
            if kind == "db":
                _put_db(cur, title=(title or filename)[:120], filename=filename,
                        uploader=uploader, script=data)
            else:
                _put_file(cur, kind=kind, title=(title or filename)[:120],
                          filename=filename, uploader=uploader, data=data)
        conn.commit()
        item_id = cur.lastrowid
    finally:
        conn.close()
    return {"id": item_id, "kind": kind, "size": len(data)}


def parse_script_tables(text: str) -> list[str]:
    """从 SQL 脚本里解析 CREATE TABLE 的表名（按出现顺序去重）。"""
    names = []
    for stmt in split_sql(text):
        m = re.match(
            r"CREATE\s+(?:TEMPORARY\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?([\w\u4e00-\u9fff-]+)",
            stmt, re.I)
        if m and m.group(1).lower() not in [n.lower() for n in names]:
            names.append(m.group(1))
    return names


# ---------- 导入 / 下载 / 打开 / 删除 ----------

def _import_structured_table(uconn, t, overwrite):
    name = t["name"]
    with uconn.cursor() as cur:
        cur.execute("SHOW TABLES")
        existing = {r[0] for r in cur.fetchall()}
        if name in existing:
            if not overwrite:
                return False  # 跳过
            cur.execute(f"DROP TABLE {q_ident(name)}")
        cur.execute(t["ddl"])
        rows = t.get("rows") or []
        if rows:
            cols = t.get("cols") or []
            ph = ", ".join(["%s"] * len(cols))
            for i in range(0, len(rows), 500):
                cur.executemany(f"INSERT INTO {q_ident(name)} VALUES ({ph})",
                                rows[i : i + 500])
    return True


def import_item(item_id: int, account: dict, target_db: str,
                overwrite: bool, table: str | None = None, has_header: bool = True,
                new_db_name: str | None = None) -> dict:
    """导入社区资源。

    - db 条目整库导入：在本账号名下创建一个【独立的新数据库】并灌入全部表
      （权限只授予导入者本人 → 仅导入者可访问），返回 newDb
    - db 条目按表导入 / csv / xlsx：把表导入到 target_db（当前选中的库）
    - py 条目：不支持导入
    """
    from . import importer, sessions as _sessions

    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            it = _get_item(cur, item_id)
            data_bytes = _unpack(it["data_gz"]) if it["kind"] in ("db", "csv", "xlsx", "py") else b""
    finally:
        conn.close()

    kind = it["kind"]

    # ---- 数据库条目 ----
    if kind == "db":
        is_script = it["filename"] != ""
        if table:
            if is_script:
                raise CommunityError("脚本型数据库不支持按表导入，请整库导入")
            uconn = user_conn(target_db, account["mysql_user"], account["mysql_pass"])
            try:
                data = json.loads(_unpack(it["data_gz"]).decode("utf-8"))
                t = next((t for t in data.get("tables", []) if t["name"] == table), None)
                if not t:
                    raise CommunityError("这个表不在此资源里")
                with uconn.cursor() as cur:
                    ok = _import_structured_table(uconn, t, overwrite)
                uconn.commit()
            except pymysql.MySQLError as e:
                try:
                    uconn.rollback()
                except Exception:
                    pass
                msg = e.args[1] if len(e.args) > 1 else str(e)
                raise CommunityError(f"导入失败：{msg}") from e
            finally:
                uconn.close()
            _inc_download(item_id)
            _sessions.add_imported_tables(account["id"], target_db, [table])
            return {"imported": [table] if ok else [], "skipped": [] if ok else [table]}

        # ---- 整库导入：创建独立新库（仅导入者可访问；来源标记为社区，禁止原样回传） ----
        base = _sessions.sanitize_db_name(new_db_name or it["shareName"] or it["name"] or it["title"])
        new_db = _sessions.create_user_db_unique(account, base or "imported_db",
                                                 origin="community")

        if is_script:
            from .sqlrun import run_sql

            run_sql(new_db, account["mysql_user"], account["mysql_pass"],
                    data_bytes.decode("utf-8", "replace"), owned_dbs=[new_db])
            _inc_download(item_id)
            return {"imported": [], "skipped": [], "script": True, "newDb": new_db}

        data = json.loads(_unpack(it["data_gz"]).decode("utf-8"))
        tables = data.get("tables", [])
        uconn = user_conn(new_db, account["mysql_user"], account["mysql_pass"])
        try:
            with uconn.cursor() as cur:
                for t in tables:
                    cur.execute(t["ddl"])
                    rows = t.get("rows") or []
                    if rows:
                        cols = t.get("cols") or []
                        ph = ", ".join(["%s"] * len(cols))
                        for i in range(0, len(rows), 500):
                            cur.executemany(f"INSERT INTO {q_ident(t['name'])} VALUES ({ph})",
                                            rows[i : i + 500])
            uconn.commit()
        except pymysql.MySQLError as e:
            try:
                uconn.rollback()
            except Exception:
                pass
            msg = e.args[1] if len(e.args) > 1 else str(e)
            raise CommunityError(f"导入失败：{msg}") from e
        finally:
            uconn.close()
        _inc_download(item_id)
        _sessions.add_imported_tables(account["id"], new_db, [t["name"] for t in tables])
        return {"imported": [t["name"] for t in tables], "skipped": [], "newDb": new_db}

    # ---- Python 文件 ----
    if kind == "py":
        raise CommunityError("Python 代码请用「打开到编辑器」或下载后运行")

    # ---- 表格文件（csv / xlsx）----
    stem = it["filename"].rsplit(".", 1)[0] if it["filename"] else it["title"]
    table = sanitize_table(stem)
    if kind == "csv":
        importer.import_csv(db_name, mysql_user, mysql_pass, table, data_bytes,
                            has_header, overwrite, source_name=it["filename"])
    else:
        importer.import_xlsx(db_name, mysql_user, mysql_pass, table, data_bytes,
                             has_header, overwrite, source_name=it["filename"])
    _inc_download(item_id)
    return {"imported": [table], "skipped": []}


def sanitize_table(stem: str) -> str:
    t = re.sub(r"[^\w\u4e00-\u9fff-]", "_", stem or "", flags=re.UNICODE)[:60].strip("_")
    if not t:
        t = "community_import"
    if t[0].isdigit():
        t = "t" + t
    return t


def publish_database(db_name: str, mysql_user: str, mysql_pass: str, uploader: str,
                     account_id: int | None = None, share_name: str | None = None,
                     public: bool = True) -> dict:
    """发布数据库。

    public=True  → 上架到社区广场（所有人可见）
    public=False → 只生成私有分享链接（不出现在社区列表）
    """
    """把自己的整个数据库（全部表）发布为一个社区数据库条目。"""
    if account_id is not None:
        from . import sessions as _sessions

        if _sessions.db_origin(account_id, db_name) == "community":
            raise CommunityError(
                f"数据库 {db_name} 来自社区下载，不能原样回传社区。"
                f"可以分享你自己新建或创作的库。")
    uconn = user_conn(db_name, mysql_user, mysql_pass)
    tables = []
    try:
        with uconn.cursor() as cur:
            cur.execute("SHOW TABLES")
            names = [r[0] for r in cur.fetchall()]
            if not names:
                raise CommunityError("这个库里没有表，没什么可发布的")
            if len(names) > 50:
                raise CommunityError("库里的表超过 50 张，无法整库发布")
            for name in names:
                cur.execute("SHOW CREATE TABLE " + q_ident(name))
                ddl = cur.fetchone()[1]
                cur.execute(f"SELECT * FROM {q_ident(name)} LIMIT %s", (C.SHARE_ROWS_MAX,))
                cols = [d[0] for d in cur.description]
                rows = [[conv_value(v) for v in r] for r in cur.fetchall()]
                cur.execute(f"SELECT COUNT(*) FROM {q_ident(name)}")
                total = cur.fetchone()[0]
                if len(rows) >= C.SHARE_ROWS_MAX and total > C.SHARE_ROWS_MAX:
                    raise CommunityError(f"表 {name} 太大（{total} 行），无法整库发布")
                tables.append({"name": name, "ddl": ddl, "cols": cols, "rows": rows})
    finally:
        uconn.close()

    conn = root_conn(C.COMMUNITY_DB)
    new_code = secrets.token_hex(4)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM items WHERE uploader=%s", (uploader,))
            if cur.fetchone()[0] >= 50:
                raise CommunityError("每人最多分享 50 份资源，可先删除旧的")
            listed = 1 if public else 0
            cur.execute("SELECT id, share_code FROM items WHERE uploader=%s AND kind='db'"
                        " AND name=%s AND listed=%s", (uploader, db_name, listed))
            old = cur.fetchone()
            if old:
                new_code = old[1] or new_code  # 重复分享保持链接不变
                cur.execute("DELETE FROM items WHERE id=%s", (old[0],))
            _put_db(cur, title=db_name, name=db_name, uploader=uploader, tables=tables,
                    share_name=share_name or db_name, share_code=new_code, listed=listed)
        conn.commit()
    finally:
        conn.close()
    return {"name": db_name, "tables": len(tables), "shareCode": new_code}


def export_database(db_name: str, mysql_user: str, mysql_pass: str, max_rows: int = 1000) -> bytes:
    """把一个数据库导出为 .sql 文本（DROP+建表+INSERT），供下载。"""
    conn = user_conn(db_name, mysql_user, mysql_pass)
    lines = [f"-- 导出自 SQL·Py 课堂实验室 · 数据库 {db_name}",
             "SET NAMES utf8mb4;", ""]
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            names = [r[0] for r in cur.fetchall()]
            for name in names:
                cur.execute("SHOW CREATE TABLE " + q_ident(name))
                ddl = cur.fetchone()[1]
                lines.append(f"-- 表 {name}")
                lines.append(f"DROP TABLE IF EXISTS {q_ident(name)};")
                lines.append(ddl.rstrip(";") + ";")
                cur.execute(f"SELECT * FROM {q_ident(name)} LIMIT %s", (max_rows,))
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                if rows:
                    cols_sql = ", ".join(q_ident(c) for c in cols)
                    for i in range(0, len(rows), 100):
                        chunk = rows[i : i + 100]
                        vals = ", ".join(
                            "(" + ", ".join(conn.literal(v) for v in r) + ")" for r in chunk)
                        lines.append(f"INSERT INTO {q_ident(name)} ({cols_sql}) VALUES {vals};")
                lines.append("")
    finally:
        conn.close()
    return ("\n".join(lines)).encode("utf-8")


def get_file(item_id: int) -> tuple[str, bytes]:
    """下载资源。数据库条目：脚本给原文件；结构化库生成 .sql 导出。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            it = _get_item(cur, item_id)
            data = _unpack(it["data_gz"])
            _bump(cur, item_id)
        conn.commit()
    finally:
        conn.close()
    if it["kind"] == "db":
        fname = it["filename"] or (it["name"] or it["title"]) + ".sql"
        if it["filename"]:
            return fname, data
        # 结构化库 → 生成 .sql 文本
        tables = json.loads(data.decode("utf-8")).get("tables", [])
        lines = [f"-- 导出自社区 · {it['title']}", "SET NAMES utf8mb4;", ""]
        for t in tables:
            lines.append(f"-- 表 {t['name']}")
            lines.append(f"DROP TABLE IF EXISTS {q_ident(t['name'])};")
            lines.append(t["ddl"].rstrip(";") + ";")
            for r in t.get("rows") or []:
                vals = ", ".join("NULL" if v is None else
                                 ("'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'")
                                 for v in r)
                lines.append(f"INSERT INTO {q_ident(t['name'])} VALUES ({vals});")
            lines.append("")
        return fname, ("\n".join(lines)).encode("utf-8")
    return it["filename"] or (it["title"] + "." + it["kind"]), data


def get_py_code(item_id: int) -> tuple[str, str]:
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            it = _get_item(cur, item_id)
            if it["kind"] != "py":
                raise CommunityError("只有 Python 代码可以打开到编辑器")
            code = _unpack(it["data_gz"]).decode("utf-8", "replace")
            _bump(cur, item_id)
        conn.commit()
    finally:
        conn.close()
    return it["filename"] or it["title"], code


def delete_item(item_id: int, uploader: str):
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM items WHERE id=%s AND builtin=0 AND uploader=%s",
                        (item_id, uploader))
            if cur.rowcount == 0:
                raise CommunityError("只能删除自己上传的资源")
        conn.commit()
    finally:
        conn.close()


def _inc_download(item_id: int):
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            _bump(cur, item_id)
        conn.commit()
    finally:
        conn.close()


def _bump(cur, item_id: int):
    cur.execute("UPDATE items SET downloads = downloads + 1 WHERE id=%s", (item_id,))
