#!/usr/bin/env python
"""Portal unified dev runner — starts all services + serves unified frontend.

  make dev  →  ChatLab :8000  +  Alfred :8001  +  Dev Server :8080

Startup: launch backends in parallel, poll health, then boot dev server.
All three stay alive until Ctrl+C.

Dev Server (:8080) routing:
  /                          → Portal homepage
  /chatlab                   → ChatHistoryAnalyst frontend
  /alfred  [/alfred/*]       → reverse proxy to Alfred :8001
  /api/chat/*                → proxy to Alfred :8001
  /api/sessions/*            → proxy to Alfred :8001
  /api/knowledge/*           → proxy to Alfred :8001
  /api/feedback/*            → proxy to Alfred :8001
  /api/files/*               → proxy to Alfred :8001
  /api/handover/*            → proxy to Alfred :8001
  /api/health                → proxy to Alfred :8001
  /api/*                     → proxy to ChatLab :8000
"""

import http.server
import os
import signal
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PORTAL_STATIC = ROOT / "static"
CHATLAB_FRONTEND = ROOT / "ChatHistoryAnalyst" / "frontend"

API_CHATLAB = "http://127.0.0.1:8000"
API_ALFRED = "http://127.0.0.1:8001"
API_JOURNAL = "http://127.0.0.1:8002"

ALFRED_API_PREFIXES = (
    "/api/chat", "/api/sessions", "/api/knowledge",
    "/api/feedback", "/api/files", "/api/handover", "/api/health",
)

PROCS = []       # (name, Popen)
STARTUP_DONE = threading.Event()


# ============================================================
# Process management
# ============================================================

def stop(sig=None, frame=None, *, exit_code=0):
    print("\n[STOP] Shutting down...")
    for name, p in PROCS:
        if p.poll() is None:
            print(f"  stopping {name} ...")
            p.terminate()
    deadline = time.time() + 5
    for name, p in PROCS:
        if p.poll() is None:
            try:
                p.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
    print("[STOP] All services stopped.")
    sys.exit(exit_code)


def _check_health(url: str, timeout: float = 3) -> bool:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except Exception:
        return False


def _wait_for_backend(name: str, url: str, process: subprocess.Popen, max_wait: int = 60):
    """Poll a backend's health endpoint until it responds."""
    elapsed = 0
    while elapsed < max_wait:
        return_code = process.poll()
        if return_code is not None:
            print(f"  [ERROR] {name} exited during startup (code {return_code})")
            return False
        if _check_health(url):
            print(f"  [OK] {name} ready ({elapsed}s)")
            return True
        time.sleep(1.5)
        elapsed += 1.5
    print(f"  [ERROR] {name} not responding after {max_wait}s")
    return False


def _record_health(results, name, url, process):
    results[name] = _wait_for_backend(name, url, process)


def _port_owner(port: int) -> str | None:
    import shutil
    if not shutil.which("ss"):
        return None
    result = subprocess.run(
        ["ss", "-H", "-ltnp", f"sport = :{port}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None

def _ensure_ports_free(ports: tuple[int, ...]) -> None:
    occupied = {port: _port_owner(port) for port in ports}
    occupied = {port: owner for port, owner in occupied.items() if owner}
    if occupied:
        details = "\n".join(f"  :{port}: {owner}" for port, owner in occupied.items())
        raise SystemExit("端口已被占用，请先停止对应进程：\n" + details)


# ============================================================
# HTTP Handler
# ============================================================

class PortalHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split("?")[0]

        # Private Journal reverse proxy
        if path == "/journal" or path.startswith("/journal/"):
            return self._proxy("GET", API_JOURNAL + self.path)

        # ── Alfred reverse proxy ──
        if path == "/alfred" or path.startswith("/alfred/"):
            sub = path[len("/alfred"):] or "/"
            return self._proxy("GET", API_ALFRED + sub, prefix="/alfred")

        # ── API routing ──
        if path.startswith("/api"):
            to_alfred = any(path.startswith(p) for p in ALFRED_API_PREFIXES)
            target = API_ALFRED if to_alfred else API_CHATLAB
            return self._proxy("GET", target + path, prefix="/alfred" if to_alfred else "")

        # ── Static file serving ──
        fp = self._resolve_static(path)
        if fp is None:
            self.send_error(404)
            return
        self._serve_file(fp)

    def do_POST(self):
        path = self.path.split("?")[0]

        if path == "/journal" or path.startswith("/journal/"):
            return self._proxy("POST", API_JOURNAL + self.path)

        if path == "/alfred" or path.startswith("/alfred/"):
            sub = path[len("/alfred"):] or "/"
            return self._proxy("POST", API_ALFRED + sub, prefix="/alfred")

        if path.startswith("/api"):
            to_alfred = any(path.startswith(p) for p in ALFRED_API_PREFIXES)
            target = API_ALFRED if to_alfred else API_CHATLAB
            return self._proxy("POST", target + path, prefix="/alfred" if to_alfred else "")

        self.send_response(405)
        self.end_headers()

    def do_PUT(self):
        path = self.path.split("?")[0]
        if path == "/journal" or path.startswith("/journal/"):
            return self._proxy("PUT", API_JOURNAL + self.path)
        self.send_response(405)
        self.end_headers()

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if path == "/journal" or path.startswith("/journal/"):
            return self._proxy("DELETE", API_JOURNAL + self.path)
        self.send_response(405)
        self.end_headers()

    def _resolve_static(self, path: str) -> Path | None:
        clean = path.lstrip("/")
        if not clean:
            return PORTAL_STATIC / "index.html"
        if clean == "chatlab" or clean.startswith("chatlab/"):
            rel = clean[len("chatlab"):].lstrip("/")
            return CHATLAB_FRONTEND / (rel or "chatlab.html")
        return PORTAL_STATIC / clean

    def _serve_file(self, fp: Path):
        allowed = (CHATLAB_FRONTEND if str(fp).startswith(str(CHATLAB_FRONTEND)) else PORTAL_STATIC).resolve()
        try:
            fp = fp.resolve()
            if fp != allowed and allowed not in fp.parents:
                self.send_error(403)
                return
        except OSError:
            self.send_error(403)
            return
        try:
            content = fp.read_bytes()
        except FileNotFoundError:
            alt = fp.with_suffix(fp.suffix + ".html")
            try:
                content = alt.read_bytes()
            except (FileNotFoundError, IsADirectoryError, PermissionError):
                self.send_error(404)
                return
        except IsADirectoryError:
            try:
                content = (fp / "index.html").read_bytes()
            except (FileNotFoundError, PermissionError):
                self.send_error(404)
                return
        except PermissionError:
            self.send_error(403)
            return

        ct = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".md": "text/markdown; charset=utf-8",
        }.get(fp.suffix.lower(), "application/octet-stream")

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _proxy(self, method: str, target: str, *, prefix: str = ""):
        body = None
        cl = int(self.headers.get("Content-Length", 0))
        if cl > 0:
            body = self.rfile.read(cl)

        try:
            req = urllib.request.Request(target, data=body, method=method)
            for h in ("Content-Type", "Authorization", "Accept", "Cookie", "X-Journal-Request"):
                if h in self.headers:
                    req.add_header(h, self.headers[h])
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_body = resp.read()
                resp_ct = resp.headers.get_content_type() or ""

                # ── Inject <base> tag for subpath proxying ──
                if prefix and "text/html" in resp_ct:
                    import re as _re
                    resp_body = _re.sub(
                        rb"(<head[^>]*>)",
                        rf'\1<base href="{prefix}/">'.encode(),
                        resp_body, count=1,
                    )
                    print(f"  [proxy] Injected base href={prefix}/ into HTML")

                self.send_response(resp.status)
                # Always send correct Content-Length after possible injection
                send_headers = {
                    "Content-Type": resp_ct or "application/octet-stream",
                    "Content-Length": str(len(resp_body)),
                }
                for k, v in resp.headers.items():
                    if k.lower() in ("cache-control", "set-cookie"):
                        send_headers["Cache-Control" if k.lower() == "cache-control" else "Set-Cookie"] = v
                for k, v in send_headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except urllib.error.URLError:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                f'{{"error":"Backend unreachable: {target}"}}'.encode()
            )

    def log_message(self, fmt, *args):
        print(f"  [{self.command}] {args[0]}")


# ============================================================
# Main
# ============================================================

def main():
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    env = os.environ.copy()
    for key in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT", "PIP_REQUIRE_VIRTUALENV"):
        env.pop(key, None)

    _ensure_ports_free((8000, 8001, 8002, 8080))

    # ── Launch backends in parallel ──
    print("[+] Launching backends...\n")

    chatlab = subprocess.Popen(
        ["uv", "run", "python", "-m", "uvicorn",
         "src.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=ROOT / "ChatHistoryAnalyst",
        env=env,
        stdout=sys.stdout, stderr=sys.stderr,
    )
    PROCS.append(("ChatLab", chatlab))

    alfred = subprocess.Popen(
        ["uv", "run", "python", "-m", "uvicorn",
         "app:app", "--host", "0.0.0.0", "--port", "8001"],
        cwd=ROOT / "MakeItSpecific",
        env=env,
        stdout=sys.stdout, stderr=sys.stderr,
    )
    PROCS.append(("Alfred", alfred))

    journal = subprocess.Popen(
        ["uv", "run", "python", "-m", "uvicorn",
         "app:app", "--host", "0.0.0.0", "--port", "8002"],
        cwd=ROOT / "Journal",
        env=env,
        stdout=sys.stdout, stderr=sys.stderr,
    )
    PROCS.append(("Journal", journal))

    # ── Poll health concurrently ──
    health_results = {"ChatLab": False, "Alfred": False, "Journal": False}
    threads = [
        threading.Thread(target=_record_health, args=(health_results, "ChatLab", "http://127.0.0.1:8000/docs", chatlab), daemon=True),
        threading.Thread(target=_record_health, args=(health_results, "Alfred", "http://127.0.0.1:8001/api/health", alfred), daemon=True),
        threading.Thread(target=_record_health, args=(health_results, "Journal", "http://127.0.0.1:8002/journal/health", journal), daemon=True),
    ]
    for t in threads:
        t.start()

    for t in threads:
        t.join()
    failed = [name for name, ready in health_results.items() if not ready]
    if failed:
        print("[ERROR] 服务启动失败: " + ", ".join(failed))
        stop(exit_code=1)

    # ── Dev Server :8080 ──
    class ThreadingPortalServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadingPortalServer(("0.0.0.0", 8080), PortalHandler)

    print("""
╔══════════════════════════════════════════════════════╗
║              Portal — Unified Dev Mode               ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║   Homepage  http://localhost:8080/                    ║
║   ChatLab   http://localhost:8080/chatlab             ║
║   Alfred    http://localhost:8080/alfred              ║
║   Journal   http://localhost:8080/journal              ║
║                                                      ║
║   Direct:   ChatLab :8000  |  Alfred :8001  |  Journal :8002 ║
║                                                      ║
║   All backends ready                                 ║
║   Press Ctrl+C to stop all services                  ║
╚══════════════════════════════════════════════════════╝
""")

    webbrowser.open("http://localhost:8080")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        stop()


if __name__ == "__main__":
    main()
