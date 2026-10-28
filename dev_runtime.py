"""Linux/WSL development process ownership; never kill by listening port."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import time


def process_identity(pid):
    # /proc comm may contain spaces and parentheses; field 22 is starttime.
    return Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]


@contextmanager
def runner_lock(root):
    fd = os.open(root / ".portal-dev.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    locked = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("已有 Portal 开发启动器运行；请先 make stop 或在原终端 Ctrl+C。") from None
        locked = True
        os.fchmod(fd, 0o600)
        os.ftruncate(fd, 0)
        record = {"pid": os.getpid(), "starttime": process_identity(os.getpid()), "root": str(root)}
        os.write(fd, json.dumps(record).encode())
        os.fsync(fd)
        yield
    finally:
        if locked:
            os.ftruncate(fd, 0)
        os.close(fd)  # Keep inode so concurrent runners cannot bypass flock.


def stop_runner(root):
    try:
        record = json.loads((root / ".portal-dev.lock").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        print("没有记录到本项目运行中的开发启动器。")
        return 0
    pid = record.get("pid")
    if not isinstance(pid, int) or pid <= 1 or record.get("root") != str(root):
        raise RuntimeError("启动器记录无效，未终止任何进程。")
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        print("上次启动器已退出；未终止其他进程。")
        return 0
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        is_runner = any(Path(os.fsdecode(arg)).name == "run_dev.py" for arg in args if arg)
        if (process_identity(pid) != record.get("starttime") or not is_runner
                or Path(f"/proc/{pid}/cwd").resolve() != root):
            raise RuntimeError("进程身份与本项目启动记录不符，未终止任何进程。")
        signal.pidfd_send_signal(fd, signal.SIGTERM)
        poller = select.poll()
        poller.register(fd, select.POLLIN)
        if not poller.poll(12000):
            raise RuntimeError("已请求停止，启动器尚未退出；请查看原终端。未强杀进程。")
        print("本次 Portal 开发服务已停止。")
        return 0
    except (ProcessLookupError, FileNotFoundError):
        return 0
    finally:
        os.close(fd)


class Children:
    def __init__(self):
        self.processes = []

    def start(self, name, command, *, cwd, env):
        process = subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True)
        self.processes.append((name, process))
        return process

    def close(self):
        handles = []
        groups = {process.pid for _, process in self.processes}
        # Keep pidfds for descendants too: terminating uv does not reap uvicorn.
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                group = int((entry / "stat").read_text().rsplit(") ", 1)[1].split()[2])
                if group in groups:
                    handles.append(os.pidfd_open(int(entry.name)))
            except (ProcessLookupError, FileNotFoundError, PermissionError):
                pass
        for _, process in self.processes:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 5
        for _, process in self.processes:
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        # Only groups created above, including descendants of an exited uv parent.
        for _, process in self.processes:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        self.processes.clear()
        try:
            poller = select.poll()
            for fd in handles:
                poller.register(fd, select.POLLIN)
            pending = set(handles)
            deadline = time.monotonic() + 3
            while pending and time.monotonic() < deadline:
                for fd, _ in poller.poll(100):
                    pending.discard(fd)
                    poller.unregister(fd)
            if pending:
                raise RuntimeError("本次部分子进程尚未退出；请查看原终端，未停止无关进程。")
        finally:
            for fd in handles:
                os.close(fd)
