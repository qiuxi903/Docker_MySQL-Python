"""SQL 执行引擎：语句切分、墙钟超时看门狗、行数上限。

学生 SQL 用其专属受限 MySQL 账号执行 —— 数据库层面保证只能碰自己的库。
"""
import re
import threading
import time

import pymysql

from .config import C
from .db import conv_value, q_ident, root_conn, user_conn

# 常见错误的友好提示（追加在 MySQL 原始错误后）
ERROR_HINTS = {
    1044: "侧栏里的名字是「表」而不是数据库：删表用 DROP TABLE 表名；删自己的整个库是被禁止的。",
    1146: "表不存在。点左侧表名可以查看现有的表。",
    1054: "列名不存在，可用 DESCRIBE 表名 查看有哪些列。",
    1064: "语法有误。检查一下拼写、逗号和引号。",
}

# 拦截 DROP DATABASE / DROP SCHEMA（学生库的权限本身也删不了别的库，这里统一给友好提示）
_DROP_DB_RE = re.compile(r"^DROP\s+(?:DATABASE|SCHEMA)\b", re.I)


def drop_db_target(stmt: str) -> str | None:
    """DROP DATABASE 类语句返回目标库名；其它语句返回 None。"""
    m = _DROP_DB_RE.match(stmt.strip())
    if not m:
        return None
    rest = stmt.strip()[m.end():].strip()
    if rest.lower().startswith("if exists"):
        rest = rest[9:].strip()
    parts = rest.split()
    return parts[0].strip("`\"';,") if parts else ""


def _db_exists(name: str) -> bool:
    try:
        conn = root_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name=%s", (name,))
                return cur.fetchone() is not None
        finally:
            conn.close()
    except Exception:
        return True  # 查询失败时放行给 MySQL 原生报错


def drop_db_message(stmt: str, own_db: str, owned_dbs: list[str] | None = None) -> str | None:
    """DROP DATABASE 类语句生成友好提示（含存在性检查和拼写纠错）；其它语句返回 None。

    自己名下的「导入库」允许直接 DROP（后端会同步清理登记记录）。"""
    target = drop_db_target(stmt)
    if target is None:
        return None
    if target.lower() == own_db.lower():
        return (f"不能删除默认数据库（{own_db}）。"
                f"要清空数据可以逐表执行 DROP TABLE 表名；要重置整个库请找管理员。")
    owned = [o.lower() for o in (owned_dbs or [])]
    if target.lower() in owned:
        return None
    if not _db_exists(target):
        import difflib

        close = difflib.get_close_matches(target.lower(), [own_db.lower()], cutoff=0.6)
        did_you_mean = f" 你是不是想输入 {own_db}（你自己的库）？自己的整个库也不允许 DROP。" if close else ""
        return f"数据库 {target} 不存在。{did_you_mean}侧栏里的名字是表，不是库。"
    return f"只能操作自己的数据库（{own_db}），其它人的数据库无权访问。如需删除请联系管理员。"


def drop_db_targets(sql: str) -> list[str]:
    """语句里出现过的所有 DROP DATABASE 目标名（供上层同步登记记录）。"""
    out = []
    for stmt in prepare_statements(sql):
        t = drop_db_target(stmt)
        if t and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out


_DELIM_RE = re.compile(r"^\s*DELIMITER\s+(\S+)\s*$", re.I | re.M)
# 复合语句（存储过程 / 函数 / 触发器 / 事件）：内部的分号不能当语句结束
_COMPOUND_START = re.compile(
    r"^\s*CREATE\s+(?:DEFINER\s*=\s*\S+\s+)?(PROCEDURE|FUNCTION|TRIGGER|EVENT)\b", re.I)
_END_LINE = re.compile(r"^\s*END\s*(?:;|//|;;|//\s*;|;\s*//)?\s*$", re.I)


def strip_delimiter(sql: str) -> str:
    """把 mysql 客户端的存储过程/触发器块整理成 PyMySQL 能执行的形式。

    两种常见导出都支持：
      A) 标准 mysqldump：DELIMITER // ... END// DELIMITER ;
      B) Navicat：DELIMITER ; 后接 CREATE PROCEDURE ... BEGIN ...; ... END （分号单独一行）

    做法：块内部的换行保留，但把内部分号替换成占位符，避免被 split_sql 提前切断；
    末尾统一输出一个 ";". split_sql 之后再还原占位符。
    """
    text = sql or ""
    if not re.search(r"^\s*DELIMITER\s+", text, re.I | re.M) \
            and not re.search(r"^\s*CREATE\s+(?:DEFINER\s*=\s*\S+\s+)?(PROCEDURE|FUNCTION|TRIGGER|EVENT)\b",
                              text, re.I | re.M):
        return text

    lines = text.splitlines()
    out: list[str] = []
    buf: list[str] = []          # 当前普通语句缓冲
    comp: list[str] | None = None  # 正在收集的复合语句
    delim = ";"
    pending_split = False        # 上一行是单独的定界符，等待并入块

    def flush_normal():
        nonlocal buf
        if buf:
            out.append("\n".join(buf))
            buf = []

    for raw in lines:
        m = _DELIM_RE.match(raw)
        if m:
            flush_normal()
            delim = m.group(1)
            continue

        stripped = raw.strip()

        if comp is None:
            # 复合语句开始：把已缓冲的行先落盘
            if _COMPOUND_START.match(raw):
                flush_normal()
                comp = [raw]
                continue
            # 普通语句：遇到行尾定界符就结束（定界符不是 ";" 时）
            if delim != ";" and stripped.endswith(delim):
                body = stripped[: -len(delim)].rstrip()
                buf.append(body)
                flush_normal()
                continue
            buf.append(raw)
            continue

        # ---- 收集复合语句内部 ----
        # 找到 END（可能跟定界符），整块结束
        if _END_LINE.match(stripped):
            comp.append("END;")
            out.append(_protect_compound("\n".join(comp)))
            comp = None
            continue
        comp.append(raw)

    if comp:
        out.append(_protect_compound("\n".join(comp)))
    flush_normal()
    return "\n".join(out)


def _protect_compound(block: str) -> str:
    """把复合语句内部的分号换成占位符（保留最后的 END;）。"""
    body = block.rstrip()
    if body.endswith(";"):
        body = body[:-1]
    body = body.replace(";", _SEMI_PLACEHOLDER)
    return body + ";"


_SEMI_PLACEHOLDER = "\x00SEMI\x00"


def restore_semicolons(stmt: str) -> str:
    return stmt.replace(_SEMI_PLACEHOLDER, ";")


def split_sql(sql: str) -> list[str]:
    """按分号切分 SQL，跳过字符串/反引号里的分号和三种注释。"""
    sql = strip_delimiter(sql)
    stmts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c in ("'", '"', "`"):
            quote = c
            buf.append(c)
            i += 1
            closed = False
            while i < n:
                ch = sql[i]
                buf.append(ch)
                if ch == "\\" and quote in ("'", '"') and i + 1 < n:
                    buf.append(sql[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    # 双写引号（'' 或 "" 或 ``）表示转义
                    if quote in ("'", '"') and i + 1 < n and sql[i + 1] == quote:
                        buf.append(sql[i + 1])
                        i += 2
                        continue
                    i += 1
                    closed = True
                    break
                i += 1
            if not closed:
                break
            continue
        if c == "-" and sql[i : i + 2] == "--":
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "#":
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and sql[i : i + 2] == "/*":
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == ";":
            s = "".join(buf).strip()
            if s:
                stmts.append(s)
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


class SqlError(Exception):
    """带用户可读信息的 SQL 错误。"""


# 无分号模式：这些关键字开头的行被视为一条新语句的开始
_STMT_KEYWORDS = {
    "select", "insert", "update", "delete", "create", "drop", "alter",
    "show", "describe", "desc", "explain", "use", "set", "truncate",
    "rename", "grant", "revoke", "with", "replace", "call", "commit",
    "rollback", "begin", "start", "lock", "unlock", "flush", "optimize",
    "analyze", "do", "prepare", "execute", "release", "help",
}


def prepare_statements(sql: str) -> list[str]:
    """和真 mysql 命令行一样宽容：有分号按分号切；没分号则按行聚合，
    以语句关键字开头的行自动开启新语句（支持不带分号的多条/多行输入）。"""
    if ";" in sql:
        return split_sql(sql)
    stmts: list[str] = []
    cur: list[str] = []
    for raw in sql.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("--") or low.startswith("#") or low.startswith("/*"):
            continue  # 纯注释行跳过
        first = low.split(None, 1)[0].rstrip("(")
        if first in _STMT_KEYWORDS and cur:
            stmts.append("\n".join(cur))
            cur = [raw]
        else:
            cur.append(raw)
    if cur:
        stmts.append("\n".join(cur))
    return [s.strip() for s in stmts if s.strip()]


def _short(stmt: str, limit: int = 120) -> str:
    s = " ".join(stmt.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def run_sql(db_name: str, mysql_user: str, mysql_pass: str, sql: str,
            owned_dbs: list[str] | None = None, batch: bool = False,
            timeout: float | None = None) -> dict:
    """在学生自己的库上执行（可能多条）SQL，逐条返回结果。

    batch=True 用于「题目初始化 / 标准答案」这类内部脚本：整批放在一个事务里提交，
    磁盘慢的机器上不会因为每条语句都 fsync 而超时；timeout 也可以单独放宽。
    """
    limit = float(timeout if timeout is not None else C.SQL_TIMEOUT)
    stmts = prepare_statements(sql)
    if not stmts:
        raise SqlError("没有可执行的 SQL 语句")
    if len(stmts) > 200:
        raise SqlError("一次最多执行 200 条语句")

    results: list[dict] = []
    killed = threading.Event()

    def watchdog(conn_id: int):
        # 墙钟超时：root 连接 KILL 该查询连接
        try:
            conn = root_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("KILL %s", (conn_id,))
            finally:
                conn.close()
        except Exception:
            pass
        killed.set()

    conn = user_conn(db_name, mysql_user, mysql_pass)
    if batch:
        try:
            conn.autocommit(False)
        except Exception:
            pass
    timer = None
    t_start = time.monotonic()
    try:
        timer = threading.Timer(limit, watchdog, (conn.thread_id(),))
        timer.daemon = True
        timer.start()

        for idx, stmt in enumerate(stmts, 1):
            t0 = time.monotonic()
            stmt = restore_semicolons(stmt)
            guard_msg = drop_db_message(stmt, db_name, owned_dbs)
            if guard_msg:
                results.append({"type": "error", "index": idx, "sql": _short(stmt),
                                "msg": guard_msg})
                break
            try:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                    if cur.description:  # 有结果集（SELECT/SHOW/DESC 等）
                        columns = [d[0] for d in cur.description]
                        rows = cur.fetchmany(C.ROWS_LIMIT + 1)
                        truncated = len(rows) > C.ROWS_LIMIT
                        rows = rows[: C.ROWS_LIMIT]
                        results.append({
                            "type": "rows",
                            "index": idx,
                            "sql": _short(stmt),
                            "columns": columns,
                            "rows": [[conv_value(v) for v in r] for r in rows],
                            "rowCount": len(rows),
                            "truncated": truncated,
                            "ms": int((time.monotonic() - t0) * 1000),
                        })
                    else:
                        results.append({
                            "type": "ok",
                            "index": idx,
                            "sql": _short(stmt),
                            "affected": max(cur.rowcount, 0),
                            "ms": int((time.monotonic() - t0) * 1000),
                        })
            except pymysql.MySQLError as e:
                if killed.is_set():
                    results.append({
                        "type": "error", "index": idx, "sql": _short(stmt),
                        "msg": f"执行超时（超过 {limit:g} 秒），已被服务器终止。"
                               f"如果是查询太慢，试试加 LIMIT 或建索引。",
                    })
                    break
                errno = e.args[0] if e.args else 0
                msg = e.args[1] if len(e.args) > 1 else str(e)
                if errno in ERROR_HINTS:
                    msg = f"{msg}（提示：{ERROR_HINTS[errno]}）"
                results.append({"type": "error", "index": idx, "sql": _short(stmt),
                                "errno": int(errno), "msg": str(msg)})
                break
        if batch and not any(r.get("type") == "error" for r in results):
            try:
                conn.commit()
            except pymysql.MySQLError:
                pass
    finally:
        if timer is not None:
            timer.cancel()
        try:
            conn.close()
        except Exception:
            pass

    return {
        "results": results,
        "tookMs": int((time.monotonic() - t_start) * 1000),
    }


def list_tables(db_name: str, mysql_user: str, mysql_pass: str) -> list[dict]:
    """我的表列表（含精确行数，表数量多时截断到前 100 张）。"""
    conn = user_conn(db_name, mysql_user, mysql_pass)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            # __ 开头的是系统内部表（如 __sources 源文件存档），不对学生展示
            names = [r[0] for r in cur.fetchall() if not r[0].startswith("__")][:100]
            out = []
            for name in names:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {q_ident(name)}")
                    cnt = cur.fetchone()[0]
                except pymysql.MySQLError:
                    cnt = None
                out.append({"name": name, "rows": cnt})
            return out
    finally:
        conn.close()
