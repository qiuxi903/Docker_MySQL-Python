"""练习：可自动判分的题目。

题型：
  sql     —— 出题给「初始化 SQL」（建表 + 初始数据）+「标准答案 SQL」。
             判分时在学生自己名下建临时库：跑 setup → 跑学生 SQL → 跑标准答案 SQL，
             比对结果集（列名多重集 + 行值多重集，不看行序）。
  python  —— 出题给「起始代码」+「输入数据」+「期望输出」。
             判分时把代码交给 runner 沙箱执行，输出与期望输出比对（逐行去首尾空白、丢空行）。
  single  —— 单选，选项精确匹配。
  boolean —— 判断，选项精确匹配。
  fill    —— 填空，宽松比对（忽略空格、大小写、全半角、常见标点）。

防作弊：verify_sql / expected_output / answer_json 只在「出题人 / 管理员」的接口里下发，
学生做题时拿不到标准答案；提交判分后才返回对照结果。
"""
import io
import json
import re
import time
import urllib.error
import urllib.request

import pymysql

from .config import C
from .db import conv_value, q_ident, root_conn

DRILL_TYPES = ("sql", "python", "single", "multiple", "boolean", "fill")
# 各题型的判分模式（出题人可选，默认第一个）
JUDGE_MODES = {
    "sql": ["result", "result_ordered", "rows_only", "cell", "contains", "state", "dbstate"],
    "python": ["output", "contains", "regex", "tests"],
    "single": ["key"], "multiple": ["keys"], "boolean": ["key"],
    "fill": ["loose"],
}
JUDGE_LABEL = {
    "result": "结果集一致（列名+数据，不计顺序）",
    "result_ordered": "结果集一致（数据顺序也要一致）",
    "rows_only": "数据一致即可（不检查列名）",
    "cell": "只检查一个值（首个单元格）",
    "contains": "结果中包含指定值",
    "state": "改数据题：执行后校验数据状态",
    "dbstate": "比对整库状态（建表/增删改通用）",
    "output": "输出完全一致",
    "contains": "输出包含指定文字",
    "regex": "输出匹配正则表达式",
    "tests": "多组测试用例全部通过",
    "key": "选中正确选项",
    "keys": "选出全部正确选项",
    "loose": "宽松匹配（忽略大小写/空格/标点）",
}
COURSE_LABEL = {"sql": "SQL 练习", "python": "Python 练习", "basic": "客观题"}
TYPE_LABEL = {"sql": "SQL 练习题", "python": "Python 练习题", "single": "单选题",
              "multiple": "多选题", "boolean": "判断题", "fill": "填空题"}
TITLE_MAX = 160
DRILL_MAX = 200          # 每人最多题目数
PY_RUN_TIMEOUT = 25.0    # 判分时沙箱最长等待（秒）


class DrillError(Exception):
    pass


# ---------------- 建表 ----------------

def init():
    conn = root_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)}.drills (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    uploader VARCHAR(64) NOT NULL DEFAULT '',
                    course VARCHAR(16) NOT NULL DEFAULT 'sql',
                    type VARCHAR(16) NOT NULL,
                    title VARCHAR(200) NOT NULL DEFAULT '',
                    stem MEDIUMTEXT,
                    setup_sql MEDIUMTEXT,
                    verify_sql MEDIUMTEXT,
                    starter_code MEDIUMTEXT,
                    input_data MEDIUMTEXT,
                    expected_output MEDIUMTEXT,
                    options_json MEDIUMTEXT,
                    answer_json MEDIUMTEXT,
                    judge_mode VARCHAR(24) NOT NULL DEFAULT '',
                    test_cases MEDIUMTEXT,
                    hint TEXT,
                    status TINYINT(1) NOT NULL DEFAULT 0,
                    builtin TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    published_at DATETIME NULL,
                    KEY idx_course (course, status),
                    KEY idx_owner (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            try:  # 旧库升级：判分模式 + 多测试用例
                cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.drills "
                            "ADD COLUMN judge_mode VARCHAR(24) NOT NULL DEFAULT ''")
                cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.drills "
                            "ADD COLUMN test_cases MEDIUMTEXT")
            except Exception:
                pass
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)}.drill_submissions (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    drill_id BIGINT NOT NULL,
                    passed TINYINT(1) NOT NULL DEFAULT 0,
                    answer MEDIUMTEXT,
                    detail MEDIUMTEXT,
                    ms INT NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_user (account_id, drill_id),
                    KEY idx_drill (drill_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    finally:
        conn.close()


# ---------------- 比对规则 ----------------

def _cells(row):
    return ["" if v is None else str(v) for v in row]


def normalize_rows(rows):
    """每行内先排序、行间再排序 —— 结果集比对不看列序行序。"""
    return sorted(sorted(_cells(r)) for r in rows or [])


def compare_sets(student, expected):
    """列名多重集 + 行值多重集全等。"""
    if student is None or expected is None:
        return False
    cols_ok = sorted(str(c) for c in (student.get("columns") or [])) == \
        sorted(str(c) for c in (expected.get("columns") or []))
    rows_ok = normalize_rows(student.get("rows")) == normalize_rows(expected.get("rows"))
    return cols_ok and rows_ok


def normalize_out(s):
    """输出比对：逐行去首尾空白、丢掉空行。"""
    lines = [ln.strip() for ln in str(s or "").splitlines()]
    return "\n".join(ln for ln in lines if ln)


_PUNCT = "，。！？；：、,.!?;:\"'“”‘’()（）【】[]{}<>《》—-_~`|/\\*#$&^%+="


def normalize_text(s):
    """填空宽松比对：去所有空白、统一大小写、全角转半角、去常见标点。"""
    t = str(s or "").strip().lower()
    out = []
    for ch in t:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:      # 全角 → 半角
            ch = chr(code - 0xFEE0)
        if ch.isspace() or ch in _PUNCT:
            continue
        out.append(ch)
    return "".join(out)


# ---------------- 读取 ----------------

_COLS = ("id, account_id, uploader, course, type, title, stem, setup_sql, verify_sql, "
         "starter_code, input_data, expected_output, options_json, answer_json, hint, "
         "status, builtin, created_at, updated_at, published_at, judge_mode, test_cases")
_N_DRILL_COLS = len(_COLS.split(","))          # 题面列数（后面才是进度列）


def _row_to_dict(r):
    return {
        "id": r[0], "account_id": r[1], "uploader": r[2], "course": r[3], "type": r[4],
        "title": r[5] or "(未命名题目)", "stem": r[6] or "", "setupSql": r[7] or "",
        "verifySql": r[8] or "", "starterCode": r[9] or "", "inputData": r[10] or "",
        "expectedOutput": r[11] or "", "optionsJson": r[12] or "", "answerJson": r[13] or "",
        "hint": r[14] or "", "status": r[15], "builtin": bool(r[16]),
        "createdAt": str(r[17]), "updatedAt": str(r[18]),
        "publishedAt": str(r[19]) if r[19] else "",
        "judgeMode": r[20] or "", "testCases": r[21] or "",
    }


def _public(d: dict, with_answer: bool) -> dict:
    out = {k: v for k, v in d.items()
           if k not in ("account_id", "verifySql", "expectedOutput", "answerJson")}
    try:
        out["options"] = json.loads(d["optionsJson"]) if d["optionsJson"] else []
    except Exception:
        out["options"] = []
    out["typeLabel"] = TYPE_LABEL.get(d["type"], d["type"])
    out["courseLabel"] = COURSE_LABEL.get(d["course"], d["course"])
    out["judgeMode"] = d["judgeMode"] or (JUDGE_MODES.get(d["type"]) or [""])[0]
    out["judgeLabel"] = JUDGE_LABEL.get(out["judgeMode"], out["judgeMode"])
    if with_answer:
        out["verifySql"] = d["verifySql"]
        out["expectedOutput"] = d["expectedOutput"]
        try:
            out["answer"] = json.loads(d["answerJson"]) if d["answerJson"] else {}
        except Exception:
            out["answer"] = {}
    return out


def list_drills(account: dict, course: str = "", mine: bool = False) -> list[dict]:
    """已发布的题（所有人可见）+ 自己的草稿；带我的做题进度。"""
    where = ["(d.status=1 OR d.account_id=%s)"]
    params = [account["id"]]
    if mine:
        where = ["d.account_id=%s"]
    if course:
        where.append("d.course=%s")
        params.append(course)
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT d.{_COLS.replace(', ', ', d.')},
                                   MAX(s.passed) AS passed, COUNT(s.id) AS attempts,
                                   MAX(s.created_at) AS last_at
                            FROM drills d
                            LEFT JOIN drill_submissions s
                                   ON s.drill_id=d.id AND s.account_id=%s
                            WHERE {' AND '.join(where)}
                            GROUP BY d.id
                            ORDER BY FIELD(d.course,'sql','python','basic'), d.builtin DESC,
                                     d.published_at DESC, d.title ASC, d.id ASC""",
                        [account["id"]] + params[1:] if mine else [account["id"]] + params)
            rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        n = _N_DRILL_COLS
        d = _public(_row_to_dict(r[:n]), with_answer=False)
        d["passed"] = bool(r[n])
        d["attempts"] = int(r[n + 1] or 0)
        d["lastAt"] = str(r[n + 2]) if r[n + 2] else ""
        d["mine"] = r[1] == account["id"]
        out.append(d)
    return out


def get_full(did: int) -> dict:
    """完整题面（含 verify_sql / expected_output / answer）——仅服务端判分使用，绝不下发给学生。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_COLS} FROM drills WHERE id=%s", (did,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        raise DrillError("题目不存在")
    return _row_to_dict(r)


def get_drill(account: dict, did: int) -> dict:
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_COLS} FROM drills WHERE id=%s", (did,))
            r = cur.fetchone()
            if not r:
                raise DrillError("题目不存在")
            cur.execute("""SELECT MAX(passed), COUNT(id), MAX(created_at)
                           FROM drill_submissions WHERE drill_id=%s AND account_id=%s""",
                        (did, account["id"]))
            p = cur.fetchone()
    finally:
        conn.close()
    d = _row_to_dict(r)
    mine = d["account_id"] == account["id"]
    if not d["status"] and not (mine or account.get("role") == "admin"):
        raise DrillError("这是别人的草稿，不能查看")
    out = _public(d, with_answer=mine or account.get("role") == "admin")
    out["passed"] = bool(p[0])
    out["attempts"] = int(p[1] or 0)
    out["mine"] = mine
    return out


def progress(account: dict) -> dict:
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT d.course, COUNT(*) AS total,
                                  SUM(CASE WHEN p.passed=1 THEN 1 ELSE 0 END) AS done
                           FROM drills d
                           LEFT JOIN (SELECT drill_id, MAX(passed) AS passed
                                      FROM drill_submissions WHERE account_id=%s
                                      GROUP BY drill_id) p ON p.drill_id=d.id
                           WHERE d.status=1
                           GROUP BY d.course""", (account["id"],))
            rows = cur.fetchall()
    finally:
        conn.close()
    res = {}
    for course, total, done in rows:
        res[course] = {"total": int(total or 0), "done": int(done or 0)}
    return res


# ---------------- 出题（草稿 → 发布） ----------------

def _require_perm(account: dict):
    if account["role"] != "admin" and not account.get("can_publish"):
        raise DrillError("还没有出题权限（管理员可在「管理」面板按人开通）")


def _validate(account: dict, p: dict, dr_type: str):
    if dr_type not in DRILL_TYPES:
        raise DrillError("题型不对")
    title = (p.get("title") or "").strip()[:TITLE_MAX]
    if not title:
        raise DrillError("先给题目起个名字")
    course = p.get("course") or ("sql" if dr_type == "sql" else
                                 "python" if dr_type == "python" else "basic")
    if course not in ("sql", "python", "basic"):
        raise DrillError("分类不对")
    modes = JUDGE_MODES.get(dr_type) or []
    jm = p.get("judgeMode") or (modes[0] if modes else "")
    if jm not in modes:
        raise DrillError("判分方式不对")
    if dr_type == "sql":
        if not (p.get("setupSql") or "").strip():
            raise DrillError("SQL 题要填「初始化 SQL」（题目数据从哪来）")
        if not (p.get("verifySql") or "").strip():
            raise DrillError("SQL 题要填「标准答案 SQL」（用来判分）")
    if dr_type == "python":
        if jm == "tests":
            try:
                cases = json.loads(p.get("testCases") or "[]")
            except Exception:
                cases = []
            if not cases or not all((c.get("input") is not None and c.get("expected") is not None)
                                    for c in cases):
                raise DrillError("多组测试用例至少要有一组，且每组都要填输入和期望输出")
        elif not (p.get("expectedOutput") or "").strip():
            raise DrillError("Python 题要填「期望输出」（用来判分）")
    if dr_type in ("single", "boolean", "multiple"):
        opts = p.get("options") or []
        if len(opts) < 2:
            raise DrillError("至少要有两个选项")
        if dr_type == "multiple":
            keys = (p.get("answer") or {}).get("keys") or []
            if len(keys) < 1:
                raise DrillError("要指定正确选项（可多选）")
        elif not (p.get("answer") or {}).get("key"):
            raise DrillError("要指定正确选项")
    if dr_type == "fill":
        answers = (p.get("answer") or {}).get("values") or []
        if not answers:
            raise DrillError("要填至少一个可接受答案")
    return title, course, jm


def save(account: dict, did: int, p: dict) -> dict:
    _require_perm(account)
    dr_type = p.get("type") or "sql"
    title, course, judge_mode = _validate(account, p, dr_type)
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            if did:
                cur.execute("SELECT account_id, builtin FROM drills WHERE id=%s", (did,))
                row = cur.fetchone()
                if not row:
                    raise DrillError("题目不存在")
                if row[0] != account["id"] and account.get("role") != "admin":
                    raise DrillError("只能改自己的题目")
                if row[1]:
                    raise DrillError("内置题目不能改")
                cur.execute(f"""UPDATE drills SET course=%s, type=%s, title=%s, stem=%s,
                                       setup_sql=%s, verify_sql=%s, starter_code=%s,
                                       input_data=%s, expected_output=%s,
                                       options_json=%s, answer_json=%s, hint=%s,
                                       judge_mode=%s, test_cases=%s
                               WHERE id=%s""",
                            (course, dr_type, title, p.get("stem") or "",
                             p.get("setupSql") or "", p.get("verifySql") or "",
                             p.get("starterCode") or "", p.get("inputData") or "",
                             p.get("expectedOutput") or "",
                             json.dumps(p.get("options") or [], ensure_ascii=False),
                             json.dumps(p.get("answer") or {}, ensure_ascii=False),
                             p.get("hint") or "", judge_mode,
                             p.get("testCases") or "", did))
            else:
                cur.execute("SELECT COUNT(*) FROM drills WHERE account_id=%s", (account["id"],))
                if cur.fetchone()[0] >= DRILL_MAX:
                    raise DrillError(f"最多出 {DRILL_MAX} 道题")
                cur.execute(f"""INSERT INTO drills
                    (account_id, uploader, course, type, title, stem, setup_sql, verify_sql,
                     starter_code, input_data, expected_output, options_json, answer_json, hint,
                     judge_mode, test_cases)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (account["id"], account["display"], course, dr_type, title,
                             p.get("stem") or "", p.get("setupSql") or "",
                             p.get("verifySql") or "", p.get("starterCode") or "",
                             p.get("inputData") or "", p.get("expectedOutput") or "",
                             json.dumps(p.get("options") or [], ensure_ascii=False),
                             json.dumps(p.get("answer") or {}, ensure_ascii=False),
                             p.get("hint") or "", judge_mode, p.get("testCases") or ""))
                did = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return {"id": did}


def publish(account: dict, did: int, on: bool) -> dict:
    _require_perm(account)
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT account_id, builtin, type, title, verify_sql,
                                  expected_output, setup_sql, answer_json, options_json,
                                  judge_mode, test_cases
                           FROM drills WHERE id=%s""", (did,))
            r = cur.fetchone()
            if not r:
                raise DrillError("题目不存在")
            if r[0] != account["id"] and account.get("role") != "admin":
                raise DrillError("只能发布自己的题目")
            if r[1]:
                raise DrillError("内置题目不能改")
            if on:
                dtype, mode = r[2], (r[9] or "")
                if dtype == "sql":
                    if not (r[4] or "").strip():
                        raise DrillError("SQL 题要有标准答案 SQL 才能发布")
                    if not (r[6] or "").strip():
                        raise DrillError("SQL 题要有初始化 SQL 才能发布")
                elif dtype == "python":
                    if mode == "tests":
                        if not (r[10] or "").strip():
                            raise DrillError("多组测试题要配置测试用例才能发布")
                    elif not (r[5] or "").strip():
                        raise DrillError("Python 题要有期望输出才能发布")
                elif dtype in ("single", "boolean", "multiple"):
                    if not (r[8] or "").strip():
                        raise DrillError("客观题要有选项")
                    if not (r[7] or "").strip():
                        raise DrillError("客观题要有答案")
            cur.execute("""UPDATE drills SET status=%s,
                           published_at=CASE WHEN %s=1 AND published_at IS NULL THEN NOW()
                                             WHEN %s=0 THEN NULL ELSE published_at END
                           WHERE id=%s""", (1 if on else 0, 1 if on else 0, 1 if on else 0, did))
        conn.commit()
    finally:
        conn.close()
    return {"id": did, "published": bool(on)}


def delete(account: dict, did: int):
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id, builtin FROM drills WHERE id=%s", (did,))
            row = cur.fetchone()
            if not row:
                raise DrillError("题目不存在")
            if row[0] != account["id"] and account.get("role") != "admin":
                raise DrillError("只能删除自己的题目")
            if row[1]:
                raise DrillError("内置题目不能删除")
            cur.execute("DELETE FROM drill_submissions WHERE drill_id=%s", (did,))
            cur.execute("DELETE FROM drills WHERE id=%s", (did,))
        conn.commit()
    finally:
        conn.close()


# ---------------- 判分 ----------------

# ---------------- 出题：初始数据导入（文件 / 已有数据库） ----------------

SETUP_IMPORT_ROWS = 5000      # 单次导入行数上限（题目数据不宜过大）
SETUP_IMPORT_COLS = 64
SETUP_TEXT_MAX = 2 * 1024 * 1024


def _sql_lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace("'", "\\'")
    return "'" + s + "'"


def tables_to_sql(table: str, cols: list, types: list, rows: list) -> str:
    """把二维数据转成 CREATE TABLE + INSERT 语句。"""
    from .db import valid_ident

    name = table if valid_ident(table) else "data_table"
    defs = ", ".join(f"`{c}` {t}" for c, t in zip(cols, types))
    lines = [f"-- 由导入文件生成：{name}（{len(rows)} 行）",
             f"CREATE TABLE `{name}` (\n  {defs}\n);"]
    if rows:
        collist = ", ".join(f"`{c}`" for c in cols)
        for i in range(0, len(rows), 50):
            chunk = rows[i:i + 50]
            vals = ",\n  ".join("(" + ", ".join(_sql_lit(v) for v in r) + ")" for r in chunk)
            lines.append(f"INSERT INTO `{name}` ({collist}) VALUES\n  {vals};")
    return "\n".join(lines)


def _table_name_from(filename: str) -> str:
    import os
    import re as _re

    stem = os.path.splitext(os.path.basename(filename or ""))[0] or "data_table"
    n = _re.sub(r"[^\w\u4e00-\u9fff-]", "_", stem).strip("_")[:40]
    return n or "data_table"


def setup_from_file(filename: str, data: bytes) -> dict:
    """把上传的 .sql / .csv / .xlsx 转成初始化 SQL 文本（不执行、不落库）。"""
    from . import importer

    name = (filename or "").lower()
    if len(data) > 8 * 1024 * 1024:
        raise DrillError("文件超过 8MB")
    if name.endswith(".sql"):
        from .community import parse_script_tables

        text = importer._decode(data)
        if len(text) > SETUP_TEXT_MAX:
            raise DrillError("SQL 脚本文本超过 2MB")
        tables = parse_script_tables(text)
        return {"sql": text, "tables": tables, "rows": None, "source": "sql"}

    if name.endswith(".csv"):
        import csv
        from .config import C

        text = importer._decode(data)
        first = text.splitlines()[0] if text.splitlines() else ""
        delim = max([",", ";", "\t", "|"], key=first.count)
        grid = [r for r in csv.reader(io.StringIO(text), delimiter=delim)
                if any((c or "").strip() for c in r)]
        if len(grid) > SETUP_IMPORT_ROWS + 1:
            raise DrillError(f"行数超过上限（{SETUP_IMPORT_ROWS} 行）")
        cols, types, rows = importer._rows_from_grid(grid, True)
        table = _table_name_from(filename)
        return {"sql": tables_to_sql(table, cols, types, rows),
                "tables": [table], "rows": len(rows), "source": "csv"}

    if name.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise DrillError("服务器未安装 openpyxl，无法解析 Excel")
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:
            raise DrillError(f"Excel 解析失败：{e}")
        try:
            ws = wb.worksheets[0]
            grid = []
            for row in ws.iter_rows(values_only=True):
                grid.append(list(row))
                if len(grid) > SETUP_IMPORT_ROWS + 1:
                    break
        finally:
            wb.close()
        from . import importer as _imp

        cols, types, rows = _imp._rows_from_grid(grid, True)
        table = _table_name_from(filename)
        return {"sql": tables_to_sql(table, cols, types, rows),
                "tables": [table], "rows": len(rows), "source": "xlsx"}

    raise DrillError("只支持 .sql / .csv / .xlsx 文件")


def setup_from_db(account: dict, db_name: str, max_rows: int = 2000) -> dict:
    """把一个已有数据库（含题库导入的素材包）导出成初始化 SQL。"""
    from . import community, sessions

    db_name = (db_name or "").strip()
    if not db_name:
        raise DrillError("先选一个数据库")
    if db_name not in sessions.owned_dbs(account["id"]):
        raise DrillError(f"数据库 {db_name} 不在你的名下")
    data = community.export_database(db_name, account["mysql_user"], account["mysql_pass"],
                                     max_rows=max_rows)
    sql = data.decode("utf-8", "replace")
    tables = community.parse_script_tables(sql)
    if len(sql) > SETUP_TEXT_MAX:
        raise DrillError("导出的 SQL 超过 2MB，建议换用数据量小一些的库")
    return {"sql": sql, "tables": tables, "rows": None, "source": "db", "db": db_name}


# ---------------- 出题人试跑（不落库、不改任何学生数据） ----------------

def try_sql(account: dict, setup: str, sql: str) -> dict:
    """在临时库里跑 setup + sql，返回表清单/结果/报错，供出题页实时预览。"""
    from . import sessions, sqlrun

    tmp = None
    try:
        tmp = sessions.create_user_db_unique(account, "try", origin="exam")
        out = {"tables": [], "results": [], "error": ""}
        if (setup or "").strip():
            r = sqlrun.run_sql(tmp, account["mysql_user"], account["mysql_pass"],
                               setup, owned_dbs=[tmp])
            out["results"] = r.get("results") or []
            e = _first_error(out["results"])
            if e:
                out["error"] = "初始化 SQL 出错：" + e
                return out
        out["tables"] = sqlrun.list_tables(tmp, account["mysql_user"], account["mysql_pass"])
        if (sql or "").strip():
            r2 = sqlrun.run_sql(tmp, account["mysql_user"], account["mysql_pass"],
                                sql, owned_dbs=[tmp])
            out["results"] = r2.get("results") or []
            e2 = _first_error(out["results"])
            if e2:
                out["error"] = "执行出错：" + e2
        return out
    finally:
        if tmp:
            try:
                sessions.drop_user_db(account, tmp)
            except Exception:
                pass


def try_python(account: dict, code: str, stdin_text: str = "") -> dict:
    """在沙箱里跑一段代码（出题人预览用）。"""
    r = _run_py_once(account, code, stdin_text)
    return {"out": r.get("out") or "", "err": r.get("err") or "",
            "exit": r.get("exit"), "why": r.get("why") or ""}


# ---------------- 题目包导入（一份试卷 + 参考答案 → 多道练习题） ----------------

QPACK_MAX_FILES = 12
QPACK_FILE_MAX = 8 * 1024 * 1024


def parse_package(files: list[dict]) -> dict:
    """解析上传的题目包，返回预览：试卷信息 + 每道小题（含答案、建议判分方式）。

    files: [{name, data(bytes)}]
    分类规则（按扩展名 + 内容特征）：
      .sql / .myd / .txt 里含 CREATE TABLE → 数据脚本（所有小题共用）
      .txt/.md 里含「题 干」或「1、2、」编号 → 题干
      其余含 -- 1 / ---8 分隔或 SQL 关键字 → 参考答案
    """
    from . import qpack

    if not files:
        raise DrillError("没有收到文件")
    if len(files) > QPACK_MAX_FILES:
        raise DrillError(f"一次最多 {QPACK_MAX_FILES} 个文件")

    data_sqls = []
    stem_texts = []
    ans_texts = []
    names = []

    for f in files:
        name = (f.get("name") or "").strip()
        raw = f.get("data") or b""
        if len(raw) > QPACK_FILE_MAX:
            raise DrillError(f"文件 {name} 超过 8MB")
        names.append(name)
        low = name.lower()
        text = qpack.decode_text(raw)

        # 1) 参考答案最先判定：有 -- 1 / ---8 这类题号分隔（题干和数据脚本都不会这样写）
        if re.search(r"^\s*-{2,}\s*(?:第\s*)?\d+\s*(?:题)?\s*$", text, re.M):
            ans_texts.append(text)
            continue
        # 2) 数据脚本：扩展名 .sql/.myd，或纯建表语句
        if low.endswith((".sql", ".myd")) or (
                low.endswith(".txt") and "CREATE TABLE" in text.upper() and "题" not in text[:200]):
            data_sqls.append(text)
            continue
        # 3) 题干：含「题 干」标记，或连续编号小题且不含 SQL 语句
        has_stem_mark = bool(re.search(r"[『【]?\s*题\s*干\s*[』】]?", text))
        numbered = len(re.findall(r"^\s*(?:\d+\s*[、.．)]|[(（]\d+[)）])", text, re.M))
        has_sql = bool(re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE)\b", text, re.I))
        if has_stem_mark or (numbered >= 3 and not has_sql):
            stem_texts.append(text)
            continue
        # 4) 其余含 SQL 关键字的当答案
        if has_sql:
            ans_texts.append(text)
            continue
        stem_texts.append(text)   # 兜底当题干

    if not stem_texts:
        raise DrillError("没有找到题干文件（需要含 1、2、3… 编号的小题）")

    stem = qpack.parse_stem("\n\n".join(stem_texts))
    answers = qpack.split_answer_files([{"content": t} for t in ans_texts])
    data_sql = qpack.clean_data_sql("\n\n".join(data_sqls)) if data_sqls else ""
    # 老师给的数据文件常常是「做完题之后」的库快照 —— 先把答案产物（建的表、
    # 插入的行、视图/触发器/存储过程）剔掉，否则学生作答会报“已存在/主键重复”。
    stripped_note = []
    if data_sql and answers:
        data_sql, stripped_note = qpack.strip_answer_artifacts(
            data_sql, [answers[k] for k in sorted(answers)])

    if not stem["questions"]:
        raise DrillError("题干里没有解析出小题（需要 1、2、3… 这样编号）")

    items = []
    for q in stem["questions"]:
        ans = answers.get(q["no"], "")
        qtype = qpack.guess_type(q["text"], ans)
        # 建对象/改数据题一律用「整库状态」判分：学生答案和参考答案各在一个干净库里
        # 执行，再比较最终数据库状态（不会重复执行同一句 SQL 导致“已存在”）
        if qtype in ("sql_dml", "sql_ddl"):
            mode = "dbstate"
        else:
            mode = "result"
        items.append({
            "no": q["no"],
            "text": q["text"],
            "note": q.get("note", ""),
            "answer": qpack.clean_answer(ans),
            "kind": qtype,
            "judgeMode": mode,
            "hasAnswer": bool(ans.strip()),
        })

    from .community import parse_script_tables

    return {
        "title": stem["title"] or "未命名试卷",
        "description": stem["description"],
        "dataSql": data_sql,
        "tables": parse_script_tables(data_sql) if data_sql else [],
        "questions": items,
        "files": names,
        "stripped": stripped_note,
        "warnings": qpack.answer_touches_missing_data(
            data_sql, [qpack.clean_answer(answers[k]) for k in sorted(answers)]),
        "stats": {
            "total": len(items),
            "withAnswer": sum(1 for x in items if x["hasAnswer"]),
            "select": sum(1 for x in items if x["kind"] == "sql_select"),
            "dml": sum(1 for x in items if x["kind"] == "sql_dml"),
            "ddl": sum(1 for x in items if x["kind"] == "sql_ddl"),
        },
    }


def create_from_package(account: dict, pkg: dict, publish: bool = True,
                        judge_override: dict | None = None) -> dict:
    """把解析好的题目包批量建成练习题（共用同一份初始化数据）。"""
    _require_perm(account)
    questions = pkg.get("questions") or []
    if not questions:
        raise DrillError("没有可创建的题目")
    data_sql = pkg.get("dataSql") or ""
    judge_override = judge_override or {}

    created = []
    duplicates = []
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            # 同一份试卷重复导入时跳过同名题，避免点两次「创建」就多出一整套
            cur.execute("SELECT title FROM drills WHERE account_id=%s AND course='sql'",
                        (account["id"],))
            existing = {r[0] for r in cur.fetchall()}
            for q in questions:
                if not (q.get("answer") or "").strip():
                    continue      # 没有参考答案的题跳过（无法判分）
                mode = judge_override.get(str(q["no"])) or q.get("judgeMode") or "result"
                title = f"{q['no']}. " + " ".join((q.get("text") or "").split())[:60]
                if title in existing:
                    duplicates.append({"no": q["no"], "title": title})
                    continue
                # DDL / DML 用 state 判分：答案作为“校验语句”不合适时，改用查询校验
                verify = q["answer"]
                cur.execute(f"""INSERT INTO drills
                    (account_id, uploader, course, type, title, stem, setup_sql, verify_sql,
                     starter_code, input_data, expected_output, options_json, answer_json, hint,
                     judge_mode, test_cases, status, published_at)
                    VALUES (%s,%s,'sql','sql',%s,%s,%s,%s,'','','','[]','{{}}',%s,%s,'',
                            %s, CASE WHEN %s=1 THEN NOW() ELSE NULL END)""",
                    (account["id"], account["display"], title,
                     (q.get("text") or "") + (("\n\n" + q["note"]) if q.get("note") else ""),
                     data_sql, verify, q.get("note", ""), mode,
                     1 if publish else 0, 1 if publish else 0))
                created.append({"id": cur.lastrowid, "no": q["no"], "title": title})
                existing.add(title)
        conn.commit()
    finally:
        conn.close()
    return {"created": created, "duplicates": duplicates,
            "skipped": len(questions) - len(created) - len(duplicates)}


# ---------------- SQL 题沙箱库 ----------------
# 每个（学生, 题目）一个独立的真实数据库，初始化 SQL 跑在里面。
# 学生可以像主页一样自由查询、点表预览，交卷时再用另一个临时库判分（不影响沙箱）。

def _sandbox_name(account_id: int, drill_id: int) -> str:
    return f"x_{account_id}_{drill_id}"


def ensure_sandbox(account: dict, drill_id: int, reset: bool = False) -> dict:
    """确保该题的沙箱库存在并已执行初始化 SQL，返回 {db, tables}。"""
    from . import sessions, sqlrun

    full = get_full(drill_id)
    if full["type"] != "sql":
        raise DrillError("只有 SQL 题需要沙箱库")
    mine = full["account_id"] == account["id"]
    if not full["status"] and not (mine or account.get("role") == "admin"):
        raise DrillError("这题还没发布")

    db = _sandbox_name(account["id"], drill_id)
    owner = False
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id FROM dbs WHERE db_name=%s", (db,))
            row = cur.fetchone()
            owner = bool(row) and row[0] == account["id"]
    finally:
        conn.close()

    if reset and owner:
        try:
            sessions.drop_user_db(account, db)
        except Exception:
            pass
        owner = False
    if not owner:
        try:
            sessions.create_user_db(account, db, origin="drill")
        except Exception:
            # 并发/残留：已存在同名库时直接复用
            pass
        setup = (full.get("setupSql") or "").strip()
        if setup:
            r = sqlrun.run_sql(db, account["mysql_user"], account["mysql_pass"],
                               setup, owned_dbs=[db])
            err = _first_error(r.get("results"))
            if err:
                raise DrillError("题目的初始化 SQL 有问题，请联系出题老师：" + err)
    tables = sqlrun.list_tables(db, account["mysql_user"], account["mysql_pass"])
    return {"db": db, "tables": tables}


def _runner(method: str, path: str, payload=None):
    req = urllib.request.Request(
        C.RUNNER_URL + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Runner-Token": C.RUNNER_TOKEN},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"error": "沙箱执行出错"}
    except Exception:
        return {"error": "沙箱服务不可用"}


def _last_rows(results):
    for r in reversed(results or []):
        if r.get("type") == "rows":
            return {"columns": r.get("columns") or [], "rows": r.get("rows") or []}
    return None


def _first_error(results):
    for r in results or []:
        if r.get("type") == "error":
            return r.get("msg") or "SQL 出错了"
    return None


def _mode(dr: dict) -> str:
    return dr.get("judgeMode") or (JUDGE_MODES.get(dr.get("type")) or [""])[0]


def _first_cell(rs):
    if not rs or not rs.get("rows") or not rs["rows"][0]:
        return None
    return rs["rows"][0][0]


def _all_cells(rs):
    return [v for row in (rs or {}).get("rows") or [] for v in row]


def snapshot_db(db: str, user: str, password: str, max_rows: int = 500) -> dict:
    """整库快照：{表名: {cols, rows}}，用于 dbstate 判分（建表/增删改通用）。"""
    from .db import q_ident, user_conn

    out = {}
    conn = user_conn(db, user, password)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            names = [r[0] for r in cur.fetchall() if not str(r[0]).startswith("__")]
            for name in sorted(names):
                try:
                    cur.execute(f"SELECT * FROM {q_ident(name)} LIMIT %s", (max_rows,))
                    cols = [d[0] for d in cur.description]
                    rows = [[conv_value(v) for v in r] for r in cur.fetchall()]
                    out[str(name).lower()] = {"cols": cols, "rows": rows}
                except Exception:
                    out[str(name).lower()] = {"cols": [], "rows": []}
    finally:
        conn.close()
    return out


def compare_db(student: dict, expected: dict) -> tuple[bool, str]:
    """比较两个整库快照。返回 (是否一致, 说明)。"""
    sk, ek = set(student), set(expected)
    missing = sorted(ek - sk)
    extra = sorted(sk - ek)
    if missing:
        return False, "缺少对象：" + "、".join(missing[:6])
    if extra:
        return False, "多了不该有的对象：" + "、".join(extra[:6])
    for t in sorted(ek):
        s_cols = [str(c) for c in student[t]["cols"]]
        e_cols = [str(c) for c in expected[t]["cols"]]
        if s_cols != e_cols:
            return False, f"表 {t} 的字段不一致（期望 {', '.join(e_cols[:6])}）"
        s_rows = sorted([str(v) for v in row] for row in student[t]["rows"])
        e_rows = sorted([str(v) for v in row] for row in expected[t]["rows"])
        if s_rows != e_rows:
            if len(s_rows) != len(e_rows):
                return False, (f"表 {t} 的数据不一致（期望 {len(e_rows)} 行，"
                               f"你的是 {len(s_rows)} 行）")
            # 行数相同但内容不同：指出第一处差异，学生才知道错在哪
            s_set, e_set = set(map(tuple, s_rows)), set(map(tuple, e_rows))
            lost = next(iter(e_set - s_set), None)
            made = next(iter(s_set - e_set), None)
            cols = [str(c) for c in e_cols]

            def fmt(row):
                pairs = [f"{c}={v}" for c, v in zip(cols, row) if v not in ("None", "")]
                return ", ".join(pairs[:4]) or "(空行)"

            detail = []
            if lost:
                detail.append(f"缺少 {fmt(lost)}")
            if made:
                detail.append(f"多了 {fmt(made)}")
            return False, (f"表 {t} 的数据不一致（行数都是 {len(e_rows)} 行，"
                           f"但内容不同：{'；'.join(detail)}）")
    return True, "数据库状态与标准答案一致。"


def judge_sql(account: dict, dr: dict, answer: str) -> dict:
    """SQL 判分，按 dr.judgeMode 选择比对方式。"""
    from . import sessions, sqlrun

    if not (answer or "").strip():
        raise DrillError("先写点 SQL")
    mode = _mode(dr)
    setup = dr.get("setupSql") or ""
    verify = dr.get("verifySql") or ""

    def new_db(tag):
        return sessions.create_user_db_unique(account, tag, origin="exam")

    def drop(db):
        if db:
            try:
                sessions.drop_user_db(account, db)
            except Exception:
                pass

    def run(db, sql):
        out = sqlrun.run_sql(db, account["mysql_user"], account["mysql_pass"],
                             sql, owned_dbs=[db])
        results = out.get("results") or []
        return results, _first_error(results), _last_rows(results)

    db = None
    try:
        db = new_db("exam")
        if setup.strip():
            _, e, _ = run(db, setup)
            if e:
                raise DrillError("题目的初始化 SQL 有问题，请联系出题老师：" + e)

        st_results, st_err, student = run(db, answer)
        if st_err:
            return {"passed": False, "kind": "sql", "mode": mode,
                    "reason": "你的 SQL 执行出错：" + st_err,
                    "student": None, "expected": None}

        # ---- 改数据题：学生 SQL 已执行，再跑校验读「实际状态」 ----
        if mode == "dbstate":
            # 学生 SQL 已执行完，比较「整库」的结构与数据
            student_snap = snapshot_db(db, account["mysql_user"], account["mysql_pass"])
            db2 = None
            try:
                db2 = new_db("exam_key")
                if setup.strip():
                    run(db2, setup)
                _, e2, _ = run(db2, verify)
                if e2:
                    return {"passed": False, "kind": "sql", "mode": mode,
                            "reason": "标准答案执行出错（请检查参考答案）：" + e2,
                            "student": None, "expected": None}
                expected_snap = snapshot_db(db2, account["mysql_user"], account["mysql_pass"])
                passed, why = compare_db(student_snap, expected_snap)
                rows_out = [[k, len(v["rows"])] for k, v in sorted(expected_snap.items())]
                return {"passed": passed, "kind": "sql", "mode": mode,
                        "reason": why if not passed else "数据库状态正确，通过。",
                        "student": {"columns": ["对象", "行数"],
                                    "rows": [[k, len(v["rows"])] for k, v in sorted(student_snap.items())]},
                        "expected": {"columns": ["对象", "行数"], "rows": rows_out}}
            finally:
                drop(db2)

        if mode == "state":
            _, vf_err, actual = run(db, verify)
            if vf_err or actual is None:
                return {"passed": False, "kind": "sql", "mode": mode,
                        "reason": "校验语句执行出错（请检查题目的标准答案 SQL）。",
                        "student": None, "expected": None}
            # 另起一个库：只跑 setup + 标准答案 SQL，再跑校验得到「期望状态」
            db2 = None
            try:
                db2 = new_db("exam_key")
                if setup.strip():
                    run(db2, setup)
                _, e2, _ = run(db2, verify)
                if e2:
                    return {"passed": False, "kind": "sql", "mode": mode,
                            "reason": "标准答案执行出错（请检查题目的标准答案 SQL）。",
                            "student": actual, "expected": None}
                # 标准答案在本模式下由出题人写在 verifySql 里（用于读状态），
                # 期望值需要出题人另外给出——这里用「出题人答案」不可得，
                # 因此 state 模式的期望来自 answer_json 里的 values（可选）。
                expected_vals = (_answer_of(dr).get("values") or [])
                if expected_vals:
                    got = [str(v) for v in _all_cells(actual)]
                    passed = got == [str(v) for v in expected_vals]
                    return {"passed": passed, "kind": "sql", "mode": mode,
                            "reason": ("数据修改正确。" if passed
                                       else "修改后的数据与期望不一致。"),
                            "student": actual,
                            "expected": {"columns": actual["columns"],
                                         "rows": [[v] for v in expected_vals]},
                            "colsOk": True}
                # 没配期望值时，用「学生答案」重新初始化后执行标准答案 SQL 比对
                _, _, ref = run(db2, verify)
                passed = compare_sets(actual, ref) if ref is not None else False
                return {"passed": passed, "kind": "sql", "mode": mode,
                        "reason": ("数据修改正确。" if passed
                                   else "修改后的数据与期望不一致。"),
                        "student": actual, "expected": ref}
            finally:
                drop(db2)

        if student is None:
            if mode in ("state", "dbstate"):
                student = {"columns": [], "rows": []}
            else:
                return {"passed": False, "kind": "sql", "mode": mode,
                        "reason": "没有查到结果：请用一条 SELECT 查询语句作答。",
                        "student": None, "expected": None}

        # ---- 其余模式：拿标准答案的结果集来比 ----
        _, vf_err, expected = run(db, verify)
        if vf_err or expected is None:
            return {"passed": False, "kind": "sql", "mode": mode,
                    "reason": "标准答案查询失败，请联系出题老师。",
                    "student": student, "expected": None}

        if mode == "cell":
            a, b = _first_cell(student), _first_cell(expected)
            passed = a is not None and b is not None and str(a) == str(b)
            reason = (f"结果正确（{b}）。" if passed else f"结果不对：期望 {b}，你查出的是 {a}。")
        elif mode == "contains":
            want = expected["rows"][0][0] if expected.get("rows") else None
            vals = [str(v) for v in _all_cells(student)]
            passed = want is not None and str(want) in vals
            reason = (f"结果中包含 {want}，通过。" if passed
                      else f"结果里没有找到 {want}。")
        elif mode == "rows_only":
            passed = normalize_rows(student.get("rows")) == normalize_rows(expected.get("rows"))
            reason = ("数据与标准答案一致，通过。" if passed else "数据行与标准答案不一致。")
        elif mode == "result_ordered":
            sc = [str(c) for c in student.get("columns") or []]
            ec = [str(c) for c in expected.get("columns") or []]
            sr = [[str(v) for v in row] for row in student.get("rows") or []]
            er = [[str(v) for v in row] for row in expected.get("rows") or []]
            passed = sc == ec and sr == er
            reason = ("结果集完全一致（含顺序），通过。" if passed
                      else "结果集或数据顺序与标准答案不一致。")
        else:
            passed = compare_sets(student, expected)
            reason = ("结果集与标准答案一致，通过。" if passed
                      else "结果集与标准答案不一致。")

        return {"passed": passed, "kind": "sql", "mode": mode, "reason": reason,
                "student": {"columns": student["columns"], "rows": student["rows"][:20]},
                "expected": {"columns": expected["columns"], "rows": expected["rows"][:20]},
                "colsOk": sorted(map(str, student["columns"])) ==
                          sorted(map(str, expected["columns"]))}
    finally:
        drop(db)


def _run_py_once(account: dict, code: str, stdin_text: str = "") -> dict:
    """在 runner 里跑一次代码，同步等待结果。"""
    start = _runner("POST", "/start", {
        "code": code,
        "db": {"host": C.DB_HOST, "port": C.DB_PORT, "user": account["mysql_user"],
               "pass": account["mysql_pass"], "name": account["db_name"]},
    })
    if not start.get("job"):
        return {"out": "", "err": str(start.get("error") or start.get("detail") or "沙箱启动失败"),
                "exit": -1, "why": "error"}
    job = start["job"]
    if (stdin_text or "").strip():
        _runner("POST", f"/job/{job}/input", {"text": stdin_text})
    st = {}
    deadline = time.monotonic() + PY_RUN_TIMEOUT
    while time.monotonic() < deadline:
        st = _runner("GET", f"/job/{job}/out?since_out=0&since_err=0")
        if st.get("error"):
            return {"out": "", "err": str(st["error"]), "exit": -1, "why": "error"}
        if not st.get("running"):
            break
        time.sleep(0.3)
    if st.get("running"):
        return {"out": st.get("out") or "", "err": st.get("err") or "",
                "exit": -9, "why": "timeout"}
    return {"out": st.get("out") or "", "err": st.get("err") or "",
            "exit": st.get("exit"), "why": st.get("why") or ""}


def judge_python(account: dict, dr: dict, code: str) -> dict:
    if not (code or "").strip():
        raise DrillError("先写点 Python 代码")
    mode = _mode(dr)
    expected = dr.get("expectedOutput") or ""

    # 多组测试用例：逐组跑，全过才通过
    if mode == "tests":
        try:
            cases = json.loads(dr.get("testCases") or "[]")
        except Exception:
            cases = []
        if not cases:
            raise DrillError("这道题没有配置测试用例，请联系出题老师")
        results = []
        all_ok = True
        first_got = ""
        for i, c in enumerate(cases[:5], 1):
            r = _run_py_once(account, code, c.get("input") or "")
            got = r["out"]
            if i == 1:
                first_got = got
            err = (r.get("err") or "").strip()
            if err:
                ok = False
                detail = "运行出错：" + err.splitlines()[-1][:160]
            else:
                ok = normalize_out(got) == normalize_out(c.get("expected") or "")
                detail = "" if ok else "输出与期望不一致"
            all_ok = all_ok and ok
            results.append({"n": i, "ok": ok, "input": (c.get("input") or "")[:200],
                            "expected": (c.get("expected") or "")[:400],
                            "got": got[:400], "detail": detail})
        return {"passed": all_ok, "kind": "python", "mode": mode,
                "reason": ("全部 %d 组测试通过。" % len(results)) if all_ok
                          else ("有 %d 组测试未通过。" % sum(1 for x in results if not x["ok"])),
                "got": first_got[:2000], "expected": "", "cases": results}

    r = _run_py_once(account, code, dr.get("inputData") or "")
    got = r["out"]
    err = (r.get("err") or "").strip()
    if r.get("why") == "timeout":
        return {"passed": False, "kind": "python", "mode": mode, "got": got,
                "expected": expected, "reason": "程序没有在 25 秒内结束。"}
    if err:
        return {"passed": False, "kind": "python", "mode": mode, "got": got,
                "expected": expected, "reason": "运行出错了：" + err.splitlines()[-1][:200]}

    if mode == "contains":
        passed = expected.strip() != "" and expected.strip() in got
        reason = ("输出包含期望内容，通过。" if passed
                  else "输出里没有找到期望的内容。")
    elif mode == "regex":
        try:
            passed = re.search(expected, got, re.S) is not None
            reason = ("输出符合要求，通过。" if passed else "输出不符合正则要求。")
        except re.error as e:
            return {"passed": False, "kind": "python", "mode": mode, "got": got,
                    "expected": expected, "reason": "题目的正则表达式有误：" + str(e)}
    else:
        passed = normalize_out(got) == normalize_out(expected)
        reason = ("输出与期望一致，通过。" if passed else "输出与期望不一致。")
    return {"passed": passed, "kind": "python", "mode": mode,
            "got": got[:4000], "expected": expected[:4000], "reason": reason}


def _answer_of(d: dict) -> dict:
    """兼容两种形态：公开形态 answer / 原始行 answerJson。"""
    if isinstance(d.get("answer"), dict) and d["answer"]:
        return d["answer"]
    try:
        return json.loads(d.get("answerJson") or "{}")
    except Exception:
        return {}


def judge_objective(dr: dict, answer) -> dict:
    t = dr["type"]
    ans = _answer_of(dr)
    if t == "fill":
        want_list = ans.get("values") or []
        got = normalize_text(answer)
        answers = [normalize_text(v) for v in want_list]
        passed = bool(got) and any(got == a for a in answers)
        return {"passed": passed, "kind": "fill", "mode": "loose",
                "reason": "答案正确。" if passed else "答案不对。",
                "expected": list(want_list)}
    if t == "multiple":
        keys = [str(k).upper() for k in (ans.get("keys") or [])]
        got = [str(k).upper() for k in (answer or [])] if isinstance(answer, list) else \
              [x.strip().upper() for x in str(answer or "").split(",") if x.strip()]
        passed = sorted(set(keys)) == sorted(set(got)) and bool(keys)
        return {"passed": passed, "kind": "multiple", "mode": "keys",
                "reason": "选项全部正确。" if passed else "选项不对或不完整。",
                "expected": "、".join(sorted(keys))}
    keys = [str(answer or "").upper()]
    want = str(ans.get("key") or "").upper()
    passed = want != "" and keys[0] == want
    return {"passed": passed, "kind": t, "mode": "key",
            "reason": "答对了。" if passed else "答错了。", "expected": want}


def submit(account: dict, did: int, answer) -> dict:
    full = get_full(did)
    mine = full["account_id"] == account["id"]
    if not full["status"] and not (mine or account.get("role") == "admin"):
        raise DrillError("这题还没发布")
    t0 = time.monotonic()
    if full["type"] == "sql":
        res = judge_sql(account, full, str(answer or ""))
    elif full["type"] == "python":
        res = judge_python(account, full, str(answer or ""))
    else:
        res = judge_objective(full, answer)
    ms = int((time.monotonic() - t0) * 1000)
    res["ms"] = ms
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO drill_submissions
                           (account_id, drill_id, passed, answer, detail, ms)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (account["id"], did, 1 if res["passed"] else 0,
                         json.dumps(answer, ensure_ascii=False) if not isinstance(answer, str)
                         else answer[:60000],
                         json.dumps(res, ensure_ascii=False, default=str)[:20000], ms))
        conn.commit()
    finally:
        conn.close()
    res["passed"] = bool(res["passed"])
    return res


def my_wrong(account: dict, limit: int = 100) -> list[dict]:
    """错题重做：做过且没通过的已发布题。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT d.{_COLS.replace(', ', ', d.')}
                            FROM drills d
                            JOIN (SELECT drill_id, MAX(passed) AS passed
                                  FROM drill_submissions WHERE account_id=%s
                                  GROUP BY drill_id) s ON s.drill_id=d.id
                            WHERE d.status=1 AND s.passed=0
                            ORDER BY d.course, d.id DESC LIMIT %s""",
                        (account["id"], limit))
            rows = cur.fetchall()
    finally:
        conn.close()
    return [_public(_row_to_dict(r), with_answer=False) for r in rows]
