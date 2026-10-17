"""账号密码策略与 PBKDF2 哈希。

注册规则（面向学生自助注册，兼顾课堂易用与安全）：
- 用户名：3-20 位，必须字母开头，只能字母和数字（不允许中文/下划线/特殊字符）
- 密码：8-32 位，必须同时含字母和数字
- 拒绝弱密码：纯数字、纯字母、常见弱口令、与用户名相同/包含用户名
- 拒绝敏感用户名：admin / root / system / test 等
"""
import hashlib
import re
import secrets

ITERATIONS = 200_000

# 用户名：字母开头 + 字母数字
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{2,19}$")

# 禁止注册的敏感名（会造成混淆或与系统冲突）
RESERVED_USERNAMES = {
    "admin", "administrator", "root", "system", "sysadmin", "administrator",
    "test", "guest", "anonymous", "demo", "user", "users", "mysql",
    "postgres", "db", "database", "sqlpy", "lab", "labadmin", "superuser",
    "sa", "operator", "manager", "webmaster", "support", "info", "null",
    "undefined", "backup", "server", "api", "dev", "debug",
}

# 常见弱口令（归一化后比对：转小写 + 去掉非字母数字）
WEAK_PASSWORDS = {
    "123456", "123456789", "12345678", "1234567890", "000000", "111111",
    "654321", "666666", "888888", "123123", "abc123", "abc1234", "a123456",
    "password", "password1", "password123", "passw0rd", "p@ssw0rd",
    "qwerty", "qwerty123", "qwertyuiop", "asdfgh", "asdfghjkl", "zxcvbn",
    "admin", "admin123", "administrator", "root", "root123", "toor",
    "letmein", "welcome", "welcome1", "welcome123", "hello", "hello123",
    "iloveyou", "monkey", "dragon", "sunshine", "princess", "football",
    "superman", "trustno1", "starwars", "master", "login", "guest",
    "whatever", "computer", "internet", "samsung", "google", "baidu",
    "tencent", "alibaba", "taobao", "123abc", "a1b2c3", "abc123456",
    "qazwsx", "1q2w3e", "1q2w3e4r", "asd123", "zxc123", "147258369",
    "963852741", "woaini", "woshi", "nihao", "5201314", "1314520",
}


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt.encode("ascii"), ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, iters, salt, hexdig = (stored or "").split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt.encode("ascii"), int(iters))
        return secrets.compare_digest(dk.hex(), hexdig)
    except Exception:
        return False


def validate_username(name: str) -> tuple[bool, str]:
    """返回 (是否合法, 错误提示)。"""
    n = (name or "").strip()
    if not n:
        return False, "请输入账号"
    if len(n) < 3:
        return False, "账号至少 3 位"
    if len(n) > 20:
        return False, "账号最多 20 位"
    if not n[0].isalpha():
        return False, "账号必须以字母开头"
    if not USERNAME_RE.match(n):
        return False, "账号只能用英文字母和数字，且必须字母开头"
    if n.lower() in RESERVED_USERNAMES:
        return False, f"「{n}」是系统保留名，换一个吧"
    return True, ""


def validate_password(pw: str, username: str = "") -> tuple[bool, str]:
    """返回 (是否合法, 错误提示)。"""
    p = pw or ""
    if len(p) < 8:
        return False, "密码至少 8 位"
    if len(p) > 32:
        return False, "密码最多 32 位"
    has_alpha = any(c.isalpha() and c.isascii() for c in p)
    has_digit = any(c.isdigit() for c in p)
    if not (has_alpha and has_digit):
        return False, "密码必须同时包含字母和数字"
    norm = re.sub(r"[^A-Za-z0-9]", "", p).lower()
    if norm in WEAK_PASSWORDS:
        return False, "这个密码太常见了，换一个更安全的"
    # 纯数字或纯字母（如 aaaaaaaa / 12345678）
    if norm.isdigit() or norm.isalpha():
        return False, "密码不能是纯数字或纯字母"
    if len(set(norm)) < 4:
        return False, "密码重复字符太多，太容易被猜到"
    # 不能与用户名相同或包含用户名（如 user123 / zhangsan666）
    u = re.sub(r"[^A-Za-z0-9]", "", username or "").lower()
    if u and (u in norm or norm in u):
        return False, "密码不能和账号一样或包含账号"
    return True, ""


def valid_username(name: str) -> bool:
    return validate_username(name)[0]


def valid_password(pw: str, username: str = "") -> bool:
    return validate_password(pw, username)[0]
