"""FastAPI 入口：所有 HTTP API + 静态页面托管。"""
import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import pymysql

from . import community, drills, importer, sessions, sqlrun, users
from .config import C
from .community import CommunityError
from .drills import DrillError
from .users import UserError
from .importer import ImportError_ as ImportFormatError
from .sessions import AuthError
from .sqlrun import SqlError

STATIC_DIR = Path(__file__).parent / "static"


# ---------- 启动 / 后台清理 ----------

async def _cleanup_loop():
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(sessions.cleanup_pass)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(sessions.wait_for_db)
    await asyncio.to_thread(sessions._init_meta)
    await asyncio.to_thread(sessions.ensure_admin)
    await asyncio.to_thread(community.ensure_builtin_seed)
    await asyncio.to_thread(drills.init)
    await asyncio.to_thread(users.init)
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="SQL·Py 课堂实验室", lifespan=lifespan)


# ---------- 简单 IP 限流 ----------

_buckets: dict[str, deque] = defaultdict(lambda: deque(maxlen=300))


@app.middleware("http")
async def no_cache_frontend(request: Request, call_next):
    """html/css/js 不缓存（课堂场景改代码要立即生效），字体等大文件正常缓存。"""
    response = await call_next(request)
    p = request.url.path
    if p == "/" or p.endswith((".html", ".css", ".js")):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        if C.TRUST_PROXY and request.headers.get("x-forwarded-for"):
            ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "?"
        dq = _buckets[ip]
        now = time.monotonic()
        dq.append(now)
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) > C.RATE_LIMIT:
            return JSONResponse({"detail": "请求太频繁，请稍后再试"}, status_code=429)
    return await call_next(request)


# ---------- 工具 ----------

def client_ip(request: Request) -> str:
    """真实客户端 IP（反代模式下取 X-Forwarded-For 第一段）。"""
    if C.TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def sess(request: Request) -> dict:
    s = sessions.get_session(request.headers.get("x-token", ""))
    if not s:
        raise HTTPException(401, "登录已失效，请重新登录")
    return s


def acct(s: dict) -> dict:
    return s["account"]


class LoginBody(BaseModel):
    mode: str = "login"  # login | register | guest
    username: str = ""
    password: str = ""


class SqlBody(BaseModel):
    sql: str
    db: str = ""


class CodeBody(BaseModel):
    code: str
    db: str = ""
    filename: str = ""


class ShareBody(BaseModel):
    table: str = ""
    db: str = ""
    share_name: str = ""
    public: bool = False


class CreateDbBody(BaseModel):
    name: str


class AdminResetBody(BaseModel):
    username: str
    new_password: str


class AdminDeleteBody(BaseModel):
    id: int


# ---------- 认证 ----------

@app.post("/api/login")
def api_login(b: LoginBody, request: Request):
    ip = client_ip(request)
    try:
        if b.mode == "guest":
            account = sessions.create_guest(ip)
        elif b.mode == "register":
            account = sessions.register(b.username.strip(), b.password, ip)
        else:
            account = sessions.authenticate(b.username.strip(), b.password, ip)
    except AuthError as e:
        raise HTTPException(400, str(e))
    token = sessions.create_session(account["id"])
    return {"token": token,
            "user": {"name": account["display"], "kind": account["kind"],
                     "role": account["role"],
                     "canPublish": account["role"] == "admin" or bool(account.get("can_publish"))}}


@app.post("/api/logout")
def api_logout(request: Request):
    sessions.logout_cleanup(request.headers.get("x-token", ""))
    return {"ok": True}


@app.post("/api/pyfiles/clear-uploaded")
def api_pyfiles_clear_uploaded(request: Request):
    """删除当前账号所有「上传的临时 py 文件」（刷新页面时前端调用）。"""
    a = acct(sess(request))
    n = sessions.pyfiles_delete_uploaded(a["id"])
    return {"removed": n}


@app.get("/api/me")
def api_me(request: Request):
    s = sess(request)
    a = acct(s)
    return {"user": {"name": a["display"], "kind": a["kind"], "role": a["role"],
                     "db": a["db_name"],
                     "canPublish": a["role"] == "admin" or bool(a.get("can_publish"))},
            "db": a["db_name"],
            "databases": sessions.list_dbs(a),
            "tables": sqlrun.list_tables(a["db_name"], a["mysql_user"], a["mysql_pass"])}


class PwBody(BaseModel):
    old_password: str = ""
    new_password: str = ""


@app.get("/api/me/profile")
def api_me_profile(request: Request):
    a = acct(sess(request))
    try:
        return users.profile(a)
    except UserError as e:
        raise HTTPException(400, str(e))


@app.post("/api/me/password")
def api_me_password(b: PwBody, request: Request):
    a = acct(sess(request))
    try:
        return users.change_password(a, b.old_password, b.new_password,
                                     request.headers.get("x-token", ""))
    except UserError as e:
        raise HTTPException(400, str(e))


@app.post("/api/me/logout_all")
def api_me_logout_all(request: Request):
    a = acct(sess(request))
    return users.logout_all(a, request.headers.get("x-token", ""))


# ---------- SQL ----------

@app.get("/api/databases")
def api_databases(request: Request):
    a = acct(sess(request))
    return {"databases": sessions.list_dbs(a), "db": a["db_name"]}


@app.post("/api/databases")
def api_database_create(b: CreateDbBody, request: Request):
    a = acct(sess(request))
    try:
        name = sessions.create_user_db(a, b.name.strip())
    except AuthError as e:
        raise HTTPException(400, str(e))
    return {"name": name, "databases": sessions.list_dbs(a)}


@app.get("/api/databases/{name}/tables")
def api_database_tables(name: str, request: Request):
    a = acct(sess(request))
    if name not in sessions.owned_dbs(a["id"]):
        raise HTTPException(403, "该数据库不在你的名下")
    return {"db": name,
            "tables": sqlrun.list_tables(name, a["mysql_user"], a["mysql_pass"])}


@app.delete("/api/databases/{name}")
def api_database_delete(name: str, request: Request):
    a = acct(sess(request))
    try:
        sessions.drop_user_db(a, name)
    except AuthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "databases": sessions.list_dbs(a)}


@app.get("/api/databases/{name}/export")
def api_database_export(name: str, request: Request):
    from urllib.parse import quote

    from fastapi.responses import Response

    a = acct(sess(request))
    if name not in sessions.owned_dbs(a["id"]):
        raise HTTPException(403, "只能导出自己的数据库")
    data = community.export_database(name, a["mysql_user"], a["mysql_pass"])
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name + '.sql')}"},
    )


@app.get("/api/tables")
def api_tables(request: Request):
    a = acct(sess(request))
    return {"db": a["db_name"],
            "tables": sqlrun.list_tables(a["db_name"], a["mysql_user"], a["mysql_pass"])}


@app.post("/api/sql")
def api_sql(b: SqlBody, request: Request):
    a = acct(sess(request))
    if len(b.sql.encode("utf-8")) > C.SQL_MAX:
        raise HTTPException(400, "SQL 内容超过 64KB 上限")

    owned = sessions.owned_dbs(a["id"])
    target = b.db.strip() or a["db_name"]
    if target not in owned:
        raise HTTPException(403, f"数据库 {target} 不在你的名下")

    def run():
        return sqlrun.run_sql(target, a["mysql_user"], a["mysql_pass"], b.sql,
                              owned_dbs=owned)

    try:
        try:
            result = run()
        except pymysql.MySQLError as e:
            if e.args and e.args[0] == 1049:
                # 该库不存在（例如误删了导入的库）→ 若是默认库则自动重建重试
                if target == a["db_name"]:
                    sessions.ensure_account_ready(a)
                    result = run()
                else:
                    sessions.remove_db_row(a["id"], target)
                    raise HTTPException(400, f"数据库 {target} 已不存在，已从列表移除，刷新后可见")
            else:
                raise
    except SqlError as e:
        raise HTTPException(400, str(e))

    # 学生用 SQL 自己 DROP 了名下的导入库 → 同步清理登记
    for t in sqlrun.drop_db_targets(b.sql):
        if t.lower() != a["db_name"].lower() and t.lower() in [o.lower() for o in owned] \
                and not sessions._db_exists(t):
            sessions.remove_db_row(a["id"], t)
    result["db"] = target
    return result


# ---------- 导入 ----------

def _sanitize_table(stem: str) -> str:
    t = re.sub(r"[^\w\u4e00-\u9fff-]", "_", stem or "", flags=re.UNICODE)[:60].strip("_")
    if not t:
        t = "导入表"
    if t[0].isdigit():
        t = "t" + t
    return t


@app.post("/api/import")
async def api_import(request: Request, file: UploadFile = File(...),
                     table: str = Form(""), header: bool = Form(True),
                     overwrite: bool = Form(False), db: str = Form("")):
    a = acct(sess(request))
    owned = sessions.owned_dbs(a["id"])
    target_db = db.strip() or a["db_name"]
    if target_db not in owned:
        raise HTTPException(403, f"数据库 {target_db} 不在你的名下")
    data = await file.read()
    if len(data) > C.UPLOAD_MAX:
        raise HTTPException(400, "文件超过 5MB 上限")
    name = file.filename or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("csv", "xlsx", "sql"):
        raise HTTPException(400, "仅支持 .csv / .xlsx / .sql 文件")
    target = _sanitize_table(table or name.rsplit(".", 1)[0])
    args = (target_db, a["mysql_user"], a["mysql_pass"], target)

    def run():
        if ext == "csv":
            return {"kind": "table", "result": importer.import_csv(*args, data, header, overwrite,
                                                                   source_name=name)}
        if ext == "xlsx":
            return {"kind": "table", "result": importer.import_xlsx(*args, data, header, overwrite,
                                                                     source_name=name)}
        try:
            return {"kind": "sql", "result": importer.import_sql(*args[:3], data)}
        except pymysql.MySQLError as e:
            if e.args and e.args[0] == 1049:
                if target_db == a["db_name"]:
                    sessions.ensure_account_ready(a)
                    return {"kind": "sql", "result": importer.import_sql(*args[:3], data)}
                sessions.remove_db_row(a["id"], target_db)
                raise HTTPException(400, f"数据库 {target_db} 已不存在，已从列表移除")
            raise

    try:
        out = await asyncio.to_thread(run)
    except ImportFormatError as e:
        raise HTTPException(400, str(e))
    out["db"] = target_db
    out["databases"] = sessions.list_dbs(a)
    out["tables"] = sqlrun.list_tables(target_db, a["mysql_user"], a["mysql_pass"])
    return out


# ---------- 题库 ----------

@app.get("/api/community")
def api_community(request: Request):
    sess(request)
    return {"items": community.list_items(),
            "questions": community.question_list_published()}


@app.post("/api/community/upload")
async def api_community_upload(request: Request, file: UploadFile = File(...),
                               title: str = Form("")):
    a = acct(sess(request))
    if a["kind"] == "guest":
        raise HTTPException(403, "游客不能上传到题库，注册账号后即可分享")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "文件超过 8MB 上限")
    try:
        return community.upload_file(a["display"], file.filename or "", data, title.strip())
    except CommunityError as e:
        raise HTTPException(400, str(e))


@app.post("/api/community/publish")
def api_community_publish(b: ShareBody, request: Request):
    a = acct(sess(request))
    if a["kind"] == "guest":
        raise HTTPException(403, "游客不能发布到题库，注册账号后即可分享")
    if b.public:
        _need_publish_perm(a)   # 私有分享链接不受限，公开发布需要权限
    try:
        if b.db.strip():
            owned = sessions.owned_dbs(a["id"])
            if b.db.strip() not in owned:
                raise CommunityError("只能发布自己名下的数据库")
            return community.publish_database(b.db.strip(), a["mysql_user"], a["mysql_pass"],
                                              a["display"], account_id=a["id"],
                                              share_name=b.share_name.strip() or None,
                                              public=b.public)
        return community.publish_table(a["db_name"], a["mysql_user"], a["mysql_pass"],
                                       b.table.strip(), a["display"], account_id=a["id"])
    except CommunityError as e:
        raise HTTPException(400, str(e))


@app.get("/api/community/by-code/{code}")
def api_community_by_code(code: str, request: Request):
    sess(request)
    try:
        d = community.get_by_code(code)
    except CommunityError as e:
        raise HTTPException(404, str(e))
    return d


class CommunityImportBody(BaseModel):
    id: int
    overwrite: bool = False
    header: bool = True
    table: str = ""
    db: str = ""
    new_db_name: str = ""


@app.post("/api/community/import")
def api_community_import(b: CommunityImportBody, request: Request):
    a = acct(sess(request))
    target_db = b.db.strip() or a["db_name"]
    if target_db not in sessions.owned_dbs(a["id"]):
        raise HTTPException(403, f"数据库 {target_db} 不在你的名下")
    try:
        result = community.import_item(b.id, account=a, target_db=target_db,
                                       overwrite=b.overwrite, table=(b.table or None),
                                       new_db_name=(b.new_db_name.strip() or None))
    except CommunityError as e:
        raise HTTPException(400, str(e))
    except AuthError as e:
        raise HTTPException(400, str(e))
    tables = None
    new_db = result.get("newDb")
    if new_db:
        tables = sqlrun.list_tables(new_db, a["mysql_user"], a["mysql_pass"])
        result["databases"] = sessions.list_dbs(a)
    elif not result.get("script"):
        try:
            tables = sqlrun.list_tables(target_db, a["mysql_user"], a["mysql_pass"])
        except Exception:
            pass
    return {"result": result, "tables": tables, "db": new_db or target_db}


class CommunityOpenBody(BaseModel):
    id: int


@app.get("/api/community/{item_id}/detail")
def api_community_detail(item_id: int, request: Request):
    sess(request)
    try:
        return community.get_detail(item_id)
    except CommunityError as e:
        raise HTTPException(400, str(e))


@app.get("/api/community/{item_id}/preview")
def api_community_preview(item_id: int, request: Request, table: str):
    sess(request)
    try:
        return community.item_table_preview(item_id, table)
    except CommunityError as e:
        raise HTTPException(400, str(e))


@app.post("/api/community/open")
def api_community_open(b: CommunityOpenBody, request: Request):
    a = acct(sess(request))
    try:
        filename, code = community.get_py_code(b.id)
        final = sessions.pyfiles_unique_name(a["id"], filename)
        sessions.pyfiles_save(a["id"], final, code)
    except CommunityError as e:
        raise HTTPException(400, str(e))
    return {"filename": final, "code": code}


# ---------- Python 多文件 ----------

@app.get("/api/pyfiles")
def api_pyfiles(request: Request):
    a = acct(sess(request))
    return {"files": sessions.pyfiles_list(a["id"])}


@app.post("/api/pyfiles/upload")
async def api_pyfiles_upload(request: Request, files: list[UploadFile] = File(...)):
    a = acct(sess(request))
    current = sessions.pyfiles_list(a["id"])
    if len(current) + len(files) > sessions.PYFILE_MAX_COUNT:
        raise HTTPException(400, f"文件数量超过上限（{sessions.PYFILE_MAX_COUNT} 个）")

    uploads = []
    for file in files:
        filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        name = sessions.normalize_pyfile_name(filename)
        if not name or not filename.lower().endswith(".py"):
            raise HTTPException(400, f"只支持有效的 .py 文件：{filename or '未命名文件'}")
        raw = await file.read(C.CODE_MAX + 1)
        if len(raw) > C.CODE_MAX:
            raise HTTPException(400, f"文件 {filename} 超过 256KB 上限")
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(400, f"文件 {filename} 不是 UTF-8 编码")
        uploads.append((name, content))

    saved = []
    existing = {f["name"].casefold() for f in current}
    for name, content in uploads:
        final = sessions.pyfiles_unique_name(a["id"], name, existing)
        # 上传的文件是临时文件：刷新页面或退出登录时自动删除
        sessions.pyfiles_save(a["id"], final, content, uploaded=True)
        existing.add(final.casefold())
        saved.append({"name": final, "size": len(content.encode("utf-8"))})
    return {"files": saved}


@app.get("/api/pyfiles/{name}")
def api_pyfile_get(name: str, request: Request):
    a = acct(sess(request))
    name = sessions.normalize_pyfile_name(name)
    if not name:
        raise HTTPException(400, "文件名不合法")
    f = sessions.pyfiles_get(a["id"], name)
    if f is None:
        raise HTTPException(404, "文件不存在")
    return f


class PyfileSaveBody(BaseModel):
    content: str


@app.put("/api/pyfiles/{name}")
def api_pyfile_save(name: str, b: PyfileSaveBody, request: Request):
    a = acct(sess(request))
    name = sessions.normalize_pyfile_name(name)
    if not name:
        raise HTTPException(400, "文件名不合法")
    if len(b.content.encode("utf-8")) > C.CODE_MAX:
        raise HTTPException(400, "文件超过 256KB 上限")
    if len(sessions.pyfiles_list(a["id"])) >= sessions.PYFILE_MAX_COUNT \
            and not sessions.pyfiles_get(a["id"], name):
        raise HTTPException(400, f"文件数量超过上限（{sessions.PYFILE_MAX_COUNT} 个）")
    sessions.pyfiles_save(a["id"], name, b.content)
    return {"name": name, "size": len(b.content.encode("utf-8"))}


@app.delete("/api/pyfiles/{name}")
def api_pyfile_delete(name: str, request: Request):
    a = acct(sess(request))
    sessions.pyfiles_delete(a["id"], name)
    return {"ok": True}


# ---------- 题目（草稿 → 发布） ----------

class QuestionBody(BaseModel):
    id: int = 0
    title: str = ""
    note: str = ""
    db: str = ""
    py: list[str] = []
    publish: bool = False


@app.get("/api/questions/mine")
def api_questions_mine(request: Request):
    a = acct(sess(request))
    return {"questions": community.question_list_mine(a["id"]),
            "databases": sessions.list_dbs(a)}


def _need_publish_perm(a: dict):
    if a["role"] != "admin" and not a.get("can_publish"):
        raise HTTPException(403, "还没有出题权限（管理员可在「管理」面板按人开通）")


@app.post("/api/questions/save")
def api_questions_save(b: QuestionBody, request: Request):
    a = acct(sess(request))
    if a["kind"] == "guest":
        raise HTTPException(403, "游客不能出题，注册账号后即可把素材分享给同学")
    # 与练习出题同一口径：建草稿 / 发布都要「出题权限」（管理员默认有）
    _need_publish_perm(a)
    try:
        return community.question_save(a, qid=b.id or None, title=b.title, note=b.note,
                                       db_name=b.db, py_names=b.py, publish=b.publish)
    except CommunityError as e:
        raise HTTPException(400, str(e))


@app.get("/api/questions/{qid}")
def api_question_detail(qid: int, request: Request):
    a = acct(sess(request))
    try:
        return community.question_detail(a, qid)
    except CommunityError as e:
        raise HTTPException(400, str(e))


@app.post("/api/questions/{qid}/publish")
def api_question_publish(qid: int, b: QuestionBody, request: Request):
    a = acct(sess(request))
    if a["kind"] == "guest":
        raise HTTPException(403, "游客不能发布题目，注册账号后即可分享")
    if b.publish:
        _need_publish_perm(a)
    try:
        return community.question_publish(a, qid, b.publish)
    except CommunityError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/questions/{qid}")
def api_question_delete(qid: int, request: Request):
    a = acct(sess(request))
    try:
        community.question_delete(a, qid)
    except CommunityError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/questions/{qid}/import")
def api_question_import(qid: int, b: QuestionBody, request: Request):
    a = acct(sess(request))
    try:
        return community.question_import(a, qid, new_db_name=b.db.strip())
    except CommunityError as e:
        raise HTTPException(400, str(e))


@app.get("/api/questions/{qid}/download")
def api_question_download(qid: int, request: Request):
    sess(request)
    from urllib.parse import quote

    from fastapi.responses import Response

    try:
        filename, data = community.question_zip(qid)
    except CommunityError as e:
        raise HTTPException(400, str(e))
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.get("/api/community/{item_id}/download")
def api_community_download(item_id: int, request: Request):
    sess(request)
    from urllib.parse import quote

    from fastapi.responses import Response

    try:
        filename, data = community.get_file(item_id)
    except CommunityError as e:
        raise HTTPException(400, str(e))
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.delete("/api/community/{item_id}")
def api_community_delete(item_id: int, request: Request):
    a = acct(sess(request))
    try:
        community.delete_item(item_id, a["display"])
    except CommunityError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ---------- 表源文件（导入时的原始文件） ----------

@app.get("/api/source/{table}")
def api_source(table: str, request: Request):
    a = acct(sess(request))
    from .db import valid_ident

    if not valid_ident(table):
        raise HTTPException(400, "表名不合法")
    src = importer.get_source(a["db_name"], a["mysql_user"], a["mysql_pass"], table)
    if not src:
        return {"exists": False}
    text = None
    if src["kind"] in ("csv", "sql"):
        data = src["data"]
        for enc in ("utf-8-sig", "gbk"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            try:
                text = data.decode("gb18030")
            except UnicodeDecodeError:
                text = None
    return {"exists": True, "filename": src["filename"], "kind": src["kind"],
            "size": len(src["data"]), "createdAt": src["createdAt"], "text": text}


@app.get("/api/source/{table}/download")
def api_source_download(table: str, request: Request):
    a = acct(sess(request))
    from .db import valid_ident
    from urllib.parse import quote

    from fastapi.responses import Response

    if not valid_ident(table):
        raise HTTPException(400, "表名不合法")
    src = importer.get_source(a["db_name"], a["mysql_user"], a["mysql_pass"], table)
    if not src:
        raise HTTPException(404, "这张表没有源文件（可能是手写建表或题库导入的）")
    return Response(
        content=src["data"],
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(src['filename'])}"},
    )


# ---------- Python 交互式运行（作业转发到 runner） ----------

_pyrun_owner = {}


def _pyrun_forward(method: str, path: str, payload=None):
    req = urllib.request.Request(
        C.RUNNER_URL + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Runner-Token": C.RUNNER_TOKEN},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail", "沙箱执行出错")
        except Exception:
            detail = "沙箱执行出错"
        raise HTTPException(e.code if e.code in (400, 404, 429) else 502, detail)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HTTPException(502, "沙箱服务暂不可用，请稍后再试")


@app.post("/api/pyrun/start")
def api_pyrun_start(b: CodeBody, request: Request):
    a = acct(sess(request))
    if len(b.code.encode("utf-8")) > C.CODE_MAX:
        raise HTTPException(400, "代码超过 256KB 上限")
    target = b.db.strip() or a["db_name"]
    if target not in sessions.owned_dbs(a["id"]):
        raise HTTPException(403, f"数据库 {target} 不在你的名下")
    files = sessions.pyfiles_contents(a["id"])
    if b.filename in files:
        files[b.filename] = b.code
    d = _pyrun_forward("POST", "/start", {
        "code": b.code,
        "files": files,
        "db": {"host": C.DB_HOST, "port": C.DB_PORT,
               "user": a["mysql_user"], "pass": a["mysql_pass"], "name": target},
    })
    _pyrun_owner[d["job"]] = a["id"]
    return d


class PyrunInputBody(BaseModel):
    job: str
    text: str


@app.post("/api/pyrun/input")
def api_pyrun_input(b: PyrunInputBody, request: Request):
    a = acct(sess(request))
    if _pyrun_owner.get(b.job) != a["id"]:
        raise HTTPException(403, "这个运行任务不属于你")
    return _pyrun_forward("POST", f"/job/{b.job}/input", {"text": b.text})


@app.get("/api/pyrun/status/{job_id}")
def api_pyrun_status(job_id: str, request: Request, since_out: int = 0, since_err: int = 0):
    a = acct(sess(request))
    if _pyrun_owner.get(job_id) != a["id"]:
        raise HTTPException(403, "这个运行任务不属于你")
    return _pyrun_forward("GET", f"/job/{job_id}/out?since_out={since_out}&since_err={since_err}")


# ---------- 管理员 ----------

def require_admin(request: Request) -> dict:
    s = sess(request)
    if acct(s).get("role") != "admin":
        raise HTTPException(403, "需要管理员权限")
    return s


@app.get("/api/admin/overview")
def api_admin_overview(request: Request):
    require_admin(request)
    return users.overview()


@app.get("/api/admin/users")
def api_admin_users(request: Request, kind: str = "user", q: str = "",
                    page: int = 1, size: int = 50, only: str = ""):
    require_admin(request)
    d = users.list_users(kind=kind, q=q, page=page, size=size, only=only)
    d["kind"] = kind
    return d


class AdminCreateBody(BaseModel):
    username: str
    password: str
    can_publish: bool = False


class AdminUpdateBody(BaseModel):
    can_publish: bool | None = None
    disabled: bool | None = None
    password: str = ""


class AdminBatchBody(BaseModel):
    ids: list[int] = []
    action: str = ""


@app.get("/api/admin/users/{uid}")
def api_admin_user_detail(uid: int, request: Request):
    require_admin(request)
    try:
        return users.detail(uid)
    except UserError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users")
def api_admin_user_create(b: AdminCreateBody, request: Request):
    s = require_admin(request)
    a = acct(s)
    try:
        return users.create_user(b.username.strip(), b.password, client_ip(request),
                                 b.can_publish, a)
    except UserError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{uid}/update")
def api_admin_user_update(uid: int, b: AdminUpdateBody, request: Request):
    s = require_admin(request)
    a = acct(s)
    fields = {}
    if b.can_publish is not None:
        fields["can_publish"] = b.can_publish
    if b.disabled is not None:
        fields["disabled"] = b.disabled
    if b.password:
        fields["password"] = b.password
    if not fields:
        raise HTTPException(400, "没有要修改的内容")
    try:
        return users.update(uid, fields, a)
    except UserError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{uid}/revoke_sessions")
def api_admin_revoke(uid: int, request: Request):
    s = require_admin(request)
    try:
        return users.revoke_sessions(uid, acct(s))
    except UserError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/batch")
def api_admin_batch(b: AdminBatchBody, request: Request):
    s = require_admin(request)
    try:
        return users.batch(b.ids, b.action, acct(s))
    except UserError as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/auth_log")
def api_admin_auth_log(request: Request, limit: int = 100, only_fail: bool = False):
    require_admin(request)
    return {"logs": users.auth_log(limit, only_fail)}


@app.post("/api/admin/reset_password")
def api_admin_reset(b: AdminResetBody, request: Request):
    require_admin(request)
    try:
        sessions.admin_reset_password(b.username.strip(), b.new_password)
    except AuthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


class AdminPermBody(BaseModel):
    id: int
    allow: bool = True


@app.post("/api/admin/set_publish_permission")
def api_admin_set_perm(b: AdminPermBody, request: Request):
    require_admin(request)
    try:
        return sessions.set_publish_permission(b.id, b.allow)
    except AuthError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/delete_user")
def api_admin_delete(b: AdminDeleteBody, request: Request):
    require_admin(request)
    try:
        sessions.admin_delete_user(b.id)
    except AuthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ---------- 练习（可判分的题目） ----------

class DrillBody(BaseModel):
    id: int = 0
    course: str = "sql"
    type: str = "sql"
    title: str = ""
    stem: str = ""
    setupSql: str = ""
    verifySql: str = ""
    starterCode: str = ""
    inputData: str = ""
    expectedOutput: str = ""
    options: list[dict] = []
    answer: dict = {}
    hint: str = ""
    judgeMode: str = ""
    testCases: str = ""
    publish: bool = False
    answer_text: object = ""


@app.get("/api/drills/progress")
def api_drills_progress(request: Request):
    a = acct(sess(request))
    try:
        return {"progress": drills.progress(a)}
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.get("/api/drills/mine")
def api_drills_mine(request: Request):
    a = acct(sess(request))
    try:
        return {"drills": drills.list_drills(a, mine=True)}
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.get("/api/drills/wrong")
def api_drills_wrong(request: Request):
    a = acct(sess(request))
    try:
        return {"drills": drills.my_wrong(a)}
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.get("/api/drills")
def api_drills_list(request: Request, course: str = ""):
    a = acct(sess(request))
    try:
        return {"drills": drills.list_drills(a, course=course)}
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.post("/api/drills")
def api_drills_save(b: DrillBody, request: Request):
    a = acct(sess(request))
    try:
        r = drills.save(a, b.id, {
            "course": b.course, "type": b.type, "title": b.title, "stem": b.stem,
            "setupSql": b.setupSql, "verifySql": b.verifySql,
            "starterCode": b.starterCode, "inputData": b.inputData,
            "expectedOutput": b.expectedOutput, "options": b.options,
            "answer": b.answer, "hint": b.hint,
            "judgeMode": b.judgeMode, "testCases": b.testCases,
        })
        if b.publish:
            drills.publish(a, r["id"], True)
        return r
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.get("/api/drills/{did}")
def api_drill_detail(did: int, request: Request):
    a = acct(sess(request))
    try:
        return drills.get_drill(a, did)
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.post("/api/drills/{did}/publish")
def api_drill_publish(did: int, b: DrillBody, request: Request):
    a = acct(sess(request))
    try:
        return drills.publish(a, did, b.publish)
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/drills/{did}")
def api_drill_delete(did: int, request: Request):
    a = acct(sess(request))
    try:
        drills.delete(a, did)
    except DrillError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


class TrySqlBody(BaseModel):
    setup: str = ""
    sql: str = ""


class TryPyBody(BaseModel):
    code: str = ""
    stdin: str = ""


@app.post("/api/author/try_sql")
def api_author_try_sql(b: TrySqlBody, request: Request):
    a = acct(sess(request))
    if a["role"] != "admin" and not a.get("can_publish"):
        raise HTTPException(403, "还没有出题权限")
    try:
        return drills.try_sql(a, b.setup, b.sql)
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.post("/api/author/try_python")
def api_author_try_python(b: TryPyBody, request: Request):
    a = acct(sess(request))
    if a["role"] != "admin" and not a.get("can_publish"):
        raise HTTPException(403, "还没有出题权限")
    try:
        return drills.try_python(a, b.code, b.stdin)
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.post("/api/author/qpack/parse")
async def api_qpack_parse(request: Request, files: list[UploadFile] = File(...)):
    """解析题目包（题干 + 参考答案 + 数据脚本），返回预览，不落库。"""
    a = acct(sess(request))
    if a["role"] != "admin" and not a.get("can_publish"):
        raise HTTPException(403, "还没有出题权限")
    if len(files) > drills.QPACK_MAX_FILES:
        raise HTTPException(400, f"一次最多 {drills.QPACK_MAX_FILES} 个文件")
    payload = []
    for f in files:
        raw = await f.read(drills.QPACK_FILE_MAX + 1)
        if len(raw) > drills.QPACK_FILE_MAX:
            raise HTTPException(400, f"文件 {f.filename} 超过 8MB")
        payload.append({"name": f.filename or "", "data": raw})
    try:
        return drills.parse_package(payload)
    except DrillError as e:
        raise HTTPException(400, str(e))


class QpackCreateBody(BaseModel):
    package: dict
    publish: bool = True
    judge: dict = {}


@app.post("/api/author/qpack/create")
def api_qpack_create(b: QpackCreateBody, request: Request):
    a = acct(sess(request))
    if a["role"] != "admin" and not a.get("can_publish"):
        raise HTTPException(403, "还没有出题权限")
    try:
        return drills.create_from_package(a, b.package, publish=b.publish,
                                          judge_override=b.judge or {})
    except DrillError as e:
        raise HTTPException(400, str(e))


class SetupFromDbBody(BaseModel):
    db: str = ""


@app.post("/api/author/setup_from_db")
def api_author_setup_from_db(b: SetupFromDbBody, request: Request):
    a = acct(sess(request))
    if a["role"] != "admin" and not a.get("can_publish"):
        raise HTTPException(403, "还没有出题权限")
    try:
        return drills.setup_from_db(a, b.db)
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.post("/api/author/setup_from_file")
async def api_author_setup_from_file(request: Request, file: UploadFile = File(...)):
    a = acct(sess(request))
    if a["role"] != "admin" and not a.get("can_publish"):
        raise HTTPException(403, "还没有出题权限")
    data = await file.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "文件超过 8MB")
    try:
        return drills.setup_from_file(file.filename or "", data)
    except DrillError as e:
        raise HTTPException(400, str(e))


class SandboxBody(BaseModel):
    reset: bool = False


@app.post("/api/drills/{did}/sandbox")
def api_drill_sandbox(did: int, b: SandboxBody, request: Request):
    a = acct(sess(request))
    try:
        return drills.ensure_sandbox(a, did, b.reset)
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.post("/api/drills/{did}/submit")
def api_drill_submit(did: int, b: DrillBody, request: Request):
    a = acct(sess(request))
    try:
        return drills.submit(a, did, b.answer_text)
    except DrillError as e:
        raise HTTPException(400, str(e))


@app.get("/api/health")
def api_health():
    return {"ok": True}


# ---------- 分享链接入口 ----------

@app.get("/s/{code}")
def share_entry(code: str):
    from fastapi.responses import FileResponse

    return FileResponse(STATIC_DIR / "index.html",
                        headers={"Cache-Control": "no-cache"})


# ---------- 静态页面（放在最后，/ 返回 index.html） ----------

class SPAStatic(StaticFiles):
    """静态文件；找不到的页面请求回退到 index.html（单页应用刷新任意路径都不白屏）。"""

    async def get_response(self, path, scope):
        from starlette.exceptions import HTTPException as StarletteHTTPException

        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            accept = ""
            for k, v in scope.get("headers", []):
                if k.lower() == b"accept":
                    accept = v.decode("latin-1")
                    break
            # 只有浏览器"打开页面"的请求才回退；图片/脚本等资源缺失仍然 404
            if "text/html" not in accept:
                raise
            resp = await super().get_response("index.html", scope)
            resp.headers["Cache-Control"] = "no-cache"
            return resp


@app.get("/index.html")
def index_canonical():
    """统一入口地址：/index.html → /（地址栏始终是带斜杠的根路径）。"""
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/", status_code=307)


app.mount("/", SPAStatic(directory=str(STATIC_DIR), html=True), name="static")
