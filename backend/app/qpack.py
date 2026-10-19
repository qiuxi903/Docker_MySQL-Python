"""题目包导入：把「一份试卷 + 参考答案」拆成多道可判分的练习题。

支持的上传材料（任选，可混合）：
  - 题干文件：.txt / .md —— 含「题  干」和 1、2、3… 编号小题
  - 参考答案：.txt / .md —— 以 -- 1 / ---8 / 1、 等分隔，按题号对应
  - 数据脚本：.sql / .myd（Navicat 导出的其实就是 SQL 文本）—— 作为所有小题共用的初始化数据

解析规则尽量宽容：中文全角/半角标点、题号后缀、空行都容忍。
"""
import re

# 题干里出现这些词，说明这一行是「要求/注意」，不是题目正文
NOTE_RE = re.compile(r"^(注意|说明|提示)\s*[:：]?")

# 小题起始行：1、 / 1. / 1． / （1） / (1) / 第1题
Q_START = re.compile(
    r"^\s*(?:第\s*(\d+)\s*题|[(（]\s*(\d+)\s*[)）]|(\d+)\s*[、.．)）])\s*(.*)$"
)

# 参考答案里的分隔：-- 1 / ---8 / --9 / -- 第1题
A_SEP = re.compile(r"^\s*-{2,}\s*(?:第\s*)?(\d+)\s*(?:题)?\s*$")

# 答案里混入的说明行（如"用sql语句查询…"）不算代码
A_NOISE = re.compile(r"^\s*(?:用\s*sql|请将|注意|说明)")


def decode_text(data: bytes) -> str:
    """容错解码：课堂材料常见 UTF-8 / GBK / GB18030 / UTF-16。"""
    if not data:
        return ""
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        try:
            return data.decode("utf-16")
        except Exception:
            pass
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _tidy(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def clean_data_sql(text: str) -> str:
    """清理 Navicat / mysqldump 导出的噪音，得到能直接执行的初始化脚本。

    - 去掉 /* ... */ 注释头（Navicat 的 Data Transfer 信息）
    - 规范小写 delimiter 指令（统一成大写交给 strip_delimiter 处理）
    - 去掉 DROP TRIGGER/PROCEDURE 之类对判分无意义的行（保留建表与数据）
    - 折叠连续分号（Navicat 用 ;; 结尾存储过程）
    """
    t = _tidy(text)

    # 1) 去掉块注释（Navicat 头）
    t = _BLOCK_COMMENT.sub("", t)

    # 2) 统一 delimiter 写法（Navicat 有时小写）
    t = re.sub(r"^\s*delimiter\s+", "DELIMITER ", t, flags=re.I | re.M)

    # 3) 折叠 ;;; 之类
    t = re.sub(r";\s*;+", ";", t)

    # 4) 丢掉单独的 SET FOREIGN_KEY_CHECKS（无害但也无用）
    t = re.sub(r"^\s*SET\s+FOREIGN_KEY_CHECKS\s*=\s*[01]\s*;?\s*$", "", t, flags=re.I | re.M)

    # 5) 压缩多余空行
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# ---------------- 从数据快照里剔除「答案产物」 ----------------

# 从答案 SQL 里提取它创建/修改的对象名
_OBJ_PATTERNS = [
    (re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:ALGORITHM\s*=\s*\w+\s+)?"
                r"(?:DEFINER\s*=\s*\S+\s+)?(?:SQL\s+SECURITY\s+\w+\s+)?"
                r"TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([\w\u4e00-\u9fff]+)`?", re.I), "table"),
    (re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:ALGORITHM\s*=\s*\w+\s+)?"
                r"(?:DEFINER\s*=\s*\S+\s+)?(?:SQL\s+SECURITY\s+\w+\s+)?"
                r"(?:VIEW|TRIGGER|PROCEDURE|FUNCTION)\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([\w\u4e00-\u9fff]+)`?", re.I), "object"),
]


def answer_artifacts(answer_sqls: list[str]) -> dict:
    """从所有参考答案里找出「这道题会创建的对象」和「会插入的主键值」。

    返回 {"tables": set, "objects": set, "inserts": [(table, first_value)]}
    """
    tables: set[str] = set()
    objects: set[str] = set()
    inserts: list[tuple[str, str]] = []
    for sql in answer_sqls:
        text = sql or ""
        for pat, kind in _OBJ_PATTERNS:
            for m in pat.finditer(text):
                name = m.group(1)
                (tables if kind == "table" else objects).add(name.lower())
        # INSERT INTO t VALUES (v1, ...) → 记录 (表, 首列值)，用于从快照里删掉这一行
        for m in re.finditer(r"INSERT\s+INTO\s+`?([\w\u4e00-\u9fff]+)`?[^;]*?VALUES\s*\(\s*([^,)]+)", text, re.I):
            inserts.append((m.group(1).lower(), m.group(2).strip().strip("'\"")))
    return {"tables": tables, "objects": objects, "inserts": inserts}


def _stmt_object_name(stmt: str) -> tuple[str, str] | None:
    """判断一条语句创建了什么对象，返回 (类型, 小写名)。"""
    head = stmt.lstrip()[:400]
    m = re.match(r"CREATE\s+(?:ALGORITHM\s*=\s*\w+\s+)?(?:DEFINER\s*=\s*\S+\s+)?"
                 r"(?:SQL\s+SECURITY\s+\w+\s+)?(TABLE|VIEW|TRIGGER|PROCEDURE|FUNCTION)\s+"
                 r"(?:IF\s+NOT\s+EXISTS\s+)?`?([\w\u4e00-\u9fff]+)`?", head, re.I)
    if not m:
        return None
    return m.group(1).lower(), m.group(2).lower()


def strip_answer_artifacts(data_sql: str, answers: list[str]) -> tuple[str, list[str]]:
    """从初始化数据里移除「做完答案后才会产生的对象和数据」。

    典型场景：老师给的 .sql 是做完题之后的数据库快照 —— 里面已经有
    第 1 题建的表、第 2 题插入的员工、第 7 题的视图、第 8/9 题的触发器与存储过程。
    这些必须先剔除，否则学生作答时会报「表已存在 / 主键重复」。

    返回 (清理后的 SQL, 被移除的对象说明列表)。
    """
    from .sqlrun import restore_semicolons, split_sql

    art = answer_artifacts(answers)
    if not art["tables"] and not art["objects"] and not art["inserts"]:
        return data_sql, []

    stmts = split_sql(data_sql)
    kept: list[str] = []
    removed: list[str] = []

    for raw in stmts:
        stmt = restore_semicolons(raw)
        obj = _stmt_object_name(stmt)
        if obj:
            kind, name = obj
            if name in art["objects"] or (kind == "table" and name in art["tables"]):
                removed.append(f"CREATE {kind} {name}")
                continue
        else:
            # DROP TABLE/VIEW/... 与被删对象一起丢掉，避免二次残留
            m = re.match(r"DROP\s+(TABLE|VIEW|TRIGGER|PROCEDURE|FUNCTION)\s+"
                         r"(?:IF\s+EXISTS\s+)?`?([\w\u4e00-\u9fff]+)`?", stmt.lstrip(), re.I)
            if m:
                name = m.group(2).lower()
                if name in art["objects"] or name in art["tables"]:
                    continue
            # 答案里 INSERT 的那一行，如果快照里已有同样主键，也删掉
            m = re.match(r"INSERT\s+INTO\s+`?([\w\u4e00-\u9fff]+)`?[^;]*?VALUES\s*\(\s*([^,)]+)",
                         stmt.lstrip(), re.I | re.S)
            if m:
                tbl, first = m.group(1).lower(), m.group(2).strip().strip("'\"")
                if any(t == tbl and v == first for t, v in art["inserts"]):
                    removed.append(f"INSERT {tbl} ({first})")
                    continue
        kept.append(raw)

    if not removed:
        return data_sql, []
    return ";\n".join(kept) + ";", removed


def clean_answer(sql: str) -> str:
    """参考答案清洗：去掉 DELIMITER 包装，返回可直接执行的语句（多条用分号分隔）。"""
    text = _tidy(sql)
    if not text.strip():
        return ""
    from .sqlrun import restore_semicolons, split_sql

    try:
        stmts = [restore_semicolons(x).strip().rstrip(";") for x in split_sql(text)]
        stmts = [x for x in stmts if x.strip()]
        return ";\n".join(stmts) + (";" if stmts else "")
    except Exception:
        return text


def answer_touches_missing_data(data_sql: str, answers: list[str]) -> list[str]:
    """检测「答案要删除/修改的数据，题目数据里已经没有了」的情况。

    典型：老师给的 .sql 是做完题之后的快照，第 3 题是 “删除 id=10040 的薪资”，
    但快照里那行早被删了 —— 学生无论怎么答都判不出差别。
    返回可疑题号说明，供出题人确认（不阻断导入）。
    """
    warns: list[str] = []
    for idx, sql in enumerate(answers, 1):
        text = sql or ""
        for m in re.finditer(r"DELETE\s+FROM\s+`?(\w+)`?[^;]*?WHERE\s+[`\w.]+\s*=\s*([\w'\"一-鿿]+)",
                             text, re.I):
            table, val = m.group(1), m.group(2).strip().strip("'\"")
            # 在数据脚本里找这行是否存在
            pat = re.compile(r"INSERT\s+INTO\s+`?" + re.escape(table) + r"`?[^;]*?VALUES\s*\(\s*"
                             + re.escape(val) + r"", re.I)
            if data_sql and not pat.search(data_sql):
                warns.append(f"第 {idx} 题要删除的 {table}(id={val}) 在题目数据里不存在，"
                             f"学生做了也看不出差别（建议改题或补数据）")
    return warns


def extract_title(stem_text: str) -> str:
    """题干第一行通常就是题目标题（如 人力资源管理系统…），取第一段非空文本短句。"""
    for line in _tidy(stem_text).splitlines():
        line = line.strip()
        if not line or line.startswith("『") or line.startswith("【"):
            continue
        if len(line) <= 60:
            return line
        return line[:60] + "…"
    return ""


def parse_stem(stem_text: str) -> dict:
    """拆题干：返回 {title, description, questions:[{no, text}]}"""
    text = _tidy(stem_text)
    lines = text.split("\n")
    title = extract_title(text)

    # 题干正文：去掉标题行与『题 干』标记，保留表结构说明
    desc_lines = []
    for line in lines:
        s = line.strip()
        if not s:
            if desc_lines and desc_lines[-1] != "":
                desc_lines.append("")
            continue
        if re.fullmatch(r"[『【]?\s*题\s*干\s*[』】]?", s):
            continue
        if s == title:
            continue
        if Q_START.match(s):
            break
        desc_lines.append(s)
    # 去掉尾部空行
    while desc_lines and desc_lines[-1] == "":
        desc_lines.pop()

    # 小题：从第一个题号开始，按题号切
    questions = []
    cur_no = None
    cur_buf = []
    for line in lines:
        m = Q_START.match(line)
        if m and m.group(4) is not None:
            no = int(m.group(1) or m.group(2) or m.group(3))
            if cur_no is not None:
                questions.append({"no": cur_no, "text": "\n".join(cur_buf).strip()})
            cur_no = no
            cur_buf = [m.group(4).strip()]
        elif cur_no is not None:
            cur_buf.append(line.rstrip())
    if cur_no is not None:
        questions.append({"no": cur_no, "text": "\n".join(cur_buf).strip()})

    # 把「注意：保存为 xxx.txt」这类要求从题目里拆出来，作为备注
    cleaned = []
    for q in questions:
        body, notes = [], []
        for line in q["text"].split("\n"):
            if NOTE_RE.match(line.strip()):
                notes.append(line.strip())
            else:
                body.append(line)
        cleaned.append({
            "no": q["no"],
            "text": "\n".join(body).strip(),
            "note": " ".join(notes).strip(),
        })
    return {"title": title, "description": "\n".join(desc_lines).strip(),
            "questions": cleaned}


def parse_answers(ans_text: str) -> dict[int, str]:
    """拆参考答案：按 -- 1 / ---8 等分隔，返回 {题号: SQL文本}"""
    text = _tidy(ans_text)
    out: dict[int, str] = {}
    cur_no = None
    buf: list[str] = []

    def flush():
        if cur_no is None:
            return
        code = "\n".join(buf).strip()
        # 去掉分隔符残留与纯说明行
        code = "\n".join(l for l in code.split("\n") if not A_NOISE.match(l.strip())).strip()
        if code:
            out[cur_no] = code

    for line in text.split("\n"):
        m = A_SEP.match(line)
        if m:
            flush()
            cur_no = int(m.group(1))
            buf = []
            continue
        if cur_no is None:
            # 开头没有分隔符时，尝试从 "1、" 这类题号开始
            m2 = re.match(r"^\s*(\d+)\s*[、.．)]\s*$", line)
            if m2:
                cur_no = int(m2.group(1))
                buf = []
            continue
        buf.append(line.rstrip())
    flush()
    return out


def guess_type(question_text: str, answer_sql: str) -> str:
    """按答案和题干猜题型：改/建对象 vs 查询。"""
    ans = (answer_sql or "").upper()
    q = question_text or ""
    if re.search(r"\b(CREATE|ALTER|DROP)\s+(TABLE|VIEW|TRIGGER|PROCEDURE|FUNCTION|INDEX|DATABASE)\b", ans):
        return "sql_ddl"
    if re.search(r"\b(INSERT|UPDATE|DELETE)\b", ans) and "SELECT" not in ans.split("INSERT")[0]:
        return "sql_dml"
    if re.search(r"\bSELECT\b", ans):
        return "sql_select"
    # 题干里明确"创建一个.../删除.../修改..."也算改数据题
    if re.search(r"(创建|新建|添加|插入|删除|修改|更新|建立)", q):
        return "sql_dml"
    return "sql_select"


def split_answer_files(ans_files: list[dict]) -> dict[int, str]:
    """多份答案文件合并（题号可能分散在 tj11.txt / tj12.txt 里）。"""
    merged: dict[int, str] = {}
    for f in ans_files:
        merged.update(parse_answers(f.get("content") or ""))
    return merged


# ---------------- 判分建议 ----------------

# 说明/备注里提到「保存为 xxx.txt」的，按查询题处理
def suggest_judge(question_no: int, qtype: str, question_text: str) -> str:
    if qtype == "sql_select":
        return "result"
    if qtype == "sql_dml":
        return "state"
    return "result"
