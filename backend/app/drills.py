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
import hashlib
import io
import json
import os
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
SETUP_TIMEOUT = 90.0     # 题目初始化 / 标准答案这类内部脚本的执行上限（慢盘也够用）
SCORE_DEFAULT = 10       # 单题默认分值
SCORE_MIN, SCORE_MAX = 1, 100
PAPER_TITLE_MAX = 120


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
            # 一套题 = 一张试卷卡片：题目归属试卷，并带分值
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)}.drill_papers (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    uploader VARCHAR(64) NOT NULL DEFAULT '',
                    course VARCHAR(16) NOT NULL DEFAULT 'sql',
                    title VARCHAR(200) NOT NULL DEFAULT '',
                    description TEXT,
                    status TINYINT(1) NOT NULL DEFAULT 0,
                    max_attempts INT NOT NULL DEFAULT 0,
                    show_answer TINYINT(1) NOT NULL DEFAULT 1,
                    time_limit_minutes INT NOT NULL DEFAULT 0,
                    allow_pause TINYINT(1) NOT NULL DEFAULT 1,
                    max_resumes INT NOT NULL DEFAULT 3,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    published_at DATETIME NULL,
                    KEY idx_owner (account_id),
                    KEY idx_course (course, status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 旧库升级：可交卷次数（0=不限）/ 交卷后是否显示答案
            for col, ddl in (
                ("max_attempts", "ADD COLUMN max_attempts INT NOT NULL DEFAULT 0"),
                ("show_answer", "ADD COLUMN show_answer TINYINT(1) NOT NULL DEFAULT 1"),
                ("time_limit_minutes", "ADD COLUMN time_limit_minutes INT NOT NULL DEFAULT 0"),
                ("allow_pause", "ADD COLUMN allow_pause TINYINT(1) NOT NULL DEFAULT 1"),
                ("max_resumes", "ADD COLUMN max_resumes INT NOT NULL DEFAULT 3"),
            ):
                try:
                    cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.drill_papers {ddl}")
                except Exception:
                    pass
            try:
                cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.drills "
                            f"ADD COLUMN paper_id BIGINT NOT NULL DEFAULT 0")
                cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.drills "
                            f"ADD COLUMN score INT NOT NULL DEFAULT {SCORE_DEFAULT}")
            except Exception:
                pass
            _migrate_papers(cur)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)}.drill_submissions (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    account_id BIGINT NOT NULL,
                    drill_id BIGINT NOT NULL,
                    attempt_id BIGINT NOT NULL DEFAULT 0,
                    passed TINYINT(1) NOT NULL DEFAULT 0,
                    answer MEDIUMTEXT,
                    detail MEDIUMTEXT,
                    ms INT NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_user (account_id, drill_id),
                    KEY idx_drill (drill_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            try:
                cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.drill_submissions "
                            "ADD COLUMN attempt_id BIGINT NOT NULL DEFAULT 0")
            except Exception:
                pass
            # 整卷交卷记录：一次交卷一整行，次数限制和统计都按整卷算
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)}.drill_paper_attempts (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    paper_id BIGINT NOT NULL,
                    account_id BIGINT NOT NULL,
                    attempt_no INT NOT NULL DEFAULT 1,
                    score INT NOT NULL DEFAULT 0,
                    total_score INT NOT NULL DEFAULT 0,
                    passed_n INT NOT NULL DEFAULT 0,
                    answered_n INT NOT NULL DEFAULT 0,
                    question_n INT NOT NULL DEFAULT 0,
                    timed_out TINYINT(1) NOT NULL DEFAULT 0,
                    started_at DATETIME NULL,
                    limit_minutes INT NOT NULL DEFAULT 0,
                    detail MEDIUMTEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_user (account_id, paper_id),
                    KEY idx_paper (paper_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            for col, ddl in (
                ("timed_out", "ADD COLUMN timed_out TINYINT(1) NOT NULL DEFAULT 0"),
                ("started_at", "ADD COLUMN started_at DATETIME NULL"),
                ("limit_minutes", "ADD COLUMN limit_minutes INT NOT NULL DEFAULT 0"),
            ):
                try:
                    cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.drill_paper_attempts {ddl}")
                except Exception:
                    pass
            # 限时作答：开始做题时记一行，交卷后删除，下一次重新计时
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.COMMUNITY_DB)}.drill_paper_sessions (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    paper_id BIGINT NOT NULL,
                    account_id BIGINT NOT NULL,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    limit_minutes INT NOT NULL DEFAULT 0,
                    elapsed_seconds INT NOT NULL DEFAULT 0,
                    active_since DATETIME NULL,
                    last_seen DATETIME NULL,
                    resume_count INT NOT NULL DEFAULT 0,
                    visit_id VARCHAR(48) NOT NULL DEFAULT '',
                    UNIQUE KEY uq_user_paper (account_id, paper_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            for col, ddl in (
                ("elapsed_seconds", "ADD COLUMN elapsed_seconds INT NOT NULL DEFAULT 0"),
                ("active_since", "ADD COLUMN active_since DATETIME NULL"),
                ("last_seen", "ADD COLUMN last_seen DATETIME NULL"),
                ("resume_count", "ADD COLUMN resume_count INT NOT NULL DEFAULT 0"),
                ("visit_id", "ADD COLUMN visit_id VARCHAR(48) NOT NULL DEFAULT ''"),
            ):
                try:
                    cur.execute(f"ALTER TABLE {q_ident(C.COMMUNITY_DB)}.drill_paper_sessions {ddl}")
                except Exception:
                    pass
    finally:
        conn.close()


def _migrate_papers(cur):
    """旧库升级：把还没有归属试卷的题目按「同一次创建」归成一套，各建一张试卷。

    同一次批量导入（题目包）的题创建时间在同一秒内，据此分组；单独出的题各自成一套。
    """
    db = q_ident(C.COMMUNITY_DB)
    cur.execute(f"""SELECT id, account_id, uploader, course, title, status, created_at
                    FROM {db}.drills WHERE paper_id=0
                    ORDER BY account_id, course, created_at, id""")
    rows = cur.fetchall()
    groups = {}
    for r in rows:
        groups.setdefault((r[1], r[3], str(r[6])), []).append(r)
    for (acc, course, _ts), items in groups.items():
        title = (items[0][4] or "未命名试卷")[:PAPER_TITLE_MAX]
        if len(items) > 1:
            title = f"{title[:40]} 等 {len(items)} 题"
        published = any(x[5] for x in items)
        cur.execute(f"""INSERT INTO {db}.drill_papers
                        (account_id, uploader, course, title, description, status,
                         created_at, published_at)
                        VALUES (%s,%s,%s,%s,'',%s,%s,%s)""",
                    (acc, items[0][2], course, title, 1 if published else 0,
                     items[0][6], items[0][6] if published else None))
        pid = cur.lastrowid
        ids = [x[0] for x in items]
        marks = ",".join(["%s"] * len(ids))
        cur.execute(f"UPDATE {db}.drills SET paper_id=%s WHERE id IN ({marks})", [pid] + ids)


def _ensure_paper(cur, account: dict, course: str, title: str, description: str = "",
                  publish: bool = False) -> int:
    """按名字找试卷，没有就建一张（同一账号 + 分类 + 同名视为同一套）。"""
    name = (title or "").strip()[:PAPER_TITLE_MAX] or "未命名试卷"
    cur.execute("""SELECT id FROM drill_papers
                   WHERE account_id=%s AND course=%s AND title=%s LIMIT 1""",
                (account["id"], course, name))
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute("""INSERT INTO drill_papers
                   (account_id, uploader, course, title, description, status, published_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (account["id"], account["display"], course, name, description or "",
                 1 if publish else 0, None))
    return int(cur.lastrowid)


def _sync_paper_status(cur, paper_id: int):
    """试卷可见性跟着题目走：只要有一道题发布了，这张卡片就算已发布。"""
    if not paper_id:
        return
    cur.execute("""UPDATE drill_papers p
                   SET p.status = (SELECT MAX(d.status) FROM drills d WHERE d.paper_id=p.id),
                       p.published_at = COALESCE(
                           p.published_at,
                           (SELECT MIN(d.published_at) FROM drills d
                            WHERE d.paper_id=p.id AND d.published_at IS NOT NULL))
                   WHERE p.id=%s""", (paper_id,))


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
         "status, builtin, created_at, updated_at, published_at, judge_mode, test_cases, "
         "paper_id, score")
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
        "paperId": int(r[22] or 0), "score": int(r[23] or 0),
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


# ---------------- 试卷（一套题 = 一张卡片） ----------------

def _paper_row(r) -> dict:
    return {
        "id": int(r[0]), "uploader": r[2] or "", "course": r[3] or "sql",
        "title": r[4] or "(未命名试卷)", "description": r[5] or "",
        "status": int(r[6] or 0), "createdAt": str(r[7]),
        "publishedAt": str(r[8]) if r[8] else "",
        "questionCount": int(r[9] or 0), "totalScore": int(r[10] or 0),
        "myScore": int(r[11] or 0), "doneCount": int(r[12] or 0),
        "triedCount": int(r[13] or 0),
        "maxAttempts": int(r[14] or 0), "showAnswer": bool(r[15]),
        "timeLimitMinutes": int(r[16] or 0),
        "allowPause": bool(r[17]) if r[17] is not None else True,
        "maxResumes": int(r[18] or 3),
    }


_PAPER_SELECT = """
    SELECT p.id, p.account_id, p.uploader, p.course, p.title, p.description,
           p.status, p.created_at, p.published_at,
           COUNT(d.id) AS qn,
           COALESCE(SUM(d.score), 0) AS total_score,
           COALESCE(SUM(CASE WHEN s.passed = 1 THEN d.score ELSE 0 END), 0) AS my_score,
           COALESCE(SUM(CASE WHEN s.passed = 1 THEN 1 ELSE 0 END), 0) AS done_n,
           COALESCE(SUM(CASE WHEN s.attempts > 0 THEN 1 ELSE 0 END), 0) AS tried_n,
           p.max_attempts, p.show_answer, p.time_limit_minutes,
           p.allow_pause, p.max_resumes
      FROM drill_papers p
      LEFT JOIN drills d
             ON d.paper_id = p.id AND (d.status = 1 OR d.account_id = %s)
      LEFT JOIN (SELECT drill_id, MAX(passed) AS passed, COUNT(*) AS attempts
                   FROM drill_submissions WHERE account_id = %s
                  GROUP BY drill_id) s ON s.drill_id = d.id
"""


def _attempt_map(account_id: int, paper_ids: list[int], with_detail: bool = False) -> dict:
    """按试卷批量取「我」的整卷交卷记录，按交卷顺序返回。"""
    out = {}
    ids = [int(x) for x in paper_ids if int(x or 0) > 0]
    if not ids:
        return out
    marks = ",".join(["%s"] * len(ids))
    cols = ("id, attempt_no, score, total_score, passed_n, answered_n, question_n"
            + (", detail" if with_detail else "") + ", created_at")
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT paper_id, {cols} FROM drill_paper_attempts
                             WHERE account_id=%s AND paper_id IN ({marks})
                             ORDER BY attempt_no ASC, id ASC""",
                        [account_id] + ids)
            rows = cur.fetchall()
    finally:
        conn.close()
    for r in rows:
        pid = int(r[0])
        d = {"id": int(r[1]), "no": int(r[2]), "score": int(r[3] or 0),
             "totalScore": int(r[4] or 0), "passed_n": int(r[5] or 0),
             "answered_n": int(r[6] or 0), "question_n": int(r[7] or 0)}
        if with_detail:
            d["detail"] = r[8] or ""
            d["at"] = str(r[9])
        else:
            d["at"] = str(r[8])
        out.setdefault(pid, []).append(d)
    return out


def _apply_attempt_summary(p: dict, rows: list[dict]):
    p["attemptCount"] = len(rows)
    if not rows:
        p["lastScore"] = 0
        p["lastAttemptAt"] = ""
        return
    last = rows[-1]
    p["myScore"] = max(r["score"] for r in rows)
    p["doneCount"] = max(r["passed_n"] for r in rows)
    p["triedCount"] = last["answered_n"]
    p["lastScore"] = last["score"]
    p["lastAttemptAt"] = last["at"]
    p["finished"] = p["questionCount"] > 0 and p["doneCount"] >= p["questionCount"]


def list_papers(account: dict, course: str = "") -> list[dict]:
    """练习页的卡片清单：已发布的试卷 + 自己的草稿试卷，带我的得分与进度。"""
    where = ["(p.status = 1 OR p.account_id = %s)"]
    params = [account["id"], account["id"], account["id"]]
    if course:
        where.append("p.course = %s")
        params.append(course)
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""{_PAPER_SELECT}
                            WHERE {' AND '.join(where)}
                            GROUP BY p.id
                            HAVING qn > 0
                            ORDER BY FIELD(p.course,'sql','python','basic'),
                                     p.status DESC, p.published_at DESC, p.id DESC""", params)
            rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        p = _paper_row(r)
        p["courseLabel"] = COURSE_LABEL.get(p["course"], p["course"])
        p["mine"] = r[1] == account["id"]
        p["finished"] = p["questionCount"] > 0 and p["doneCount"] >= p["questionCount"]
        p["attemptCount"] = 0
        out.append(p)
    amap = _attempt_map(account["id"], [p["id"] for p in out])
    for p in out:
        _apply_attempt_summary(p, amap.get(p["id"]) or [])
    return out


def get_paper(account: dict, pid: int) -> dict:
    """试卷详情：题目清单（不含答案）+ 我的得分。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""{_PAPER_SELECT}
                            WHERE p.id = %s
                            GROUP BY p.id""",
                        [account["id"], account["id"], pid])
            r = cur.fetchone()
            if not r:
                raise DrillError("试卷不存在")
            if not r[6] and r[1] != account["id"] and account.get("role") != "admin":
                raise DrillError("这是别人的草稿，不能查看")
            cur.execute(f"""SELECT d.{_COLS.replace(', ', ', d.')},
                                   MAX(s.passed) AS passed, COUNT(s.id) AS attempts,
                                   MAX(s.created_at) AS last_at
                              FROM drills d
                              LEFT JOIN drill_submissions s
                                     ON s.drill_id = d.id AND s.account_id = %s
                             WHERE d.paper_id = %s AND (d.status = 1 OR d.account_id = %s)
                             GROUP BY d.id
                             ORDER BY d.id ASC""",
                        (account["id"], pid, account["id"]))
            rows = cur.fetchall()
    finally:
        conn.close()
    p = _paper_row(r)
    p["courseLabel"] = COURSE_LABEL.get(p["course"], p["course"])
    p["mine"] = r[1] == account["id"]
    p["finished"] = p["questionCount"] > 0 and p["doneCount"] >= p["questionCount"]
    qs = []
    for i, row in enumerate(rows, 1):
        n = _N_DRILL_COLS
        d = _public(_row_to_dict(row[:n]), with_answer=False)
        d["no"] = i
        d["passed"] = bool(row[n])
        d["attempts"] = int(row[n + 1] or 0)
        d["lastAt"] = str(row[n + 2]) if row[n + 2] else ""
        d["gotScore"] = d["score"] if d["passed"] else 0
        qs.append(d)
    p["questions"] = qs
    # 整卷口径：有交卷记录时，卡片/详情的分数和每题状态都以最近的整卷交卷为准
    amap = _attempt_map(account["id"], [pid])
    arows = amap.get(pid) or []
    _apply_attempt_summary(p, arows)
    p["latestAttemptNo"] = 0
    p["latestAttemptAt"] = ""
    if arows:
        last = arows[-1]
        p["latestAttemptNo"] = last["no"]
        p["latestAttemptAt"] = last["at"]
        detail = {}
        conn = root_conn(C.COMMUNITY_DB)
        try:
            with conn.cursor() as cur:
                cur.execute("""SELECT detail FROM drill_paper_attempts
                                WHERE paper_id=%s AND account_id=%s
                                ORDER BY attempt_no DESC, id DESC LIMIT 1""",
                            (pid, account["id"]))
                dr = cur.fetchone()
                if dr and dr[0]:
                    try:
                        detail = json.loads(dr[0])
                    except Exception:
                        detail = {}
        finally:
            conn.close()
        infos = {}
        for x in detail.get("questions") or []:
            try:
                infos[int(x.get("id"))] = x
            except Exception:
                pass
        for q in qs:
            info = infos.get(int(q["id"]))
            if info:
                q["passed"] = bool(info.get("passed"))
                q["gotScore"] = int(info.get("score") or 0)
                q["attempts"] = 1 if info.get("answered") else 0
                q["lastAt"] = last["at"] if info.get("answered") else ""
            else:
                q["passed"] = False
                q["gotScore"] = 0
                q["attempts"] = 0
                q["lastAt"] = ""
    return p


def update_paper_settings(account: dict, pid: int, max_attempts: int = 0,
                          show_answer: bool = True, time_limit_minutes: int = 0,
                          allow_pause: bool = True, max_resumes: int = 3) -> dict:
    """出卷人设置：次数、答案、限时、是否允许中途退出、异常退出可续做次数。"""
    n = int(max_attempts or 0)
    n = max(0, min(99, n))
    t = int(time_limit_minutes or 0)
    t = max(0, min(1440, t))
    mr = int(max_resumes or 3)
    mr = max(1, min(5, mr))
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id FROM drill_papers WHERE id=%s", (pid,))
            row = cur.fetchone()
            if not row:
                raise DrillError("试卷不存在")
            if row[0] != account["id"] and account.get("role") != "admin":
                raise DrillError("只能修改自己的试卷")
            cur.execute("""UPDATE drill_papers
                              SET max_attempts=%s, show_answer=%s, time_limit_minutes=%s,
                                  allow_pause=%s, max_resumes=%s
                            WHERE id=%s""",
                        (n, 1 if show_answer else 0, t,
                         1 if allow_pause else 0, mr, pid))
            # 正在作答的会话也按新时限从原开始时间重新计算
            cur.execute("""UPDATE drill_paper_sessions SET limit_minutes=%s
                            WHERE paper_id=%s""", (t, pid))
        conn.commit()
    finally:
        conn.close()
    return {"id": pid, "maxAttempts": n, "showAnswer": bool(show_answer),
            "timeLimitMinutes": t, "allowPause": bool(allow_pause),
            "maxResumes": mr}


def _decode_submitted_answer(raw):
    s = raw or ""
    if isinstance(s, str) and s[:1] in ("[", "{"):
        try:
            return json.loads(s)
        except Exception:
            pass
    return s


def _paper_ref_answer(dtype: str, verify_sql: str, expected_output: str,
                      answer_json: str, test_cases: str) -> dict:
    """统计页的参考答案（只在老师允许显示、且这道题交过卷时返回）。"""
    if dtype == "sql":
        return {"sql": verify_sql or ""}
    if dtype == "python":
        out = {"output": expected_output or ""}
        try:
            cases = json.loads(test_cases or "[]")
        except Exception:
            cases = []
        if cases:
            out["cases"] = [{"input": (c.get("input") or "")[:1000],
                             "expected": (c.get("expected") or "")[:2000]}
                            for c in cases[:5]]
            if not out["output"]:
                out["output"] = out["cases"][0]["expected"]
        return out
    try:
        ans = json.loads(answer_json or "{}")
    except Exception:
        ans = {}
    if dtype == "fill":
        return {"values": ans.get("values") or []}
    if dtype == "multiple":
        return {"keys": ans.get("keys") or []}
    if dtype == "boolean":
        k = str(ans.get("key") or "").upper()
        return {"key": {"T": "对（T）", "F": "错（F）"}.get(k, k)}
    return {"key": ans.get("key") or ""}


def paper_stats(account: dict, pid: int) -> dict:
    """本套试卷的作答统计：按「第 N 次交卷」展示每题得分与我的答案。"""
    p, used = _paper_cfg(account, pid)
    mine = p[1] == account["id"]
    max_attempts = int(p[5] or 0)
    show_answer = bool(p[6])
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, type, title, stem, score, judge_mode,
                                  verify_sql, expected_output, answer_json, test_cases
                             FROM drills
                            WHERE paper_id=%s AND (status=1 OR account_id=%s)
                            ORDER BY id ASC""", (pid, account["id"]))
            drows = cur.fetchall()
            cur.execute("""SELECT id, attempt_no, score, total_score, passed_n,
                                  answered_n, question_n, timed_out, started_at,
                                  limit_minutes, detail, created_at
                             FROM drill_paper_attempts
                            WHERE paper_id=%s AND account_id=%s
                            ORDER BY attempt_no ASC, id ASC""", (pid, account["id"]))
            arows = cur.fetchall()
            srows = []
            if not arows:
                cur.execute("""SELECT s.drill_id, s.passed, s.answer, s.created_at, s.ms
                                 FROM drill_submissions s
                                 JOIN drills d ON d.id = s.drill_id
                                WHERE s.account_id=%s AND d.paper_id=%s
                                ORDER BY s.id ASC""", (account["id"], pid))
                srows = cur.fetchall()
    finally:
        conn.close()

    base = {"id": int(p[0]), "title": p[2] or "", "course": p[3] or "sql",
            "mine": mine, "maxAttempts": max_attempts, "showAnswer": show_answer}

    if arows:
        attempts = []
        for a in arows:
            (aid, ano, ascore, atotal, apassed, aanswered, aqn,
             atimed_out, astarted, alimit, detail_raw, at) = a
            at = str(at)
            try:
                detail = json.loads(detail_raw or "{}")
            except Exception:
                detail = {}
            infos = {}
            for x in detail.get("questions") or []:
                try:
                    infos[int(x.get("id"))] = x
                except Exception:
                    pass
            qs = []
            for i, r in enumerate(drows, 1):
                dr_id, dtype = int(r[0]), (r[1] or "sql")
                score = int(r[4] or 0)
                info = infos.get(dr_id) or {}
                answered = bool(info.get("answered"))
                passed = bool(info.get("passed"))
                q = {
                    "no": i, "id": dr_id, "type": dtype,
                    "typeLabel": TYPE_LABEL.get(dtype, dtype),
                    "title": r[2] or "", "stem": r[3] or "", "score": score,
                    "judgeMode": r[5] or "",
                    "judgeLabel": JUDGE_LABEL.get(r[5] or "", r[5] or ""),
                    "passed": passed, "answered": answered,
                    "attempts": 1 if answered else 0,
                    "gotScore": int(info.get("score") or 0),
                    "lastAt": at if answered else "",
                    "lastAnswer": info.get("answer"),
                    "history": ([{"at": at, "passed": passed,
                                  "ms": int(info.get("ms") or 0)}] if answered else []),
                    "ref": None,
                }
                if show_answer and answered:
                    q["ref"] = _paper_ref_answer(dtype, r[6] or "", r[7] or "",
                                                 r[8] or "", r[9] or "")
                qs.append(q)
            attempts.append({
                "id": int(aid), "no": int(ano), "score": int(ascore or 0),
                "totalScore": int(atotal or 0), "passedCount": int(apassed or 0),
                "answeredCount": int(aanswered or 0),
                "questionCount": len(qs), "at": at, "questions": qs,
                "timedOut": bool(atimed_out),
                "startedAt": str(astarted) if astarted else "",
                "limitMinutes": int(alimit or 0),
                "finished": len(qs) > 0 and int(apassed or 0) >= len(qs),
            })
        latest = attempts[-1]
        out = dict(base)
        out.update({
            "attemptCount": len(attempts), "attempts": attempts,
            "currentNo": latest["no"],
            "questionCount": latest["questionCount"],
            "totalScore": latest["totalScore"], "myScore": latest["score"],
            "doneCount": latest["passedCount"], "triedCount": latest["answeredCount"],
            "finished": latest["finished"], "questions": latest["questions"],
        })
        return out

    # ---- 兼容旧数据：还没有整卷交卷记录时，按单题提交历史汇总 ----
    hist = {}
    for dr_id, passed, answer, at, ms in srows:
        hist.setdefault(int(dr_id), []).append({
            "at": str(at), "passed": bool(passed), "ms": int(ms or 0),
            "answer": _decode_submitted_answer(answer),
        })
    questions = []
    total_score = my_score = 0
    done_n = tried_n = 0
    for i, r in enumerate(drows, 1):
        dr_id, dtype = int(r[0]), (r[1] or "sql")
        score = int(r[4] or 0)
        attempts = hist.get(dr_id, [])
        passed = any(a["passed"] for a in attempts)
        last = attempts[-1] if attempts else None
        total_score += score
        if passed:
            my_score += score
            done_n += 1
        if attempts:
            tried_n += 1
        q = {
            "no": i, "id": dr_id, "type": dtype,
            "typeLabel": TYPE_LABEL.get(dtype, dtype),
            "title": r[2] or "", "stem": r[3] or "", "score": score,
            "judgeMode": r[5] or "",
            "judgeLabel": JUDGE_LABEL.get(r[5] or "", r[5] or ""),
            "passed": passed, "answered": bool(attempts),
            "attempts": len(attempts), "gotScore": score if passed else 0,
            "lastAt": last["at"] if last else "",
            "lastAnswer": last["answer"] if last else None,
            "history": [{"at": a["at"], "passed": a["passed"], "ms": a["ms"]}
                        for a in attempts[-20:]],
            "ref": None,
        }
        if show_answer and attempts:
            q["ref"] = _paper_ref_answer(dtype, r[6] or "", r[7] or "",
                                         r[8] or "", r[9] or "")
        questions.append(q)
    out = dict(base)
    out.update({
        "attemptCount": 0, "attempts": [], "currentNo": 0,
        "questionCount": len(drows), "totalScore": total_score,
        "myScore": my_score, "doneCount": done_n, "triedCount": tried_n,
        "finished": bool(questions) and done_n >= len(questions),
        "questions": questions,
    })
    return out


def paper_score(account_id: int, paper_id: int) -> dict:
    """某张试卷里「我」的得分汇总（提交后回显用）。"""
    if not paper_id:
        return {}
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT COUNT(d.id), COALESCE(SUM(d.score), 0),
                                  COALESCE(SUM(CASE WHEN s.passed = 1 THEN d.score ELSE 0 END), 0),
                                  COALESCE(SUM(CASE WHEN s.passed = 1 THEN 1 ELSE 0 END), 0)
                             FROM drills d
                             LEFT JOIN (SELECT drill_id, MAX(passed) AS passed
                                          FROM drill_submissions WHERE account_id = %s
                                         GROUP BY drill_id) s ON s.drill_id = d.id
                            WHERE d.paper_id = %s AND d.status = 1""", (account_id, paper_id))
            r = cur.fetchone()
            cur.execute("""SELECT title, max_attempts, show_answer
                             FROM drill_papers WHERE id=%s""", (paper_id,))
            t = cur.fetchone()
    finally:
        conn.close()
    return {"id": paper_id, "title": (t[0] if t else "") or "",
            "questionCount": int(r[0] or 0), "totalScore": int(r[1] or 0),
            "myScore": int(r[2] or 0), "doneCount": int(r[3] or 0),
            "maxAttempts": int(t[1] or 0) if t else 0,
            "showAnswer": bool(t[2]) if t else True}


def rename_paper(account: dict, pid: int, title: str) -> dict:
    """改试卷名（练习页卡片上的标题）。"""
    name = (title or "").strip()[:PAPER_TITLE_MAX]
    if not name:
        raise DrillError("试卷名不能为空")
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id FROM drill_papers WHERE id=%s", (pid,))
            r = cur.fetchone()
            if not r:
                raise DrillError("试卷不存在")
            if r[0] != account["id"] and account.get("role") != "admin":
                raise DrillError("只能改自己的试卷")
            cur.execute("UPDATE drill_papers SET title=%s WHERE id=%s", (name, pid))
        conn.commit()
    finally:
        conn.close()
    return {"id": pid, "title": name}


def delete_paper(account: dict, pid: int):
    """删掉整套题（连同它的题目与提交记录）。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id FROM drill_papers WHERE id=%s", (pid,))
            r = cur.fetchone()
            if not r:
                raise DrillError("试卷不存在")
            if r[0] != account["id"] and account.get("role") != "admin":
                raise DrillError("只能删除自己的试卷")
            cur.execute("SELECT id FROM drills WHERE paper_id=%s AND builtin=1", (pid,))
            if cur.fetchone():
                raise DrillError("这套题里有内置题目，不能删除")
            cur.execute("""DELETE s FROM drill_submissions s
                           JOIN drills d ON d.id = s.drill_id
                           WHERE d.paper_id = %s""", (pid,))
            cur.execute("DELETE FROM drill_paper_attempts WHERE paper_id=%s", (pid,))
            cur.execute("DELETE FROM drill_paper_sessions WHERE paper_id=%s", (pid,))
            cur.execute("DELETE FROM drills WHERE paper_id=%s", (pid,))
            cur.execute("DELETE FROM drill_papers WHERE id=%s", (pid,))
        conn.commit()
    finally:
        conn.close()


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
            pid = int(r[22] or 0)
            cfg = None
            if pid:
                cur.execute("""SELECT max_attempts, show_answer, title
                                 FROM drill_papers WHERE id=%s""", (pid,))
                cfg = cur.fetchone()
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
    if cfg:
        out["paperTitle"] = cfg[2] or ""
        out["paperMaxAttempts"] = int(cfg[0] or 0)
        out["paperShowAnswer"] = bool(cfg[1])
    else:
        out["paperTitle"] = ""
        out["paperMaxAttempts"] = 0
        out["paperShowAnswer"] = True
    if d["type"] == "python":
        # 标准输入不是答案，可以给学生看（学生才知道要喂什么数据）
        out["inputData"] = d["inputData"] or ""
        out["starterCode"] = d["starterCode"] or ""
    return out


def progress(account: dict) -> dict:
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT d.course, COUNT(*) AS total,
                                  SUM(CASE WHEN p.passed=1 THEN 1 ELSE 0 END) AS done,
                                  COALESCE(SUM(d.score), 0) AS max_score,
                                  COALESCE(SUM(CASE WHEN p.passed=1 THEN d.score ELSE 0 END), 0)
                                      AS my_score
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
    for course, total, done, max_score, my_score in rows:
        res[course] = {"total": int(total or 0), "done": int(done or 0),
                       "maxScore": int(max_score or 0), "myScore": int(my_score or 0)}
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
    try:
        score = int(p.get("score") or SCORE_DEFAULT)
    except (TypeError, ValueError):
        score = SCORE_DEFAULT
    score = max(SCORE_MIN, min(SCORE_MAX, score))
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            if did:
                cur.execute("SELECT account_id, builtin, paper_id FROM drills WHERE id=%s", (did,))
                row = cur.fetchone()
                if not row:
                    raise DrillError("题目不存在")
                if row[0] != account["id"] and account.get("role") != "admin":
                    raise DrillError("只能改自己的题目")
                if row[1]:
                    raise DrillError("内置题目不能改")
                paper_id = int(row[2] or 0)
                # 出题人填了试卷名 → 归到那张试卷；没填就沿用原来的归属
                paper_name = (p.get("paper") or "").strip()
                if paper_name:
                    paper_id = _ensure_paper(cur, account, course, paper_name)
                elif not paper_id:
                    paper_id = _ensure_paper(cur, account, course, title)
                cur.execute(f"""UPDATE drills SET course=%s, type=%s, title=%s, stem=%s,
                                       setup_sql=%s, verify_sql=%s, starter_code=%s,
                                       input_data=%s, expected_output=%s,
                                       options_json=%s, answer_json=%s, hint=%s,
                                       judge_mode=%s, test_cases=%s, paper_id=%s, score=%s
                               WHERE id=%s""",
                            (course, dr_type, title, p.get("stem") or "",
                             p.get("setupSql") or "", p.get("verifySql") or "",
                             p.get("starterCode") or "", p.get("inputData") or "",
                             p.get("expectedOutput") or "",
                             json.dumps(p.get("options") or [], ensure_ascii=False),
                             json.dumps(p.get("answer") or {}, ensure_ascii=False),
                             p.get("hint") or "", judge_mode,
                             p.get("testCases") or "", paper_id, score, did))
            else:
                cur.execute("SELECT COUNT(*) FROM drills WHERE account_id=%s", (account["id"],))
                if cur.fetchone()[0] >= DRILL_MAX:
                    raise DrillError(f"最多出 {DRILL_MAX} 道题")
                # 一道题也是一套：没指定试卷名就用题目标题当试卷名
                paper_name = (p.get("paper") or "").strip() or title
                paper_id = _ensure_paper(cur, account, course, paper_name)
                cur.execute(f"""INSERT INTO drills
                    (account_id, uploader, course, type, title, stem, setup_sql, verify_sql,
                     starter_code, input_data, expected_output, options_json, answer_json, hint,
                     judge_mode, test_cases, paper_id, score)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (account["id"], account["display"], course, dr_type, title,
                             p.get("stem") or "", p.get("setupSql") or "",
                             p.get("verifySql") or "", p.get("starterCode") or "",
                             p.get("inputData") or "", p.get("expectedOutput") or "",
                             json.dumps(p.get("options") or [], ensure_ascii=False),
                             json.dumps(p.get("answer") or {}, ensure_ascii=False),
                             p.get("hint") or "", judge_mode, p.get("testCases") or "",
                             paper_id, score))
                did = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return {"id": did, "paperId": paper_id, "score": score}


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
            cur.execute("SELECT paper_id FROM drills WHERE id=%s", (did,))
            pr = cur.fetchone()
            if pr:
                _sync_paper_status(cur, int(pr[0] or 0))
        conn.commit()
    finally:
        conn.close()
    return {"id": did, "published": bool(on)}


def delete(account: dict, did: int):
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id, builtin, paper_id FROM drills WHERE id=%s", (did,))
            row = cur.fetchone()
            if not row:
                raise DrillError("题目不存在")
            if row[0] != account["id"] and account.get("role") != "admin":
                raise DrillError("只能删除自己的题目")
            if row[1]:
                raise DrillError("内置题目不能删除")
            cur.execute("DELETE FROM drill_submissions WHERE drill_id=%s", (did,))
            cur.execute("DELETE FROM drills WHERE id=%s", (did,))
            # 一套题删空了就把这张卡片也收掉
            pid = int(row[2] or 0)
            if pid:
                cur.execute("SELECT COUNT(*) FROM drills WHERE paper_id=%s", (pid,))
                if not cur.fetchone()[0]:
                    cur.execute("DELETE FROM drill_papers WHERE id=%s", (pid,))
                else:
                    _sync_paper_status(cur, pid)
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
                               setup, owned_dbs=[tmp], batch=True, timeout=SETUP_TIMEOUT)
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

QPACK_MAX_FILES = 40
QPACK_FILE_MAX = 8 * 1024 * 1024
QPACK_ZIP_MAX = 40 * 1024 * 1024      # 上传的 zip 本体上限


def unpack_package(files: list[dict]) -> list[dict]:
    """把一个或多个上传文件展开成待解析的材料列表。

    现在前端只上传一个 .zip；这里同时兼容直接多选文件的旧方式，
    以及误把 zip 改名成别的扩展名的情况（按文件头识别 PK）。
    """
    from . import qpack

    if not files:
        raise DrillError("没有收到文件")

    out = []
    for f in files:
        name = (f.get("name") or "").strip()
        raw = f.get("data") or b""
        if len(raw) > QPACK_ZIP_MAX:
            raise DrillError(f"文件 {name} 超过 40MB")
        is_zip = raw[:2] == b"PK" or name.lower().endswith(".zip")
        if not is_zip:
            out.append({"name": name, "data": raw})
            continue
        try:
            out.extend(qpack.expand_zip(raw))
        except ValueError as e:
            raise DrillError(str(e))

    if len(out) > QPACK_MAX_FILES:
        raise DrillError(f"题目包里的文件太多（{len(out)} 个，最多 {QPACK_MAX_FILES} 个）")
    return out


def _file_question_no(name: str):
    """从文件名里取题号：1.py / 2_求平均.py / 第3题.py / q4.py 都认。"""
    base = os.path.splitext(os.path.basename(name or ""))[0]
    m = re.match(r"^\D*(\d+)", base)
    return int(m.group(1)) if m else None


def parse_package(files: list[dict]) -> dict:
    """解析上传的题目包，返回预览：试卷信息 + 每道小题（含答案、建议判分方式）。

    files: [{name, data(bytes)}] —— 可以是一个 zip，也可以直接是多个文件。
    分类规则（按扩展名 + 内容特征）：
      .sql / .myd / .txt 里含 CREATE TABLE → 数据脚本（所有小题共用）
      .txt/.md 里含「题 干」或「1、2、」编号 → 题干
      其余含 -- 1 / ---8 分隔或 SQL 关键字 → 参考答案
    """
    from . import qpack

    files = unpack_package(files)

    data_sqls = []
    stem_texts = []
    ans_texts = []
    names = []
    py_answers = {}      # 题号 -> 参考答案程序源码
    py_inputs = {}       # 题号 -> 标准输入（.in 文件）

    for f in files:
        name = (f.get("name") or "").strip()
        raw = f.get("data") or b""
        if len(raw) > QPACK_FILE_MAX:
            raise DrillError(f"文件 {name} 超过 8MB")
        names.append(name)
        low = name.lower()
        text = qpack.decode_text(raw)

        # 0) Python 参考答案程序：1.py / 2_求平均.py / 第3题.py …
        if low.endswith(".py"):
            no = _file_question_no(name)
            if no is None:
                raise DrillError(
                    f"Python 参考答案文件「{name}」看不出题号，"
                    "请改成 1.py、2_求平均.py 这种带题号的文件名")
            py_answers[no] = text
            continue
        # 0b) Python 标准输入：1.in / 2_求平均.in
        if low.endswith(".in"):
            no = _file_question_no(name)
            if no is None:
                raise DrillError(
                    f"标准输入文件「{name}」看不出题号，请改成 1.in、2_求平均.in")
            py_inputs[no] = text
            continue

        # 1) 参考答案最先判定：有 -- 1 / ---8 这类题号分隔（题干和数据脚本都不会这样写）
        if re.search(r"^\s*-{2,}\s*(?:第\s*)?\d+\s*(?:题)?\s*$", text, re.M):
            ans_texts.append(text)
            continue
        # 2) 表格数据：先转成 CREATE TABLE + INSERT，和 SQL 导出同等对待
        if low.endswith((".csv", ".xlsx")):
            try:
                conv = setup_from_file(name, raw)
                data_sqls.append(conv["sql"])
            except DrillError as e:
                raise DrillError(f"数据文件 {name} 解析失败：{e}")
            continue
        # 3) 数据脚本：扩展名 .sql/.myd，或纯建表语句
        if low.endswith((".sql", ".myd")) or (
                low.endswith(".txt") and "CREATE TABLE" in text.upper() and "题" not in text[:200]):
            data_sqls.append(text)
            continue
        # 4) 题干：含「题 干」标记，或连续编号小题且不含 SQL 语句
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
        if q["no"] in py_answers:
            # 这题是 Python 题：参考程序就是标准答案
            qtype = "python"
        else:
            qtype = qpack.guess_type(q["text"], ans)
        # 建对象/改数据题一律用「整库状态」判分：学生答案和参考答案各在一个干净库里
        # 执行，再比较最终数据库状态（不会重复执行同一句 SQL 导致“已存在”）
        if qtype in ("sql_dml", "sql_ddl"):
            mode = "dbstate"
        else:
            mode = "result"
        item = {
            "no": q["no"],
            "text": q["text"],
            "note": q.get("note", ""),
            "answer": qpack.clean_answer(ans),
            "kind": qtype,
            "judgeMode": mode,
            "hasAnswer": bool(ans.strip()),
        }
        if q["no"] in py_answers:
            item["answer"] = py_answers[q["no"]]
            item["pyCode"] = py_answers[q["no"]]
            item["pyInput"] = py_inputs.get(q["no"], "")
            item["hasAnswer"] = True
            item["judgeMode"] = "output"
        items.append(item)

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
            "python": sum(1 for x in items if x["kind"] == "python"),
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
    warnings = []
    # 有些卷子是连续实验：后面的题依赖前面题改动过的表结构/数据。
    # 逐题验证参考答案，前面的答案会累加到 cum_sql，供后面的题当初始数据。
    cum_sql = data_sql
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            paper_title = (pkg.get("title") or "未命名试卷")[:PAPER_TITLE_MAX]
            # 这套题是 SQL 题还是 Python 题：看有没有 Python 参考答案程序
            is_py_paper = any(x.get("kind") == "python" for x in questions)
            course = "python" if is_py_paper else "sql"
            # 先建一张试卷卡片，再往里放题；重复导入落到同一张卡片
            paper_id = _ensure_paper(cur, account, course, paper_title,
                                     pkg.get("description") or "", publish)
            # 只跟「同一张试卷」里的题比：不同试卷可以有同名小题，重复导入才跳过
            cur.execute("SELECT title FROM drills WHERE paper_id=%s", (paper_id,))
            existing = {r[0] for r in cur.fetchall()}
            for q in questions:
                if not (q.get("answer") or "").strip():
                    continue      # 没有参考答案的题跳过（无法判分）
                mode = judge_override.get(str(q["no"])) or q.get("judgeMode") or "result"
                title = f"{q['no']}. " + " ".join((q.get("text") or "").split())[:60]
                if title in existing:
                    duplicates.append({"no": q["no"], "title": title})
                    # 重复导入时，这套卷子里已有的题也可能被后面的新题依赖
                    if q.get("kind") in ("sql_dml", "sql_ddl"):
                        add = f"\n\n-- 第 {q['no']} 题参考答案\n" + q["answer"] + "\n"
                        if len(cum_sql) + len(add) <= SETUP_TEXT_MAX:
                            cum_sql += add
                    continue
                score = int(q.get("score") or SCORE_DEFAULT)
                score = max(SCORE_MIN, min(SCORE_MAX, score))
                stem_text = (q.get("text") or "") + (("\n\n" + q["note"]) if q.get("note") else "")
                if q.get("kind") == "python":
                    # Python 题：参考程序就是标准答案，跑一遍拿到期望输出
                    expected, py_err, py_why = "", "", ""
                    py_input = q.get("pyInput") or ""
                    try:
                        r = _run_py_once(account, q.get("pyCode") or "", py_input)
                        expected = r.get("out") or ""
                        py_err = (r.get("err") or "").strip()
                        py_why = r.get("why") or ""
                    except Exception as e:   # 沙箱不可用也不该让整批导入失败
                        py_err = str(e)
                    # 期望输出是空的题没法判分：建成草稿（学生看不到），并提醒老师
                    ready = bool(expected.strip()) and not py_err
                    if py_err:
                        warnings.append(
                            f"第 {q['no']} 题的参考程序运行出错，已存为草稿，"
                            f"请修好答案或手工填写期望输出：{py_err.splitlines()[-1][:120]}")
                    elif not ready:
                        tip = ("等待输入超时，可能缺少对应的标准输入文件"
                               if py_why in ("idle", "timeout") else "参考程序没有输出")
                        warnings.append(
                            f"第 {q['no']} 题{tip}（放一个 {q['no']}.in 或手工填写期望输出），"
                            f"已存为草稿")
                    cur.execute(f"""INSERT INTO drills
                        (account_id, uploader, course, type, title, stem, setup_sql, verify_sql,
                         starter_code, input_data, expected_output, options_json, answer_json, hint,
                         judge_mode, test_cases, status, published_at, paper_id, score)
                        VALUES (%s,%s,'python','python',%s,%s,'','','',%s,%s,'[]','{{}}',%s,'output','',
                                %s, CASE WHEN %s=1 THEN NOW() ELSE NULL END,%s,%s)""",
                        (account["id"], account["display"], title, stem_text,
                         py_input, expected, q.get("note", ""),
                         1 if (publish and ready) else 0,
                         1 if (publish and ready) else 0, paper_id, score))
                else:
                    # SQL 题：先在临时库里把参考答案跑一遍，答案本身报错就存草稿并提醒。
                    # 先在本题自己的初始数据上跑；失败且前面题改过数据时，再试一次
                    # 「原始数据 + 前面题的答案」，这样连续实验卷也能自动接上。
                    ref = q["answer"]

                    def _ref_err(setup):
                        try:
                            tr = try_sql(account, setup, ref)
                            return (tr.get("error") or "").strip()
                        except Exception as e:
                            return str(e)[:200]

                    ref_error = _ref_err(data_sql)
                    setup_sql = data_sql
                    used_prior = False
                    if ref_error and cum_sql.strip() and cum_sql != data_sql:
                        cum_err = _ref_err(cum_sql)
                        if not cum_err:
                            setup_sql = cum_sql
                            ref_error = ""
                            used_prior = True
                        else:
                            ref_error = cum_err or ref_error
                    publish_one = publish
                    if ref_error:
                        publish_one = False
                        warnings.append(
                            f"第 {q['no']} 题的参考答案在题目数据上执行失败，已存为草稿："
                            f"{ref_error[:180]}")
                    elif used_prior:
                        warnings.append(
                            f"第 {q['no']} 题依赖前面题目的结果，已自动把前面题的答案"
                            f"并入本题初始数据")
                    # 把本题的改表/改数据答案累加给后面的题
                    if not ref_error and q.get("kind") in ("sql_dml", "sql_ddl"):
                        add = f"\n\n-- 第 {q['no']} 题参考答案\n" + ref + "\n"
                        if len(cum_sql) + len(add) <= SETUP_TEXT_MAX:
                            cum_sql += add
                    # SQL 题：整库状态判分，答案作为「校验语句」不合适时改用查询校验
                    verify = q["answer"]
                    cur.execute(f"""INSERT INTO drills
                        (account_id, uploader, course, type, title, stem, setup_sql, verify_sql,
                         starter_code, input_data, expected_output, options_json, answer_json, hint,
                         judge_mode, test_cases, status, published_at, paper_id, score)
                        VALUES (%s,%s,'sql','sql',%s,%s,%s,%s,'','','','[]','{{}}',%s,%s,'',
                                %s, CASE WHEN %s=1 THEN NOW() ELSE NULL END,%s,%s)""",
                        (account["id"], account["display"], title, stem_text,
                         setup_sql, verify, q.get("note", ""), mode,
                         1 if publish_one else 0, 1 if publish_one else 0, paper_id, score))
                created.append({"id": cur.lastrowid, "no": q["no"], "title": title,
                                "score": score, "kind": q.get("kind") or "sql"})
                existing.add(title)
            _sync_paper_status(cur, paper_id)
        conn.commit()
    finally:
        conn.close()
    return {"created": created, "duplicates": duplicates, "paperId": paper_id,
            "paperTitle": paper_title, "course": course, "warnings": warnings,
            "skipped": len(questions) - len(created) - len(duplicates)}


# ---------------- SQL 题沙箱库 ----------------
# 每个（学生, 题目）一个独立的真实数据库，初始化 SQL 跑在里面。
# 学生可以像主页一样自由查询、点表预览，交卷时再用另一个临时库判分（不影响沙箱）。

# 同一套试卷的题共用一个沙箱库（第一题的改动第二题能看到，来回切换不丢）；
# 单题（不属于任何试卷）仍一题一库。共享库内每题的初始化 SQL 用 meta.drill_setup_done 记账，
# 保证只跑一次；老师改了卷内任何一题的数据（setup 变了），整卷沙箱作废重建。
_LEDGER_TABLE = "drill_setup_done"
_IGNORE_ERRNOS = {1050, 1061, 1062}   # 表/索引已存在、主键冲突：共享库里跑别的题的 setup 可忽略


def _sandbox_name(account_id: int, drill_id: int, paper_id: int = 0) -> str:
    if paper_id:
        return f"x_{account_id}_p{paper_id}"
    return f"x_{account_id}_{drill_id}"


def _paper_setup_sig(paper_id: int) -> str:
    """整卷所有 SQL 题初始化数据的聚合指纹——任何一题改了数据，整卷沙箱重建。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT id, setup_sql FROM {q_ident(C.COMMUNITY_DB)}.drills
                            WHERE paper_id=%s AND type='sql' ORDER BY id""", (paper_id,))
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return ""
    h = hashlib.sha1()
    for did, setup in rows:
        h.update(f"{did}:".encode())
        h.update((setup or "").encode("utf-8"))
    return h.hexdigest()


def _ledger_ensure(conn, db_name: str):
    cur = conn.cursor()
    cur.execute(f"""CREATE TABLE IF NOT EXISTS {q_ident(C.META_DB)}.{_LEDGER_TABLE} (
        db_name VARCHAR(64) NOT NULL,
        drill_id BIGINT NOT NULL,
        sig CHAR(40) NOT NULL DEFAULT '',
        done_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (db_name, drill_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


def _ledger_get(conn, db_name: str, drill_id: int) -> str:
    cur = conn.cursor()
    cur.execute(f"SELECT sig FROM {q_ident(C.META_DB)}.{_LEDGER_TABLE} "
                f"WHERE db_name=%s AND drill_id=%s", (db_name, drill_id))
    r = cur.fetchone()
    return (r[0] or "") if r else ""


def _ledger_put(conn, db_name: str, drill_id: int, sig: str):
    cur = conn.cursor()
    cur.execute(f"""INSERT INTO {q_ident(C.META_DB)}.{_LEDGER_TABLE} (db_name, drill_id, sig)
                    VALUES (%s,%s,%s)
                    ON DUPLICATE KEY UPDATE sig=VALUES(sig), done_at=CURRENT_TIMESTAMP""",
                (db_name, drill_id, sig))


def _ledger_drop_db(conn, db_name: str):
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {q_ident(C.META_DB)}.{_LEDGER_TABLE} WHERE db_name=%s", (db_name,))


def _run_setup_tolerant(account: dict, db: str, setup: str):
    """在共享沙箱里补跑某题的初始化 SQL：忽略「已存在/主键冲突」类错误
    （别的题可能已经建过同名表/插过同主键的行），真错误照常抛出。"""
    from . import sqlrun
    stmts = sqlrun.prepare_statements(setup)
    for stmt in stmts:
        try:
            r = sqlrun.run_sql(db, account["mysql_user"], account["mysql_pass"], stmt,
                               owned_dbs=[db], batch=False,
                               timeout=SETUP_TIMEOUT, max_statements=100000)
        except Exception as e:
            raise DrillError("题目的初始化 SQL 执行失败：" + str(e)[:300])
        err = _first_error(r.get("results"))
        if err and err.get("errno") not in _IGNORE_ERRNOS:
            raise DrillError("题目的初始化 SQL 有问题，请联系出题老师：" + (err.get("msg") or ""))


def ensure_sandbox(account: dict, drill_id: int, reset: bool = False) -> dict:
    """确保本题的沙箱库存在并已执行初始化 SQL，返回 {db, tables}。

    同一套试卷的题共用一个沙箱库（题间数据互通）；单题一题一库。
    共享库内每题的初始化 SQL 只跑一次（meta.drill_setup_done 记账）；
    老师改了卷内任何一题的数据，整卷沙箱作废重建（回到干净初始状态）。
    """
    from . import sessions, sqlrun

    full = get_full(drill_id)
    if full["type"] != "sql":
        raise DrillError("只有 SQL 题需要沙箱库")
    mine = full["account_id"] == account["id"]
    if not full["status"] and not (mine or account.get("role") == "admin"):
        raise DrillError("这题还没发布")

    paper_id = int(full.get("paperId") or 0)
    db = _sandbox_name(account["id"], drill_id, paper_id)
    setup = (full.get("setupSql") or "").strip()
    setup_sig = hashlib.sha1(setup.encode("utf-8")).hexdigest() if setup else ""
    # 共享库看整卷聚合指纹；单题看本题指纹
    check_sig = _paper_setup_sig(paper_id) if paper_id else setup_sig

    owner = False
    old_sig = ""
    conn = root_conn(C.META_DB)
    try:
        _ledger_ensure(conn, db)
        with conn.cursor() as cur:
            cur.execute("SELECT account_id, setup_sig FROM dbs WHERE db_name=%s", (db,))
            row = cur.fetchone()
            owner = bool(row) and row[0] == account["id"]
            old_sig = (row[1] or "") if row else ""
    finally:
        conn.close()

    def _drop():
        try:
            sessions.drop_user_db(account, db)
        except Exception:
            pass
        c2 = root_conn(C.META_DB)
        try:
            _ledger_drop_db(c2, db)
        finally:
            c2.close()
        nonlocal owner
        owner = False

    # 老师改过数据（本题或卷内任何一题）：旧沙箱自动作废重建
    if owner and check_sig and old_sig != check_sig:
        _drop()
    if reset and owner:
        _drop()
    # 上一次初始化失败会留下一个空沙箱；发现有库没表时自动重建
    if owner and setup:
        try:
            existing = sqlrun.list_tables(db, account["mysql_user"], account["mysql_pass"])
        except Exception:
            existing = []
        if not existing:
            _drop()

    if not owner:
        try:
            sessions.create_user_db(account, db, origin="drill")
        except Exception:
            # 并发/残留：已存在同名库时直接复用
            pass
        if setup:
            try:
                r = sqlrun.run_sql(db, account["mysql_user"], account["mysql_pass"],
                                   setup, owned_dbs=[db], batch=True,
                                   timeout=SETUP_TIMEOUT, max_statements=100000)
                err = _first_error(r.get("results"))
                if err:
                    raise DrillError("题目的初始化 SQL 有问题，请联系出题老师：" + err)
                conn = root_conn(C.META_DB)
                try:
                    with conn.cursor() as cur:
                        cur.execute("""UPDATE dbs SET setup_sig=%s
                                        WHERE db_name=%s AND account_id=%s""",
                                    (check_sig, db, account["id"]))
                        _ledger_put(conn, db, drill_id, setup_sig)
                finally:
                    conn.close()
            except DrillError:
                _drop()
                raise
            except Exception as e:
                _drop()
                raise DrillError("题目的初始化 SQL 执行失败：" + str(e)[:300])
    elif paper_id and setup:
        # 共享库已存在：本题的初始化 SQL 可能还没跑过（从第一题切过来）
        conn = root_conn(C.META_DB)
        try:
            done_sig = _ledger_get(conn, db, drill_id)
        finally:
            conn.close()
        if done_sig != setup_sig:
            _run_setup_tolerant(account, db, setup)
            conn = root_conn(C.META_DB)
            try:
                _ledger_put(conn, db, drill_id, setup_sig)
            finally:
                conn.close()

    tables = sqlrun.list_tables(db, account["mysql_user"], account["mysql_pass"])
    return {"db": db, "tables": tables}


def navicat_schema(account: dict, drill_id: int) -> dict:
    """Navicat 模拟界面用的完整库结构：表、列、索引、视图、函数、触发器。"""
    from .db import q_ident, user_conn

    sb = ensure_sandbox(account, drill_id)
    db = sb["db"]
    out = {"db": db, "charset": "", "collation": "", "tables": [], "views": [],
           "routines": [], "triggers": []}
    conn = user_conn(db, account["mysql_user"], account["mysql_pass"])
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("""SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
                               FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s""", (db,))
                r = cur.fetchone()
                if r:
                    out["charset"] = r[0] or ""
                    out["collation"] = r[1] or ""
            except Exception:
                pass

            cur.execute("""SELECT TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_ROWS,
                                  DATA_LENGTH, UPDATE_TIME, TABLE_COMMENT
                           FROM information_schema.TABLES
                           WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME""", (db,))
            tabs = cur.fetchall()

            cur.execute("""SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
                                  COLUMN_KEY, COLUMN_DEFAULT, EXTRA, COLUMN_COMMENT,
                                  ORDINAL_POSITION, CHARACTER_MAXIMUM_LENGTH,
                                  NUMERIC_PRECISION, NUMERIC_SCALE,
                                  GENERATION_EXPRESSION
                           FROM information_schema.COLUMNS
                           WHERE TABLE_SCHEMA=%s
                           ORDER BY TABLE_NAME, ORDINAL_POSITION""", (db,))
            cols = {}
            for c in cur.fetchall():
                cols.setdefault(str(c[0]).lower(), []).append({
                    "name": c[1], "type": c[2] or "", "nullable": c[3] == "YES",
                    "key": c[4] or "", "default": "" if c[5] is None else str(c[5]),
                    "extra": c[6] or "", "comment": c[7] or "",
                    "position": int(c[8] or 0), "genExpr": c[12] or "",
                })

            cur.execute("""SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX,
                                  COLUMN_NAME, INDEX_TYPE
                           FROM information_schema.STATISTICS
                           WHERE TABLE_SCHEMA=%s
                           ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX""", (db,))
            idx = {}
            for x in cur.fetchall():
                by_table = idx.setdefault(str(x[0]).lower(), {})
                item = by_table.setdefault(x[1], {
                    "name": x[1], "unique": int(x[2]) == 0,
                    "type": x[5] or "", "columns": []})
                item["columns"].append(x[4])

            # 外键关系（查询创建工具自动连线 + 设计表「外键」标签页用）
            fks = {}
            try:
                cur.execute("""SELECT k.TABLE_NAME, k.COLUMN_NAME,
                                      k.REFERENCED_TABLE_NAME, k.REFERENCED_COLUMN_NAME,
                                      k.CONSTRAINT_NAME, r.DELETE_RULE, r.UPDATE_RULE
                               FROM information_schema.KEY_COLUMN_USAGE k
                               LEFT JOIN information_schema.REFERENTIAL_CONSTRAINTS r
                                 ON r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
                                AND r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
                               WHERE k.TABLE_SCHEMA=%s AND k.REFERENCED_TABLE_NAME IS NOT NULL
                               ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION""",
                            (db,))
                for x in cur.fetchall():
                    fks.setdefault(str(x[0]).lower(), []).append({
                        "col": x[1], "refTable": x[2], "refCol": x[3],
                        "name": x[4] or "", "onDelete": x[5] or "RESTRICT",
                        "onUpdate": x[6] or "RESTRICT"})
            except Exception:
                pass

            cur.execute("""SELECT TABLE_NAME, VIEW_DEFINITION FROM information_schema.VIEWS
                           WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME""", (db,))
            view_defs = {str(r[0]).lower(): r[1] or "" for r in cur.fetchall()}

            for t in tabs:
                name = t[0]
                key = str(name).lower()
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {q_ident(name)}")
                    row_count = int(cur.fetchone()[0])
                except Exception:
                    row_count = 0
                item = {
                    "name": name, "rows": row_count,
                    "dataLength": int(t[4] or 0), "engine": t[2] or "",
                    "updated": str(t[5]) if t[5] else "",
                    "comment": t[6] or "",
                    "columns": cols.get(key, []),
                    "indexes": list(idx.get(key, {}).values()),
                    "fks": fks.get(key, []),
                }
                if str(t[1]).upper() == "VIEW":
                    item["definition"] = view_defs.get(key, "")
                    out["views"].append(item)
                else:
                    item["primaryKey"] = [c["name"] for c in item["columns"]
                                          if c["key"] == "PRI"]
                    out["tables"].append(item)

            # 函数 / 存储过程
            cur.execute("""SELECT ROUTINE_NAME, ROUTINE_TYPE, DTD_IDENTIFIER,
                                  ROUTINE_DEFINITION, ROUTINE_COMMENT
                           FROM information_schema.ROUTINES
                           WHERE ROUTINE_SCHEMA=%s
                           ORDER BY ROUTINE_TYPE, ROUTINE_NAME""", (db,))
            routines = cur.fetchall()
            params = {}
            try:
                cur.execute("""SELECT SPECIFIC_NAME, PARAMETER_MODE, PARAMETER_NAME,
                                      DTD_IDENTIFIER, ORDINAL_POSITION
                               FROM information_schema.PARAMETERS
                               WHERE SPECIFIC_SCHEMA=%s
                               ORDER BY SPECIFIC_NAME, ORDINAL_POSITION""", (db,))
                for p in cur.fetchall():
                    if p[2] is None:      # 函数返回值那一行
                        continue
                    params.setdefault(str(p[0]).lower(), []).append({
                        "mode": p[1] or "IN", "name": p[2], "type": p[3] or "",
                        "position": int(p[4] or 0)})
            except Exception:
                pass
            for r in routines:
                out["routines"].append({
                    "name": r[0], "type": r[1], "returns": r[2] or "",
                    "definition": r[3] or "", "comment": r[4] or "",
                    "params": params.get(str(r[0]).lower(), []),
                })

            # 触发器
            try:
                cur.execute("""SELECT TRIGGER_NAME, ACTION_TIMING, EVENT_MANIPULATION,
                                      EVENT_OBJECT_TABLE, ACTION_STATEMENT
                               FROM information_schema.TRIGGERS
                               WHERE TRIGGER_SCHEMA=%s ORDER BY TRIGGER_NAME""", (db,))
                for t in cur.fetchall():
                    out["triggers"].append({
                        "name": t[0], "timing": t[1], "event": t[2],
                        "table": t[3], "statement": t[4] or "",
                    })
            except Exception:
                pass
    finally:
        conn.close()
    return out


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


def _norm_def(sql: str, db: str = "") -> str:
    """对象定义归一化：去空白差异、DEFINER 和库名前缀，避免同义写法被误判。

    MySQL 存视图定义时会把表名补成 `库名`.`表名`；学生库和标准答案库的库名
    不同，必须先把库名去掉再比。
    """
    t = re.sub(r"\s+", " ", str(sql or "")).strip().lower()
    t = re.sub(r"\bdefiner\s*=\s*`[^`]*`@`[^`]*`\s*", "", t)
    if db:
        for name in {db.lower(), db}:
            t = t.replace("`" + name + "`.", "").replace(name + ".", "")
    return t.rstrip("; ").strip()


def _norm_col_type(t: str) -> str:
    """字段类型归一化：整数显示宽度（int(8) / int(11)）不算差异，其余保留。"""
    s = re.sub(r"\s+", " ", str(t or "").lower().strip())
    s = re.sub(r"^(tinyint|smallint|mediumint|int|bigint)\(\d+\)", r"\1", s)
    return s


def snapshot_db(db: str, user: str, password: str, max_rows: int = 500) -> dict:
    """整库快照：表/视图的数据 + 表结构 + 视图/函数/存储过程/触发器的定义。

    用于 dbstate 判分 —— Navicat 式的“建表、设计表、建视图、建函数、建触发器”
    都能真正比对，而不是只看有没有留下表。
    """
    from .db import q_ident, user_conn

    out = {}
    conn = user_conn(db, user, password)
    try:
        with conn.cursor() as cur:
            # 表结构（字段名/类型/可空/主键），用于「设计表」类题目的判分
            meta = {}
            try:
                cur.execute("""SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
                                      COLUMN_KEY, ORDINAL_POSITION
                               FROM information_schema.COLUMNS
                               WHERE TABLE_SCHEMA=%s
                               ORDER BY TABLE_NAME, ORDINAL_POSITION""", (db,))
                for c in cur.fetchall():
                    meta.setdefault(str(c[0]).lower(), []).append(
                        [str(c[1]), _norm_col_type(c[2]), c[3] == "YES", c[4] == "PRI"])
            except Exception:
                pass

            cur.execute("SHOW FULL TABLES")
            objs = [(r[0], r[1]) for r in cur.fetchall() if not str(r[0]).startswith("__")]
            for name, kind in sorted(objs):
                key = str(name).lower()
                try:
                    cur.execute(f"SELECT * FROM {q_ident(name)} LIMIT %s", (max_rows,))
                    cols = [d[0] for d in cur.description]
                    rows = [[conv_value(v) for v in r] for r in cur.fetchall()]
                except Exception:
                    cols, rows = [], []
                item = {"cols": cols, "rows": rows}
                if str(kind).upper() == "VIEW":
                    try:
                        cur.execute("""SELECT VIEW_DEFINITION FROM information_schema.VIEWS
                                       WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s""", (db, name))
                        v = cur.fetchone()
                        item["def"] = _norm_def(v[0], db) if v else ""
                    except Exception:
                        item["def"] = ""
                elif key in meta:
                    item["schema"] = meta[key]
                out[key] = item

            # 函数 / 存储过程：签名 + 函数体
            routines = []
            try:
                cur.execute("""SELECT ROUTINE_NAME, ROUTINE_TYPE, DTD_IDENTIFIER,
                                      ROUTINE_DEFINITION
                               FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s""", (db,))
                routines = cur.fetchall()
            except Exception:
                pass
            for rname, rtype, returns, body in routines:
                sig = ""
                try:
                    cur.execute("""SELECT PARAMETER_MODE, PARAMETER_NAME, DTD_IDENTIFIER
                                   FROM information_schema.PARAMETERS
                                   WHERE SPECIFIC_SCHEMA=%s AND SPECIFIC_NAME=%s
                                   ORDER BY ORDINAL_POSITION""", (db, rname))
                    parts = []
                    for mode, pname, ptype in cur.fetchall():
                        if pname is None:
                            continue
                        parts.append(f"{str(mode or 'IN').lower()} {str(pname).lower()} "
                                     f"{str(ptype or '').lower()}")
                    sig = "(" + ",".join(parts) + ")"
                except Exception:
                    pass
                ret = (" returns " + str(returns).lower())                     if str(rtype).upper() == "FUNCTION" and returns else ""
                key = f"{str(rtype).lower()}:{str(rname).lower()}"
                out[key] = {"cols": [], "rows": [],
                            "def": _norm_def(f"{rtype} {rname}{sig}{ret} {body or ''}", db)}

            # 触发器：时机 + 事件 + 表 + 语句
            triggers = []
            try:
                cur.execute("""SELECT TRIGGER_NAME, ACTION_TIMING, EVENT_MANIPULATION,
                                      EVENT_OBJECT_TABLE, ACTION_STATEMENT
                               FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s""", (db,))
                triggers = cur.fetchall()
            except Exception:
                pass
            for tname, timing, event, table, body in triggers:
                key = "trigger:" + str(tname).lower()
                out[key] = {"cols": [], "rows": [],
                            "def": _norm_def(f"{timing} {event} on {table} {body or ''}", db)}
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
        # 视图 / 函数 / 存储过程 / 触发器：先比定义
        s_def = student[t].get("def", "")
        e_def = expected[t].get("def", "")
        if s_def or e_def:
            if s_def != e_def:
                return False, f"{t} 的定义与标准答案不一致"
            continue
        s_cols = [str(c) for c in student[t]["cols"]]
        e_cols = [str(c) for c in expected[t]["cols"]]
        if s_cols != e_cols:
            return False, f"表 {t} 的字段不一致（期望 {', '.join(e_cols[:6])}）"
        # 字段定义（类型/可空/主键）：设计表类题目要看这个
        if "schema" in expected[t] and "schema" in student[t]:
            if student[t]["schema"] != expected[t]["schema"]:
                want = "，".join(
                    f"{c[0]} {c[1]}{'' if c[2] else ' NOT NULL'}{' PK' if c[3] else ''}"
                    for c in expected[t]["schema"][:6])
                return False, f"表 {t} 的字段定义不一致（期望 {want}）"
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

    def run(db, sql, cap=None):
        # 判分脚本（初始化 + 标准答案 + 学生答案）整批提交，慢盘上也不会一条一条 fsync
        # 初始化/标准答案可以很多条；学生答案仍限制 200 条，防止提交巨型脚本
        out = sqlrun.run_sql(db, account["mysql_user"], account["mysql_pass"],
                             sql, owned_dbs=[db], batch=True, timeout=SETUP_TIMEOUT,
                             max_statements=(cap or 100000))
        results = out.get("results") or []
        return results, _first_error(results), _last_rows(results)

    db = None
    try:
        db = new_db("exam")
        if setup.strip():
            _, e, _ = run(db, setup)
            if e:
                raise DrillError("题目的初始化 SQL 有问题，请联系出题老师：" + e)

        st_results, st_err, student = run(db, answer, 200)
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


def _judge_one(account: dict, full: dict, answer, show_answer: bool) -> dict:
    """判一道题并按老师设置裁剪答案，返回带分值的判分结果。"""
    t0 = time.monotonic()
    if full["type"] == "sql":
        res = judge_sql(account, full, str(answer or ""))
    elif full["type"] == "python":
        res = judge_python(account, full, str(answer or ""))
    else:
        res = judge_objective(full, answer)
    res["ms"] = int((time.monotonic() - t0) * 1000)
    # 老师设置交卷后不显示答案：把参考答案和逐组期望值去掉，
    # 也不再用“期望是 X”这类提示把答案带出来
    if not show_answer:
        res.pop("expected", None)
        for c in res.get("cases") or []:
            if isinstance(c, dict):
                c.pop("expected", None)
        if not res.get("passed") and _mode(full) in ("cell", "contains", "state", "dbstate"):
            res["reason"] = "未通过，请再检查一下作答。"
    max_score = int(full.get("score") or SCORE_DEFAULT)
    res["maxScore"] = max_score
    res["score"] = max_score if res["passed"] else 0
    res["passed"] = bool(res["passed"])
    return res


def _store_submission(account: dict, did: int, answer, res: dict, attempt_id: int = 0):
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO drill_submissions
                           (account_id, drill_id, attempt_id, passed, answer, detail, ms)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (account["id"], did, int(attempt_id or 0),
                         1 if res["passed"] else 0,
                         json.dumps(answer, ensure_ascii=False) if not isinstance(answer, str)
                         else answer[:60000],
                         json.dumps(res, ensure_ascii=False, default=str)[:20000],
                         int(res.get("ms") or 0)))
        conn.commit()
    finally:
        conn.close()


def _answer_is_empty(a) -> bool:
    if a is None:
        return True
    if isinstance(a, str):
        return not a.strip()
    if isinstance(a, (list, tuple, dict)):
        return not a
    return False


def _paper_cfg(account: dict, pid: int):
    """读试卷设置与「我」已交卷次数，顺便做可见性校验。返回 (paper_row, used)。"""
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, account_id, title, course, status,
                                  max_attempts, show_answer, time_limit_minutes,
                                  allow_pause, max_resumes
                             FROM drill_papers WHERE id=%s""", (pid,))
            p = cur.fetchone()
            if not p:
                raise DrillError("试卷不存在")
            mine = p[1] == account["id"]
            if not p[4] and not (mine or account.get("role") == "admin"):
                raise DrillError("这是别人的草稿，不能查看")
            cur.execute("""SELECT COUNT(*) FROM drill_paper_attempts
                            WHERE paper_id=%s AND account_id=%s""", (pid, account["id"]))
            used = int(cur.fetchone()[0] or 0)
    finally:
        conn.close()
    return p, used


def submit(account: dict, did: int, answer) -> dict:
    """单题交卷（兼容旧入口）；整卷做题请用 submit_paper。"""
    full = get_full(did)
    mine = full["account_id"] == account["id"]
    if not full["status"] and not (mine or account.get("role") == "admin"):
        raise DrillError("这题还没发布")
    if full["type"] in ("sql", "python") and isinstance(answer, str)             and len(answer.encode("utf-8")) > C.CODE_MAX:
        raise DrillError("作答内容超过 256KB 上限")
    pid = int(full.get("paperId") or 0)
    show_answer = True
    if pid:
        # 单题入口只用于错题本重做，不消耗整卷交卷次数
        p, _used = _paper_cfg(account, pid)
        show_answer = bool(p[6])
    res = _judge_one(account, full, answer, show_answer)
    _store_submission(account, did, answer, res)
    paper = paper_score(account["id"], pid)
    if paper:
        res["paper"] = paper
    return res


def start_paper(account: dict, pid: int, visit_id: str = "") -> dict:
    """开始 / 继续一次整卷作答：返回已用时、限时与续做信息。

    允许中途退出的卷子：退出时暂停计时，回来继续累计；
    不允许中途退出的卷子：正常退出由前端直接交卷，异常退出（刷新/关闭）按 visit_id 计一次续做。
    """
    p, used = _paper_cfg(account, pid)
    mine = p[1] == account["id"]
    is_admin = account.get("role") == "admin"
    limit = int(p[7] or 0)
    allow_pause = bool(p[8]) if p[8] is not None else True
    max_resumes = int(p[9] or 3)
    max_attempts = int(p[5] or 0)
    if mine or is_admin:
        limit = 0
        allow_pause = True        # 出卷人 / 管理员试做：可以随时离开，不强制交卷
    out = {"limitMinutes": 0, "secondsLeft": 0, "elapsedSeconds": 0,
           "startedAt": "", "attemptsUsed": used, "maxAttempts": max_attempts,
           "expired": False, "allowPause": allow_pause,
           "maxResumes": max_resumes, "resumeCount": 0, "resumeBlocked": False}
    if max_attempts > 0 and used >= max_attempts:
        return out
    visit_id = (visit_id or "")[:48]
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT started_at, limit_minutes, elapsed_seconds,
                                  active_since, last_seen, resume_count, visit_id
                             FROM drill_paper_sessions
                            WHERE account_id=%s AND paper_id=%s""",
                        (account["id"], pid))
            row = cur.fetchone()
            if not row:
                cur.execute("""INSERT INTO drill_paper_sessions
                               (paper_id, account_id, limit_minutes, elapsed_seconds,
                                active_since, last_seen, resume_count, visit_id)
                               VALUES (%s,%s,%s,0,NOW(),NOW(),0,%s)""",
                            (pid, account["id"], limit, visit_id))
                conn.commit()
                cur.execute("""SELECT started_at, limit_minutes, elapsed_seconds,
                                      active_since, last_seen, resume_count, visit_id
                                 FROM drill_paper_sessions
                                WHERE account_id=%s AND paper_id=%s""",
                            (account["id"], pid))
                row = cur.fetchone()
            started, sess_limit, elapsed0, active_since, last_seen, resume_count, old_visit = row
            sess_limit = int(sess_limit or 0)
            elapsed0 = int(elapsed0 or 0)
            resume_count = int(resume_count or 0)
            same_visit = bool(visit_id) and (visit_id == (old_visit or ""))
            if allow_pause:
                if active_since is None:
                    # 上次是正常暂停，恢复计时
                    cur.execute("""UPDATE drill_paper_sessions
                                      SET active_since=NOW(), last_seen=NOW(), visit_id=%s
                                    WHERE account_id=%s AND paper_id=%s""",
                                (visit_id, account["id"], pid))
                elif not same_visit:
                    # 刷新 / 关闭页面等异常离开：只累计到最后心跳，空白时间不算
                    cur.execute("""UPDATE drill_paper_sessions
                                      SET elapsed_seconds=elapsed_seconds +
                                            GREATEST(0, TIMESTAMPDIFF(SECOND, active_since,
                                                                      COALESCE(last_seen, active_since))),
                                          active_since=NOW(), last_seen=NOW(), visit_id=%s
                                    WHERE account_id=%s AND paper_id=%s""",
                                (visit_id, account["id"], pid))
                else:
                    cur.execute("""UPDATE drill_paper_sessions SET last_seen=NOW()
                                    WHERE account_id=%s AND paper_id=%s""",
                                (account["id"], pid))
            else:
                if visit_id and old_visit and not same_visit:
                    resume_count += 1
                cur.execute("""UPDATE drill_paper_sessions
                                  SET resume_count=%s, last_seen=NOW(), visit_id=%s
                                WHERE account_id=%s AND paper_id=%s""",
                            (resume_count, visit_id, account["id"], pid))
            conn.commit()
            cur.execute("""SELECT started_at, limit_minutes, elapsed_seconds,
                                  active_since, resume_count,
                                  TIMESTAMPDIFF(SECOND, started_at, NOW())
                             FROM drill_paper_sessions
                            WHERE account_id=%s AND paper_id=%s""",
                        (account["id"], pid))
            started, sess_limit, elapsed0, active_since, resume_count, wall = cur.fetchone()
    finally:
        conn.close()
    # 用数据库的 NOW() 重新计算已用时，避免应用和 DB 的时钟/时区差
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT elapsed_seconds +
                                  IF(active_since IS NULL, 0,
                                     GREATEST(0, TIMESTAMPDIFF(SECOND, active_since, NOW()))),
                                  started_at, limit_minutes, resume_count
                             FROM drill_paper_sessions
                            WHERE account_id=%s AND paper_id=%s""",
                        (account["id"], pid))
            elapsed, started, sess_limit, resume_count = cur.fetchone()
    finally:
        conn.close()
    elapsed = int(elapsed or 0)
    if not allow_pause:
        elapsed = int(wall or 0)
    sess_limit = int(sess_limit or 0)
    if mine or is_admin:
        sess_limit = 0
    resume_count = int(resume_count or 0)
    blocked = (not allow_pause) and resume_count > max_resumes
    sec_left = max(0, sess_limit * 60 - elapsed) if sess_limit > 0 else 0
    out.update({
        "limitMinutes": sess_limit,
        "secondsLeft": sec_left,
        "elapsedSeconds": elapsed,
        "startedAt": str(started) if started else "",
        "expired": sess_limit > 0 and sec_left <= 0,
        "allowPause": allow_pause,
        "maxResumes": max_resumes,
        "resumeCount": resume_count,
        "resumeBlocked": blocked,
    })
    return out


def pause_paper(account: dict, pid: int, active: bool = True) -> dict:
    """正常退出：允许中途退出的卷子把当前活跃时间记入并暂停；不允许的卷子不暂停。

    active=True：刚从做题页退出，累计到当前时刻；
    active=False：从试卷详情退出（可能刚刷新过），只累计到最后心跳，空白时间不算。
    """
    p, used = _paper_cfg(account, pid)
    mine = p[1] == account["id"]
    allow = bool(p[8]) if p[8] is not None else True
    if mine or account.get("role") == "admin":
        allow = True
    out = {"paused": False, "elapsedSeconds": 0, "secondsLeft": 0, "limitMinutes": 0}
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            if allow:
                cur.execute("""UPDATE drill_paper_sessions
                                  SET elapsed_seconds=elapsed_seconds +
                                        GREATEST(0, TIMESTAMPDIFF(SECOND, active_since,
                                          CASE WHEN %s THEN NOW()
                                               ELSE COALESCE(last_seen, active_since) END)),
                                      active_since=NULL, last_seen=NOW()
                                WHERE account_id=%s AND paper_id=%s
                                  AND active_since IS NOT NULL""",
                            (1 if active else 0, account["id"], pid))
                conn.commit()
            cur.execute("""SELECT elapsed_seconds, limit_minutes,
                                  TIMESTAMPDIFF(SECOND, started_at, NOW()),
                                  active_since
                             FROM drill_paper_sessions
                            WHERE account_id=%s AND paper_id=%s""", (account["id"], pid))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return out
    elapsed = int(row[0] or 0)
    limit = int(row[1] or 0)
    if not allow:
        elapsed = int(row[2] or 0)
    if mine or account.get("role") == "admin":
        limit = 0
    out.update({"paused": allow,
                "elapsedSeconds": elapsed,
                "limitMinutes": limit,
                "secondsLeft": max(0, limit * 60 - elapsed) if limit > 0 else 0})
    return out


def heartbeat_paper(account: dict, pid: int) -> dict:
    """作答中定期上报，把已过的活跃时间记进会话；异常退出时空白时间不算。"""
    p, used = _paper_cfg(account, pid)
    mine = p[1] == account["id"]
    allow = bool(p[8]) if p[8] is not None else True
    if mine or account.get("role") == "admin":
        allow = True
    if not allow:
        return {"elapsedSeconds": 0, "secondsLeft": 0, "paused": False}
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""UPDATE drill_paper_sessions
                              SET elapsed_seconds=elapsed_seconds +
                                    GREATEST(0, TIMESTAMPDIFF(SECOND, active_since, NOW())),
                                  active_since=NOW(), last_seen=NOW()
                            WHERE account_id=%s AND paper_id=%s
                              AND active_since IS NOT NULL""", (account["id"], pid))
            conn.commit()
            cur.execute("""SELECT elapsed_seconds, limit_minutes
                             FROM drill_paper_sessions
                            WHERE account_id=%s AND paper_id=%s""", (account["id"], pid))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return {"elapsedSeconds": 0, "secondsLeft": 0, "paused": True}
    elapsed = int(row[0] or 0)
    limit = int(row[1] or 0)
    if mine or account.get("role") == "admin":
        limit = 0
    return {"elapsedSeconds": elapsed,
            "secondsLeft": max(0, limit * 60 - elapsed) if limit > 0 else 0,
            "paused": True}


def submit_paper(account: dict, pid: int, answers: dict, auto: bool = False) -> dict:
    """整卷交卷：一次判完整套题，只消耗一次交卷机会。"""
    p, used = _paper_cfg(account, pid)
    mine = p[1] == account["id"]
    max_attempts = int(p[5] or 0)
    show_answer = bool(p[6])
    if (max_attempts > 0 and not mine and account.get("role") != "admin"
            and used >= max_attempts):
        raise DrillError(f"这套试卷最多可以交卷 {max_attempts} 次，"
                         f"你已经交过 {used} 次了。")
    answers = answers or {}
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT {_COLS} FROM drills
                             WHERE paper_id=%s AND (status=1 OR account_id=%s)
                             ORDER BY id ASC""", (pid, account["id"]))
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        raise DrillError("这套试卷还没有可作答的题目")

    infos = []
    pending = []
    total_score = my_score = 0
    passed_n = answered_n = 0
    for i, row in enumerate(rows, 1):
        dr = _row_to_dict(row)
        did = int(dr["id"])
        qscore = int(dr.get("score") or 0)
        total_score += qscore
        ans = answers.get(str(did), answers.get(did))
        if _answer_is_empty(ans):
            infos.append({"id": did, "no": i, "answered": False, "passed": False,
                          "score": 0, "maxScore": qscore, "reason": "未作答",
                          "answer": None, "ms": 0})
            continue
        if isinstance(ans, str) and len(ans.encode("utf-8")) > C.CODE_MAX:
            raise DrillError(f"第 {i} 题的作答超过 256KB 上限")
        res = _judge_one(account, dr, ans, show_answer)
        answered_n += 1
        if res["passed"]:
            passed_n += 1
            my_score += res["score"]
        infos.append({"id": did, "no": i, "answered": True,
                      "passed": bool(res["passed"]), "score": res["score"],
                      "maxScore": res["maxScore"], "reason": res.get("reason") or "",
                      "answer": ans, "ms": res.get("ms") or 0})
        pending.append((did, ans, res))
    # 计时：允许中途退出的累计活跃时间；不允许的按开始到现在的墙钟时间
    allow_pause = bool(p[8]) if p[8] is not None else True
    started_at = None
    limit_minutes = int(p[7] or 0)
    elapsed_used = 0
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT started_at, limit_minutes, elapsed_seconds,
                                  active_since,
                                  TIMESTAMPDIFF(SECOND, started_at, NOW()),
                                  elapsed_seconds + IF(active_since IS NULL, 0,
                                    GREATEST(0, TIMESTAMPDIFF(SECOND, active_since, NOW())))
                             FROM drill_paper_sessions
                            WHERE account_id=%s AND paper_id=%s""",
                        (account["id"], pid))
            sess = cur.fetchone()
    finally:
        conn.close()
    if sess:
        started_at = sess[0]
        limit_minutes = int(sess[1] or 0)
        elapsed_used = int(sess[5] or 0) if allow_pause else int(sess[4] or 0)
    if mine or account.get("role") == "admin":
        limit_minutes = 0
    expired = limit_minutes > 0 and elapsed_used >= limit_minutes * 60
    if answered_n == 0 and not expired and not auto:
        raise DrillError("还没有作答，先做几道题再交卷")

    # 先写整卷记录，再把每题提交挂到这次交卷上
    detail = {"questions": infos}
    conn = root_conn(C.COMMUNITY_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO drill_paper_attempts
                           (paper_id, account_id, attempt_no, score, total_score,
                            passed_n, answered_n, question_n, timed_out, started_at,
                            limit_minutes, detail)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,NOW()),%s,%s)""",
                        (pid, account["id"], used + 1, my_score, total_score,
                         passed_n, answered_n, len(rows), 1 if expired else 0,
                         started_at, limit_minutes,
                         json.dumps(detail, ensure_ascii=False, default=str)[:4_000_000]))
            attempt_id = int(cur.lastrowid)
            cur.execute("""DELETE FROM drill_paper_sessions
                            WHERE account_id=%s AND paper_id=%s""", (account["id"], pid))
        conn.commit()
    finally:
        conn.close()
    for did, ans, res in pending:
        _store_submission(account, did, ans, res, attempt_id)

    out = paper_stats(account, pid)
    out["attemptId"] = attempt_id
    out["attemptNo"] = used + 1
    return out


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
