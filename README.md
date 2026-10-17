# SQL · Py 课堂实验室（Docker_MySQL-Python）

一个 Docker 一键部署的课堂教学网站：学生打开浏览器就能写 MySQL、跑 Python，什么都不用装。每个学生一个互相隔离的独立数据库，注册或游客一键进入，**点开就能跑通第一条 SQL 和第一段 Python**。

本项目由 AI Coding 编写，基于 [MIT](LICENSE) 协议开源。

详细文档（项目结构 / 功能细则 / 使用指南 / 运维手册）见 [PROJECT.md](PROJECT.md)。

## 项目特点

- **零学习成本**：新账号自动送三张经典教学表（EMP 员工 / DEPT 部门 / SALGRADE 工资等级），SQL 编辑器预填好 `SELECT * FROM emp`，Python 页预置好一段查自己数据库的示例，点一下「运行」就有结果。
- **像真的 mysql 命令行**：SQL 不用写分号，多条语句一行一条；输出是 mysql 风格的深色控制台，语句、结果集、影响行数、耗时逐条追加。
- **像真的 IDE**：CodeMirror 编辑器（行号 / 语法高亮 / 括号匹配 / 自动缩进 / 补全），内置 `query() / execute() / get_conn()` 直连自己的数据库，`input()` 交互也能用。
- **严格隔离**：每个账号一个独立数据库 + 只授权本库的专用 MySQL 账号；Python 代码在独立沙箱容器执行，限 CPU / 内存 / 时长。
- **导入与社区**：CSV / Excel / SQL 脚本上传后自动建表入库；整库可生成私有分享链接发给同学，也可发布到社区广场供全班使用。
- **手机电脑都好用**：手机竖屏底部标签栏 + 抽屉布局，电脑横屏左右分栏；MiSans 字体、GitHub Primer 配色、深浅色主题切换。

## 技术栈与环境

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 + FastAPI + Uvicorn（`.env` 一行可切 Python 3.14） |
| 数据库 | MySQL 5.7（官方 Docker 镜像，数据持久化到 Docker 卷） |
| 驱动 / 解析 | PyMySQL、openpyxl |
| 前端 | 原生 HTML/CSS/JS + Vue 3 + CodeMirror 5（全部本地内置，无 CDN、无构建步骤） |
| 字体 | MiSans（本地内置 4 个字重） |
| 部署 | Docker Compose，3 个容器：`web`（API + 静态页面）/ `runner`（Python 沙箱）/ `db`（MySQL） |

## 快速开始（使用方法）

```bash
git clone https://github.com/qiuxi903/Docker_MySQL-Python.git
cd Docker_MySQL-Python
cp .env.example .env          # Linux/Mac；Windows 直接复制一份改名 .env
# 编辑 .env：改掉 MYSQL_ROOT_PASSWORD / ADMIN_PASSWORD / RUNNER_TOKEN 三个默认值
docker compose up -d --build
```

等 MySQL 初始化 20~40 秒（`docker compose logs -f web` 出现 `Application startup complete` 即就绪），浏览器访问 **http://localhost:8000**：

1. 点「游客试用」直接进入，或注册账号（字母开头、仅字母数字 3-20 位；密码至少 8 位且同时含字母和数字）；
2. MySQL 工作台直接点「运行」，看到 emp 表 14 行结果；
3. 切到 Python 页再点「运行」，看到查询自己数据库的输出。

更多具体用法（写 SQL、导入自己的数据、Python 连库、交作业）见 [PROJECT.md](PROJECT.md) 的使用指南章节。

## 部署方法

| 场景 | 做法 |
|---|---|
| **宝塔面板（推荐，域名 + HTTPS，学生任何设备可访问）** | 宝塔装 Docker，上传项目，配置 `.env`，`docker compose up -d --build`，域名反代 `127.0.0.1:8000`，申请 SSL 证书，`.env` 设 `TRUST_PROXY=1`。完整步骤见 [PROJECT.md](PROJECT.md) 的部署手册。 |
| **内网机房 / 本机** | 教师机装 Docker Desktop，`docker compose up -d --build`，学生访问 `http://教师机IP:8000`。 |

国内服务器拉不动 docker.io 镜像时：`.env` 里取消注释 `PYTHON_IMAGE` / `MYSQL_IMAGE` 两行（daocloud 镜像源）再 build。

## 账号说明

- **管理员**：`.env` 里配置的 `ADMIN_USER / ADMIN_PASSWORD`（默认 admin / admin123，**上线务必修改**）。登录后右上角「管理」：查看注册用户与游客（含 IP）、重置学生密码、删除账号（连库一起删）。
- **注册学生**：自助注册，数据长期保留，换设备登录不丢。
- **游客**：免注册一键进入，数据保存在浏览器里，7 天不使用自动回收。

## 开源协议

[MIT License](LICENSE)
