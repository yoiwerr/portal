#!/usr/bin/env python3
"""Portal local entry: Python :8001, Journal :8002, Go auth :8083, proxy :8080.

Run with `make dev` on Linux/WSL. Only this runner's process groups are stopped.
The proxy preserves auth/error/redirect responses and flushes SSE immediately.
"""

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import http.server
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from dev_runtime import Children, runner_lock, stop_runner

ROOT = Path(__file__).parent.resolve()
PORTAL_STATIC = ROOT / "static"
API_DUDE = "http://127.0.0.1:8001"
API_JOURNAL = "http://127.0.0.1:8002"
API_ADMIN = "http://127.0.0.1:8083"
DUDE_API_PREFIXES = (
    "/api/chat", "/api/sessions", "/api/knowledge", "/api/feedback",
    "/api/files", "/api/handover", "/api/health",
)


def _under(path, prefix):
    return path == prefix or path.startswith(prefix + "/")


def proxy_route(request_path):
    """Path-only matching; preserve query strings and match Go before Python."""
    parsed = urllib.parse.urlsplit(request_path)
    path = parsed.path
    if _under(path, "/alfred"):
        path = "/dude" + path[len("/alfred"):]
    query = "?" + parsed.query if parsed.query else ""
    for area in ("auth", "admin"):
        if _under(path, f"/dude/{area}"):
            sub = path[len("/dude"):]
            static = f"/{area}/static/"
            if sub.startswith(static):
                sub = "/static/" + sub[len(static):]
            return API_ADMIN + sub + query, ""
        for prefix in (f"/dude/api/v1/{area}", f"/dude/api/{area}"):
            if _under(path, prefix):
                return API_ADMIN + f"/api/v1/{area}" + path[len(prefix):] + query, ""
    if _under(path, "/journal"):
        return API_JOURNAL + path + query, ""
    if _under(path, "/dude"):
        return API_DUDE + (path[len("/dude"):] or "/") + query, "/dude"
    if any(_under(path, p) for p in DUDE_API_PREFIXES):
        return API_DUDE + path + query, "/dude"
    return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


class PortalHandler(http.server.SimpleHTTPRequestHandler):
    def _retired(self, path):
        if path.startswith("/chatlab") or path in ("/css/chatlab.css", "/js/chatlab.js"):
            self.send_error(410, "This project has been archived")
            return True
        return False

    def _dispatch(self):
        path = urllib.parse.urlsplit(self.path).path
        if self._retired(path):
            return
        if self.command in ("GET", "HEAD") and path in ("/dude", "/dude/auth", "/dude/admin", "/alfred", "/alfred/auth", "/alfred/admin"):
            query = urllib.parse.urlsplit(self.path).query
            self.send_response(308)
            self.send_header("Location", path.replace("/alfred", "/dude", 1) + "/" + ("?" + query if query else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        route = proxy_route(self.path)
        if route:
            return self._proxy(self.command, route[0], prefix=route[1])
        if path.startswith("/api"):
            return self.send_error(410, "This API has been retired")
        if self.command not in ("GET", "HEAD"):
            return self.send_error(405)
        return self._serve_file(PORTAL_STATIC / urllib.parse.unquote(path).lstrip("/"))

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _dispatch

    def _serve_file(self, fp):
        allowed = PORTAL_STATIC.resolve()
        # Revalidate directory index and .html fallback too, including symlinks.
        for candidate in (fp, fp / "index.html", fp.with_suffix(fp.suffix + ".html")):
            try:
                resolved = candidate.resolve()
                if not resolved.is_relative_to(allowed):
                    return self.send_error(403)
                if not resolved.is_file():
                    continue
                content = resolved.read_bytes()
            except (OSError, ValueError):
                continue
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(str(resolved)))
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)
            return
        self.send_error(404)

    def _proxy(self, method, target, *, prefix=""):
        if self.headers.get("Transfer-Encoding"):
            return self.send_error(400, "Chunked request bodies are not supported")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 80 * 1024 * 1024:
                return self.send_error(413)
        except ValueError:
            return self.send_error(400, "Invalid Content-Length")
        body = self.rfile.read(length) if length else None
        request = urllib.request.Request(target, data=body, method=method)
        for header in ("Content-Type", "Authorization", "Accept", "Cookie", "X-Journal-Request", "Last-Event-ID"):
            if header in self.headers:
                request.add_header(header, self.headers[header])
        request.add_header("X-Forwarded-Proto", "http")
        request.add_header("X-Forwarded-For", self.client_address[0])
        request.add_header("X-Forwarded-Host", self.headers.get("Host", "localhost:8080"))
        try:
            try:
                response = _opener().open(request, timeout=300)
            except urllib.error.HTTPError as error:
                response = error
        except (OSError, urllib.error.URLError):
            return self.send_error(502, "Local backend unavailable")
        with response:
            is_stream = response.headers.get_content_type() == "text/event-stream"
            content = None if is_stream else response.read()
            if content and prefix and response.headers.get_content_type() == "text/html":
                content = re.sub(rb"(<head[^>]*>)", rf'\1<base href="{prefix}/">'.encode(), content, count=1)
            self.send_response(response.status)
            excluded = {"connection", "keep-alive", "transfer-encoding", "content-length", "server", "date", "trailer", "upgrade", "proxy-authenticate", "proxy-authorization"}
            excluded.update(h.strip().lower() for h in response.headers.get("Connection", "").split(","))
            for key, value in response.headers.items():
                if key.lower() in excluded:
                    continue
                if key.lower() == "location":
                    value = self._redirect_location(value, target)
                self.send_header(key, value)
            if is_stream:
                self.send_header("Connection", "close")
                self.send_header("X-Accel-Buffering", "no")
                self.close_connection = True
            else:
                size = response.headers.get("Content-Length", "0") if method == "HEAD" else str(len(content))
                self.send_header("Content-Length", size)
            self.end_headers()
            if method == "HEAD":
                return
            try:
                if is_stream:
                    while chunk := response.read1(8192):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                else:
                    self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True

    def _redirect_location(self, location, target):
        parsed = urllib.parse.urlsplit(urllib.parse.urljoin(target, location))
        upstream = urllib.parse.urlsplit(target)
        if (parsed.scheme, parsed.netloc) != (upstream.scheme, upstream.netloc):
            return location
        path = parsed.path
        if upstream.netloc in (urllib.parse.urlsplit(API_ADMIN).netloc, urllib.parse.urlsplit(API_DUDE).netloc):
            if not _under(path, "/dude"):
                path = "/dude" + path
        return urllib.parse.urlunsplit(("", "", path, parsed.query, parsed.fragment))

    def log_message(self, fmt, *args):
        print(f"  [{self.command}] {urllib.parse.urlsplit(self.path).path}")


@dataclass(frozen=True)
class Service:
    name: str
    directory: str
    port: int
    health: str
    command: tuple[str, ...]
    prepare: tuple[str, ...] = ()


SERVICES = (
    Service("dude", "dude", 8001, "/api/health", ("uv", "run", "--frozen", "python", "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8001")),
    Service("Journal", "Journal", 8002, "/journal/health", ("uv", "run", "--frozen", "python", "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8002")),
    Service("dude-admin", "dude/dude-admin", 8083, "/api/v1/health", ("{build}/dude-admin",),
            ("go", "build", "-mod=readonly", "-o", "{build}/dude-admin", "./cmd/gateway")),
)


def _development_environment(source):
    env = dict(source)
    for name in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT", "PIP_REQUIRE_VIRTUALENV"):
        env.pop(name, None)
    for name in ("JWT_SECRET", "ADMIN_INIT_PASSWORD", "PGSQLPASSWORD"):
        if not env.get(name) or env[name].startswith("replace-with-"):
            raise RuntimeError(f"请在根 .env 配置 {name}；不会启用旧默认凭证。")
    if len(env["JWT_SECRET"]) < 32:
        raise RuntimeError("JWT_SECRET 至少需要 32 字符，并与 Go/Python 共用。")
    if env["ADMIN_INIT_PASSWORD"] == "admin123":
        raise RuntimeError("请替换 ADMIN_INIT_PASSWORD 的旧弱默认值。")
    for canonical, legacy, default in (
        ("DB_HOST", "PG_HOST", "localhost"), ("DB_PORT", "PG_PORT", "5432"),
        ("DB_NAME", "PG_DATABASE", "alfred"), ("DB_USER", "PG_USER", "postgres"),
    ):
        env[canonical] = env.get(canonical) or env.get(legacy) or default
    host = env["DB_HOST"]
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    quote = lambda value: urllib.parse.quote(value, safe="")
    env["DATABASE_URL"] = (f"postgresql://{quote(env['DB_USER'])}:{quote(env['PGSQLPASSWORD'])}"
                           f"@{host}:{int(env['DB_PORT'])}/{quote(env['DB_NAME'])}")
    if not env.get("JOURNAL_DATABASE_URL"):
        password = env.get("JOURNAL_DB_PASSWORD", "")
        if not password or password.startswith("replace-with-"):
            raise RuntimeError("请配置 JOURNAL_DATABASE_URL 或 JOURNAL_DB_PASSWORD。")
        env["JOURNAL_DATABASE_URL"] = (f"postgresql+psycopg://journal_user:{quote(password)}"
                                       f"@{host}:{int(env['DB_PORT'])}/journal")
    env["ADMIN_HOST"], env["ADMIN_PORT"] = "127.0.0.1", "8083"
    return env


def _port_owner(port):
    if shutil.which("ss"):
        result = subprocess.run(["ss", "-H", "-ltnp", f"sport = :{port}"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    except OSError:
        return "端口无法绑定（进程信息不可用）；请用 ss -ltnp 检查"
    return None


def _ensure_ports_free(ports):
    details = [f"  :{port}: {owner}" for port in ports if (owner := _port_owner(port))]
    if details:
        raise RuntimeError("端口已被占用，请先确认对应进程：\n" + "\n".join(details))


def _check_health(url, timeout=1):
    try:
        with _opener().open(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def _wait_for_backends(backends, timeout=60):
    ready = set()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        exited = [(s.name, p.poll()) for s, p in backends if p.poll() is not None]
        if exited:
            raise RuntimeError("服务提前退出：" + ", ".join(f"{n} (code {c})" for n, c in exited))
        with ThreadPoolExecutor(max_workers=len(backends)) as executor:
            probes = {executor.submit(_check_health, f"http://127.0.0.1:{s.port}{s.health}"): s
                      for s, _ in backends if s.name not in ready}
            for future, service in probes.items():
                if future.result():
                    ready.add(service.name)
                    print(f"  [OK] {service.name} ready")
        if len(ready) == len(backends):
            if all(p.poll() is None for _, p in backends):
                return
        time.sleep(0.2)
    raise RuntimeError("健康检查超时：" + ", ".join(s.name for s, _ in backends if s.name not in ready))


def _interrupted(signum, frame):
    raise KeyboardInterrupt


def main():
    if sys.argv[1:] == ["--stop"]:
        return stop_runner(ROOT)
    if sys.argv[1:]:
        raise RuntimeError("用法：python run_dev.py [--stop]")
    signal.signal(signal.SIGINT, _interrupted)
    signal.signal(signal.SIGTERM, _interrupted)
    with runner_lock(ROOT):
        env = _development_environment(os.environ)
        _ensure_ports_free(tuple(s.port for s in SERVICES) + (8080,))
        for tool in ("go", "uv"):
            if not shutil.which(tool):
                raise RuntimeError(f"缺少 {tool}；请先按 README 安装开发依赖。")
        with tempfile.TemporaryDirectory(prefix="portal-dev-build-") as build:
            children = Children()
            try:
                for service in SERVICES:
                    if service.prepare:
                        print(f"[BUILD] {service.name}", flush=True)
                        process = children.start(service.name + " build", [arg.format(build=build) for arg in service.prepare], cwd=ROOT/service.directory, env=env)
                        if process.wait() != 0:
                            raise RuntimeError(f"{service.name} 构建失败；未启动后端。")
                        children.processes.remove((service.name + " build", process))
                backends = [(s, children.start(s.name, [arg.format(build=build) for arg in s.command], cwd=ROOT/s.directory, env=env)) for s in SERVICES]
                _wait_for_backends(backends)
                with http.server.ThreadingHTTPServer(("127.0.0.1", 8080), PortalHandler) as server:
                    server.timeout = 0.2
                    print("[READY] Portal http://localhost:8080/\n"
                          "  dude http://localhost:8080/dude/\n"
                          "  登录   http://localhost:8080/dude/auth/\n"
                          "  管理   http://localhost:8080/dude/admin/\n"
                          "  Journal http://localhost:8080/journal/\n"
                          "  Ctrl+C 或 make stop 停止本次服务。", flush=True)
                    while True:
                        failed = [(s.name, p.poll()) for s, p in backends if p.poll() is not None]
                        if failed:
                            raise RuntimeError("运行中服务退出：" + ", ".join(f"{n} (code {c})" for n, c in failed))
                        server.handle_request()
            finally:
                children.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except KeyboardInterrupt:
        print("\n[STOP] 本次启动的服务已停止。")
    except (RuntimeError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        raise SystemExit(1)
