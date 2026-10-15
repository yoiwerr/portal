"""Exercise the production nginx file with isolated loopback upstreams.

NGINX_BINARY=/path/to/nginx uv run pytest tests/test_auth_routing.py -q
No production services, credentials or databases are touched.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import threading
import time
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

import pytest


PORTAL = Path(__file__).resolve().parents[2]


class EchoUpstream(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond()

    do_POST = do_PUT = do_DELETE = do_GET

    def respond(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        result = {
            "path": self.path, "method": self.command,
            "body": body.decode(), "authorization": self.headers.get("Authorization"),
            "forwarded_proto": self.headers.get("X-Forwarded-Proto"),
        }
        payload = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@contextmanager
def upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), EchoUpstream)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def proxy(tmp_path_factory):
    binary = os.environ.get("NGINX_BINARY") or shutil.which("nginx")
    if not binary:
        pytest.skip("nginx is unavailable; set NGINX_BINARY to run real proxy tests")
    if not shutil.which("openssl"):
        pytest.skip("openssl is required to create the isolated test certificate")
    work = tmp_path_factory.mktemp("alfred-nginx")
    cert, key = work / "cert.pem", work / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-days", "1", "-subj", "/CN=localhost", "-keyout", str(key), "-out", str(cert),
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
    ], check=True, capture_output=True)
    http_port, https_port = free_port(), free_port()
    with upstream() as port:
        config = (PORTAL / "nginx/default.conf").read_text()
        # Only environment bindings change; all production locations and
        # rewrite directives are tested verbatim, including the general fallback.
        for host in ("alfred-admin:8080", "specific-api:8000", "journal:8000", "api:8000"):
            config = config.replace(host, f"127.0.0.1:{port}")
        config = config.replace("listen 80;", f"listen 127.0.0.1:{http_port};")
        config = config.replace("listen 443 ssl;", f"listen 127.0.0.1:{https_port} ssl;")
        config = config.replace("/etc/letsencrypt/live/yoiwerr.site/fullchain.pem", str(cert))
        config = config.replace("/etc/letsencrypt/live/yoiwerr.site/privkey.pem", str(key))
        site = work / "site.conf"
        site.write_text(config)
        main = work / "nginx.conf"
        main.write_text(
            f"pid {work}/nginx.pid;\nerror_log stderr warn;\nevents {{}}\n"
            f"http {{ access_log off; client_body_temp_path {work}/body;\n"
            f"proxy_temp_path {work}/proxy; fastcgi_temp_path {work}/fastcgi;\n"
            f"uwsgi_temp_path {work}/uwsgi; scgi_temp_path {work}/scgi;\n"
            f"include {site}; }}\n"
        )
        command = [binary, "-p", str(work), "-c", str(main), "-e", "stderr"]
        checked = subprocess.run(command + ["-t"], capture_output=True, text=True)
        assert checked.returncode == 0, checked.stderr
        log = (work / "nginx.log").open("w")
        process = subprocess.Popen(command + ["-g", "daemon off;"], stderr=log)
        context = ssl.create_default_context(cafile=str(cert))
        try:
            deadline = time.monotonic() + 5
            while True:
                if process.poll() is not None:
                    pytest.fail("nginx exited during startup: " + (work / "nginx.log").read_text())
                try:
                    # A listening socket alone does not mean TLS is ready.
                    with socket.create_connection(("127.0.0.1", https_port), timeout=0.5) as sock:
                        with context.wrap_socket(sock, server_hostname="localhost"):
                            break
                except OSError:
                    if time.monotonic() >= deadline:
                        pytest.fail("nginx TLS did not start: " + (work / "nginx.log").read_text())
                    time.sleep(0.05)
            # Trust only the generated test certificate, never disable TLS checks.
            # Bind requests to the same IPv4 loopback, ignoring host proxy settings.
            client = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
            yield f"https://127.0.0.1:{https_port}", client
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.close()


@pytest.mark.parametrize(("public", "internal"), [
    ("/alfred/api/v1/auth/login", "/api/v1/auth/login"),
    ("/alfred/api/v1/auth/register", "/api/v1/auth/register"),
    ("/alfred/api/v1/auth/refresh", "/api/v1/auth/refresh"),
    ("/alfred/api/v1/auth/logout", "/api/v1/auth/logout"),
    ("/alfred/api/v1/auth/me?probe=1", "/api/v1/auth/me?probe=1"),
    ("/alfred/api/auth/login", "/api/v1/auth/login"),
    ("/alfred/api/auth/me?probe=1", "/api/v1/auth/me?probe=1"),
    ("/alfred/api/v1/admin/models/id/toggle", "/api/v1/admin/models/id/toggle"),
    ("/alfred/api/admin/stats/tokens?limit=2", "/api/v1/admin/stats/tokens?limit=2"),
    ("/alfred/auth/", "/auth/"),
    ("/alfred/admin/", "/admin/"),
    ("/alfred/auth/static/js/auth.js?v=20261015", "/static/js/auth.js?v=20261015"),
    ("/alfred/auth/static/css/login.css", "/static/css/login.css"),
    ("/alfred/admin/static/js/admin.js", "/static/js/admin.js"),
    ("/alfred/admin/static/css/admin.css", "/static/css/admin.css"),
    ("/alfred/api/health", "/api/health"),
    ("/alfred/api/chat", "/api/chat"),
    ("/alfred/js/chat.js?v=20261015", "/js/chat.js?v=20261015"),
    ("/journal/api/entries", "/journal/api/entries"),
])
def test_production_route_preserves_suffix_and_query(proxy, public, internal):
    base, client = proxy
    request = Request(base + public, headers={"Authorization": "Bearer routing-test"})
    with client.open(request, timeout=3) as response:
        data = json.load(response)
    assert data["path"] == internal
    assert data["authorization"] == "Bearer routing-test"
    if not public.startswith("/alfred/auth/static/") and not public.startswith("/alfred/admin/static/"):
        assert data["forwarded_proto"] == "https"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_proxy_preserves_methods_and_json_body(proxy, method):
    base, client = proxy
    request = Request(
        base + "/alfred/api/v1/auth/login", data=b'{"probe":true}', method=method,
        headers={"Content-Type": "application/json"},
    )
    with client.open(request, timeout=3) as response:
        data = json.load(response)
    assert data["method"] == method
    assert data["body"] == '{"probe":true}'
