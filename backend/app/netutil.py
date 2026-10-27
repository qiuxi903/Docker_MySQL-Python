"""客户端真实 IP 判定。

单独成模块是为了能脱离 FastAPI 单测（见 tests/local_test.py）。

背景：容器里看到的来源地址取决于部署方式 ——
  - 学生直连容器端口（`http://服务器:8000`）：来源被 Docker 端口转发改写成内部网关
    （172.x），拿不到真实 IP；
  - 经 Nginx / 宝塔反代：反代会把真实来源写进 `X-Forwarded-For` / `X-Real-IP`，
    读这两个头才能拿到学生 IP。

`TRUST_PROXY_HOPS`（默认 1）= 可信反代层数：X-Forwarded-For 从右往左数第几跳是学生真实 IP
（宝塔/Nginx 单层反代用 1；CDN + Nginx 两层用 2）。

`TRUST_PROXY` 决定信不信这两个头：
  - 未设置（auto）  ：有反代头就用（兼容旧行为）
  - `1`（always）   ：信任反代头（宝塔/Nginx 反代后面用这个）
  - `0`（never）    ：只认 socket 来源，防止有人伪造 X-Forwarded-For 刷限流
"""
import ipaddress

MODE_AUTO = "auto"
MODE_ALWAYS = "always"
MODE_NEVER = "never"


def parse_mode(raw) -> str:
    """把 .env 里的 TRUST_PROXY 值解析成三种模式之一。"""
    v = str(raw or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return MODE_ALWAYS
    if v in ("0", "false", "no", "off"):
        return MODE_NEVER
    return MODE_AUTO


def valid_ip(s) -> bool:
    try:
        ipaddress.ip_address(str(s or "").strip())
        return True
    except ValueError:
        return False


def valid_list(header: str) -> list:
    """X-Forwarded-For 里所有合法 IP，按出现顺序（左→右）。"""
    out = []
    for part in str(header or "").split(","):
        part = part.strip()
        if part and valid_ip(part):
            out.append(part)
    return out


def last_valid(header: str, hops: int = 1) -> str:
    """取 X-Forwarded-For 里「从右往左数第 hops 个」合法 IP —— 可信反代写入的那一跳。

    为什么从右往左数：nginx 的 `$proxy_add_x_forwarded_for` 是
    `客户端自带的值, $remote_addr` —— 学生伪造的内容留在**最左边**，
    反代把真实来源**追加在最右边**。所以：
      - 一层反代（宝塔/Nginx 直接对外）：hops=1，取最右一个 = 学生真实 IP；
      - 两层反代（CDN + Nginx）：hops=2，取右数第二个。
    取最左边是错的：那正是学生可以随便伪造的位置（能刷限流、栽赃别人 IP）。
    """
    ips = valid_list(header)
    if not ips:
        return ""
    hops = max(1, int(hops or 1))
    return ips[-hops] if len(ips) >= hops else ips[0]


def is_private(ip: str) -> bool:
    """内网 / 回环 / 链路本地 —— 直连容器时看到的就是这类地址。

    （Python 的 `is_private` 语义更宽，连 203.0.113.x 这类文档保留段也算非公网；
    这里只关心「是不是学生真实来源」，所以按实际会出现的地址集合判定。）
    """
    try:
        a = ipaddress.ip_address(str(ip or "").strip())
    except ValueError:
        return False
    return bool(a.is_private or a.is_loopback or a.is_link_local or a.is_unspecified)


def resolve(mode: str, forwarded_for: str, real_ip: str, socket_ip: str,
            hops: int = 1) -> str:
    """按模式判定真实客户端 IP（返回截断到 64 字符的字符串）。

    hops = 可信反代层数（默认 1）：X-Forwarded-For 从右往左数第 hops 个才是学生真实 IP。
    """
    sock = str(socket_ip or "").strip()[:64]
    if mode == MODE_NEVER:
        return sock
    fwd = last_valid(forwarded_for, hops)
    if fwd:
        return fwd[:64]
    real = str(real_ip or "").strip()
    if valid_ip(real):
        return real[:64]
    return sock


def diagnose(mode: str, forwarded_for: str, real_ip: str, socket_ip: str,
             hops: int = 1) -> dict:
    """给管理后台的「网络诊断」用：原始值 + 判定结果 + 一句可操作的提示。"""
    resolved = resolve(mode, forwarded_for, real_ip, socket_ip, hops)
    has_header = bool(valid_list(forwarded_for) or valid_ip(real_ip))
    return {
        "mode": mode,
        "hops": max(1, int(hops or 1)),
        "socketIp": str(socket_ip or "")[:64],
        "forwardedFor": str(forwarded_for or "")[:200],
        "realIp": str(real_ip or "")[:64],
        "resolved": resolved,
        "hasProxyHeader": has_header,
        "private": is_private(resolved),
        "hint": _hint(mode, has_header, resolved),
    }


def _hint(mode: str, has_header: bool, resolved: str) -> str:
    if mode == MODE_NEVER:
        if has_header:
            return ("当前 TRUST_PROXY=0：反代已经带了真实 IP 头，但按配置不采用。"
                    "要让管理后台显示学生真实 IP，把 .env 的 TRUST_PROXY 改成 1，"
                    "再 docker compose up -d 重建 web 容器。")
        return "当前 TRUST_PROXY=0：只认直连来源。若经反代访问，请把 TRUST_PROXY 设为 1。"
    if has_header:
        if is_private(resolved):
            return ("已收到反代头，但判定值仍是内网地址 —— 可能是内网访问，"
                    "或反代没有把最外层来源透传进来（检查反代是否覆盖了 X-Forwarded-For）。")
        return "已收到反代头，管理后台记录的即为学生真实 IP。"
    if is_private(resolved):
        return ("没有收到任何反代头（X-Forwarded-For / X-Real-IP），看到的是直连来源"
                "（Docker 网关或局域网地址）。两种修法：① 宝塔/Nginx 反代里加 "
                "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; 与 "
                "proxy_set_header X-Real-IP $remote_addr; ② 或启用内置 realip 反代："
                "docker compose --profile realip up -d，学生改从 PROXY_PORT 访问。")
    return "没有反代头，但来源是公网地址：学生是直连本机端口访问的。"
