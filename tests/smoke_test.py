"""端到端烟测：需要网站已在本机跑起来（默认 http://localhost:8000）。多库模型版。"""
import io
import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✔ {name}")
    else:
        FAIL += 1
        print(f"  ✖ {name}  {extra}")


def call(path, body=None, token="", method=None, raw=None, ctype="application/json"):
    url = BASE + path
    data = None
    headers = {"X-Token": token}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = ctype
    if raw is not None:
        data = raw
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, headers=headers, method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def download(path, token=""):
    req = urllib.request.Request(BASE + path, headers={"X-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Disposition", "")
    except urllib.error.HTTPError as e:
        return e.code, b"", ""


def multipart(field, filename, content, extra=None):
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in (extra or {}).items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
              "Content-Type: application/octet-stream\r\n\r\n".encode())
    buf.write(content if isinstance(content, bytes) else content.encode())
    buf.write(f"\r\n--{boundary}--\r\n".encode())
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


print("== 1. 注册 / 登录 / 游客 ==")
u1 = "stu" + uuid.uuid4().hex[:6]
code, d = call("/api/login", {"mode": "register", "username": u1, "password": "Test1234abc"})
check("注册成功", code == 200 and d.get("token"), str(d))
tok1 = d.get("token", "")

code, d = call("/api/me", token=tok1)
db1 = d.get("db", "")
tables1 = [t["name"] for t in d.get("tables", [])]
dbs1 = d.get("databases", [])
check("自动赠送内置三表", {"emp", "dept", "salgrade"} <= {t.lower() for t in tables1}, str(tables1))
check("返回默认库名", db1.startswith("u_"), str(d)[:150])
check("返回我的数据库列表", any(x["name"] == db1 and x["primary"] for x in dbs1), str(dbs1)[:200])

code, d = call("/api/login", {"mode": "register", "username": u1, "password": "Test1234abc"})
check("重复注册被拒", code == 400)
code, d = call("/api/login", {"mode": "login", "username": u1, "password": "WrongPass9x"})
check("密码错误被拒", code == 400)
code, d = call("/api/login", {"mode": "guest"})
check("游客登录", code == 200 and d.get("token"))
code, d = call("/api/me", token="bad-token")
check("无效token被拒", code == 401)

print("== 2. SQL 执行（默认库 + 无分号多行） ==")
code, d = call("/api/sql", {"sql": "SELECT * FROM emp;"}, token=tok1)
res = d.get("results", [])
check("SELECT 返回14行", code == 200 and res and res[0]["type"] == "rows" and res[0]["rowCount"] == 14, str(d)[:200])
check("响应带目标库名", d.get("db") == db1, str(d)[:100])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM emp\nWHERE SAL > 2000"}, token=tok1)
res = d.get("results", [])
check("无分号多行单条", code == 200 and res and res[0]["type"] == "rows" and res[0]["rows"][0][0] == 6, str(res)[:200])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM dept\nSELECT COUNT(*) FROM emp"}, token=tok1)
res = d.get("results", [])
check("无分号多条(每行一条)", code == 200 and len(res) == 2 and res[0]["rows"][0][0] == 4 and res[1]["rows"][0][0] == 14, str(res)[:200])
code, d = call("/api/sql", {"sql": "SELECT * FROM 不存在的表;"}, token=tok1)
check("SQL报错友好返回", code == 200 and d["results"][0]["type"] == "error", str(d)[:150])
code, d = call("/api/sql", {"sql": "SELECT * FROM nope"}, token=tok1)
check("错误附带友好提示", code == 200 and "提示" in d["results"][0].get("msg", ""), str(d)[:200])

print("== 3. DROP 库保护（默认库禁删 / 不存在给提示） ==")
code, d = call("/api/sql", {"sql": f"DROP DATABASE {db1};"}, token=tok1)
check("默认库禁删", code == 200 and d["results"][0]["type"] == "error"
      and "不能删除默认数据库" in d["results"][0]["msg"], str(d)[:200])
code, d = call("/api/sql", {"sql": f"DROP DATABASE {db1[:-1]};"}, token=tok1)
check("拼写接近给纠错提示", code == 200 and d["results"][0]["type"] == "error"
      and "你是不是想输入" in d["results"][0]["msg"], str(d)[:250])
code, d = call("/api/sql", {"sql": "DROP DATABASE dept;"}, token=tok1)
check("删不存在的库给不存在提示", code == 200 and "不存在" in d["results"][0]["msg"], str(d)[:200])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM emp;"}, token=tok1)
check("拦截后数据库仍正常", code == 200 and d["results"][0]["rows"][0][0] == 14, str(d)[:150])

print("== 4. 多库：新建 / 按库执行 / 导出 / 删除 ==")
dbx = "shop" + uuid.uuid4().hex[:8]
code, d = call("/api/databases", {"name": dbx}, token=tok1, method="POST")
check("新建数据库", code == 200 and any(x["name"] == dbx for x in d.get("databases", [])), str(d)[:200])
code, d = call("/api/databases", {"name": dbx}, token=tok1, method="POST")
check("重名被拒", code == 400)
code, d = call(f"/api/databases/{dbx}/tables", token=tok1)
check("新库为空", code == 200 and d.get("tables") == [], str(d)[:150])

code, d = call("/api/sql", {"sql": "CREATE TABLE t1 (id INT); INSERT INTO t1 VALUES (1),(2);",
                            "db": dbx}, token=tok1)
check("按库执行SQL", code == 200 and d.get("db") == dbx, str(d)[:200])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM t1;", "db": dbx}, token=tok1)
check("新库里可查询", code == 200 and d["results"][0]["rows"][0][0] == 2, str(d)[:150])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM t1;"}, token=tok1)
check("默认库看不到新库的表", code == 200 and d["results"][0]["type"] == "error", str(d)[:150])

code, data, cd = download(f"/api/databases/{dbx}/export", token=tok1)
check("导出.sql", code == 200 and b"CREATE TABLE" in data and b"INSERT INTO" in data and ".sql" in cd, str(cd)[:120])
code, d = call(f"/api/databases/{dbx}", token=tok1, method="DELETE")
check("删除导入库", code == 200 and not any(x["name"] == dbx for x in d.get("databases", [])), str(d)[:200])
code, d = call("/api/sql", {"sql": "SELECT 1;", "db": dbx}, token=tok1)
check("删除后执行被拒", code == 403, str(code))

print("== 5. 账号间隔离 ==")
u2 = "stu" + uuid.uuid4().hex[:6]
code, d = call("/api/login", {"mode": "register", "username": u2, "password": "Test1234abc"})
tok2 = d.get("token", "")
db2 = ""
code, d2 = call("/api/me", token=tok2)
db2 = d2.get("db", "")
check("两个账号库不同", db2 != db1, f"{db1} vs {db2}")
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM dept;", "db": db1}, token=tok2)
check("B不能对A的库执行SQL", code == 403, str(code))
code, d = call("/api/sql", {"sql": "USE mysql; SELECT user FROM user;"}, token=tok2)
check("B无法访问mysql系统库", code == 200 and d["results"][0]["type"] == "error", str(d)[:150])

print("== 6. 导入 + 表源文件（导入到指定库） ==")
csv_data = "学号,姓名,成绩\n1,张三,90\n2,李四,85.5\n3,王五,缺考\n"
body, ct = multipart("file", "测试成绩.csv", csv_data, {"table": "cj", "header": "true", "overwrite": "false"})
code, d = call("/api/import", token=tok1, raw=body, ctype=ct)
check("CSV导入默认库", code == 200 and d.get("kind") == "table" and d["result"]["rows"] == 3, str(d)[:200])
csv2 = "学号,姓名,成绩\n1,张三,90\n2,李四,85.5\n3,王五,缺考\n"
csvdb = "csvdb" + uuid.uuid4().hex[:6]
code, d = call("/api/databases", {"name": csvdb}, token=tok1, method="POST")
check("为导入新建库", code == 200)
body, ct = multipart("file", "测试成绩2.csv", csv2, {"table": "cj2", "header": "true", "db": csvdb})
code, d = call("/api/import", token=tok1, raw=body, ctype=ct)
check("CSV导入到指定库", code == 200 and d.get("db") == csvdb, str(d)[:200])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM cj2;", "db": csvdb}, token=tok1)
check("指定库里可查询", code == 200 and d["results"][0]["rows"][0][0] == 3, str(d)[:200])
body, ct = multipart("file", "bad.txt", "xxx", {})
code, d = call("/api/import", token=tok1, raw=body, ctype=ct)
check("不支持类型被拒", code == 400)
big_content = b"a,b\n" + b"1,2\n" * (2 * 1024 * 1024)
body, ct = multipart("file", "big.csv", big_content, {"table": "bigt"})
code, d = call("/api/import", token=tok1, raw=body, ctype=ct)
check("超过5MB被拒", code == 400, str(code))

print("== 7. 社区（数据库单元：详情/整库导入为独立库/按表导入/发布） ==")
code, d = call("/api/community", token=tok1)
items = d.get("items", [])
check("社区条目全部是数据库单元", len(items) > 0 and all(i["kind"] == "db" for i in items),
      str([(i['kind'], i['title']) for i in items])[:150])
bid = next((i["id"] for i in items if i["builtin"]), 0)
code, d = call(f"/api/community/{bid}/detail", token=tok1)
tnames = [t["name"].lower() for t in d.get("tables", [])]
check("详情可见三张表", code == 200 and {"emp", "dept", "salgrade"} <= set(tnames), str(d)[:200])

# B 整库导入 → B 名下出现独立新库
code, d = call("/api/community/import", {"id": bid, "overwrite": False}, token=tok2)
new_db = d.get("db", "")
check("B整库导入创建独立新库", code == 200 and new_db.startswith("bjpowernode"), str(d)[:250])
code, d2 = call("/api/me", token=tok2)
check("B的数据库列表出现新库", any(x["name"] == new_db for x in d2.get("databases", [])), str(d2)[:200])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM emp;", "db": new_db}, token=tok2)
check("新库独立可查询", code == 200 and d["results"][0]["rows"][0][0] == 14, str(d)[:150])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM emp;"}, token=tok2)
check("B默认库未受影响", code == 200 and d["results"][0]["rows"][0][0] == 14, str(d)[:150])
code, d = call("/api/community/publish", {"db": new_db}, token=tok2)
check("社区下载的库不能回传社区", code == 400 and "来自社区下载" in str(d.get("detail", "")), str(d)[:200])

# B 按表导入内置库的 salgrade 到自己的默认库 → 再回传应被拦截
code, d = call("/api/community/import", {"id": bid, "overwrite": False, "table": "salgrade", "db": db2}, token=tok2)
check("B按表导入 salgrade", code == 200, str(d)[:200])
code, d = call("/api/community/publish", {"table": "salgrade"}, token=tok2)
check("社区下载的表不能回传社区", code == 400 and "来自社区下载" in str(d.get("detail", "")), str(d)[:200])

# A 发布单表 + B 按表导入到 B 的默认库
code, d = call("/api/community/publish", {"table": "cj"}, token=tok1)
check("A发布单表为数据库", code == 200, str(d))

# A 整库分享（自定义对方导入后的库名）+ 分享链接全流程
code, d = call("/api/community/publish", {"db": db1, "share_name": "共享教学库"}, token=tok1)
check("整库分享自定义库名", code == 200 and d.get("shareCode"), str(d)[:200])
code, dl = call("/api/community", token=tok1)
check("私有分享不进社区广场", not any(i.get("shareName") == "共享教学库" and i.get("title") == db1 for i in dl.get("items", []) if i.get("title") != db1) and not any(i["title"] == db1 for i in dl.get("items", [])), str([i["title"] for i in dl.get("items", [])])[:150])
share_code = d.get("shareCode")
sreq = urllib.request.Request(BASE + "/s/" + share_code)
with urllib.request.urlopen(sreq, timeout=30) as resp:
    html = resp.read()
check("链接入口返回SPA", b'id="app"' in html)
code, d = call(f"/api/community/by-code/{share_code}", token=tok2)
check("按码取详情带默认库名", code == 200 and d.get("shareName") == "共享教学库"
      and len(d.get("tables", [])) >= 3, str(d)[:200])
code, d = call("/api/community/import", {"id": d["id"], "overwrite": False,
               "new_db_name": "我导的库"}, token=tok2)
check("自定义名导入为独立库", code == 200 and d.get("db") == "我导的库", str(d)[:200])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM emp;", "db": "我导的库"}, token=tok2)
check("独立库可查询", code == 200 and d["results"][0]["rows"][0][0] == 14, str(d)[:150])

# 公开发布才进社区
code, d = call("/api/community/publish", {"db": db1, "share_name": "公开库", "public": True}, token=tok1)
code, dl = call("/api/community", token=tok2)
check("公开发布出现在社区", any(i["title"] == db1 for i in dl.get("items", [])), str([i["title"] for i in dl.get("items", [])])[:150])
code, d = call("/api/community", token=tok2)
shared = [i for i in d.get("items", []) if not i["builtin"]]
check("B看到A发布的库", any(i["name"] == "cj" and i["uploader"] == u1 for i in shared), str(shared)[:200])
sid = shared[0]["id"]
code, d = call("/api/community/import", {"id": sid, "overwrite": False, "table": "cj", "db": db2}, token=tok2)
check("B按表导入到默认库", code == 200 and "cj" in d["result"]["imported"], str(d)[:200])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM cj;", "db": db2}, token=tok2)
rows_val = None
if code == 200 and d.get("results"):
    try:
        rows_val = d["results"][0].get("rows", [[None]])[0][0]
    except Exception:
        pass
check("按表导入后可查询", rows_val == 3, str(d)[:250])

# A 上传 .sql → 数据库条目；B 整库导入为独立库
sql_up = "CREATE TABLE hello (id INT, msg VARCHAR(50)); INSERT INTO hello VALUES (1, '你好');"
body, ct = multipart("file", "init.sql", sql_up, {"title": "建库脚本"})
code, d = call("/api/community/upload", token=tok1, raw=body, ctype=ct)
check("上传sql脚本为数据库条目", code == 200 and d.get("kind") == "db", str(d)[:150])
sql_id = d.get("id")
code, d = call(f"/api/community/{sql_id}/detail", token=tok2)
check("脚本解析出表清单", code == 200 and any(t["name"] == "hello" for t in d.get("tables", [])), str(d)[:200])
code, d = call("/api/community/import", {"id": sql_id, "overwrite": False}, token=tok2)
new_db2 = d.get("db", "")
check("脚本整库导入为独立库", code == 200 and bool(new_db2), str(d)[:200])
code, d = call("/api/sql", {"sql": "SELECT msg FROM hello;", "db": new_db2}, token=tok2)
check("独立库可查询", code == 200 and d["results"][0]["rows"][0][0] == "你好", str(d)[:150])
code, data, cd = download(f"/api/community/{sql_id}/download", token=tok2)
check("下载脚本", code == 200 and "init.sql" in cd and b"hello" in data, str(cd))
code, data, cd = download(f"/api/community/{bid}/download", token=tok2)
check("内置库可导出.sql", code == 200 and b"CREATE TABLE" in data, str(cd)[:100])
code, d = call("/api/community/import", {"id": py_id if False else sql_id, "overwrite": False, "table": "hello"}, token=tok2)
check("脚本条目不支持按表导入", code == 400, str(d)[:150])

py_code = "print('来自社区的代码')\nprint(6 * 7)\n"
body, ct = multipart("file", "demo.py", py_code, {"title": "演示代码"})
code, d = call("/api/community/upload", token=tok1, raw=body, ctype=ct)
check("上传py代码", code == 200 and d.get("kind") == "py", str(d)[:150])
py_id = d.get("id")
code, d = call("/api/community/open", {"id": py_id}, token=tok2)
check("B打开py代码", code == 200 and "来自社区的代码" in d.get("code", ""), str(d)[:150])
code, d = call("/api/community/import", {"id": py_id, "overwrite": False}, token=tok2)
check("py不能导入", code == 400)

print("== 8. Python 交互式运行 ==")
import time as _time


def wait_job(job, token, tries=25):
    st = {}
    for _ in range(tries):
        _, st = call(f"/api/pyrun/status/{job}?since_out=0&since_err=0", token=token)
        if not st.get("running"):
            return st
        _time.sleep(0.4)
    return st


code, d = call("/api/pyrun/start", {"code": "print(123+456)", "db": db1}, token=tok1)
check("启动Python作业", code == 200 and d.get("job"), str(d)[:150])
st = wait_job(d.get("job", ""), tok1)
check("Python运行输出", "579" in (st.get("out") or "") and st.get("exit") == 0, str(st)[:200])

code, d = call("/api/pyrun/start", {"code": "while True:\n    pass\n", "db": db1}, token=tok1)
st = wait_job(d.get("job", ""), tok1)
check("死循环被强杀", st.get("running") is False and (st.get("why") in ("idle", "max") or (st.get("exit") or 0) < 0), str(st)[:150])

code, d = call("/api/pyrun/start", {"code": "x = [0] * 10**9", "db": db1}, token=tok1)
st = wait_job(d.get("job", ""), tok1)
check("内存炸弹不炸服务器", st.get("running") is False and st.get("exit") != 0, str(st)[:150])

# input() 真正可交互
code, d = call("/api/pyrun/start",
               {"code": "n = input('你的名字：')\nprint('你好，' + n)", "db": db1}, token=tok1)
job4 = d.get("job", "")
_time.sleep(1.0)
_, st = call(f"/api/pyrun/status/{job4}?since_out=0&since_err=0", token=tok1)
check("input等待用户输入", st.get("running") is True and "你的名字" in (st.get("out") or ""), str(st)[:200])
code, d = call("/api/pyrun/input", {"job": job4, "text": "小明"}, token=tok1)
check("写入标准输入", code == 200, str(d)[:150])
st = wait_job(job4, tok1)
check("input内容进入程序", "你好，小明" in (st.get("out") or "") and st.get("exit") == 0, str(st)[:200])

code, d = call("/api/pyrun/start",
               {"code": "rows = query(\"SELECT COUNT(*) FROM emp\")\nprint('emp行数:', rows[0][0])", "db": db1},
               token=tok1)
st = wait_job(d.get("job", ""), tok1)
check("Python直连MySQL查询", "emp行数: 14" in (st.get("out") or ""), str(st)[:250])

print("== 8b. Python 多文件 ==")
code, d = call("/api/pyfiles", token=tok1)
check("pyfiles 自动建 main.py", any(f["name"] == "main.py" for f in d.get("files", [])), str(d)[:150])
code, d = call("/api/pyfiles", token=tok2)
code, d = call("/api/pyfiles/main.py", token=tok2)
check("新账号main.py带开箱示例", "query(" in (d.get("content") or "") and d.get("content", "").strip() != "",
      str(d)[:200])
code, d = call("/api/pyrun/start", {"code": d.get("content", ""), "db": db2}, token=tok2)
st = wait_job(d.get("job", ""), tok2)
check("main.py示例直接可运行", st.get("exit") == 0 and "工资前 5 名" in (st.get("out") or ""), str(st)[:250])
code, d = call("/api/pyfiles/demo.py", {"content": "print(1)"}, token=tok1, method="PUT")
check("保存py文件", code == 200 and d.get("size") == 8, str(d)[:150])
code, d = call("/api/pyfiles/demo.py", token=tok1)
check("读取py文件", d.get("content") == "print(1)", str(d)[:150])
code, d = call("/api/pyfiles/demo.py", token=tok1, method="DELETE")
check("删除py文件", code == 200, str(d)[:150])

print("== 9. 隔离补充 ==")
code, d = call("/api/sql", {"sql": "DROP TABLE emp;", "db": new_db}, token=tok2)
check("B删自己独立库里的表", code == 200)
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM emp;"}, token=tok1)
check("A的emp安然无恙", code == 200 and d["results"][0]["rows"][0][0] == 14, str(d)[:150])
code, d = call("/api/sql", {"sql": f"DROP DATABASE {new_db};"}, token=tok2)
check("B可删自己导入的独立库", code == 200 and d["results"][0]["type"] == "ok", str(d)[:200])
code, d = call("/api/databases", token=tok2)
check("删除后列表同步", not any(x["name"] == new_db for x in d.get("databases", [])), str(d)[:200])

print("== 10. 管理员 + 清理 ==")
code, d = call("/api/admin/users", token=tok1)
check("普通用户访问admin被拒", code == 403)
code, d = call("/api/login", {"mode": "login", "username": "admin", "password": "admin123"})
check("admin登录", code == 200 and d.get("token"), str(d))
tok_admin = d.get("token", "")
code, d = call("/api/admin/users", token=tok_admin)
check("admin列出用户", code == 200 and any(u["username"] == u1 for u in d.get("users", [])), str(d)[:200])
code, d = call("/api/community", token=tok1)
leftover = [i for i in d["items"] if i["uploader"] == u1 and not i["builtin"]]
for it in leftover:
    code, d = call(f"/api/community/{it['id']}", token=tok1, method="DELETE")
    check(f"删除资源 {it['title']}", code == 200, str(d))
# 管理后台拆两页
code, dg = call("/api/admin/users?kind=guest", token=tok_admin)
check("管理后台游客页", code == 200 and all(u["kind"] == "guest" for u in dg.get("users", [])) or not dg.get("users"), str(dg)[:150])

# 弱密码/非法用户名被拒
for bad_u, bad_p, why in [("张三", "Test1234abc", "中文用户名"),
                          ("1abc", "Test1234abc", "数字开头"),
                          ("has_under", "Test1234abc", "含下划线"),
                          ("goodname", "123456", "弱密码"),
                          ("goodname", "abcdefgh", "纯字母"),
                          ("admin", "Test1234abc", "保留名")]:
    code, d = call("/api/login", {"mode": "register", "username": bad_u, "password": bad_p})
    check(f"拒绝注册({why})", code == 400 and d.get("detail"), str(d)[:100])

code, d = call("/api/admin/users?kind=user", token=tok_admin)
u2_id = next((u["id"] for u in d.get("users", []) if u["username"] == u2), 0)
check("管理后台列出IP", code == 200 and all(u.get("lastIp") for u in d.get("users", [])), str(d)[:200])
code, d = call("/api/admin/delete_user", {"id": u2_id}, token=tok_admin)
check("admin删除用户", code == 200, str(d))
code, d = call("/api/me", token=tok2)
check("被删用户会话失效", code == 401)

print()
print(f"===== 烟测通过 {PASS} 项，失败 {FAIL} 项 =====")
sys.exit(1 if FAIL else 0)
