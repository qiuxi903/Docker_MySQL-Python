"""本地自测：不需要 MySQL，验证纯逻辑模块 + 沙箱执行引擎。"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✔ {name}")
    else:
        FAIL += 1
        print(f"  ✖ {name}  {extra}")


print("== 1. SQL 语句切分器 ==")
from app.sqlrun import split_sql

check("简单两条", split_sql("SELECT 1; SELECT 2;") == ["SELECT 1", "SELECT 2"])
check("无尾分号", split_sql("SELECT 1") == ["SELECT 1"])
check("字符串内分号", split_sql("SELECT 'a;b'; SELECT 2;") == ["SELECT 'a;b'", "SELECT 2"])
check("转义引号", split_sql("SELECT 'it''s';") == ["SELECT 'it''s'"])
check("反斜杠转义", split_sql(r"SELECT 'a\'b'; SELECT 2;") == [r"SELECT 'a\'b'", "SELECT 2"])
check("反引号内分号", split_sql("SELECT `a;b` FROM t;") == ["SELECT `a;b` FROM t"])
check("双横线注释", split_sql("SELECT 1; -- 注释; 分号\nSELECT 2;") == ["SELECT 1", "SELECT 2"])
check("井号注释", split_sql("SELECT 1; # 注释; 分号\nSELECT 2;") == ["SELECT 1", "SELECT 2"])
check("块注释", [" ".join(s.split()) for s in split_sql("SELECT /* 1;2;3 */ 1; SELECT 2;")] == ["SELECT 1", "SELECT 2"])
check("多行INSERT(跨行分号在引号外)",
      len(split_sql("INSERT INTO t VALUES (\n1, 'a'\n); INSERT INTO t VALUES (\n2, 'b'\n);")) == 2)
check("空语句跳过", split_sql(";;  ; SELECT 1;  ") == ["SELECT 1"])
check("bjpowernode脚本条数(3建表+23插入+3commit+3drop=32)",
      len(split_sql(open(os.path.join(ROOT, "backend/app/seed/bjpowernode.sql"),
                         encoding="utf-8").read())) == 32)

print("== 1b. 无分号语句准备（像 mysql 命令行一样） ==")
from app.sqlrun import prepare_statements as prep

check("单条无分号", prep("SELECT * FROM emp") == ["SELECT * FROM emp"])
check("多行单条不误切", prep("SELECT *\nFROM emp\nWHERE sal > 100") == ["SELECT *\nFROM emp\nWHERE sal > 100"])
check("多条无分号按行切", len(prep("select 1\nselect 2\nshow tables")) == 3)
check("括号续行不误切", len(prep("INSERT INTO t VALUES (\n1, 2, 3\n)")) == 1)
check("纯注释行跳过", prep("-- 注释\nselect 1") == ["select 1"])
check("有分号走原切分器", prep("select 1; select 2;") == ["select 1", "select 2"])
check("混合关键字函数行", len(prep("select now()\nupdate t set a=1")) == 2)

print("== 1c. DROP DATABASE 拦截 ==")
from app.sqlrun import drop_db_target as target_of

check("解析目标库名", target_of("DROP DATABASE g_abc123") == "g_abc123")
check("解析 IF EXISTS/大小写", target_of("drop schema if exists G_ABC123") == "G_ABC123")
check("普通语句返回 None", target_of("SELECT 1") is None and target_of("DROP TABLE emp") is None)

print("== 2. 导入类型推断 / 列名清洗 / 编码 ==")
from app.importer import _clean_columns, _decode, _infer_type, _rows_from_grid

check("int列", _infer_type(["1", "-2", "33"]) == "BIGINT")
check("double列", _infer_type(["1.5", "2", "-3.25"]) == "DOUBLE")
check("date列", _infer_type(["2024-01-01", "2024-12-31"]) == "DATE")
check("varchar列", _infer_type(["张三", "hello"]) == "VARCHAR(255)")
check("text列(超255)", _infer_type(["x" * 300]) == "TEXT")
check("空列", _infer_type([None, ""]) == "VARCHAR(255)")
cols = _clean_columns(["学号", "name", "name", "", "1abc", "a-b!", None])
check("列名清洗", cols == ["学号", "name", "name_2", "col4", "c1abc", "a-b_", "col7"], str(cols))
g = _rows_from_grid([["id", "名字"], ["1", "张三"], ["2", None]], True)
check("网格解析", g[0] == ["id", "名字"] and g[2] == [["1", "张三"], ["2", None]], str(g))
check("GBK解码", _decode("学号,姓名\n1,张三".encode("gbk")) == "学号,姓名\n1,张三")
check("UTF8-BOM解码", _decode("a\n1".encode("utf-8-sig")) == "a\n1")

print("== 3. 密码策略与哈希 ==")
from app.auth import (hash_password, validate_password, validate_username,
                      verify_password, RESERVED_USERNAMES)

check("用户名合法: zhangsan", validate_username("zhangsan")[0])
check("用户名合法: student01", validate_username("student01")[0])
check("拒绝中文名", not validate_username("张三")[0])
check("拒绝数字开头", not validate_username("1abc")[0])
check("拒绝下划线", not validate_username("a_b_c")[0])
check("拒绝过短", not validate_username("ab")[0])
check("拒绝 admin 等保留名", all(not validate_username(n)[0] for n in
      ["admin", "root", "test", "guest", "mysql", "administrator"]))

check("密码合法: Abcd1234", validate_password("Abcd1234", "zhangsan")[0])
check("拒绝123456", not validate_password("123456", "u")[0])
check("拒绝12345678", not validate_password("12345678", "u")[0])
check("拒绝纯字母", not validate_password("abcdefgh", "u")[0])
check("拒绝纯数字", not validate_password("1234567890", "u")[0])
check("拒绝 admin123", not validate_password("admin123", "u")[0])
check("拒绝 password", not validate_password("password1", "u")[0])
check("拒绝弱口令 123abc", not validate_password("123abc", "u")[0])
check("拒绝少于8位", not validate_password("Ab12", "u")[0])
check("拒绝与用户名相同", not validate_password("zhangsan1", "zhangsan")[0])
check("拒绝包含用户名", not validate_password("Zhangsan99", "zhangsan")[0])
check("拒绝重复字符", not validate_password("Aaaaaaaa1", "u")[0])

h = hash_password("Abcd1234")
check("哈希格式", h.startswith("pbkdf2$200000$") and len(h) > 60)
check("验证正确", verify_password("Abcd1234", h))
check("验证错误", not verify_password("Abcd1235", h))

print("== 4. 命名规则 / 标识符 / 值序列化 ==")
from app.db import conv_value, db_name_for, q_ident, valid_ident

check("ascii库名", db_name_for("zhang3") == "u_zhang3")
import re as _re
for name in ["张三", "Tony", "user_01", "学生A", "a" * 20]:
    check(f"库名合法({name})", _re.fullmatch(r"[a-z][a-z0-9_]{1,31}", db_name_for(name)) is not None,
          db_name_for(name))
check("同名同库", db_name_for("张三") == db_name_for("张三"))
check("标识符转义", q_ident("a`b") == "`a``b`")
check("表名校验", valid_ident("emp") and valid_ident("学生表") and not valid_ident("a b"))
import datetime as _dt
import decimal as _dec
check("值序列化", conv_value(_dt.datetime(2024, 1, 2, 3, 4, 5)) == "2024-01-02 03:04:05"
      and conv_value(_dec.Decimal("1.50")) == "1.50"
      and conv_value(b"abc") == "abc"
      and conv_value(None) is None)
check("纯date序列化(EMP的HIREDATE列)", conv_value(_dt.date(1980, 12, 17)) == "1980-12-17")
check("纯time序列化", conv_value(_dt.time(8, 30)) == "08:30:00")

print("== 5. FastAPI 应用可导入（路由装配检查） ==")
from app.main import app

paths = {r.path for r in app.routes}
for p in ["/api/login", "/api/me", "/api/tables", "/api/sql", "/api/import",
          "/api/community", "/api/community/upload", "/api/community/publish",
          "/api/community/import", "/api/community/open", "/api/community/{item_id}/download",
          "/api/source/{table}", "/api/source/{table}/download",
          "/api/pyrun/start", "/api/pyrun/input", "/api/admin/users", "/api/health",
          "/api/author/qpack/parse", "/api/author/qpack/create"]:
    check(f"路由 {p}", p in paths)

print("== 5b. 题目包：zip 解包与解析 ==")
import zipfile
from app import qpack
from app import drills as _drills


def make_zip(entries, folder=""):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(folder + name, data if isinstance(data, bytes) else data.encode())
    return buf.getvalue()


STEM = ("【题  干】\n人力资源库 db_hrm。\n\n"
        "1. 创建采购表 t_purchase。\n"
        "2. 向 t_employee 插入员工 10051。\n"
        "3. 查询薪资 6000 到 8000 的记录。\n")
ANS = ("-- 1\nCREATE TABLE t_purchase (id INT PRIMARY KEY, name VARCHAR(30));\n\n"
       "-- 2\nINSERT INTO t_employee VALUES (10051, '林子山');\n\n"
       "-- 3\nSELECT * FROM t_salary WHERE money BETWEEN 6000 AND 8000;\n")
DATA = ("DROP TABLE IF EXISTS t_employee;\n"
        "CREATE TABLE t_employee (id INT PRIMARY KEY, name VARCHAR(30));\n"
        "INSERT INTO t_employee VALUES (10001, '曹岚');\n"
        "INSERT INTO t_employee VALUES (10051, '林子山');\n"
        "DROP TABLE IF EXISTS t_purchase;\n"
        "CREATE TABLE t_purchase (id INT PRIMARY KEY, name VARCHAR(30));\n")

z1 = make_zip([("22试题描述.txt", STEM.encode("gbk")), ("answer.txt", ANS),
               ("db_hrm.myd", DATA)], folder="mysql题目例题/")
files = _drills.unpack_package([{"name": "试卷.zip", "data": z1}])
check("zip：解出 3 个文件", len(files) == 3, str([f["name"] for f in files]))
check("zip：去掉目录层级", sorted(f["name"] for f in files) ==
      ["22试题描述.txt", "answer.txt", "db_hrm.myd"], str([f["name"] for f in files]))

pkg = _drills.parse_package([{"name": "试卷.zip", "data": z1}])
check("zip：解析出 3 道题且都有答案",
      pkg["stats"]["total"] == 3 and pkg["stats"]["withAnswer"] == 3, str(pkg["stats"]))
check("zip：GBK 题干正确", "人力资源" in pkg["title"], pkg["title"][:40])
check("zip：答案产物被剔除", any("t_purchase" in x for x in pkg["stripped"]),
      str(pkg["stripped"]))
check("zip：建表题用整库状态判分",
      pkg["questions"][0]["kind"] == "sql_ddl" and
      pkg["questions"][0]["judgeMode"] == "dbstate", str(pkg["questions"][0]))
check("zip：包内文件清单回传", sorted(pkg["files"]) == ["22试题描述.txt", "answer.txt", "db_hrm.myd"],
      str(pkg["files"]))

# zip 里混入无关文件应被忽略
z2 = make_zip([("题干.txt", STEM), ("answer.txt", ANS), ("thumb.png", b"\x89PNG"),
               (".DS_Store", b"x"), ("~$cache1", b"x")])
files2 = _drills.unpack_package([{"name": "试卷.zip", "data": z2}])
check("zip：忽略图片/隐藏/临时文件", sorted(f["name"] for f in files2) ==
      ["answer.txt", "题干.txt"], str([f["name"] for f in files2]))

# 非 zip 直接传文件仍然兼容
files3 = _drills.unpack_package([{"name": "a.txt", "data": STEM.encode()},
                                 {"name": "b.txt", "data": ANS.encode()}])
check("兼容：直接传多个文件", len(files3) == 2)

# 坏 zip / 空包给出可读错误
for bad, why in [(b"not a zip at all", "坏 zip"), (make_zip([("a.png", b"x")]), "空包")]:
    try:
        _drills.unpack_package([{"name": "x.zip", "data": bad}])
        ok = False
    except _drills.DrillError as e:
        ok = bool(str(e))
    check(f"zip：{why} 有友好报错", ok)

# GBK 文件名的 zip（Windows 压缩工具常见）：zip 头里是原始 GBK 字节且不带 UTF-8 标志
def make_gbk_name_zip(gbk_name, data):
    """先用等长 ASCII 名打包，再把文件名字节替换成 GBK（本地头 + 中央目录各一份）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("aaaa.txt", data)
    raw = buf.getvalue()
    assert len(gbk_name) == len("aaaa.txt")
    return raw.replace(b"aaaa.txt", gbk_name)


z3 = make_gbk_name_zip("题干.txt".encode("gbk"), STEM)
files3g = _drills.unpack_package([{"name": "试卷.zip", "data": z3}])
check("zip：GBK 文件名不乱码", "题干.txt" in [f["name"] for f in files3g],
      str([f["name"] for f in files3g]))

# zip 里放 CSV 作为数据源
z4 = make_zip([("题干.txt", "1、查询所有数据\n2、统计行数\n3、删除 id=2\n"), ("answer.txt", ANS),
               ("data.csv", "id,name\n1,a\n2,b\n")])
pkg4 = _drills.parse_package([{"name": "p.zip", "data": z4}])
check("zip：CSV 数据自动转成建表语句",
      pkg4["tables"] == ["data"] and "CREATE TABLE `data`" in pkg4["dataSql"], str(pkg4["tables"]))

# 解压炸弹：声称超大
big = io.BytesIO()
with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("big.sql", b"SELECT 1;" * (9 * 1024 * 1024 // 9))
try:
    _drills.unpack_package([{"name": "big.zip", "data": big.getvalue()}])
    ok = False
except _drills.DrillError as e:
    ok = "8MB" in str(e) or "32MB" in str(e)
check("zip：超大文件被拒", ok)

print("== 6. Python 沙箱执行引擎（交互式作业） ==")
from runner import server as runner_server
import atexit
import shutil
import time as _t

NL = chr(10)   # 换行
CR = chr(13)   # 回车（Windows 输出带 CR）


@atexit.register
def _cleanup_test_jobs():
    """本地测试会直接调用 runner.start_job；进程退出后清理子进程和 temp 目录，
    否则死循环/等待输入的作业会留下 pyrun_* 目录和 Python 进程。"""
    for job in list(runner_server.jobs.values()):
        try:
            if job.proc.poll() is None:
                job.proc.kill()
                job.proc.wait(timeout=3)
        except Exception:
            pass
        try:
            shutil.rmtree(job.td, ignore_errors=True)
        except Exception:
            pass


def run_code(code, tries=40):
    """启动作业 → 轮询直到结束。"""
    job_id = runner_server.start_job(code, {})
    st = {}
    for _ in range(tries):
        st = runner_server.job_out(job_id, 0, 0, x_runner_token=runner_server.TOKEN)
        if not st["running"]:
            return st
        _t.sleep(0.3)
    return st


r = run_code('print("hello")' + NL + 'print(1 + 2)')
check("正常输出", r["out"].strip().replace(CR + NL, NL) == "hello" + NL + "3", repr(r["out"]))
check("退出码0", r["exit"] == 0, repr(r))

r = run_code("import sys" + NL + "print('x', file=sys.stderr)" + NL)
check("stderr捕获", "x" in r["err"], repr(r["err"]))

r = run_code("def f():" + NL + "    return 1 / 0" + NL + NL + "f()" + NL)
check("运行时错误过滤栈帧", "第 4 行" in r["err"] and "ZeroDivisionError" in r["err"], repr(r["err"]))
check("错误退出码", r["exit"] != 0, repr(r))

r = run_code("def f(:" + NL)
check("语法错误提示", "语法错误" in r["err"], repr(r["err"]))

r = run_code("while True:" + NL + "    pass" + NL, tries=80)
check("死循环不会一直跑", isinstance(r["running"], bool), repr(r))

r = run_code("import os" + NL + "print(os.environ.get('DB_PASS', 'NONE'))")
check("未传DB凭证则环境干净", r["out"].strip() == "NONE", repr(r["out"]))

r = run_code("from labhelpers import query, get_conn, execute, query_dicts" + NL + "print('helpers ok')")
check("数据库助手可导入", "helpers ok" in r["out"], repr(r["out"] + r["err"]))

r = run_code("print(callable(query), callable(get_conn), callable(execute), callable(query_dicts))")
check("裸调用作用域含助手函数", r["out"].strip() == "True True True True", repr(r["out"] + r["err"]))

# 交互式 input
job = runner_server.start_job("n = input('名字：')" + NL + "print('你好，' + n)", {})
_t.sleep(1.2)
st = runner_server.job_out(job, 0, 0, x_runner_token=runner_server.TOKEN)
check("input提示语可见且在等待", st["running"] is True and "名字" in st["out"], repr(st))
runner_server.job_input(job, runner_server.InputReq(text="小明"),
                        x_runner_token=runner_server.TOKEN)
for _ in range(25):
    _t.sleep(0.3)
    st = runner_server.job_out(job, 0, 0, x_runner_token=runner_server.TOKEN)
    if not st["running"]:
        break
check("input内容进入程序", "你好，小明" in st["out"] and st["exit"] == 0, repr(st))

print()
print(f"===== 通过 {PASS} 项，失败 {FAIL} 项 =====")
sys.exit(1 if FAIL else 0)
