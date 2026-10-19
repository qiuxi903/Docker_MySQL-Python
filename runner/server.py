"""Python 交互式执行服务（作业模型）。

POST /start                {code, db:{...}, files:{...}} → 启动运行作业，返回 {job}
POST /job/{id}/input       {text}                        → 向运行中的程序标准输入写入一行
GET  /job/{id}/out         ?since_out=&since_err=        → 增量获取输出与运行状态
GET /health                存活检查

作业特性：
- 子进程 stdin 保持打开 → input() 会真正等待用户在控制台输入
- 空闲超时（PY_IDLE_SEC 秒无输出且无输入）→ 结束，防挂机
- 总时长上限（PY_MAX_SEC 秒）→ 强制结束
- CPU/内存/进程数/文件大小 rlimit 照旧生效
"""
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

TOKEN = os.getenv("RUNNER_TOKEN", "change-me-runner-token")
IDLE_LIMIT = float(os.getenv("PY_IDLE_SEC", "120"))  # 无输出/无输入的存活秒数
MAX_LIMIT = float(os.getenv("PY_MAX_SEC", "300"))    # 单次运行总时长上限
CPU_SECONDS = 8
MEM_BYTES = 256 * 1024 * 1024
FSIZE_BYTES = 4 * 1024 * 1024
MAX_OUT = 512 * 1024          # 每路输出缓存上限
MAX_JOBS_RUNNING = 5

_HERE = Path(__file__).parent
HELPERS_SRC = (_HERE / "labhelpers.py").read_text(encoding="utf-8")
_STUDENT_FILENAME_RE = re.compile(r"^[\w\u4e00-\u9fff-]{1,40}\.py$", re.I)

RUN_MAIN = '''import sys, os
try:  # -I 隔离模式会忽略 PYTHONIOENCODING，这里强制 UTF-8 输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
_FILES_DIR = os.path.join(_HERE, "student_files")
if os.path.isdir(_FILES_DIR):
    sys.path.insert(0, _FILES_DIR)
from labhelpers import get_conn, query, query_dicts, execute


def _load():
    with open(os.path.join(_HERE, "code.py"), encoding="utf-8") as f:
        return f.read()


src = _load()
try:
    code = compile(src, "<你的代码>", "exec")
except SyntaxError as e:
    sys.stderr.write("语法错误：第 %s 行：%s\\n" % (e.lineno, e.msg))
    sys.exit(1)

# 让 input() 的提示语立刻出现在控制台（否则管道缓冲下要等程序结束才看到）
_real_input = input


def _input(prompt=""):
    if prompt:
        sys.stdout.write(str(prompt))
        sys.stdout.flush()
    line = sys.stdin.readline()
    if line == "":
        raise EOFError("没有更多输入了")
    return line.rstrip("\\n")


g = {"__name__": "__main__", "input": _input,
     "get_conn": get_conn, "query": query, "query_dicts": query_dicts, "execute": execute}
try:
    exec(code, g)
except SystemExit:
    raise
except BaseException:
    # 只保留学生代码相关的栈帧，报错信息更干净
    import traceback
    et, ev, tb = sys.exc_info()
    t = tb
    while t is not None and t.tb_frame.f_code.co_filename != "<你的代码>":
        t = t.tb_next
    if t is None:
        traceback.print_exception(et, ev, tb)
        sys.exit(1)
    lines = ["Traceback (most recent call last):"]
    f = t
    while f is not None:
        lines.append('  文件 "<你的代码>", 第 %d 行' % f.tb_lineno)
        f = f.tb_next
    lines.append("%s: %s" % (et.__name__, ev))
    sys.stderr.write("\\n".join(lines) + "\\n")
    sys.exit(1)
'''


class StartReq(BaseModel):
    code: str
    db: dict = {}
    files: dict[str, str] = {}


class InputReq(BaseModel):
    text: str


class Job:
    def __init__(self, job_id, proc, td):
        self.lock = threading.RLock()
        self.id = job_id
        self.proc = proc
        self.td = td
        self.out = bytearray()
        self.err = bytearray()
        self.out_done = False
        self.err_done = False
        self.done = False
        self.exit = None
        self.timed_out = False
        self.why = ""
        self.start = time.time()
        self.last_activity = time.time()


jobs = {}
jobs_lock = threading.Lock()


def _limits():
    import resource

    for res, soft in (
        (resource.RLIMIT_CPU, CPU_SECONDS),
        (resource.RLIMIT_AS, MEM_BYTES),
        (resource.RLIMIT_FSIZE, FSIZE_BYTES),
        (resource.RLIMIT_NOFILE, 128),
    ):
        try:
            resource.setrlimit(res, (soft, soft))
        except (ValueError, OSError):
            pass
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except (ValueError, OSError):
        pass
    os.setsid()  # 独立进程组，超时可整组击杀


def _kill(job):
    with job.lock:
        job.timed_out = True
        try:
            os.killpg(os.getpgid(job.proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                job.proc.kill()
            except Exception:
                pass


def _pump(job):
    """后台线程：持续读取子进程 stdout/stderr 到缓存，直到各自 EOF。"""
    def read(stream, buf, flag):
        # 用 os.read 而非 readline：input() 的提示语通常不带换行，
        # readline 会一直阻塞等换行，提示就永远显示不出来。
        try:
            fd = stream.fileno()
            while True:
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
                with job.lock:
                    buf.extend(chunk)
                    if len(buf) > MAX_OUT:
                        del buf[: len(buf) - MAX_OUT]
                    job.last_activity = time.time()
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass
            with job.lock:
                setattr(job, flag, True)

    t_out = threading.Thread(target=read, args=(job.proc.stdout, job.out, "out_done"), daemon=True)
    t_err = threading.Thread(target=read, args=(job.proc.stderr, job.err, "err_done"), daemon=True)
    t_out.start()
    t_err.start()


def _finish_watch(job):
    """等待进程退出并记录。"""
    code = job.proc.wait()
    with job.lock:
        job.done = True
        job.exit = code
        job.ended = time.time()
        try:
            if job.proc.stdin:
                job.proc.stdin.close()
        except Exception:
            pass


def _watchdog(job):
    while True:
        time.sleep(1)
        with job.lock:
            if job.done:
                return
            now = time.time()
            run_for = now - job.start
            idle_for = now - job.last_activity
        if idle_for > IDLE_LIMIT:
            with job.lock:
                job.why = "idle"
            _kill(job)
            return
        if run_for > MAX_LIMIT:
            with job.lock:
                job.why = "max"
            _kill(job)
            return


def _cleanup_later(job):
    def loop():
        job.proc.wait()
        time.sleep(600)
        import shutil

        shutil.rmtree(job.td, ignore_errors=True)
    threading.Thread(target=loop, daemon=True).start()


@app.get("/health")
def health():
    with jobs_lock:
        running = sum(1 for j in jobs.values() if not j.done)
    return {"ok": True, "jobs": running}


def start_job(code: str, db: dict, files: dict[str, str] | None = None) -> str:
    with jobs_lock:
        running = sum(1 for j in jobs.values() if not j.done)
        if running >= MAX_JOBS_RUNNING:
            raise HTTPException(429, "同时运行的程序太多，请稍后再试")
        job_id = secrets.token_hex(8)

    td = tempfile.mkdtemp(prefix="pyrun_")
    try:
        (Path(td) / "code.py").write_text(code, encoding="utf-8")
        (Path(td) / "labhelpers.py").write_text(HELPERS_SRC, encoding="utf-8")
        (Path(td) / "run_main.py").write_text(RUN_MAIN, encoding="utf-8")
        student_dir = Path(td) / "student_files"
        if files:
            student_dir.mkdir()
        for name, content in (files or {}).items():
            (student_dir / name).write_text(content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"无法准备运行环境：{e}")

    db = db or {}
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": td,
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    if db:
        env.update({
            "DB_HOST": str(db.get("host", "")),
            "DB_PORT": str(db.get("port", "3306")),
            "DB_USER": str(db.get("user", "")),
            "DB_PASS": str(db.get("pass", "")),
            "DB_NAME": str(db.get("name", "")),
        })

    t0 = time.time()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-u", "-X", "utf8", str(Path(td) / "run_main.py")],
            cwd=td, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=_limits if os.name == "posix" else None,
        )
    except Exception as e:
        raise HTTPException(500, f"启动失败：{e}")

    job = Job(job_id, proc, td)
    with jobs_lock:
        jobs[job_id] = job
    threading.Thread(target=_pump, args=(job,), daemon=True).start()
    threading.Thread(target=_finish_watch, args=(job,), daemon=True).start()
    threading.Thread(target=_watchdog, args=(job,), daemon=True).start()
    threading.Thread(target=_cleanup_later, args=(job,), daemon=True).start()
    _ = t0
    return job_id


@app.post("/start")
def start_run(req: StartReq, x_runner_token: str = Header(default="")):
    if x_runner_token != TOKEN:
        raise HTTPException(401, "forbidden")
    if len(req.code.encode("utf-8")) > 256 * 1024:
        raise HTTPException(400, "代码超过 256KB 上限")
    if len(req.files) > 30 or any(
            not isinstance(content, str)
            or not _STUDENT_FILENAME_RE.fullmatch(name)
            or len(content.encode("utf-8")) > 256 * 1024
            for name, content in req.files.items()):
        raise HTTPException(400, "Python 文件列表无效或超过限制")
    job_id = start_job(req.code, req.db, req.files)
    return {"job": job_id}


@app.post("/job/{job_id}/input")
def job_input(job_id: str, req: InputReq, x_runner_token: str = Header(default="")):
    if x_runner_token != TOKEN:
        raise HTTPException(401, "forbidden")
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.done:
        raise HTTPException(400, "程序已结束运行")
    text = (req.text or "").replace("\r\n", "\n").replace("\r", "\n")
    try:
        job.proc.stdin.write((text + ("\n" if not text.endswith("\n") else "")).encode("utf-8"))
        job.proc.stdin.flush()
    except Exception:
        raise HTTPException(400, "程序已关闭输入")
    with job.lock:
        job.last_activity = time.time()
    return {"ok": True}


@app.get("/job/{job_id}/out")
def job_out(job_id: str, since_out: int = 0, since_err: int = 0,
            x_runner_token: str = Header(default="")):
    if x_runner_token != TOKEN:
        raise HTTPException(401, "forbidden")
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    with job.lock:
        out = bytes(job.out)
        err = bytes(job.err)
        running = not job.done
        exit_code = job.exit
        timed_out = job.timed_out
        why = job.why
    return {
        "running": running,
        "exit": exit_code,
        "timed_out": timed_out,
        "why": why,
        "out": out[since_out:].decode("utf-8", "replace"),
        "err": err[since_err:].decode("utf-8", "replace"),
    }


