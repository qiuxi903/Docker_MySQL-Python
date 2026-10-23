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
            _init_questions(cur)
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


def _extract_ddl(text: str, table: str) -> str:
    """从 SQL 脚本里取出某张表的 CREATE TABLE 语句（按括号配对，避免 DECIMAL(10,2) 截断）。"""
    m = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?"
                  + re.escape(table) + r"[`\"']?\s*\(", text, re.I)
    if not m:
        return ""
    depth = 0
    for j in range(m.end() - 1, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[m.start():j + 1]
    return text[m.start():]


def item_table_preview(item_id: int, table: str) -> dict:
    """题库数据库条目里某张表的预览：结构 + 数据。

    - 结构化条目（内置教学库、发布的库）：直接给列名 + 前 200 行数据 + 建表语句
    - 脚本型条目（上传的 .sql）：只给建表语句（数据需导入后查看）
    """
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            it = _get_item(cur, item_id)
    finally:
        conn.close()
    if it["kind"] != "db":
        raise CommunityError("只有数据库条目可以预览表")
    raw = _unpack(it["data_gz"]) if it["data_gz"] else b""
    if it["filename"]:                      # 脚本型：只有原始脚本
        text = raw.decode("utf-8", "replace")
        return {"name": table, "cols": [], "rows": [], "ddl": _extract_ddl(text, table),
                "script": True, "rowCount": None, "truncated": False}
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise CommunityError("这个资源的数据读不出来")
    t = next((x for x in data.get("tables", []) if x["name"] == table), None)
    if t is None:
        raise CommunityError("这个表不在此资源里")
    rows = t.get("rows") or []
    return {"name": table, "cols": t.get("cols") or [], "rows": rows[:200],
            "ddl": t.get("ddl") or "", "script": False,
            "rowCount": len(rows), "truncated": len(rows) > 200}


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


# ==================== 题目（草稿 → 发布） ====================
# 一道题 = MySQL 部分（整库 SQL 快照）+ Python 部分（若干个 .py 快照）一组。
# 流程：先存草稿 → 在草稿里编辑 → 发布到题库广场。

def _init_questions(cur):
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)}.questions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            account_id BIGINT NOT NULL,
            uploader VARCHAR(64) NOT NULL DEFAULT '',
            title VARCHAR(128) NOT NULL DEFAULT '',
            note TEXT,
            status TINYINT(1) NOT NULL DEFAULT 0,
            builtin TINYINT(1) NOT NULL DEFAULT 0,
            db_name VARCHAR(64) NOT NULL DEFAULT '',
            db_gz LONGTEXT,
            tables_gz LONGTEXT,
            db_tables INT NOT NULL DEFAULT 0,
            py_gz LONGTEXT,
            py_count INT NOT NULL DEFAULT 0,
            downloads INT NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            published_at DATETIME NULL,
            KEY idx_owner (account_id),
            KEY idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    try:  # 旧库升级：题目表数据快照（预览用）
        cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.questions "
                    "ADD COLUMN tables_gz LONGTEXT")
    except Exception:
        pass


QUESTION_PY_MAX = 10          # 一道题最多几个 Python 文件
QUESTION_TITLE_MAX = 60


def _snapshot_db(account: dict, db_name: str) -> tuple[str, int]:
    """把一个库快照成 SQL 文本，返回 (sql文本, 表数量)。"""
    from . import sessions as _sessions

    if not db_name:
        return "", 0
    if db_name not in _sessions.owned_dbs(account["id"]):
        raise CommunityError(f"数据库 {db_name} 不在你的名下")
    if _sessions.db_origin(account["id"], db_name) == "community":
        raise CommunityError(f"数据库 {db_name} 来自社区导入，不能原样发布成题目；"
                             f"可以先改成自己的内容再发布")
    conn = user_conn(db_name, account["mysql_user"], account["mysql_pass"])
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            names = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    if not names:
        raise CommunityError(f"数据库 {db_name} 里没有表，没法作为题目的 MySQL 部分")
    if len(names) > 50:
        raise CommunityError("库里的表超过 50 张，无法作为题目")
    sql = export_database(db_name, account["mysql_user"], account["mysql_pass"],
                          max_rows=C.SHARE_ROWS_MAX)
    return sql.decode("utf-8", "replace"), len(names)


QUESTION_PREVIEW_ROWS = 200


def _capture_tables(account: dict, db_name: str, max_rows: int = QUESTION_PREVIEW_ROWS) -> list[dict]:
    """抓一份结构化表数据（建表语句 + 列名 + 前 N 行），供题目预览展示。"""
    conn = user_conn(db_name, account["mysql_user"], account["mysql_pass"])
    out = []
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            names = [r[0] for r in cur.fetchall()]
            for name in names:
                cur.execute("SHOW CREATE TABLE " + q_ident(name))
                ddl = cur.fetchone()[1]
                cur.execute(f"SELECT * FROM {q_ident(name)} LIMIT %s", (max_rows,))
                cols = [d[0] for d in cur.description]
                rows = [[conv_value(v) for v in r] for r in cur.fetchall()]
                out.append({"name": name, "ddl": ddl, "cols": cols, "rows": rows})
    finally:
        conn.close()
    return out


def _snapshot_py(account_id: int, names: list[str],
                 project_id: int = 0) -> tuple[list[dict], str]:
    """把指定项目里的 py 文件按名字快照成 [{name, content}]，返回 (列表, JSON)。"""
    from . import sessions as _sessions

    if not names:
        return [], ""
    try:
        allfiles = _sessions.pyfiles_contents(account_id, project_id)
    except Exception:
        raise CommunityError("Python 项目不存在了，请重新选择")
    files = []
    for n in names:
        if n not in allfiles:
            raise CommunityError(f"Python 文件「{n}」不存在了，请重新选择")
        content = allfiles[n] or ""
        if len(content.encode("utf-8")) > C.CODE_MAX:
            raise CommunityError(f"文件 {n} 超过 256KB，无法作为题目内容")
        files.append({"name": n, "content": content})
    if len(files) > QUESTION_PY_MAX:
        raise CommunityError(f"一道题最多放 {QUESTION_PY_MAX} 个 Python 文件")
    return files, json.dumps(files, ensure_ascii=False)


def _question_row(cur, qid: int) -> dict | None:
    cur.execute("""SELECT id, account_id, uploader, title, note, status, builtin,
                          db_name, db_gz, db_tables, py_gz, py_count, downloads,
                          created_at, updated_at, published_at
                   FROM questions WHERE id=%s""", (qid,))
    r = cur.fetchone()
    if not r:
        return None
    return {"id": r[0], "account_id": r[1], "uploader": r[2], "title": r[3],
            "note": r[4] or "", "status": r[5], "builtin": r[6],
            "dbName": r[7], "dbTables": r[8], "pyCount": r[11],
            "downloads": r[12], "createdAt": str(r[13]), "updatedAt": str(r[14]),
            "publishedAt": str(r[15]) if r[15] else ""}


def _question_card(r) -> dict:
    (qid, title, note, status, builtin, db_name, db_tables, py_count,
     downloads, uploader, created_at, published_at, updated_at) = r
    return {"id": qid, "kind": "question", "title": title or "(未命名题目)",
            "note": note or "", "status": status, "builtin": builtin,
            "dbName": db_name, "dbTables": db_tables, "pyCount": py_count,
            "downloads": downloads, "uploader": uploader,
            "createdAt": str(published_at or created_at), "updatedAt": str(updated_at)}


def question_save(account: dict, *, qid: int | None, title: str, note: str,
                  db_name: str, py_names: list[str], publish: bool,
                  py_project_id: int = 0) -> dict:
    """新建或更新题目（草稿）。db_name / py_names 为空表示不含该部分。"""
    title = (title or "").strip()[:QUESTION_TITLE_MAX]
    if not title:
        raise CommunityError("先给题目起个名字")
    db_sql, db_tables = _snapshot_db(account, (db_name or "").strip())
    tables_json = ""
    if db_sql:
        tables_json = json.dumps(_capture_tables(account, (db_name or "").strip()),
                                 ensure_ascii=False)
    py_files, py_json = _snapshot_py(account["id"], py_names or [], py_project_id)
    if publish and not db_sql and not py_files:
        raise CommunityError("题目至少要包含一个数据库（MySQL 部分）或一个 Python 文件")

    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            if qid:
                cur.execute("""SELECT account_id, builtin FROM questions WHERE id=%s""", (qid,))
                row = cur.fetchone()
                if not row:
                    raise CommunityError("题目不存在")
                if row[0] != account["id"] and account.get("role") != "admin":
                    raise CommunityError("只能编辑自己的题目")
                if row[1]:
                    raise CommunityError("内置题目不能修改")
                cur.execute("""UPDATE questions SET title=%s, note=%s, db_name=%s,
                               db_gz=%s, tables_gz=%s, db_tables=%s, py_gz=%s, py_count=%s,
                               status=%s, updated_at=CURRENT_TIMESTAMP
                               WHERE id=%s""",
                            (title, (note or "").strip(), (db_name or "").strip(),
                             _pack(db_sql.encode("utf-8")) if db_sql else None,
                             _pack(tables_json.encode("utf-8")) if tables_json else None,
                             db_tables,
                             _pack(py_json.encode("utf-8")) if py_json else None, len(py_files),
                             1 if publish else 0, qid))
                if publish:
                    cur.execute("""UPDATE questions SET published_at=NOW()
                                   WHERE id=%s AND published_at IS NULL""", (qid,))
            else:
                cur.execute("""SELECT COUNT(*) FROM questions WHERE account_id=%s""",
                            (account["id"],))
                if cur.fetchone()[0] >= 100:
                    raise CommunityError("最多创建 100 道题目，可以先删掉一些")
                cur.execute("""INSERT INTO questions
                               (account_id, uploader, title, note, status, db_name,
                                db_gz, tables_gz, db_tables, py_gz, py_count, published_at)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                       CASE WHEN %s=1 THEN NOW() ELSE NULL END)""",
                            (account["id"], account["display"], title, (note or "").strip(),
                             1 if publish else 0, (db_name or "").strip(),
                             _pack(db_sql.encode("utf-8")) if db_sql else None,
                             _pack(tables_json.encode("utf-8")) if tables_json else None,
                             db_tables,
                             _pack(py_json.encode("utf-8")) if py_json else None,
                             len(py_files), 1 if publish else 0))
                qid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return {"id": qid, "published": bool(publish)}


def question_owned(account: dict, qid: int) -> dict:
    """取题目（草稿只有本人/管理员能看）。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, account_id, uploader, title, note, status, builtin,
                                  db_name, db_tables, py_count, downloads,
                                  created_at, updated_at, published_at
                           FROM questions WHERE id=%s""", (qid,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        raise CommunityError("题目不存在")
    q = {"id": r[0], "account_id": r[1], "uploader": r[2], "title": r[3],
         "note": r[4] or "", "status": r[5], "builtin": r[6], "dbName": r[7],
         "dbTables": r[8], "pyCount": r[9], "downloads": r[10],
         "createdAt": str(r[11]), "updatedAt": str(r[12]),
         "publishedAt": str(r[13]) if r[13] else "",
         "mine": r[1] == account["id"], "admin": account.get("role") == "admin"}
    if not q["status"] and not (q["mine"] or q["admin"]):
        raise CommunityError("这是别人的草稿，不能查看")
    return q


def question_detail(account: dict, qid: int) -> dict:
    """题目详情：带上 MySQL 表清单和 Python 文件清单（不含全文）。"""
    q = question_owned(account, qid)
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT db_gz, py_gz, db_name, tables_gz FROM questions WHERE id=%s", (qid,))
            r = cur.fetchone()
    finally:
        conn.close()
    tables = []
    if r[0]:
        sql = _unpack(r[0]).decode("utf-8", "replace")
        tables = parse_script_tables(sql)
    table_data = []
    if r[3]:
        try:
            table_data = json.loads(_unpack(r[3]).decode("utf-8"))
        except Exception:
            table_data = []
    py_names = []
    py_preview = []
    if r[1]:
        files = json.loads(_unpack(r[1]).decode("utf-8"))
        for f in files:
            name = f.get("name", "")
            content = f.get("content") or ""
            py_names.append(name)
            py_preview.append({"name": name,
                               "size": len(content.encode("utf-8")),
                               "head": content[:1500]})
    q.update({"tables": tables, "tableData": table_data,
              "dbName": r[2] or q["dbName"], "pyFiles": py_names,
              "pyPreview": py_preview,
              "dbSize": len(r[0] and _unpack(r[0]) or b"")})
    return q


def question_list_mine(account_id: int) -> list[dict]:
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, title, note, status, builtin, db_name, db_tables,
                                  py_count, downloads, uploader, created_at, published_at,
                                  updated_at
                           FROM questions WHERE account_id=%s
                           ORDER BY updated_at DESC""", (account_id,))
            return [_question_card(r) for r in cur.fetchall()]
    finally:
        conn.close()


def question_list_published() -> list[dict]:
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, title, note, status, builtin, db_name, db_tables,
                                  py_count, downloads, uploader, created_at, published_at,
                                  updated_at
                           FROM questions WHERE status=1
                           ORDER BY (builtin=1) DESC, published_at DESC""")
            return [_question_card(r) for r in cur.fetchall()]
    finally:
        conn.close()


def question_publish(account: dict, qid: int, publish: bool) -> dict:
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            q = _question_row(cur, qid)
            if not q:
                raise CommunityError("题目不存在")
            if q["account_id"] != account["id"] and account.get("role") != "admin":
                raise CommunityError("只能发布自己的题目")
            if q["builtin"]:
                raise CommunityError("内置题目不能修改")
            cur.execute("SELECT db_gz, py_gz FROM questions WHERE id=%s", (qid,))
            r = cur.fetchone()
            if publish and not r[0] and not r[1]:
                raise CommunityError("题目至少要包含一个数据库（MySQL 部分）或一个 Python 文件")
            cur.execute("""UPDATE questions SET status=%s,
                           published_at=CASE WHEN %s=1 AND published_at IS NULL THEN NOW()
                                             WHEN %s=0 THEN NULL ELSE published_at END,
                           updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
                        (1 if publish else 0, 1 if publish else 0, 1 if publish else 0, qid))
        conn.commit()
    finally:
        conn.close()
    return {"id": qid, "published": bool(publish)}


def question_delete(account: dict, qid: int):
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            q = _question_row(cur, qid)
            if not q:
                raise CommunityError("题目不存在")
            if q["account_id"] != account["id"] and account.get("role") != "admin":
                raise CommunityError("只能删除自己的题目")
            if q["builtin"]:
                raise CommunityError("内置题目不能删除")
            cur.execute("DELETE FROM questions WHERE id=%s", (qid,))
        conn.commit()
    finally:
        conn.close()


def question_import(account: dict, qid: int, new_db_name: str = "",
                    py_project_id: int = 0) -> dict:
    """一键导入整套：MySQL 部分建成独立新库，Python 部分加进自己的文件列表。"""
    from . import sessions as _sessions
    from .sqlrun import run_sql

    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            q = _question_row(cur, qid)
            cur.execute("SELECT db_gz, py_gz FROM questions WHERE id=%s", (qid,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not q:
        raise CommunityError("题目不存在")
    if not q["status"] and not (q["account_id"] == account["id"] or account.get("role") == "admin"):
        raise CommunityError("这是别人的草稿，不能导入")

    result = {"db": "", "tables": [], "pyFiles": []}
    if r[0]:
        sql = _unpack(r[0]).decode("utf-8", "replace")
        base = _sessions.sanitize_db_name(new_db_name or q["dbName"] or f"题目{qid}")
        new_db = _sessions.create_user_db_unique(account, base or f"q{qid}", origin="community")
        run_sql(new_db, account["mysql_user"], account["mysql_pass"], sql, owned_dbs=[new_db])
        result["db"] = new_db
        result["tables"] = parse_script_tables(sql)
    if r[1]:
        files = json.loads(_unpack(r[1]).decode("utf-8"))
        existing = {f["name"].casefold()
                    for f in _sessions.pyfiles_list(account["id"], py_project_id)}
        saved = []
        for f in files:
            final = _sessions.pyfiles_unique_name(account["id"], f.get("name") or "file.py",
                                                  existing, py_project_id)
            _sessions.pyfiles_save(account["id"], final, f.get("content") or "",
                                   project_id=py_project_id)
            existing.add(final.casefold())
            saved.append(final)
        result["pyFiles"] = saved
    _inc_question_download(qid)
    return result


def question_zip(qid: int) -> tuple[str, bytes]:
    """打包成 zip：{库名}.sql + Python 文件，供下载。"""
    import io
    import zipfile

    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT title, db_name, db_gz, py_gz FROM questions WHERE id=%s", (qid,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        raise CommunityError("题目不存在")
    title, db_name, db_gz, py_gz = r
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if db_gz:
            z.writestr(f"{db_name or 'database'}.sql", _unpack(db_gz))
        if py_gz:
            for f in json.loads(_unpack(py_gz).decode("utf-8")):
                z.writestr(f.get("name") or "file.py", (f.get("content") or "").encode("utf-8"))
        if not db_gz and not py_gz:
            z.writestr("README.txt", "这个题目还是空的（没有 MySQL 部分也没有 Python 部分）。")
    return (f"{title or 'question'}.zip"), buf.getvalue()


def _inc_question_download(qid: int):
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE questions SET downloads = downloads + 1 WHERE id=%s", (qid,))
        conn.commit()
    finally:
        conn.close()

