"""用户系统：个人资料 / 自助改密 / 会话管理 + 管理员用户管理。

账号表（meta.accounts）在此模块负责的字段：
  disabled            TINYINT(1)  1=禁用，禁止登录、现有会话立即失效
  last_login_at       DATETIME    最近一次登录成功时间
  password_changed_at DATETIME    最近一次修改密码时间
  can_publish         TINYINT(1)  出题权限（素材包 / 练习题共用）

日志表 meta.auth_log 记录登录成功/失败、注册、改密、管理员操作，供管理后台查看。
"""
import datetime

import pymysql

from . import auth, sessions
from .config import C
from .db import q_ident, root_conn

ACTIONS = {
    "login_ok": "登录成功", "login_fail": "登录失败", "register": "注册",
    "guest": "游客进入", "change_pw": "修改密码", "admin_reset": "管理员重置密码",
    "admin_create": "管理员创建账号", "admin_disable": "禁用账号",
    "admin_enable": "启用账号", "admin_delete": "删除账号",
    "admin_grant": "开通出题权限", "admin_revoke": "收回出题权限",
    "admin_kick": "强制下线",
}


class UserError(Exception):
    pass


# ---------------- 基础 ----------------

def init():
    """建 auth_log；accounts 新列由 sessions._init_meta 迁移。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {q_ident(C.META_DB)}.auth_log (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    account_id BIGINT NULL,
                    username VARCHAR(64) NOT NULL DEFAULT '',
                    ip VARCHAR(64) NOT NULL DEFAULT '',
                    action VARCHAR(24) NOT NULL,
                    ok TINYINT(1) NOT NULL DEFAULT 1,
                    note VARCHAR(255) NOT NULL DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_created (created_at),
                    KEY idx_account (account_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    finally:
        conn.close()


def log(account_id, username: str, ip: str, action: str, ok: bool = True, note: str = ""):
    """写一条审计日志（失败不影响主流程）。"""
    try:
        conn = root_conn(C.META_DB)
        try:
            with conn.cursor() as cur:
                cur.execute(f"""INSERT INTO {q_ident(C.META_DB)}.auth_log
                                (account_id, username, ip, action, ok, note)
                                VALUES (%s,%s,%s,%s,%s,%s)""",
                            (account_id, (username or "")[:64], (ip or "")[:64],
                             action, 1 if ok else 0, (note or "")[:255]))
        finally:
            conn.close()
    except Exception:
        pass


def _row_account(r) -> dict:
    return {
        "id": r[0], "username": r[1] or "游客", "kind": r[2], "role": r[3],
        "db": r[4], "createdAt": str(r[5]), "canPublish": bool(r[6]),
        "disabled": bool(r[7]), "lastLogin": str(r[8]) if r[8] else "-",
        "lastSeen": str(r[9]) if r[9] else "-", "sessions": int(r[10] or 0),
        "regIp": r[11] or "-", "lastIp": r[12] or "-", "dbCount": int(r[13] or 0),
    }


# ---------------- 个人（所有登录用户） ----------------

def profile(account: dict) -> dict:
    """个人中心：账号信息 + 用量统计。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT created_at, last_login_at, password_changed_at,
                                  can_publish, disabled, reg_ip, last_ip
                           FROM accounts WHERE id=%s""", (account["id"],))
            r = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM dbs WHERE account_id=%s", (account["id"],))
            db_count = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM py_files WHERE account_id=%s", (account["id"],))
            py_count = int(cur.fetchone()[0] or 0)
            cur.execute("""SELECT COUNT(*) FROM community.questions WHERE account_id=%s""",
                        (account["id"],))
            material_count = int(cur.fetchone()[0] or 0)
            cur.execute("""SELECT COUNT(DISTINCT drill_id),
                                  SUM(CASE WHEN passed=1 THEN 1 ELSE 0 END),
                                  COUNT(*)
                           FROM community.drill_submissions WHERE account_id=%s""",
                        (account["id"],))
            dr, dp, dt = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM sessions WHERE account_id=%s", (account["id"],))
            sess_count = int(cur.fetchone()[0] or 0)
    finally:
        conn.close()
    if not r:
        raise UserError("账号不存在")
    return {
        "username": account["display"], "kind": account["kind"], "role": account["role"],
        "canPublish": account["role"] == "admin" or bool(r[3]),
        "disabled": bool(r[4]),
        "createdAt": str(r[0]), "lastLogin": str(r[1]) if r[1] else "-",
        "passwordChangedAt": str(r[2]) if r[2] else "-",
        "regIp": r[5] or "-", "lastIp": r[6] or "-",
        "stats": {"databases": db_count, "pyFiles": py_count,
                  "materials": material_count, "drillsTried": int(dr or 0),
                  "drillsPassed": int(dp or 0), "submissions": int(dt or 0),
                  "sessions": sess_count},
    }


def change_password(account: dict, old_pw: str, new_pw: str, keep_token: str = ""):
    if account["kind"] != "user":
        raise UserError("游客账号没有密码，注册后即可设置")
    ok, msg = auth.validate_password(new_pw, account["username"] or "")
    if not ok:
        raise UserError(msg)
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pass_hash FROM accounts WHERE id=%s", (account["id"],))
            row = cur.fetchone()
            if not row or not auth.verify_password(old_pw or "", row[0]):
                raise UserError("原密码不对")
            if auth.verify_password(new_pw, row[0]):
                raise UserError("新密码不能和原密码相同")
            cur.execute("""UPDATE accounts SET pass_hash=%s, password_changed_at=NOW()
                           WHERE id=%s""", (auth.hash_password(new_pw), account["id"]))
        conn.commit()
    finally:
        conn.close()
    # 改密后把其他设备踢下线，当前会话保留
    killed = sessions.kill_other_sessions(account["id"], keep_token)
    log(account["id"], account["display"], "", "change_pw", True, f"踢下线 {killed} 个会话")
    return {"ok": True, "killed": killed}


def logout_all(account: dict, keep_token: str = ""):
    killed = sessions.kill_other_sessions(account["id"], keep_token)
    log(account["id"], account["display"], "", "admin_kick", True,
        f"本人退出所有设备 {killed} 个会话")
    return {"ok": True, "killed": killed}


# ---------------- 管理员 ----------------

_ACCOUNT_COLS = ("a.id, a.username, a.kind, a.role, a.db_name, a.created_at, a.can_publish, "
                 "a.disabled, a.last_login_at, MAX(s.last_seen), COUNT(DISTINCT s.token), "
                 "a.reg_ip, a.last_ip, "
                 "(SELECT COUNT(*) FROM {meta}.dbs d WHERE d.account_id=a.id)")


def list_users(kind: str = "user", q: str = "", page: int = 1, size: int = 50,
               only: str = "") -> dict:
    """管理端用户列表：按类型 / 关键词 / 权限状态筛选，分页。"""
    kind = "guest" if kind == "guest" else "user"
    page = max(1, int(page or 1))
    size = min(200, max(10, int(size or 50)))
    where = ["a.kind=%s"]
    params = [kind]
    q = (q or "").strip()
    if q:
        where.append("(a.username LIKE %s OR a.db_name LIKE %s OR a.last_ip LIKE %s)")
        like = f"%{q}%"
        params += [like, like, like]
    if only == "publish":
        where.append("a.can_publish=1")
    elif only == "nopublish":
        where.append("a.can_publish=0")
    elif only == "disabled":
        where.append("a.disabled=1")
    cond = " AND ".join(where)
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM accounts a WHERE {cond}", params)
            total = int(cur.fetchone()[0] or 0)
            cur.execute(f"""
                SELECT {_ACCOUNT_COLS.format(meta=q_ident(C.META_DB))}
                FROM accounts a LEFT JOIN sessions s ON s.account_id=a.id
                WHERE {cond}
                GROUP BY a.id
                ORDER BY MAX(s.last_seen) DESC, a.id DESC
                LIMIT %s OFFSET %s
            """, params + [size, (page - 1) * size])
            rows = cur.fetchall()
    finally:
        conn.close()
    return {"users": [_row_account(r) for r in rows], "total": total,
            "page": page, "size": size, "pages": max(1, (total + size - 1) // size)}


def overview() -> dict:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM accounts WHERE kind='user'")
            users = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM accounts WHERE kind='guest'")
            guests = int(cur.fetchone()[0] or 0)
            cur.execute("""SELECT COUNT(DISTINCT account_id) FROM sessions
                           WHERE last_seen >= NOW() - INTERVAL 1 DAY""")
            active = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM accounts WHERE can_publish=1 AND kind='user'")
            publishers = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM accounts WHERE disabled=1")
            disabled = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM dbs")
            dbs = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM py_files")
            pyfiles = int(cur.fetchone()[0] or 0)
            cur.execute("""SELECT DATE(created_at), COUNT(*) FROM accounts
                           WHERE kind='user' AND created_at >= NOW() - INTERVAL 7 DAY
                           GROUP BY DATE(created_at)""")
            reg = {str(d): int(n) for d, n in cur.fetchall()}
    finally:
        conn.close()
    drills = items = submissions = 0
    try:
        c2 = root_conn(C.COMMUNITY_DB)
        try:
            with c2.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM drills")
                drills = int(cur.fetchone()[0] or 0)
                cur.execute("SELECT COUNT(*) FROM questions")
                items = int(cur.fetchone()[0] or 0)
                cur.execute("SELECT COUNT(*) FROM drill_submissions")
                submissions = int(cur.fetchone()[0] or 0)
        finally:
            c2.close()
    except Exception:
        pass
    days = []
    today = datetime.date.today()
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        days.append({"date": d.strftime("%m-%d"), "count": reg.get(str(d), 0)})
    return {"users": users, "guests": guests, "activeToday": active,
            "publishers": publishers, "disabled": disabled, "databases": dbs,
            "pyFiles": pyfiles, "drills": drills, "materials": items,
            "submissions": submissions, "regTrend": days}


def detail(account_id: int) -> dict:
    """单个用户的完整档案：基本信息 + 库 + Python 文件 + 练习成绩 + 在线会话 + 最近日志。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT {_ACCOUNT_COLS.format(meta=q_ident(C.META_DB))}
                            FROM accounts a LEFT JOIN sessions s ON s.account_id=a.id
                            WHERE a.id=%s GROUP BY a.id""", (account_id,))
            r = cur.fetchone()
            if not r:
                raise UserError("用户不存在")
            base = _row_account(r)
            cur.execute("""SELECT db_name, primary_db, origin, created_at FROM dbs
                           WHERE account_id=%s ORDER BY primary_db DESC, created_at""",
                        (account_id,))
            dbs = [{"name": x[0], "primary": bool(x[1]), "origin": x[2],
                    "createdAt": str(x[3])} for x in cur.fetchall()]
            cur.execute("""SELECT name, LENGTH(content), uploaded, updated_at FROM py_files
                           WHERE account_id=%s ORDER BY name""", (account_id,))
            files = [{"name": x[0], "size": int(x[1] or 0), "uploaded": bool(x[2]),
                      "updatedAt": str(x[3])} for x in cur.fetchall()]
            cur.execute("""SELECT token, created_at, last_seen FROM sessions
                           WHERE account_id=%s ORDER BY last_seen DESC""", (account_id,))
            sess = [{"token": x[0][:8] + "…", "createdAt": str(x[1]),
                     "lastSeen": str(x[2])} for x in cur.fetchall()]
            cur.execute("""SELECT username, ip, action, ok, note, created_at
                           FROM auth_log WHERE account_id=%s
                           ORDER BY id DESC LIMIT 20""", (account_id,))
            logs = [{"username": x[0], "ip": x[1], "action": x[2],
                     "actionLabel": ACTIONS.get(x[2], x[2]), "ok": bool(x[3]),
                     "note": x[4], "at": str(x[5])} for x in cur.fetchall()]
    finally:
        conn.close()
    drill = {"tried": 0, "passed": 0, "submissions": 0, "byCourse": {}}
    try:
        c2 = root_conn(C.COMMUNITY_DB)
        try:
            with c2.cursor() as cur:
                cur.execute("""SELECT d.course, COUNT(DISTINCT s.drill_id),
                                      SUM(CASE WHEN s.passed=1 THEN 1 ELSE 0 END), COUNT(*)
                               FROM drill_submissions s JOIN drills d ON d.id=s.drill_id
                               WHERE s.account_id=%s GROUP BY d.course""",
                            (account_id,))
                for course, tried, passed, subs in cur.fetchall():
                    drill["byCourse"][course] = {"tried": int(tried or 0),
                                                 "passed": int(passed or 0),
                                                 "submissions": int(subs or 0)}
                    drill["tried"] += int(tried or 0)
                    drill["passed"] += int(passed or 0)
                    drill["submissions"] += int(subs or 0)
        finally:
            c2.close()
    except Exception:
        pass
    return {"user": base, "databases": dbs, "pyFiles": files,
            "sessions": sess, "logs": logs, "drills": drill}


def create_user(username: str, password: str, ip: str, can_publish: bool,
                operator: dict) -> dict:
    try:
        acc = sessions.register(username, password, ip)
    except sessions.AuthError as e:
        raise UserError(str(e))
    if can_publish:
        _set_perm(acc["id"], True)
    log(acc["id"], acc["display"], ip, "admin_create", True,
        f"由 {operator['display']} 创建" + ("（含出题权限）" if can_publish else ""))
    return {"id": acc["id"], "username": acc["display"], "canPublish": bool(can_publish)}


def _set_perm(account_id: int, allow: bool):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE accounts SET can_publish=%s WHERE id=%s",
                        (1 if allow else 0, account_id))
    finally:
        conn.close()


def update(account_id: int, fields: dict, operator: dict) -> dict:
    """管理员改用户：出题权限 / 禁用 / 重置密码。只改传了的字段。"""
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, kind, role, can_publish, disabled"
                        " FROM accounts WHERE id=%s", (account_id,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        raise UserError("用户不存在")
    _id, username, kind, role, cur_perm, cur_dis = r
    if kind == "guest" and ("can_publish" in fields or "disabled" in fields):
        raise UserError("游客不支持这些设置")
    changed = []

    if "can_publish" in fields:
        allow = bool(fields["can_publish"])
        if role == "admin":
            raise UserError("管理员默认拥有出题权限")
        if allow != bool(cur_perm):
            _set_perm(account_id, allow)
            log(account_id, username, "", "admin_grant" if allow else "admin_revoke",
                True, f"由 {operator['display']} 操作")
            changed.append("can_publish")

    if "disabled" in fields:
        dis = bool(fields["disabled"])
        if role == "admin":
            raise UserError("不能禁用管理员账号")
        if dis != bool(cur_dis):
            conn = root_conn(C.META_DB)
            try:
                with conn.cursor() as cur:
                    cur.execute("UPDATE accounts SET disabled=%s WHERE id=%s",
                                (1 if dis else 0, account_id))
                    if dis:
                        cur.execute("DELETE FROM sessions WHERE account_id=%s", (account_id,))
            finally:
                conn.close()
            log(account_id, username, "", "admin_disable" if dis else "admin_enable",
                True, f"由 {operator['display']} 操作")
            changed.append("disabled")

    if fields.get("password"):
        pw = str(fields["password"])
        ok, msg = auth.validate_password(pw, username or "")
        if not ok:
            raise UserError(msg)
        if kind != "user":
            raise UserError("游客没有密码")
        conn = root_conn(C.META_DB)
        try:
            with conn.cursor() as cur:
                cur.execute("""UPDATE accounts SET pass_hash=%s, password_changed_at=NOW()
                               WHERE id=%s""", (auth.hash_password(pw), account_id))
                cur.execute("DELETE FROM sessions WHERE account_id=%s", (account_id,))
        finally:
            conn.close()
        log(account_id, username, "", "admin_reset", True, f"由 {operator['display']} 重置")
        changed.append("password")

    return {"id": account_id, "changed": changed,
            "canPublish": bool(cur_perm) if "can_publish" not in fields else bool(fields["can_publish"]),
            "disabled": bool(cur_dis) if "disabled" not in fields else bool(fields["disabled"])}


def revoke_sessions(account_id: int, operator: dict) -> dict:
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT username FROM accounts WHERE id=%s", (account_id,))
            row = cur.fetchone()
            if not row:
                raise UserError("用户不存在")
            cur.execute("DELETE FROM sessions WHERE account_id=%s", (account_id,))
            n = cur.rowcount
    finally:
        conn.close()
    log(account_id, row[0], "", "admin_kick", True, f"由 {operator['display']} 强制下线")
    return {"ok": True, "killed": n}


def batch(ids: list[int], action: str, operator: dict) -> dict:
    ids = [int(i) for i in (ids or [])][:200]
    if not ids:
        raise UserError("先勾选用户")
    done, skipped = 0, []
    for uid in ids:
        try:
            if action in ("grant", "revoke"):
                update(uid, {"can_publish": action == "grant"}, operator)
            elif action in ("disable", "enable"):
                update(uid, {"disabled": action == "disable"}, operator)
            elif action == "kick":
                revoke_sessions(uid, operator)
            elif action == "delete":
                _delete_checked(uid, operator)
            else:
                raise UserError("不支持的操作")
            done += 1
        except (UserError, sessions.AuthError) as e:
            skipped.append({"id": uid, "reason": str(e)})
    return {"done": done, "skipped": skipped}


def _delete_checked(account_id: int, operator: dict):
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT username, role FROM accounts WHERE id=%s", (account_id,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        raise UserError("用户不存在")
    if r[1] == "admin":
        raise UserError("不能删除管理员账号")
    log(account_id, r[0], "", "admin_delete", True, f"由 {operator['display']} 删除")
    sessions.admin_delete_user(account_id)


def auth_log(limit: int = 100, only_fail: bool = False) -> list[dict]:
    limit = min(500, max(10, int(limit or 100)))
    conn = root_conn(C.META_DB)
    try:
        with conn.cursor() as cur:
            where = "WHERE ok=0" if only_fail else ""
            cur.execute(f"""SELECT account_id, username, ip, action, ok, note, created_at
                            FROM auth_log {where} ORDER BY id DESC LIMIT %s""", (limit,))
            return [{"accountId": x[0], "username": x[1], "ip": x[2], "action": x[3],
                     "actionLabel": ACTIONS.get(x[3], x[3]), "ok": bool(x[4]),
                     "note": x[5], "at": str(x[6])} for x in cur.fetchall()]
    finally:
        conn.close()
