# PROJECT.md — 项目详解

> 本文件是 [README](README.md) 的配套详细文档：项目结构、总体架构、功能细则、API 一览、具体使用方法、配置参考、部署手册、运维手册、测试与安全模型。

## 目录

- [一、项目结构](#一项目结构)
- [二、总体架构](#二总体架构)
- [三、功能细则](#三功能细则)
- [四、API 一览](#四api-一览)
- [五、使用指南（学生篇 / 教师篇）](#五使用指南学生篇--教师篇)
- [六、配置参考（.env）](#六配置参考env)
- [七、部署手册](#七部署手册)
- [八、运维手册](#八运维手册)
- [九、测试](#九测试)
- [十、安全模型](#十安全模型)
- [十一、常见问题](#十一常见问题)

---

## 一、项目结构

```
Docker_MySQL-Python/
├─ docker-compose.yml          # 三容器编排：web / runner / db（内网隔离 + 数据卷）
├─ .env.example                # 配置模板（复制为 .env 后修改）
├─ README.md                   # 项目介绍 + 快速开始 + 部署方法
├─ PROJECT.md                  # 本文件：结构 / 细则 / 用法 / 运维
├─ LICENSE                     # MIT 开源协议
├─ backend/
│  ├─ Dockerfile               # ARG PYTHON_VERSION=3.12，改 .env 可切 3.14
│  ├─ requirements.txt         # fastapi / uvicorn / pymysql / openpyxl / python-multipart
│  └─ app/
│     ├─ main.py               # FastAPI 入口：全部 API 路由 + 静态托管 + IP 限流
│     ├─ config.py             # 全部配置项（环境变量 → C 类，含默认值）
│     ├─ auth.py               # 注册/登录：用户名与密码策略、弱口令与保留名拦截、PBKDF2 哈希
│     ├─ sessions.py           # 会话 token、独立库开通、MySQL 账号授权、定时清理、Python 多文件
│     ├─ db.py                 # root / 受限用户两种连接、标识符安全转义
│     ├─ sqlrun.py             # SQL 执行器：无分号智能分行、超时看门狗、行数上限、错误友好化
│     ├─ importer.py           # CSV / Excel / SQL 脚本导入、列类型推断、源文件存档
│     ├─ community.py          # 社区与分享：整库脚本 / Python / 表格的上传、解析、导入、下载
│     ├─ seed/
│     │  └─ bjpowernode.sql    # 新账号内置教学表（DEPT / EMP / SALGRADE）
│     └─ static/
│        ├─ index.html         # 单页应用模板（Vue 3 挂载点 + 全部弹窗）
│        ├─ app.js             # 全部前端逻辑（Vue 组件、CodeMirror 集成、快捷键、移动端适配）
│        ├─ style.css          # 全站样式（Primer 配色、深浅主题、响应式）
│        ├─ fonts/misans/      # MiSans 字体（4 字重 × 分包 woff2，本地内置）
│        └─ vendor/            # vue.global.prod.js + CodeMirror 及插件（本地化，无 CDN）
├─ runner/
│  ├─ server.py                # Python 沙箱执行服务（交互式作业模型、rlimit、看门狗）
│  └─ labhelpers.py            # 注入学生环境的 get_conn / query / query_dicts / execute
└─ tests/
   ├─ local_test.py            # 本地单元测试（不需要 MySQL）：语句切分、沙箱引擎等，95 项
   └─ smoke_test.py            # 端到端烟测（对着运行中的站点全流程），101 项
```

## 二、总体架构

```
浏览器（学生手机 / 电脑）
   │  http://localhost:8000 或 https://你的域名
   ↓
┌─────────────────────────── Docker Compose ───────────────────────────┐
│  web    FastAPI 后端 + Vue 前端静态托管（唯一对外端口 8000）              │
│    │  1. 注册/登录/游客 → 定位到该学生的独立库 + 专用 MySQL 账号           │
│    │  2. SQL 执行 / 文件导入 / 社区 / 分享 API                            │
│    │  3. Python 代码转发给 runner 执行                                    │
│  runner  Python 沙箱（不对外的 8100 端口、无外网、只读根目录、限资源）      │
│  db     MySQL 5.7（不对外的 3306、utf8mb4、数据持久化卷 dbdata）          │
└──────────────────────────────────────────────────────────────────────┘
```

- `lab` 内网（internal）：db、runner 只在内部网络里，无法访问外网，也无法被外部访问。
- `edge` 网络：仅 web 接入，对外只暴露 `WEB_PORT`（默认 8000）。
- 所有持久化数据都在 Docker 卷 `dbdata`（MySQL 数据目录）里，`docker compose down` 不丢数据。

## 三、功能细则

### 3.1 账号体系

- **注册**：用户名必须字母开头、仅含字母和数字、3–20 位（`^[A-Za-z][A-Za-z0-9]{2,19}$`）；`admin`、`root`、`test` 等保留名不可注册。密码 8–32 位，必须**同时含字母和数字**；拒绝常见弱口令（123456 之类）、与用户名相同或包含用户名的密码。
- **密码存储**：PBKDF2-SHA256，20 万轮，随机盐，不存明文。
- **会话**：登录后发随机 token，前端以 `X-Token` 请求头携带；30 天滑动过期，登出即销毁。
- **游客**：登录页一键进入，自动创建 `g_<随机串>` 账号；token 存浏览器 localStorage，下次打开自动续登；**7 天不使用自动回收**（连同其数据库与源文件存档）。
- **管理员**：账号密码来自 `.env`，登录后解锁「管理」入口。

### 3.2 数据库隔离（核心设计）

- 每个账号有一个**主库**：注册账号 `u_<用户名>`，游客 `g_<随机串>`；也可以另建 / 导入更多库。
- 每个库配一个**专用 MySQL 账号** `m_<随机hex>`，只 `GRANT` 这一个库，并限制 `MAX_USER_CONNECTIONS 5`。
- 学生的 SQL、导入、Python 连库全部走这个受限账号；root 仅在容器内部做开通/管理，**权限上天然读不到别人的库**。
- MySQL 以 `--lower-case-table-names=1` 启动，表名大小写不敏感（Windows/课堂习惯友好）。
- 删除库需二次确认，误删有提示。

### 3.3 SQL 工作台

- **不用分号**：像 mysql 命令行一样直接写；多行语句（如 `CREATE TABLE ...` 跨多行）按关键字智能聚合成一条；也兼容分号分隔。
- `Ctrl+Enter`（Mac `Cmd+Enter`）运行；`Ctrl+Space` 呼出 SQL 补全（表名 / 列名 / 关键字）。
- 输出：mysql 风格深色控制台，逐条显示语句、结果集（最多返回 **500 行**，超出会提示）、影响行数、耗时。
- 错误显示 MySQL 原始报错 + 中文友好提示（按 errno 映射）；表名打错时给出「您是想 … 吗」建议。
- **表列表**：侧栏数据库树；点表名打开预览弹窗——「数据」（前 200 行）/「结构」（DESCRIBE）/「源文件」（导入时的原始文件）三个页签，可一键「查询前 20 条 → 编辑器」。
- **草稿**：SQL 编辑器内容按账号存浏览器 localStorage，刷新 / 手机切后台不丢；清空即清除草稿。首次进入预填 `SELECT * FROM emp`。
- 每个库支持：导出 `.sql`、生成私有分享链接、发布到社区、删除。

### 3.4 文件导入

- 支持 **CSV**（自动识别 UTF-8 / GBK 编码，可选首行是否表头）、**Excel .xlsx**、**SQL 脚本**（逐条执行建库）。
- 自动推断列类型（INT / DOUBLE / DATE / VARCHAR）并建表。
- 上限：单文件 **5MB**、单次 **2 万行**、单表 **64 列**。
- 导入为**独立的新库**（仅导入者可见），可自定义库名；同名表可选择覆盖。
- 导入的源文件自动存档，在表预览弹窗里随时查看 / 下载。

### 3.5 社区与分享（两条独立路径）

| | 私有分享链接 | 社区广场 |
|---|---|---|
| 入口 | 工作台侧栏「分享链接」 | 社区页上传 / 「发布到社区」 |
| 可见范围 | 只有拿到 `/s/<code>` 链接的人，登录后可导入 | 全站可见 |
| 用途 | 把课件库发给某个班 / 某个同学 | 全班共享教学资源 |
| 导入 | 可自定义导入后的库名 | 一键「导入整个数据库」或下载 .sql / .py |

- 整库 SQL 脚本上传 ≤ **8MB**，自动解析表清单；Python 代码 ≤ 256KB；表格 ≤ 8MB。
- 从社区下载的资源**不能再分享回社区**（防止循环搬运刷屏）。
- 内置资源带 builtin 标记，管理员可在后台删除任意社区资源。

### 3.6 Python 沙箱

- **交互式作业**：提交代码后即可看到输出，`input()` 真的能用——控制台出现输入框，提示语即时可见，超时 120 秒无动静自动结束；单次运行总时长上限 **300 秒**。
- **进程级限制**：CPU 8 秒、内存 256MB、单文件写入 4MB、文件句柄 128、进程数 64（防死循环 / 内存炸弹 / fork 炸弹）。
- **容器级加固**：runner 容器只读根文件系统、`tmpfs /tmp`、进程数上限 96、内存上限 768MB、位于 internal 网络**无外网**、不对外暴露端口。
- **预置助手**（无需 import）：`query(sql)` 查询、`query_dicts(sql)` 字典查询、`execute(sql)` 增删改（自动 commit）、`get_conn()` 原生 pymysql 连接（已填好自己库的地址账号）。也支持手写 `import pymysql`。
- **开箱示例**：新账号的 `main.py` 预置「查 emp 工资前 5 名」示例，点开即可运行。
- **多文件**：最多 30 个 `.py`，保存在服务器，换设备登录不丢；示例下拉含 Hello World / 循环函数 / 连库查询 / input 交互 / 手写 pymysql 五个模板。
- 报错时过滤沙箱内部栈帧，只显示与学生代码相关的 traceback。

### 3.7 管理后台

- 两个页签：**注册用户** / **游客**；显示账号、库名、注册 IP 与最近活跃 IP。
- 操作：重置学生密码、删除账号（连同其所有库、MySQL 账号、Python 文件一起删）、删除社区资源。

### 3.8 前端与移动端

- Vue 3 单页应用 + CodeMirror 5，全部本地内置（vendor 目录），**内网断外网也能用**。
- 全站 MiSans 字体（代码区拉丁字符等宽、中文 MiSans）；GitHub Primer 风格配色；深 / 浅色主题切换；图标全部为内置 SVG。
- **手机竖屏（<900px）**：底部三标签（MySQL / Python / 社区）；编辑器独占屏幕；表 / 文件列表收进抽屉（悬浮按钮唤起）；控制台固定在上方；键盘弹出自动收起底栏（visualViewport 检测）；输入框字号 ≥16px 防 iOS 自动缩放。
- **电脑横屏（≥900px）**：左侧数据库树 + 右侧编辑器 / 控制台分栏。
- 静态资源带版本号（`app.js?v=N`），改版后升 N 即可强刷缓存。

## 四、API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/login` | 登录 / 注册 / 游客（mode 参数） |
| POST | `/api/logout` | 登出 |
| GET | `/api/me` | 当前用户 + 库列表 + 主库表 |
| GET/POST/DELETE | `/api/databases` | 库列表 / 新建库 / 删除库 |
| GET | `/api/databases/{name}/tables` | 指定库的表清单 |
| GET | `/api/databases/{name}/export` | 导出整库 .sql |
| POST | `/api/sql` | 执行 SQL（多语句，逐条返回结果/影响行数） |
| POST | `/api/import` | 上传 csv / xlsx / sql 导入 |
| GET | `/api/community` | 社区资源列表 |
| POST | `/api/community/upload` | 上传资源到社区 |
| POST | `/api/community/publish` | 把我的库发布到社区 |
| GET | `/api/community/by-code/{code}` | 解析分享链接 |
| POST | `/api/community/import` | 导入社区/分享资源到我的空间 |
| GET | `/api/community/{id}/detail` | 资源详情（表清单/预览） |
| GET | `/api/community/{id}/download` | 下载资源文件 |
| DELETE | `/api/community/{id}` | 删除资源（管理员/上传者） |
| POST | `/api/community/open` | 打开社区里的 .py 到编辑器 |
| GET/PUT/DELETE | `/api/pyfiles[/{name}]` | Python 多文件的列表 / 读写 / 删除 |
| POST | `/api/pyrun/start` | 提交 Python 代码 → 作业 id |
| POST | `/api/pyrun/input` | 向运行中程序写 stdin |
| GET | `/api/pyrun/status/{job}` | 轮询输出 / 状态 |
| GET | `/api/source/{table}[/download]` | 表的源文件存档查看 / 下载 |
| GET | `/s/{code}` | 分享链接落地页 |
| GET | `/api/admin/users` | 用户 / 游客列表（含 IP） |
| POST | `/api/admin/reset_password` | 重置学生密码 |
| POST | `/api/admin/delete_user` | 删除账号（连库） |
| GET | `/api/health` | 健康检查 |

## 五、使用指南（学生篇 / 教师篇）

### 学生篇

1. **第一次进入**：浏览器打开老师给的网址 → 点「游客试用」或注册账号 → 自动获得三张教学表。
2. **写 SQL**：编辑器直接写（不用分号），点「运行」或 `Ctrl+Enter`。例如：
   ```sql
   SELECT ENAME, SAL FROM emp WHERE SAL > 2000 ORDER BY SAL DESC
   SELECT DNAME, COUNT(*) FROM emp e JOIN dept d ON e.DEPTNO = d.DEPTNO GROUP BY DNAME
   ```
3. **点表名**：左侧点开数据库 → 点表名 → 看 / 找数据、看结构、看建表语句，或一键把 `SELECT ... LIMIT 20` 填进编辑器。
4. **导入自己的数据**：「导入文件」上传 CSV / Excel / SQL 脚本 → 变成自己的库，随时查询。
5. **Python 连数据库**：切到 Python 页，直接用内置函数：
   ```python
   rows = query("SELECT ENAME, JOB, SAL FROM emp ORDER BY SAL DESC LIMIT 5")
   for name, job, sal in rows:
       print(name, job, sal)

   n = execute("UPDATE emp SET SAL = SAL * 1.1 WHERE DEPTNO = 20")  # 自动 commit
   print("影响行数：", n)
   ```
6. **交作业**：工作台选中数据库 →「导出 .sql」→ 把文件交给老师；或用「分享链接」生成私有链接发给老师。

### 教师篇

1. **部署**：见下方[部署手册](#七部署手册)，一次部署全班使用。
2. **发课件库**：把课件 SQL（如 bjpowernode.sql）在工作台导入 →「发布到社区」，全班在社区页一键导入；只想给某个班就用「分享链接」。
3. **留 Python 作业模板**：社区页上传 `.py` 文件，学生可一键「打开到编辑器」运行。
4. **课堂管理**：右上角「管理」查看谁注册了（含 IP）、重置忘记密码的学生、删除捣乱账号。
5. **换教学库**：`.env` 改不动内置表；新账号统一送 bjpowernode 三张表，其他库由你通过社区分发。

## 六、配置参考（.env）

复制 `.env.example` 为 `.env` 后修改。全部参数（带默认值）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `WEB_PORT` | `8000` | 对外端口 |
| `MYSQL_ROOT_PASSWORD` | `change-me-root` | MySQL root 密码（仅容器内部管理用，**务必修改**） |
| `ADMIN_USER` / `ADMIN_PASSWORD` | `admin` / `admin123` | 管理员账号（**务必修改**） |
| `RUNNER_TOKEN` | `change-me-runner-token` | web↔runner 内部令牌（**务必修改**） |
| `PYTHON_VERSION` | `3.12` | 沙箱 Python 版本，可填 `3.14` |
| `PYTHON_IMAGE` | `python` | 基础镜像仓库（国内可换 daocloud 源） |
| `MYSQL_IMAGE` | `mysql:5.7` | **必须带 `:5.7` 标签**，否则数据目录不兼容 |
| `TRUST_PROXY` | 空 | 在宝塔/Nginx 反代后面设 `1`（限流按真实学生 IP） |
| `GUEST_TTL_DAYS` | `7` | 游客数据保留天数 |
| `SESSION_TTL_DAYS` | `30` | 登录态保留天数 |
| `SQL_TIMEOUT_SEC` | `10` | 单次 SQL 执行墙钟上限 |
| `PY_IDLE_SEC` | `120` | Python 等待输入 / 无输出的存活秒数 |
| `PY_MAX_SEC` | `300` | Python 单次运行总时长上限 |
| `ROWS_LIMIT` | `500` | 查询结果返回行数上限 |
| `RATE_LIMIT_PER_MIN` | `600` | 每 IP 每分钟请求数（机房共用出口 IP 时调高） |

## 七、部署手册

### 方式 A：宝塔面板（推荐：域名 + HTTPS，学生任何设备可访问）

前提：云服务器 1核2G 起步（国内需已备案域名），已安装宝塔面板。

1. **装 Docker**：宝塔 → Docker → 安装（Docker 和 Docker Compose 一起装）。
2. **上传项目**：宝塔 → 文件 → `/www` 下新建 `sqlpy-lab` → 项目压缩成 zip 上传后解压（或 `git clone` 本仓库）。
3. **配置 .env**：进入项目目录，复制 `.env.example` 为 `.env`，**改掉全部默认密码**；服务器拉不动 docker.io 时取消注释 `PYTHON_IMAGE / MYSQL_IMAGE` 两行镜像源。
4. **构建启动**：宝塔 → 终端：
   ```bash
   cd /www/sqlpy-lab
   docker compose up -d --build     # 老版宝塔用 docker-compose
   docker compose ps                # 等 db 显示 healthy
   ```
5. **放行端口**：宝塔 → 安全 → 放行 80/443（8000 可不对公网开放，只给反代用）。
6. **域名反代**：宝塔 → 网站 → 添加站点（填域名，纯静态）→ 站点设置 → 反向代理 → 目标 `http://127.0.0.1:8000`。
   **必须**：在该站点的 Nginx 配置里加一行 `client_max_body_size 20m;`（默认 1MB 会导致上传失败）。
7. **HTTPS**：站点设置 → SSL → Let's Encrypt 一键申请 → 开启强制 HTTPS。
8. **真实 IP 限流**：`.env` 设 `TRUST_PROXY=1`，`docker compose up -d` 重启（反代下限流按学生真实 IP 计算）。
9. 学生访问 `https://你的域名` 即可。

### 方式 B：内网机房 / 本机直跑（最简单）

教师机装 Docker Desktop → `docker compose up -d --build` → 学生访问 `http://教师机IP:8000`（`ipconfig` 查 IP；打不开就放行防火墙：`netsh advfirewall firewall add rule name="SQLPy-Lab" dir=in action=allow protocol=TCP localport=8000`）。不需要域名证书。

### 镜像拉取失败（国内常见）

`.env` 取消注释：

```
PYTHON_IMAGE=docker.m.daocloud.io/library/python
MYSQL_IMAGE=docker.m.daocloud.io/library/mysql:5.7
```

再 `docker compose up -d --build`。注意 `MYSQL_IMAGE` 必须带 `:5.7`。

## 八、运维手册

```bash
docker compose ps              # 三容器状态（db 应为 healthy）
docker compose logs -f web     # 应用日志
docker compose up -d --build   # 改代码 / 改 .env 后重建生效
docker compose down            # 停止（数据保留在 dbdata 卷）
docker compose down -v         # 清空所有数据（危险）（含全部学生库）
```

- **数据在哪**：所有业务数据都在 Docker 卷 `dbdata`（MySQL 数据目录）；源文件存档、社区资源存在 MySQL 的 meta / community 库里，不落宿主机文件系统。
- **备份**：
  ```bash
  docker exec mysqlpython-db-1 sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --all-databases' > backup.sql
  ```
- **恢复**：`docker exec -i mysqlpython-db-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' < backup.sql`
- **升级**：`git pull` → `docker compose up -d --build`（数据不受影响）。
- **改前端**：改 `backend/app/static/` 下的文件后必须重建镜像（静态文件打进镜像，不是挂载），并把 `index.html` 里的 `app.js?v=N` / `style.css?v=N` 升一位强刷缓存。

## 九、测试

```bash
# 本地单元测试（不需要 MySQL / Docker，秒级完成）
python tests/local_test.py

# 端到端烟测（需要站点已跑起来）
python tests/smoke_test.py                 # 默认打 http://localhost:8000
python tests/smoke_test.py http://其他地址  # 也可以指定
```

- `local_test.py`（95 项）：SQL 语句切分、无分号多行聚合、导入解析、密码策略、沙箱执行引擎（正常输出 / 报错 / 死循环 / input 交互）等纯逻辑。
- `smoke_test.py`（101 项）：注册 → 建库 → SQL → 导入三种格式 → 社区上传/导入/下载 → Python 运行与连库 → 隔离与权限 → 管理员 → 弱密码拦截的全流程。

## 十、安全模型

| 层 | 措施 |
|---|---|
| 账号 | 密码 PBKDF2-SHA256 加盐 20 万轮；用户名/密码策略拦截弱口令与保留名 |
| 会话 | 随机 token（`X-Token` 头），30 天滑动过期；管理接口校验 admin 角色 |
| 数据库 | 每账号独立库 + 专用 MySQL 账号（仅授权本库，`MAX_USER_CONNECTIONS 5`）；MySQL 不对外暴露端口 |
| Python 沙箱 | 独立 runner 容器：internal 网络（无外网）、只读根文件系统、`cap-drop ALL`、`no-new-privileges`、pids 96、内存 768MB |
| Python 进程 | 每次独立子进程：CPU 8s / 内存 256MB / 写盘 4MB / 进程数 64；120 秒无输出或 300 秒总时长强杀 |
| 接口护栏 | SQL ≤64KB、代码 ≤256KB、导入文件 ≤5MB、社区上传 ≤8MB、查询 ≤500 行、单次导入 ≤2 万行 × 64 列、每 IP 限流 600 次/分钟 |
| 反代 | 宝塔/Nginx 后设 `TRUST_PROXY=1`，限流按学生真实 IP；站点需配 `client_max_body_size 20m` |

## 十一、常见问题

- **页面一直转圈**：MySQL 首次初始化 20~40 秒，等 `docker compose logs -f web` 出现 `Application startup complete`。
- **镜像拉取失败**：见[部署手册](#七部署手册)的镜像源配置。
- **上传文件失败**：宝塔反代没配 `client_max_body_size 20m;`。
- **CSV 中文乱码**：已自动尝试 UTF-8 / GBK；仍乱码请另存为「CSV UTF-8」。
- **游客数据没了**：7 天未用被回收，或换了浏览器 / 清了浏览器数据；注册账号可避免。
- **刷新后 SQL 没了**：不会丢——SQL 编辑器草稿按账号存在浏览器里；换浏览器前先「导出 .sql」。
- **Python 跑太久**：等待输入 120 秒、单次总时长 300 秒会被自动结束，不会拖垮服务器。

---

## 许可

本项目基于 [MIT License](LICENSE) 开源，由 AI Coding 编写。
