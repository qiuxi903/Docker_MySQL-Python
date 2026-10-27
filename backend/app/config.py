"""全局配置：全部来自环境变量（docker-compose 注入），本地直跑有默认值。"""
import os

from . import netutil as _netutil


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


class C:
    # MySQL（root 仅用于开通/管理，学生 SQL 全部走各自受限账号）
    DB_HOST = os.getenv("DB_HOST", "db")
    DB_PORT = _int("DB_PORT", 3306)
    ROOT_PW = os.getenv("MYSQL_ROOT_PASSWORD", "change-me-root")

    # 管理员
    ADMIN_USER = os.getenv("ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

    # Python 沙箱服务
    RUNNER_URL = os.getenv("RUNNER_URL", "http://runner:8100").rstrip("/")
    RUNNER_TOKEN = os.getenv("RUNNER_TOKEN", "change-me-runner-token")

    # 业务参数
    META_DB = "meta"            # 账号/会话元数据
    COMMUNITY_DB = "community"  # 表社区存储
    GUEST_TTL_DAYS = _int("GUEST_TTL_DAYS", 7)      # 游客数据保留天数
    GUEST_SESSION_TTL_DAYS = 3                       # 游客登录态固定有效天数
    SESSION_TTL_DAYS = _int("SESSION_TTL_DAYS", 30) # 登录态保留天数
    SQL_TIMEOUT = _float("SQL_TIMEOUT_SEC", 10.0)   # 单次 SQL 执行墙钟上限
    PY_IDLE_SEC = _float("PY_IDLE_SEC", 120.0)   # Python 等待输入/无输出的存活秒数
    PY_MAX_SEC = _float("PY_MAX_SEC", 300.0)     # Python 单次运行总时长上限
    ROWS_LIMIT = _int("ROWS_LIMIT", 500)            # 查询结果返回行数上限

    SQL_MAX = 64 * 1024        # 单次提交 SQL 大小上限
    CODE_MAX = 256 * 1024      # 单次提交 Python 代码上限
    UPLOAD_MAX = 5 * 1024 * 1024   # 上传文件上限
    # Python 文件总容量配额（MB）：新用户的默认值；-1=无限。管理员永远无限。
    # 管理员可在用户管理里给每个人单独设置 / 追加。
    DEFAULT_QUOTA_MB = _int("DEFAULT_QUOTA_MB", 256)
    IMPORT_ROWS_MAX = 20000        # 单次导入行数上限
    IMPORT_COLS_MAX = 64           # 单表列数上限
    SHARE_ROWS_MAX = 5000          # 分享到社区的行数上限
    RATE_LIMIT = _int("RATE_LIMIT_PER_MIN", 600)  # 每 IP 每分钟请求数（机房共用出口 IP 时调高）
    # 反代头信任策略（.env 的 TRUST_PROXY）：
    #   未设置 = auto（有 X-Forwarded-For / X-Real-IP 就用，兼容旧行为）
    #   1      = always（宝塔/Nginx 反代后面用这个：管理后台显示学生真实 IP、限流按真实 IP）
    #   0      = never（只认 socket 来源，防止伪造反代头刷限流）
    TRUST_PROXY_RAW = os.getenv("TRUST_PROXY", "")
    TRUST_PROXY_MODE = _netutil.parse_mode(TRUST_PROXY_RAW)
    # 兼容旧写法：布尔值（auto / always 都算信任）
    TRUST_PROXY = TRUST_PROXY_MODE != _netutil.MODE_NEVER


# 防呆：允许 `from . import config as C`（模块）和 `from .config import C`（类）两种写法
# 都能访问到配置。历史上两种写法混用导致过 AttributeError，这里统一兜底。
import sys as _sys

_mod = _sys.modules[__name__]
for _name in dir(C):
    if not _name.startswith("__"):
        setattr(_mod, _name, getattr(C, _name))
