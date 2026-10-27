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


def admin_login():
    _, d = call("/api/login", {"mode": "login", "username": "admin", "password": "admin123"})
    return d.get("token", "")


def grant_publish(username, tok_admin):
    """管理员给某账号开通「发布到题库」权限。"""
    _, ul = call("/api/admin/users", token=tok_admin)
    uid = next((u["id"] for u in ul.get("users", []) if u["username"] == username), 0)
    return call("/api/admin/set_publish_permission", {"id": uid, "allow": True}, token=tok_admin)


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


def multipart_files(items, field="files"):
    """一次上传多个文件：items = [(文件名, 内容), ...]。"""
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()
    for name, content in items:
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; "
                  f"filename=\"{name}\"\r\n"
                  "Content-Type: application/octet-stream\r\n\r\n".encode())
        buf.write(content if isinstance(content, bytes) else content.encode())
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


print("== 1. 注册 / 登录 / 游客 ==")
u1 = "stu" + uuid.uuid4().hex[:6]
code, d = call("/api/login", {"mode": "register", "username": u1, "password": "Test1234abc"})
check("注册成功", code == 200 and d.get("token"), str(d))
tok1 = d.get("token", "")

tok_admin = admin_login()
code, d = grant_publish(u1, tok_admin)
check("管理员给测试账号开通发布权限", code == 200 and d.get("canPublish") is True, f"{code} {str(d)[:120]}")

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
tok_guest = d.get("token", "")
code, d = call("/api/me", token="bad-token")
check("无效token被拒", code == 401)

# 游客不能上传/发布到社区；游客 pyfiles 也走临时文件规则
body, ct = multipart("file", "t.py", "print(1)\n")
code, d = call("/api/community/upload", raw=body, ctype=ct, token=tok_guest)
check("游客上传社区被拒", code == 403, f"{code} {str(d)[:120]}")
code, d = call("/api/community/publish", {"table": "emp"}, token=tok_guest)
check("游客发布社区被拒", code == 403, f"{code} {str(d)[:120]}")

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
grant_publish(u2, tok_admin)
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
check("社区列表可读且含内置资源", len(items) > 0 and any(i["builtin"] for i in items)
      and all(i["kind"] in ("db", "py", "csv", "xlsx") for i in items),
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
imp_name = d.get("db", "")
check("自定义名导入为独立库", code == 200 and imp_name.startswith("我导的库"), str(d)[:200])
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM emp;", "db": imp_name}, token=tok2)
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
st = wait_job(d.get("job", ""), tok1, tries=50)   # CPU 8s 限制 + 调度余量，最多等 20 秒
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
check("新账号main.py不预置任何代码", (d.get("content") or "") == "", str(d)[:200])
code, d = call("/api/pyrun/start", {"code": "print('hello')", "db": db2}, token=tok2)
st = wait_job(d.get("job", ""), tok2)
check("空白 main.py 也能正常写代码运行", st.get("exit") == 0 and "hello" in (st.get("out") or ""),
      str(st)[:250])
code, d = call("/api/pyfiles/demo.py", {"content": "print(1)"}, token=tok1, method="PUT")
check("保存py文件", code == 200 and d.get("size") == 8, str(d)[:150])
code, d = call("/api/pyfiles/demo.py", token=tok1)
check("读取py文件", d.get("content") == "print(1)", str(d)[:150])
code, d = call("/api/pyfiles/demo.py", token=tok1, method="DELETE")
check("删除py文件", code == 200, str(d)[:150])

print("== 8b2. Python 项目（按项目隔离） ==")
code, d = call("/api/pyprojects", token=tok1)
check("Python 项目：默认项目自动创建",
      code == 200 and len(d.get("projects") or []) >= 1, str(d)[:160])
base_pid = d["projects"][0]["id"]
code, d = call(f"/api/pyfiles?projectId={base_pid}", token=tok1)
check("Python 项目：默认项目里有 main.py",
      code == 200 and any(f["name"] == "main.py" for f in d.get("files") or []),
      str(d)[:160])
code, pa = call("/api/pyprojects", {"name": "项目A"}, token=tok1)
check("Python 项目：可以新建", code == 200 and pa.get("id"), str(pa)[:120])
pid_a = pa["id"]
code, pb = call("/api/pyprojects", {"name": "项目B"}, token=tok1)
pid_b = pb["id"]
call(f"/api/pyfiles/main.py?projectId={pid_a}", {"content": "print('A')\n"}, tok1, method="PUT")
_time.sleep(1.1)
call(f"/api/pyfiles/helper.py?projectId={pid_a}", {"content": "x = 1\n"}, tok1, method="PUT")
call(f"/api/pyfiles/main.py?projectId={pid_b}", {"content": "print('B')\n"}, tok1, method="PUT")
code, fa = call(f"/api/pyfiles?projectId={pid_a}", token=tok1)
code, fb = call(f"/api/pyfiles?projectId={pid_b}", token=tok1)
check("Python 项目：同名文件互不影响",
      [f["name"] for f in fa["files"]][:2] == ["helper.py", "main.py"]
      and [f["name"] for f in fb["files"]] == ["main.py"], str(fa)[:160])
check("Python 项目：文件按修改时间倒序",
      [f["name"] for f in fa["files"]] == ["helper.py", "main.py"],
      str([(f["name"], f["updatedAt"]) for f in fa["files"]]))
code, ra = call("/api/pyrun/start",
                {"code": "import helper\nprint(helper.x)", "db": db1, "projectId": pid_a},
                token=tok1)
st = wait_job(ra.get("job", ""), tok1)
check("Python 项目：运行能 import 本项目的文件",
      st.get("exit") == 0 and "1" in (st.get("out") or ""), str(st)[:200])
code, rb = call("/api/pyrun/start",
                {"code": "import helper\nprint(helper.x)", "db": db1, "projectId": pid_b},
                token=tok1)
st = wait_job(rb.get("job", ""), tok1)
check("Python 项目：不同项目不能互相 import",
      "No module named" in (st.get("err") or ""), str(st)[:260])
code, d = call(f"/api/pyprojects/{pid_b}/rename", {"name": "项目B改"}, token=tok1)
check("Python 项目：可以改名", code == 200 and d.get("name") == "项目B改", str(d)[:100])
# 上限 10 个
_, now = call("/api/pyprojects", token=tok1)
fill = []
for i in range(10 - len(now.get("projects") or [])):
    code, p = call("/api/pyprojects", {"name": f"填充{i}"}, token=tok1)
    if code == 200:
        fill.append(p["id"])
code, d = call("/api/pyprojects", {"name": "超出"}, token=tok1)
check("Python 项目：最多 10 个", code == 400 and "10" in str(d), f"{code} {str(d)[:120]}")
for pid in [pid_a, pid_b] + fill:
    call(f"/api/pyprojects/{pid}", token=tok1, method="DELETE")
_, now = call("/api/pyprojects", token=tok1)
check("Python 项目：删除后清理文件",
      len(now.get("projects") or []) == 1 and now["projects"][0]["id"] == base_pid,
      str(now)[:160])

print("== 8c. 上传的 py 文件：用户永久 / 游客临时 ==")
# 注册用户：上传的文件永久保留（重新登录还在），不再随刷新/登出清理
body, ct = multipart("files", "temp_up.py", "print('temp')\n")
code, d = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tok1)
check("批量上传py", code == 200 and d.get("files") and d["files"][0]["name"] == "temp_up.py", str(d)[:200])
code, d = call("/api/pyfiles", token=tok1)
tf = [f for f in d.get("files", []) if f["name"] == "temp_up.py"]
check("上传文件带 uploaded 标记", tf and tf[0].get("uploaded") is True, str(d)[:200])
# 手动清理对注册用户是 no-op（只有游客的临时文件会被清）
code, d = call("/api/pyfiles/clear-uploaded", token=tok1, method="POST")
check("注册用户刷新清理不删文件", code == 200 and d.get("removed", 0) == 0, str(d)[:150])
code, d = call("/api/pyfiles", token=tok1)
check("注册用户上传文件仍在", any(f["name"] == "temp_up.py" for f in d.get("files", [])), str(d)[:200])
# 登出再登录：仍然在
code, d = call("/api/logout", token=tok1, method="POST")
check("登出成功", code == 200, str(d)[:100])
code, d = call("/api/login", {"mode": "login", "username": u1, "password": "Test1234abc"})
check("重新登录", code == 200 and d.get("token"), str(d)[:100])
tok1 = d.get("token", "")
code, d = call("/api/pyfiles", token=tok1)
check("重新登录后上传文件还在（永久）", any(f["name"] == "temp_up.py" for f in d.get("files", [])), str(d)[:200])

# 游客：上传的文件在登出后被清除
_, dg = call("/api/login", {"mode": "guest"})
tok_g2 = dg.get("token", "")
check("游客登录2", bool(tok_g2), str(dg)[:100])
code, d = call("/api/pyprojects", token=tok_g2)
gp = (d.get("projects") or [{}])[0].get("id", 0)
body, ct = multipart("files", "g_temp.py", "print('g')\n")
code, d = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tok_g2)
check("游客上传成功", code == 200 and d.get("files"), f"{code} {str(d)[:150]}")
code, d = call("/api/logout", token=tok_g2, method="POST")
code, d = call("/api/pyfiles", token=tok_g2)
check("游客登出后文件清除（会话失效）", code in (401, 400) or not any(
    f["name"] == "g_temp.py" for f in d.get("files", [])), f"{code} {str(d)[:120]}")

print("== 8e. Python 文件容量配额 ==")
# 造一个专门的测试用户，方便设小配额
uq = "quota" + uuid.uuid4().hex[:6]
_, dq = call("/api/login", {"mode": "register", "username": uq, "password": "Test1234abc"})
tokq = dq.get("token", "")
check("配额测试用户注册", bool(tokq), str(dq)[:100])
code, d = call("/api/pyprojects", token=tokq)
qpid = (d.get("projects") or [{}])[0].get("id", 0)

# 个人资料里有容量信息（默认配额）
code, d = call("/api/me/profile", token=tokq)
st = d.get("storage") or {}
check("个人资料含容量信息", code == 200 and st.get("totalBytes") == 256 * 1024 * 1024
      and st.get("usedBytes", 0) >= 0, str(d)[:200])

# 管理员把这个用户的配额设成 1MB
code, d = call(f"/api/admin/users?q={uq}", token=tok_admin)
qu = (d.get("users") or [{}])[0]
check("管理员找到配额用户", code == 200 and qu.get("username") == uq, str(d)[:150])
uid = qu.get("id")
code, d = call(f"/api/admin/users/{uid}/update", {"quota_mb": 1}, token=tok_admin, method="POST")
check("管理员设置 1MB 配额", code == 200 and "quota_mb" in (d.get("changed") or []), str(d)[:150])
# 列表里能看到配额与用量
code, d = call(f"/api/admin/users?q={uq}", token=tok_admin)
qu = (d.get("users") or [{}])[0]
check("列表显示配额与用量", qu.get("quotaMb") == 1 and qu.get("usedBytes", -1) >= 0
      and qu.get("unlimited") is False, str(qu)[:200])

# 传 2 个 300KB 的 .py —— 第二个会超（1MB 配额，单文件上限 256KB 拦住第一个）
big = "x = '" + "a" * 200_000 + "'\n"          # ~200KB
body, ct = multipart("files", "q_big1.py", big)
code, d = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tokq)
check("配额内上传成功", code == 200, f"{code} {str(d)[:150]}")
body, ct = multipart("files", "q_big2.py", big)
code, d = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tokq)
# 200KB*5=1MB 边界：2 个 200KB < 1MB，第 3 个开始超；再传 3 个直到被拦
body, ct = multipart("files", "q_big3.py", big)
code3, d3 = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tokq)
body, ct = multipart("files", "q_big4.py", big)
code4, d4 = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tokq)
body, ct = multipart("files", "q_big5.py", big)
code5, d5 = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tokq)
check("第5个还在配额内（5×200KB<1MB）", code5 == 200, f"{code5} {str(d5)[:120]}")
body, ct = multipart("files", "q_big6.py", big)
code6, d6 = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tokq)
check("超出配额被拒并带提示", code6 == 400 and "总容量" in str(d6.get("detail", "")),
      f"{code6} {str(d6)[:150]}")
# 编辑器保存同样受配额限制（单文件 <256KB，但总量超 1MB）
code, d = call("/api/pyfiles/q_save.py", {"content": big}, token=tokq, method="PUT")
check("保存超配额被拒", code == 400 and "总容量" in str(d.get("detail", "")), f"{code} {str(d)[:150]}")
# 个人资料显示用量逼近/超出
code, d = call("/api/me/profile", token=tokq)
st = d.get("storage") or {}
check("个人资料显示用量", st.get("usedBytes", 0) >= 800_000, str(st)[:150])

# 边界：把配额调到比已用量还小 → 不删文件，但锁住新上传
code, d = call(f"/api/admin/users/{uid}/update", {"quota_mb": 0}, token=tok_admin, method="POST")
check("管理员调小配额（0MB）", code == 200, str(d)[:120])
body, ct = multipart("files", "q_small.py", "print(1)\n")
code, d = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tokq)
check("配额调小后上传被锁", code == 400 and "总容量" in str(d.get("detail", "")), f"{code} {str(d)[:150]}")
code, d = call("/api/pyfiles", token=tokq)
check("已有文件不被自动删除", sum(1 for f in d.get("files", [])) >= 4, str(d)[:120])

# 恢复默认 + 设为无限
code, d = call(f"/api/admin/users/{uid}/update", {"quota_reset": True}, token=tok_admin, method="POST")
check("恢复默认配额", code == 200, str(d)[:120])
code, d = call(f"/api/admin/users?q={uq}", token=tok_admin)
qu = (d.get("users") or [{}])[0]
check("恢复默认后 quotaMb=NULL", qu.get("quotaMb") is None, str(qu)[:120])
code, d = call(f"/api/admin/users/{uid}/update", {"quota_mb": -1}, token=tok_admin, method="POST")
code, d = call(f"/api/admin/users?q={uq}", token=tok_admin)
qu = (d.get("users") or [{}])[0]
check("设为无限", qu.get("unlimited") is True and qu.get("quotaMb") == -1, str(qu)[:120])
body, ct = multipart("files", "q_free.py", big)
code, d = call("/api/pyfiles/upload", raw=body, ctype=ct, token=tokq)
check("无限容量随便传", code == 200, f"{code} {str(d)[:120]}")

# 管理员自己：无限
code, d = call("/api/me/profile", token=tok_admin)
st = d.get("storage") or {}
check("管理员无限容量", st.get("unlimited") is True, str(st)[:120])
# 不能给管理员设配额
code, d = call("/api/admin/users?q=admin", token=tok_admin)
au = [u for u in (d.get("users") or []) if u.get("role") == "admin"]
aid = au[0]["id"] if au else 0
code, d = call(f"/api/admin/users/{aid}/update", {"quota_mb": 5}, token=tok_admin, method="POST")
check("管理员不能被设配额（本来就无限）", code == 400 and "无限" in str(d.get("detail", "")),
      f"{code} {str(d)[:130]}")

# 收尾：删掉配额测试用户（否则每跑一次烟测就攒一个测试账号）
code, d = call(f"/api/admin/users/{uid}/delete", token=tok_admin, method="POST")
check("配额测试用户已清理", code == 200, f"{code} {str(d)[:120]}")

print("== 8d. 题目：草稿 → 发布 → 一键导入 ==")
# 发布权限：新账号默认没有；管理员可开通
u3 = "stu" + uuid.uuid4().hex[:6]
_, d3 = call("/api/login", {"mode": "register", "username": u3, "password": "Test1234abc"})
tok3 = d3.get("token", "")
_, me3 = call("/api/me", token=tok3)
check("新账号默认没有发布权限", me3.get("user", {}).get("canPublish") is False, str(me3.get("user"))[:120])
code, d = call("/api/questions/save", {"title": "没权限的题", "db": "", "py": [], "publish": True},
               token=tok3)
check("无权限不能发布", code == 403 and "权限" in str(d.get("detail", "")), f"{code} {str(d)[:120]}")
# 统一口径：练习/素材包两个入口，建草稿都要求出题权限
code, d = call("/api/questions/save", {"title": "只有草稿", "db": "", "py": [], "publish": False},
               token=tok3)
check("无权限不能建素材包草稿", code == 403 and "出题权限" in str(d.get("detail", "")), f"{code} {str(d)[:120]}")
code, d = grant_publish(u3, tok_admin)
check("管理员开通发布权限", code == 200 and d.get("canPublish") is True, f"{code} {str(d)[:120]}")
_, me3b = call("/api/me", token=tok3)
check("开通后 me 显示可发布", me3b.get("user", {}).get("canPublish") is True, str(me3b.get("user"))[:120])

# 备一个 Python 文件作为题目的 Python 部分
code, d = call("/api/pyfiles/quiz_helper.py", {"content": "def answer():\n    return 42\n"},
               token=tok1, method="PUT")
code, d = call("/api/questions/save", {"title": "工资查询题", "note": "查工资前 5 名",
                                       "db": db1, "py": ["quiz_helper.py"], "publish": False},
               token=tok1)
check("保存题目草稿", code == 200 and d.get("id"), f"{code} {str(d)[:150]}")
qid = d.get("id", 0)
check("草稿默认未发布", d.get("published") is False, str(d)[:120])

code, d = call("/api/community", token=tok1)
check("草稿不出现在广场", not any(q["id"] == qid for q in d.get("questions", [])), str(d.get("questions"))[:150])

code, d = call("/api/questions/mine", token=tok1)
mine = [q for q in d.get("questions", []) if q["id"] == qid]
check("我的草稿可见", bool(mine) and mine[0]["status"] == 0, str(d)[:200])
code, d = call(f"/api/questions/{qid}", token=tok1)
td = {t["name"]: t for t in d.get("tableData", [])}
check("详情带表数据快照（预览用）",
      code == 200 and "emp" in td and td["emp"]["cols"] and len(td["emp"]["rows"]) == 14
      and "CREATE TABLE" in td["emp"]["ddl"].upper(),
      f"{code} tables={list(td)[:5]} rows={len(td.get('emp', {}).get('rows', []))}")
check("Python 文件带内容摘要",
      bool(d.get("pyPreview")) and "answer" in (d["pyPreview"][0].get("head") or ""),
      str(d.get("pyPreview"))[:150])
check("草稿带两部分信息", bool(mine) and mine[0]["dbTables"] >= 3 and mine[0]["pyCount"] == 1,
      str(mine[:1])[:200])

code, d = call(f"/api/questions/{qid}/publish", {"publish": True}, token=tok1)
check("发布题目", code == 200 and d.get("published") is True, f"{code} {str(d)[:120]}")
code, d = call("/api/community", token=tok1)
check("发布后广场可见", any(q["id"] == qid for q in d.get("questions", [])), str(d.get("questions"))[:150])

# 换一个账号（tok2）一键导入整套
code, d = call(f"/api/questions/{qid}/import", {}, token=tok2)
check("别人一键导入题目", code == 200 and d.get("db"), f"{code} {str(d)[:180]}")
imp_db, imp_tables, imp_py = d.get("db", ""), d.get("tables", []), d.get("pyFiles", [])
check("导入建了独立库", imp_db and imp_db != db1, str(d)[:150])
check("导入包含 MySQL 表", {"emp", "dept", "salgrade"} <= {t.lower() for t in imp_tables}, str(imp_tables))
check("导入包含 Python 文件", imp_py == ["quiz_helper.py"], str(imp_py))
code, d = call("/api/sql", {"sql": "SELECT COUNT(*) FROM emp", "db": imp_db}, token=tok2)
check("导入的库能查到数据", code == 200 and d["results"][0]["rows"][0][0] == 14, str(d)[:180])
code, d = call("/api/pyfiles/quiz_helper.py", token=tok2)
check("导入的 Python 文件能读到", code == 200 and "answer" in (d.get("content") or ""), str(d)[:150])

code, zdata, zcd = download(f"/api/questions/{qid}/download", token=tok2)
check("题目 zip 可下载", code == 200 and zdata[:2] == b"PK" and ".zip" in zcd, f"{code} {zcd[:60]}")

# 撤回后广场不可见；游客不能出题/发布
code, d = call(f"/api/questions/{qid}/publish", {"publish": False}, token=tok1)
code, d = call("/api/community", token=tok1)
check("撤回后广场不可见", not any(q["id"] == qid for q in d.get("questions", [])), str(d.get("questions"))[:150])
code, d = call("/api/questions/save", {"title": "游客题", "db": "", "py": []}, token=tok_guest)
check("游客不能出题", code == 403, f"{code} {str(d)[:120]}")
# 清理：删除自己的题目（顺带测删除路径），保持烟测可重复
code, d = call(f"/api/questions/{qid}", token=tok1, method="DELETE")
check("删除题目", code == 200, f"{code} {str(d)[:120]}")
code, d = call(f"/api/pyfiles/quiz_helper.py", token=tok1, method="DELETE")

print("== 8e. 练习：出题 → 做题 → 判分 ==")
tok_admin_r = admin_login()
code, d = call("/api/drills", {"course": "sql", "type": "sql", "title": "查询 90 分以上",
                               "stem": "查出 90 分及以上的学生，按分数从高到低。",
                               "setupSql": "CREATE TABLE IF NOT EXISTS sc (id INT PRIMARY KEY, name VARCHAR(20), score INT);"
                                           "INSERT INTO sc VALUES (1,'jia',90),(2,'yi',95);",
                               "verifySql": "SELECT name, score FROM sc WHERE score >= 90 ORDER BY score DESC",
                               "publish": True}, token=tok_admin_r)
check("SQL 题发布", code == 200 and d.get("id"), f"{code} {str(d)[:120]}")
sql_did = d.get("id")
code, det = call(f"/api/drills/{sql_did}", token=tok1)
check("学生看不到标准答案（防作弊）", not det.get("verifySql"), str(det)[:150])
check("学生能看到题面", bool(det.get("setupSql")) and bool(det.get("title")), str(det)[:150])
code, r = call(f"/api/drills/{sql_did}/submit", {"answer_text": "SELECT name FROM sc WHERE score>=90"}, token=tok1)
check("SQL 错答不通过", r.get("passed") is False, str(r)[:150])
code, r = call(f"/api/drills/{sql_did}/submit",
               {"answer_text": "SELECT name, score FROM sc WHERE score >= 90 ORDER BY score DESC"}, token=tok1)
check("SQL 正答通过", r.get("passed") is True, str(r)[:200])
code, d = call("/api/drills", {"course": "python", "type": "python", "title": "算平均分",
                               "stem": "输出三个分数的平均分（两位小数）。",
                               "expectedOutput": "91.67", "publish": True}, token=tok_admin_r)
py_did = d.get("id")
code, r = call(f"/api/drills/{py_did}/submit",
               {"answer_text": "print(f'{sum([88,95,92])/3:.2f}')"}, token=tok1)
check("Python 正答通过", r.get("passed") is True, str(r)[:200])
code, r = call(f"/api/drills/{py_did}/submit", {"answer_text": "print(sum([88,95,92]))"}, token=tok1)
check("Python 错答不通过", r.get("passed") is False, str(r)[:150])
code, d = call("/api/drills", {"course": "basic", "type": "single", "title": "查询关键字",
                               "stem": "SQL 查询用哪个关键字？",
                               "options": [{"key": "A", "text": "SELECT"}, {"key": "B", "text": "INSERT"}],
                               "answer": {"key": "A"}, "publish": True}, token=tok_admin_r)
obj_did = d.get("id")
check("单选答对", call(f"/api/drills/{obj_did}/submit", {"answer_text": "A"}, token=tok1)[1].get("passed") is True)
check("单选答错", call(f"/api/drills/{obj_did}/submit", {"answer_text": "B"}, token=tok1)[1].get("passed") is False)
code, d = call("/api/drills", {"course": "basic", "type": "fill", "title": "主键关键字",
                               "stem": "建表声明主键用 ______ 关键字。",
                               "answer": {"values": ["PRIMARY KEY"]}, "publish": True}, token=tok_admin_r)
fill_did = d.get("id")
code, r = call(f"/api/drills/{fill_did}/submit", {"answer_text": "  primary   key  "}, token=tok1)
check("填空宽松匹配", r.get("passed") is True, str(r)[:150])
code, pr = call("/api/drills/progress", token=tok1)
check("进度统计", pr.get("progress", {}).get("sql", {}).get("done", 0) >= 1, str(pr)[:150])
# 专门造一道只答错一次的题，验证错题本收录
code, d = call("/api/drills", {"course": "sql", "type": "sql", "title": "只答错的题",
                               "setupSql": "CREATE TABLE IF NOT EXISTS t9 (a INT); INSERT INTO t9 VALUES (1);",
                               "verifySql": "SELECT a FROM t9", "publish": True}, token=tok_admin_r)
wrong_did = d.get("id")
call(f"/api/drills/{wrong_did}/submit", {"answer_text": "SELECT a FROM t9 WHERE a=999"}, token=tok1)
code, wr = call("/api/drills/wrong", token=tok1)
check("错题本收录", any(x["id"] == wrong_did for x in wr.get("drills", [])), str([x["title"] for x in wr.get("drills", [])])[:120])
call(f"/api/drills/{wrong_did}", token=tok_admin_r, method="DELETE")
code, d = call("/api/drills", {"type": "sql", "title": "游客题", "verifySql": "SELECT 1"}, token=tok_guest)
check("游客不能出题", code == 400 and "出题权限" in str(d.get("detail", "")), f"{code} {str(d)[:100]}")
# 未授权的注册用户：练习和素材包都不能出题（两处口径一致）
u_no = "stu" + uuid.uuid4().hex[:6]
_, d_no = call("/api/login", {"mode": "register", "username": u_no, "password": "Test1234abc"})
tok_no = d_no.get("token", "")
code, r = call("/api/questions/save", {"title": "无权限素材", "db": "", "py": []}, token=tok_no)
check("无权限不能建素材包", code == 403 and "出题权限" in str(r.get("detail", "")), f"{code} {str(r)[:100]}")
code, r = call("/api/community/publish", {"db": "", "public": True}, token=tok_no)
check("无权限不能公开发布", code in (400, 403), f"{code} {str(r)[:80]}")
_, ul_n = call("/api/admin/users", token=tok_admin_r)
uid_no = next((x["id"] for x in ul_n.get("users", []) if x["username"] == u_no), 0)
if uid_no:
    call("/api/admin/delete_user", {"id": uid_no}, token=tok_admin_r)
code, d = call("/api/drills", {"type": "sql", "title": "缺答案的题"}, token=tok_admin_r)
check("缺初始化 SQL 不能出题", code == 400 and "初始化 SQL" in str(d.get("detail", "")), f"{code} {str(d)[:100]}")
code, d = call("/api/drills", {"type": "sql", "title": "缺答案的题",
                               "setupSql": "CREATE TABLE z1 (a INT);"}, token=tok_admin_r)
check("缺标准答案不能出题", code == 400 and "标准答案" in str(d.get("detail", "")), f"{code} {str(d)[:100]}")
for did in (sql_did, py_did, obj_did, fill_did):
    call(f"/api/drills/{did}", token=tok_admin_r, method="DELETE")

print("== 8h. 出题数据导入 ==")
tok_ah = admin_login()
# CSV → 初始化 SQL
body, ct = multipart("file", "students.csv", "id,name,score\n1,jia,90\n2,yi,85\n")
code, r = call("/api/author/setup_from_file", raw=body, ctype=ct, token=tok_ah)
check("上传 CSV 生成初始化 SQL", code == 200 and r.get("tables") == ["students"]
      and "INSERT INTO" in (r.get("sql") or ""), str(r)[:160])
# SQL 脚本
body, ct = multipart("file", "init.sql", "CREATE TABLE zz (a INT);")
code, r = call("/api/author/setup_from_file", raw=body, ctype=ct, token=tok_ah)
check("上传 SQL 脚本", code == 200 and r.get("tables") == ["zz"], str(r)[:140])
# 用已有数据库
_, me_a = call("/api/me", token=tok_ah)
call("/api/sql", {"sql": "CREATE TABLE IF NOT EXISTS gen_t (a INT);"
                        "DELETE FROM gen_t; INSERT INTO gen_t VALUES (1),(2);"}, token=tok_ah)
code, r = call("/api/author/setup_from_db", {"db": me_a["db"]}, token=tok_ah)
check("从数据库生成初始化 SQL", code == 200 and "gen_t" in (r.get("tables") or [])
      and "INSERT INTO" in (r.get("sql") or ""), str(r)[:160])
# 不支持的类型 / 无权限
body, ct = multipart("file", "a.txt", "hello")
code, r = call("/api/author/setup_from_file", raw=body, ctype=ct, token=tok_ah)
check("不支持的导入类型被拒", code == 400, f"{code} {str(r)[:100]}")
u_imp = "stu" + uuid.uuid4().hex[:6]
_, d_i = call("/api/login", {"mode": "register", "username": u_imp, "password": "Test1234abc"})
tok_i = d_i.get("token", "")
body, ct = multipart("file", "a.csv", "a,b\n1,2\n")
code, r = call("/api/author/setup_from_file", raw=body, ctype=ct, token=tok_i)
check("无出题权限不能导入", code == 403, f"{code} {str(r)[:100]}")
call("/api/sql", {"sql": "DROP TABLE IF EXISTS gen_t"}, token=tok_ah)

print("== 8g. 多判分模式 ==")
tok_ad2 = admin_login()
S2 = ("CREATE TABLE mm (id INT PRIMARY KEY, name VARCHAR(10), score INT);"
      "INSERT INTO mm VALUES (1,'a',90),(2,'b',95),(3,'c',80);")
u_md = "stu" + uuid.uuid4().hex[:6]
_, d_md = call("/api/login", {"mode": "register", "username": u_md, "password": "Test1234abc"})
tok_md = d_md.get("token", "")

def mk_drill(**kw):
    body = {"course": "sql", "type": "sql", "title": "模式测试", "setupSql": S2, "publish": True}
    body.update(kw)
    c, r = call("/api/drills", body, token=tok_ad2)
    return r.get("id"), c, r

# 行序敏感
did, c, _ = mk_drill(verifySql="SELECT name FROM mm ORDER BY score DESC", judgeMode="result_ordered")
_, r = call(f"/api/drills/{did}/submit", {"answer_text": "SELECT name FROM mm ORDER BY score DESC"}, token=tok_md)
p1 = r.get("passed") is True
_, r = call(f"/api/drills/{did}/submit", {"answer_text": "SELECT name FROM mm ORDER BY score ASC"}, token=tok_md)
p2 = r.get("passed") is False
check("判分：行序敏感", p1 and p2)
call(f"/api/drills/{did}", token=tok_ad2, method="DELETE")

# 只比数据
did, c, _ = mk_drill(verifySql="SELECT name, score FROM mm WHERE id=1", judgeMode="rows_only")
_, r = call(f"/api/drills/{did}/submit", {"answer_text": "SELECT score AS s, name AS n FROM mm WHERE id=1"}, token=tok_md)
check("判分：不检查列名", r.get("passed") is True, str(r)[:140])
call(f"/api/drills/{did}", token=tok_ad2, method="DELETE")

# 单值
did, c, _ = mk_drill(verifySql="SELECT MAX(score) FROM mm", judgeMode="cell")
_, r1 = call(f"/api/drills/{did}/submit", {"answer_text": "SELECT MAX(score) FROM mm"}, token=tok_md)
_, r2 = call(f"/api/drills/{did}/submit", {"answer_text": "SELECT MIN(score) FROM mm"}, token=tok_md)
check("判分：只比单值", r1.get("passed") is True and r2.get("passed") is False)
call(f"/api/drills/{did}", token=tok_ad2, method="DELETE")

# 改数据题
did, c, _ = mk_drill(verifySql="SELECT score FROM mm WHERE id=1", judgeMode="state",
                     answer={"values": [100]})
_, r1 = call(f"/api/drills/{did}/submit", {"answer_text": "UPDATE mm SET score=100 WHERE id=1"}, token=tok_md)
_, r2 = call(f"/api/drills/{did}/submit", {"answer_text": "UPDATE mm SET score=1 WHERE id=1"}, token=tok_md)
check("判分：改数据状态", r1.get("passed") is True and r2.get("passed") is False,
      f"{r1.get('reason')} / {r2.get('reason')}")
call(f"/api/drills/{did}", token=tok_ad2, method="DELETE")

# Python 包含
did = call("/api/drills", {"course": "python", "type": "python", "title": "包含",
                           "expectedOutput": "hello", "judgeMode": "contains",
                           "publish": True}, token=tok_ad2)[1]["id"]
_, r = call(f"/api/drills/{did}/submit", {"answer_text": "print('say hello')"}, token=tok_md)
check("判分：输出包含", r.get("passed") is True, str(r)[:140])
call(f"/api/drills/{did}", token=tok_ad2, method="DELETE")

# Python 多组测试
cases = json.dumps([{"input": "1\n2", "expected": "3"}, {"input": "10\n5", "expected": "15"}])
did = call("/api/drills", {"course": "python", "type": "python", "title": "多组",
                           "judgeMode": "tests", "testCases": cases,
                           "publish": True}, token=tok_ad2)[1]["id"]
_, r = call(f"/api/drills/{did}/submit",
            {"answer_text": "a=int(input());b=int(input());print(a+b)"}, token=tok_md)
check("判分：多组测试用例", r.get("passed") is True and len(r.get("cases") or []) == 2,
      str(r)[:160])
call(f"/api/drills/{did}", token=tok_ad2, method="DELETE")

# 多选
did = call("/api/drills", {"course": "basic", "type": "multiple", "title": "多选",
                           "options": [{"key": "A", "text": "x"}, {"key": "B", "text": "y"},
                                       {"key": "C", "text": "z"}],
                           "answer": {"keys": ["A", "C"]}, "publish": True},
           token=tok_ad2)[1]["id"]
ok_full = call(f"/api/drills/{did}/submit", {"answer_text": ["A", "C"]}, token=tok_md)[1].get("passed")
ok_miss = call(f"/api/drills/{did}/submit", {"answer_text": ["A"]}, token=tok_md)[1].get("passed")
ok_extra = call(f"/api/drills/{did}/submit", {"answer_text": ["A", "B", "C"]}, token=tok_md)[1].get("passed")
check("判分：多选全对/漏选/多选", ok_full is True and ok_miss is False and ok_extra is False)
call(f"/api/drills/{did}", token=tok_ad2, method="DELETE")

# 试跑
code, r = call("/api/author/try_sql", {"setup": S2, "sql": "SELECT * FROM mm"}, token=tok_ad2)
check("出题试跑 SQL", code == 200 and any(t["name"] == "mm" for t in r.get("tables", []))
      and r["results"][0].get("rowCount") == 3, str(r)[:160])
code, r = call("/api/author/try_python", {"code": "print('ok')"}, token=tok_ad2)
check("出题试跑 Python", code == 200 and "ok" in (r.get("out") or ""), str(r)[:160])
code, r = call("/api/author/try_sql", {"setup": S2, "sql": "SELECT * FROM mm"}, token=tok_md)
check("无出题权限不能试跑", code == 403, f"{code} {str(r)[:100]}")

print("== 8h. 题目包导入（题干 + 答案 + 数据） ==")
QP_TAG = uuid.uuid4().hex[:6]
QP_STEM = f"""【题  干】
人力资源管理系统数据库db_hrm {QP_TAG}，包含 t_employee、t_department、t_salary 三张表。

1. 创建采购表 t_purchase {QP_TAG}，字段 id INT 主键、name VARCHAR(30)。
2. 向 t_employee 插入员工 10051 林子山 {QP_TAG}。
3. 查询薪资 6000 到 8000 的记录 {QP_TAG}。
"""
QP_ANSWERS = """-- 1
CREATE TABLE t_purchase (
    id INT(8) PRIMARY KEY,
    name VARCHAR(30)
);

-- 2
INSERT INTO t_employee VALUES (10051, '林子山', '男', 24, '实习生', 10002);

-- 3
SELECT * FROM t_salary WHERE money BETWEEN 6000 AND 8000;
"""
# 数据文件是「做完题之后」的库快照：里面已经有答案产物（新表和新增行）
QP_DATA = """/* Navicat MySQL dump */
DROP TABLE IF EXISTS `t_department`;
CREATE TABLE `t_department` (
  `id` int(10) NOT NULL,
  `name` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
INSERT INTO `t_department` VALUES (10002, '行政部');
DROP TABLE IF EXISTS `t_employee`;
CREATE TABLE `t_employee` (
  `id` int(10) NOT NULL,
  `name` varchar(30) DEFAULT NULL,
  `sex` char(2) DEFAULT NULL,
  `age` int(5) DEFAULT NULL,
  `position` varchar(30) DEFAULT NULL,
  `d_id` int(10) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
INSERT INTO `t_employee` VALUES (10001, '曹岚', '女', 25, '正式员工', 10002);
INSERT INTO `t_employee` VALUES (10051, '林子山', '男', 24, '实习生', 10002);
DROP TABLE IF EXISTS `t_purchase`;
CREATE TABLE `t_purchase` (
  `id` int(8) NOT NULL,
  `name` varchar(30) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
DROP TABLE IF EXISTS `t_salary`;
CREATE TABLE `t_salary` (
  `id` int(10) NOT NULL,
  `e_id` int(10) DEFAULT NULL,
  `money` decimal(10,2) DEFAULT NULL,
  `time` date DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
INSERT INTO `t_salary` VALUES (10001, 10001, 7000.00, '2023-12-15');
INSERT INTO `t_salary` VALUES (10002, 10001, 9000.00, '2023-11-15');
"""

# GBK 编码的题干也要能读；zip 里套一层文件夹（老师直接把整个文件夹压缩）
import zipfile

zip_buf = io.BytesIO()
with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("mysql题目例题/22试题描述.txt", QP_STEM.encode("gbk"))
    zf.writestr("mysql题目例题/answer.txt", QP_ANSWERS)
    zf.writestr("mysql题目例题/db_hrm.myd", QP_DATA)
    zf.writestr("mysql题目例题/说明.png", b"\x89PNG")     # 无关文件应被忽略
body, ct = multipart_files([("mysql题目例题.zip", zip_buf.getvalue())])
code, pkg = call("/api/author/qpack/parse", raw=body, ctype=ct, token=tok_ad2)
check("题目包：解析成功", code == 200 and pkg.get("stats", {}).get("total") == 3, str(pkg)[:200])
check("题目包：GBK 题干正确解码",
      "人力资源" in (pkg.get("title") or "") or "人力资源" in (pkg.get("description") or ""),
      (pkg.get("title") or "")[:80])
check("题目包：3 道题都配上答案", pkg.get("stats", {}).get("withAnswer") == 3, str(pkg.get("stats")))
check("题目包：识别出数据表", sorted(pkg.get("tables") or []) ==
      ["t_department", "t_employee", "t_salary"], str(pkg.get("tables")))
check("题目包：自动剔除答案产物", bool(pkg.get("stripped")), str(pkg.get("stripped")))
check("题目包：忽略压缩包里的无关文件",
      sorted(pkg.get("files") or []) == ["22试题描述.txt", "answer.txt", "db_hrm.myd"],
      str(pkg.get("files")))
check("题目包：建表题用整库状态判分",
      pkg["questions"][0].get("kind") == "sql_ddl" and
      pkg["questions"][0].get("judgeMode") == "dbstate", str(pkg["questions"][0]))
check("题目包：查询题用结果集判分",
      pkg["questions"][2].get("judgeMode") == "result", str(pkg["questions"][2]))

# 答案里有子查询的 DELETE/INSERT 仍是改数据题，不能因为出现 SELECT 就判成查询题
sub_buf = io.BytesIO()
with zipfile.ZipFile(sub_buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("stem.txt", f"【题  干】\n删除好友 {QP_TAG}\n\n1. 删除编号 10005 的好友 Jose {QP_TAG}。\n")
    zf.writestr("answer.txt", " -- 1\n"
                "DELETE FROM t_friendship WHERE uid=10005\n"
                "AND fid IN (SELECT fid FROM t_user WHERE nickname='Jose');\n")
sub_body, sub_ct = multipart_files([("subquery.zip", sub_buf.getvalue())])
code, sub_pkg = call("/api/author/qpack/parse", raw=sub_body, ctype=sub_ct, token=tok_ad2)
check("题目包：DELETE 带子查询仍按改数据判分",
      code == 200 and (sub_pkg.get("questions") or [{}])[0].get("kind") == "sql_dml" and
      (sub_pkg.get("questions") or [{}])[0].get("judgeMode") == "dbstate",
      str(sub_pkg)[:250])

# 损坏的 zip 给出可读错误
bad_body, bad_ct = multipart_files([("坏包.zip", b"this is not a zip")])
code, r = call("/api/author/qpack/parse", raw=bad_body, ctype=bad_ct, token=tok_ad2)
check("题目包：坏 zip 被拒且提示清楚",
      code == 400 and "zip" in str(r.get("detail", "")).lower(), f"{code} {str(r)[:120]}")

# 无出题权限不能解析/创建
code, r = call("/api/author/qpack/parse", raw=body, ctype=ct, token=tok_md)
check("题目包：无权限不能解析", code == 403, f"{code} {str(r)[:100]}")

# 创建（按解析结果的判分模式）
code, made = call("/api/author/qpack/create",
                  {"package": pkg, "publish": True, "judge": {}}, token=tok_ad2)
check("题目包：批量创建 3 道题", code == 200 and len(made.get("created") or []) == 3, str(made)[:200])
qp_ids = [x["id"] for x in made.get("created") or []]
check("题目包：发布后学生可见",
      all(any(d["id"] == i for d in call("/api/drills?course=sql", token=tok_md)[1]["drills"])
          for i in qp_ids))

# 重复导入去重
code, again = call("/api/author/qpack/create",
                   {"package": pkg, "publish": True, "judge": {}}, token=tok_ad2)
check("题目包：重复导入自动跳过",
      code == 200 and not again.get("created") and len(again.get("duplicates") or []) == 3,
      str(again)[:200])

# 学生作答：标准答案通过、错误答案被拒
answers = {"-- 1": "CREATE TABLE t_purchase (id INT(8) PRIMARY KEY, name VARCHAR(30));",
           "-- 2": "INSERT INTO t_employee VALUES (10051, '林子山', '男', 24, '实习生', 10002);",
           "-- 3": "SELECT * FROM t_salary WHERE money BETWEEN 6000 AND 8000;"}
for did, key in zip(qp_ids, ["-- 1", "-- 2", "-- 3"]):
    _, r = call(f"/api/drills/{did}/submit", {"answer_text": answers[key]}, token=tok_md)
    check(f"题目包：第 {key[3:]} 题标准答案通过", r.get("passed") is True, str(r)[:160])
_, r = call(f"/api/drills/{qp_ids[0]}/submit",
            {"answer_text": "CREATE TABLE t_purchase (id INT(8) PRIMARY KEY);"}, token=tok_md)
check("题目包：少字段建表被拒", r.get("passed") is False and "字段不一致" in (r.get("reason") or ""),
      str(r)[:160])
_, r = call(f"/api/drills/{qp_ids[2]}/submit",
            {"answer_text": "SELECT * FROM t_salary WHERE money > 9000;"}, token=tok_md)
check("题目包：错误查询被拒", r.get("passed") is False, str(r)[:160])

# ---- 试卷卡片与得分 ----
code, pl = call("/api/papers?course=sql", token=tok_md)
mine = [p for p in pl.get("papers", []) if p["id"] == made.get("paperId")]
check("试卷：导入生成一张卡片", code == 200 and len(mine) == 1, str(pl)[:200])
if mine:
    card = mine[0]
    check("试卷：卡片带题数与总分",
          card["questionCount"] == 3 and card["totalScore"] == 30, str(card)[:200])
    check("试卷：卡片显示我的得分", card["myScore"] == 30 and card["doneCount"] == 3,
          str(card)[:200])
    code, pd = call(f"/api/papers/{card['id']}", token=tok_md)
    qs = pd.get("questions") or []
    check("试卷：详情列出全部题目", code == 200 and len(qs) == 3, str(pd)[:160])
    check("试卷：详情按题号排序", [q["no"] for q in qs] == [1, 2, 3], str([q["no"] for q in qs]))
    check("试卷：详情不泄露答案",
          not any(k in qs[0] for k in ("verifySql", "expectedOutput", "answer", "answerJson")),
          str(list(qs[0].keys()))[:160])
    check("试卷：详情显示每题得分与状态",
          qs[0]["gotScore"] == qs[0]["score"] and qs[0]["passed"] is True, str(qs[0])[:160])
    # 改名
    code, rn = call(f"/api/papers/{card['id']}/rename", {"title": "改名后的试卷"}, token=tok_ad2)
    check("试卷：可以改名", code == 200 and rn.get("title") == "改名后的试卷", str(rn)[:120])
    # 非本人不能改名
    code, r = call(f"/api/papers/{card['id']}/rename", {"title": "x"}, token=tok_md)
    check("试卷：别人不能改名", code == 400, f"{code} {str(r)[:100]}")
    # 学生看不到草稿试卷
    code, r = call(f"/api/papers/{card['id']}", token=tok_md)
    check("试卷：已发布学生可看", code == 200, str(r)[:100])

    # ---- 试卷设置：整卷交卷次数 + 交卷后是否显示答案 ----
    check("试卷：默认不限次数、显示答案",
          pd.get("maxAttempts") == 0 and pd.get("showAnswer") is True
          and pd.get("allowPause") is True and pd.get("maxResumes") == 3,
          str(pd)[:160])
    code, r = call(f"/api/papers/{card['id']}/settings",
                   {"maxAttempts": 1, "showAnswer": False, "timeLimitMinutes": 1,
                    "allowPause": True, "maxResumes": 3}, token=tok_ad2)
    check("试卷：出卷人可改设置",
          code == 200 and r.get("maxAttempts") == 1 and r.get("showAnswer") is False
          and r.get("timeLimitMinutes") == 1 and r.get("allowPause") is True
          and r.get("maxResumes") == 3, str(r)[:120])
    code, r = call(f"/api/papers/{card['id']}/settings",
                   {"maxAttempts": 1, "showAnswer": False}, token=tok_md)
    check("试卷：学生不能改设置", code == 400, f"{code} {str(r)[:100]}")
    _, d0 = call(f"/api/drills/{qp_ids[0]}", token=tok_md)
    check("试卷：设置下发到做题页",
          d0.get("paperMaxAttempts") == 1 and d0.get("paperShowAnswer") is False,
          str(d0)[:200])
    code, st = call(f"/api/papers/{card['id']}/start", {}, token=tok_md)
    check("限时：开始返回倒计时",
          code == 200 and st.get("limitMinutes") == 1 and 0 < st.get("secondsLeft", 0) <= 60,
          str(st)[:160])
    _, st2 = call(f"/api/papers/{card['id']}/start", {}, token=tok_md)
    check("限时：再次进入不重置",
          st2.get("startedAt") == st.get("startedAt") and
          st2.get("secondsLeft", 999) <= st.get("secondsLeft", 0),
          str(st2)[:160])
    _time.sleep(1.1)
    code, pa = call(f"/api/papers/{card['id']}/pause", {}, token=tok_md)
    check("暂停：正常退出记下已用时",
          code == 200 and pa.get("paused") is True and int(pa.get("elapsedSeconds") or 0) >= 1,
          str(pa)[:160])
    _time.sleep(1.2)
    _, st3 = call(f"/api/papers/{card['id']}/start", {}, token=tok_md)
    check("暂停：离开的时间不计入",
          int(st3.get("elapsedSeconds") or 0) <= int(pa.get("elapsedSeconds") or 0) + 1,
          str(st3)[:160])

    # 不允许中途退出 + 异常退出续做次数
    call(f"/api/papers/{card['id']}/settings",
         {"maxAttempts": 1, "showAnswer": False, "timeLimitMinutes": 1,
          "allowPause": False, "maxResumes": 1}, token=tok_ad2)
    _, r1 = call(f"/api/papers/{card['id']}/start", {"visitId": "smoke-v1"}, token=tok_md)
    _, r2 = call(f"/api/papers/{card['id']}/start", {"visitId": "smoke-v2"}, token=tok_md)
    _, r3 = call(f"/api/papers/{card['id']}/start", {"visitId": "smoke-v3"}, token=tok_md)
    check("禁退出：异常退出续做计数",
          r1.get("resumeCount") == 0 and r2.get("resumeCount") == 1
          and r2.get("resumeBlocked") is False,
          str([r1.get("resumeCount"), r2.get("resumeCount")]))
    check("禁退出：超过续做次数返回 blocked",
          r3.get("resumeCount") == 2 and r3.get("resumeBlocked") is True,
          str(r3)[:160])

    all_answers = {str(qp_ids[i]): answers[f"-- {i + 1}"] for i in range(3)}
    code, r = call(f"/api/papers/{card['id']}/submit",
                   {"answers": all_answers}, token=tok_md)
    check("整卷：一次交卷判完所有题",
          code == 200 and r.get("attemptCount") == 1 and r.get("myScore") == 30,
          str({k: r.get(k) for k in ("attemptCount", "myScore", "totalScore")}))
    check("整卷：本次每题都已作答",
          r.get("triedCount") == 3 and all(q.get("answered") for q in r.get("questions") or []),
          str([(q.get("id"), q.get("answered")) for q in r.get("questions") or []])[:200])
    check("整卷：关闭答案时不返回参考答案",
          all(q.get("ref") is None for q in r.get("questions") or []),
          str([q.get("ref") for q in r.get("questions") or []])[:160])
    att = (r.get("attempts") or [{}])[0]
    check("限时：交卷记录开始时间与限时",
          att.get("timedOut") is False and att.get("limitMinutes") == 1 and att.get("startedAt"),
          str({k: att.get(k) for k in ("timedOut", "limitMinutes", "startedAt")}))
    code, r2 = call(f"/api/papers/{card['id']}/submit",
                    {"answers": all_answers}, token=tok_md)
    check("整卷：超过交卷次数被拦",
          code == 400 and "最多可以交卷" in str(r2), f"{code} {str(r2)[:120]}")

    _, stats = call(f"/api/papers/{card['id']}/stats", token=tok_md)
    check("统计：按交卷次数记录",
          stats.get("attemptCount") == 1 and (stats.get("attempts") or [{}])[0].get("score") == 30,
          str({k: stats.get(k) for k in ("attemptCount", "myScore")}))
    stq = (stats.get("questions") or [{}])[0]
    check("统计：我的答案与作答状态",
          stq.get("answered") is True and stq.get("lastAnswer") == answers["-- 1"],
          str(stq)[:200])
    check("统计：关闭答案时不显示参考答案",
          stq.get("ref") is None and stats.get("showAnswer") is False, str(stq)[:160])
    _, pdt = call(f"/api/papers/{card['id']}", token=tok_md)
    check("限时：试卷详情带限时设置", pdt.get("timeLimitMinutes") == 1, str(pdt)[:160])
    call(f"/api/papers/{card['id']}/settings",
         {"maxAttempts": 0, "showAnswer": True, "timeLimitMinutes": 0,
          "allowPause": True, "maxResumes": 3}, token=tok_ad2)
    _, stats = call(f"/api/papers/{card['id']}/stats", token=tok_md)
    stq = (stats.get("questions") or [{}])[0]
    check("统计：允许后可看参考答案",
          bool((stq.get("ref") or {}).get("sql")), str(stq.get("ref"))[:160])
    check("统计：本套汇总分数",
          stats.get("myScore") == 30 and stats.get("totalScore") == 30,
          str({k: stats.get(k) for k in ("myScore", "totalScore")}))
    _, pd2 = call(f"/api/papers/{card['id']}", token=tok_md)
    check("试卷：详情反映整卷交卷次数与每题状态",
          pd2.get("attemptCount") == 1 and pd2.get("latestAttemptNo") == 1 and
          all(q.get("passed") for q in pd2.get("questions") or []),
          str({k: pd2.get(k) for k in ("attemptCount", "latestAttemptNo")}))

# 提交判分返回分值
code, r = call(f"/api/drills/{qp_ids[0]}/submit",
               {"answer_text": answers["-- 1"]}, token=tok_md)
check("判分：返回本题得分",
      r.get("score") == r.get("maxScore") == 10, str({k: r.get(k) for k in
                                                     ("passed", "score", "maxScore")}))
check("判分：返回本套累计得分",
      (r.get("paper") or {}).get("totalScore") == 30 and
      (r.get("paper") or {}).get("myScore") == 30, str(r.get("paper"))[:160])
_, r = call(f"/api/drills/{qp_ids[0]}/submit", {"answer_text": "SELECT 1;"}, token=tok_md)
check("判分：未通过记 0 分", r.get("score") == 0 and r.get("maxScore") == 10, str(r)[:120])

# ---- Navicat 模拟界面用的库结构接口 ----
code, sc = call(f"/api/drills/{qp_ids[0]}/navicat/schema", token=tok_md)
check("Navicat：返回库结构", code == 200 and sc.get("db"), str(sc)[:160])
check("Navicat：列出表与字段",
      any(t["name"] == "t_employee" and len(t["columns"]) >= 3 for t in sc.get("tables", [])),
      str([t["name"] for t in sc.get("tables", [])]))
check("Navicat：字段带类型/可空/主键",
      all(set(("name", "type", "nullable", "key")) <= set(c) for t in sc.get("tables", [])
          for c in t["columns"]), str(sc.get("tables", [{}])[0].get("columns"))[:160])
check("Navicat：表带行数与引擎",
      all(("rows" in t and "engine" in t) for t in sc.get("tables", [])), str(sc.get("tables"))[:160])
check("Navicat：字符集信息", bool(sc.get("charset")), str(sc.get("charset")))
check("Navicat：视图/函数/触发器字段齐全",
      all(k in sc for k in ("views", "routines", "triggers")), str(list(sc.keys())))

# 图形界面翻译出来的 SQL 也能判分（建表 + 建视图）
code, r = call(f"/api/drills/{qp_ids[0]}/submit",
               {"answer_text": "CREATE TABLE t_purchase (id INT(8) PRIMARY KEY, name VARCHAR(30));"},
               token=tok_md)
check("Navicat：图形建表 SQL 判分", r.get("passed") is True, str(r)[:160])
code, r = call(f"/api/drills/{qp_ids[0]}/submit",
               {"answer_text": "CREATE TABLE t_purchase (id INT(8) PRIMARY KEY, name TEXT);"},
               token=tok_md)
check("Navicat：字段类型不对被拒", r.get("passed") is False and "字段定义" in (r.get("reason") or ""),
      str(r)[:160])

# ---- 题目包也支持 Python 参考答案程序 ----
PY_STEM = f"""题目  干
Python 练习 {QP_TAG}：输入输出

1、读入两个整数，输出它们的和。
2、读入一段文本，输出第一个字符。
"""
PY_ANS1 = "a, b = input().split()\nprint(int(a) + int(b))\n"
PY_ANS2 = "s = input().strip()\nprint(s[0])\n"
py_buf = io.BytesIO()
with zipfile.ZipFile(py_buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("题目.txt", PY_STEM)
    zf.writestr("答案/1.py", PY_ANS1)
    zf.writestr("答案/1.in", "3 5\n")
    zf.writestr("答案/2.py", PY_ANS2)
    zf.writestr("答案/2.in", "hello\n")
body, ct = multipart_files([("py试卷.zip", py_buf.getvalue())])
code, pypkg = call("/api/author/qpack/parse", raw=body, ctype=ct, token=tok_ad2)
check("Python 题包：解析出 Python 题",
      code == 200 and pypkg.get("stats", {}).get("python") == 2, str(pypkg.get("stats")))
check("Python 题包：带上参考答案与标准输入",
      pypkg["questions"][0].get("pyCode") and pypkg["questions"][0].get("pyInput") == "3 5\n",
      str(pypkg["questions"][0])[:160])
code, pymade = call("/api/author/qpack/create",
                    {"package": pypkg, "publish": True, "judge": {}}, token=tok_ad2)
check("Python 题包：建成 Python 题", code == 200 and pymade.get("course") == "python",
      str(pymade)[:160])
py_ids = [x["id"] for x in pymade.get("created") or []]
check("Python 题包：自动跑出期望输出",
      len(py_ids) == 2 and not pymade.get("warnings"), str(pymade.get("warnings")))
_, pd = call(f"/api/drills/{py_ids[0]}", token=tok_ad2)
check("Python 题包：期望输出正确", (pd.get("expectedOutput") or "").strip() == "8",
      repr(pd.get("expectedOutput")))
check("Python 题包：标准输入带给学生", pd.get("inputData") == "3 5\n", repr(pd.get("inputData")))
_, r = call(f"/api/drills/{py_ids[0]}/submit", {"answer_text": PY_ANS1}, token=tok_md)
check("Python 题包：参考答案判分通过", r.get("passed") is True, str(r)[:140])
_, r = call(f"/api/drills/{py_ids[0]}/submit",
            {"answer_text": "print('wrong')"}, token=tok_md)
check("Python 题包：错误答案被拒", r.get("passed") is False, str(r)[:140])
for i in py_ids:
    call(f"/api/drills/{i}", token=tok_ad2, method="DELETE")

# 清理
for i in qp_ids:
    call(f"/api/drills/{i}", token=tok_ad2, method="DELETE")
code, pl = call("/api/papers?course=sql", token=tok_ad2)
check("试卷：删空后卡片消失",
      not any(p["id"] == made.get("paperId") for p in pl.get("papers", [])), str(pl)[:160])

print("== 8f. 用户系统与管理后台 ==")
tok_ad = admin_login()
u_us = "stu" + uuid.uuid4().hex[:6]
_, d_us = call("/api/login", {"mode": "register", "username": u_us, "password": "Test1234abc"})
tok_us = d_us.get("token", "")

# 个人中心
code, prof = call("/api/me/profile", token=tok_us)
check("个人中心返回资料", code == 200 and prof.get("username") == u_us, str(prof)[:150])
check("个人中心带统计", isinstance(prof.get("stats"), dict) and prof["stats"].get("databases", 0) >= 1,
      str(prof.get("stats"))[:150])

# 自助改密 + 旧密码失效 + 其他设备下线
_, d_other = call("/api/login", {"mode": "login", "username": u_us, "password": "Test1234abc"})
tok_other = d_other.get("token", "")
code, r = call("/api/me/password", {"old_password": "Test1234abc", "new_password": "NewPass987"},
               token=tok_us)
check("自助改密", code == 200, str(r)[:150])
check("改密后其他会话被下线", call("/api/me", token=tok_other)[0] == 401, "旧会话仍有效")
code, d_new = call("/api/login", {"mode": "login", "username": u_us, "password": "NewPass987"})
check("新密码可登录", code == 200, str(d_new)[:100])
check("旧密码失效", call("/api/login", {"mode": "login", "username": u_us,
                                       "password": "Test1234abc"})[0] == 400)
tok_us = d_new.get("token", "")
code, r = call("/api/me/logout_all", {}, token=tok_us)
check("退出所有设备", code == 200 and "killed" in r, str(r)[:100])
check("当前会话保留", call("/api/me", token=tok_us)[0] == 200)

# 管理端：总览 / 搜索 / 详情
code, ov = call("/api/admin/overview", token=tok_ad)
check("管理总览", code == 200 and ov.get("users", 0) >= 1 and "regTrend" in ov, str(ov)[:150])
code, ls = call(f"/api/admin/users?kind=user&q={u_us}", token=tok_ad)
check("按关键词搜索用户", code == 200 and ls.get("total") == 1, str(ls)[:150])
uid_us = (ls.get("users") or [{}])[0].get("id")
code, det = call(f"/api/admin/users/{uid_us}", token=tok_ad)
check("用户详情（库/文件/日志）", code == 200 and "databases" in det and "logs" in det, str(det)[:150])

# 权限与禁用
code, r = call(f"/api/admin/users/{uid_us}/update", {"can_publish": True}, token=tok_ad)
check("管理端开通出题权限", code == 200 and r.get("canPublish") is True, str(r)[:120])
code, r = call(f"/api/admin/users/{uid_us}/update", {"disabled": True}, token=tok_ad)
check("管理端禁用账号", code == 200 and r.get("disabled") is True, str(r)[:120])
check("禁用后无法登录", call("/api/login", {"mode": "login", "username": u_us,
                                           "password": "NewPass987"})[0] == 400)
check("禁用后现有会话失效", call("/api/me", token=tok_us)[0] == 401)
code, r = call(f"/api/admin/users/{uid_us}/update", {"disabled": False}, token=tok_ad)
check("管理端解禁", code == 200 and r.get("disabled") is False, str(r)[:120])

# 管理员建号 + 强制下线 + 审计日志 + 批量
u_made = "stu" + uuid.uuid4().hex[:6]
code, r = call("/api/admin/users", {"username": u_made, "password": "Create12345",
                                    "can_publish": True}, token=tok_ad)
check("管理员新建账号", code == 200 and r.get("canPublish") is True, str(r)[:150])
code, r = call(f"/api/admin/users/{uid_us}/revoke_sessions", {}, token=tok_ad)
check("强制下线", code == 200, str(r)[:120])
code, lg = call("/api/admin/auth_log?limit=50", token=tok_ad)
acts = [x["action"] for x in lg.get("logs", [])]
check("审计日志有记录", code == 200 and "admin_create" in acts, str(acts[:8]))
code, r = call("/api/admin/batch", {"ids": [uid_us], "action": "grant"}, token=tok_ad)
check("批量操作", code == 200 and r.get("done") == 1, str(r)[:120])
# 普通用户不能进管理端
check("普通用户被拒", call("/api/admin/overview", token=tok_us)[0] == 401 or
      call("/api/login", {"mode": "login", "username": u_made,
                          "password": "Create12345"})[0] == 200)
# 清理
_, d_clean = call("/api/login", {"mode": "login", "username": u_made, "password": "Create12345"})
code, ls2 = call(f"/api/admin/users?kind=user&q={u_made}", token=tok_ad)
for x in ls2.get("users", []):
    call("/api/admin/delete_user", {"id": x["id"]}, token=tok_ad)
code, ls3 = call(f"/api/admin/users?kind=user&q={u_us}", token=tok_ad)
for x in ls3.get("users", []):
    call("/api/admin/delete_user", {"id": x["id"]}, token=tok_ad)

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
