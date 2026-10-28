"""Real HTTP proxy checks and process ownership tests; no business DB/API keys."""

from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_dev as dev
from dev_runtime import Children, runner_lock, stop_runner, process_identity


@contextmanager
def serving(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class QuietPortal(dev.PortalHandler):
    def log_message(self, *args):
        pass


class Backend(BaseHTTPRequestHandler):
    release_stream = threading.Event()
    requests = []

    def respond(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.requests.append((self.command, self.path))
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'event: progress\ndata: {"step":1}\n\n')
            self.wfile.flush()
            self.release_stream.wait(5)
            self.wfile.write(b'event: done\ndata: {}\n\n')
            return
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/auth/?next=1")
            self.send_header("Set-Cookie", "one=1; HttpOnly; SameSite=Strict")
            self.send_header("Set-Cookie", "two=2; Secure")
            self.end_headers()
            return
        if self.path == "/denied":
            self.send_response(401)
            self.send_header("Content-Type", "application/problem+json; charset=utf-8")
            self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            self.wfile.write(b'{"error":"expired"}')
            return
        payload = json.dumps({"method": self.command, "path": self.path,
                              "authorization": self.headers.get("Authorization"),
                              "cookie": self.headers.get("Cookie"), "body": body.decode()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = respond

    def log_message(self, *args):
        pass


class ProxyTests(unittest.TestCase):
    def setUp(self):
        Backend.requests = []
        Backend.release_stream.clear()
        self.upstream_context = serving(Backend)
        upstream = self.upstream_context.__enter__()
        self.addCleanup(self.upstream_context.__exit__, None, None, None)
        self.url = f"http://127.0.0.1:{upstream.server_port}"
        for variable in ("API_ADMIN", "API_DUDE", "API_JOURNAL"):
            mock = patch.object(dev, variable, self.url)
            mock.start()
            self.addCleanup(mock.stop)
        self.portal_context = serving(QuietPortal)
        self.portal = self.portal_context.__enter__()
        self.addCleanup(self.portal_context.__exit__, None, None, None)

    def request(self, path, method="GET", body=None, headers=None):
        connection = HTTPConnection(*self.portal.server_address, timeout=2)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            connection.close()

    def test_go_canonical_legacy_and_static_routes_preserve_suffix_query_body(self):
        for path, expected in (
            ("/dude/auth/", "/auth/"), ("/dude/admin/", "/admin/"),
            ("/dude/auth/static/js/auth.js?v=1", "/static/js/auth.js?v=1"),
            ("/dude/admin/static/css/admin.css", "/static/css/admin.css"),
            ("/dude/api/auth/login?q=a%2Fb", "/api/v1/auth/login?q=a%2Fb"),
            ("/dude/api/v1/admin/users?limit=3", "/api/v1/admin/users?limit=3"),
        ):
            status, _, body = self.request(path, "POST", '{"x":1}', {"Authorization": "Bearer test", "Cookie": "s=test"})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {"path": expected, "method": "POST", "body": '{"x":1}', "authorization": "Bearer test", "cookie": "s=test"})

    def test_all_write_methods_reach_correct_backend(self):
        for method in ("PUT", "DELETE", "PATCH"):
            for path in ("/dude/api/sessions/test", "/api/sessions/test", "/dude/api/v1/admin/models/test", "/journal/api/entries/1"):
                status, _, body = self.request(path, method)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["method"], method)

    def test_redirect_not_followed_cookies_preserved_and_location_rebased(self):
        status, headers, _ = self.request("/dude/redirect")
        self.assertEqual(status, 302)
        self.assertEqual(dict(headers)["Location"], "/dude/auth/?next=1")
        self.assertEqual(len([h for h in headers if h[0] == "Set-Cookie"]), 2)
        self.assertEqual(Backend.requests, [("GET", "/redirect")])

    def test_auth_error_content_type_body_and_challenge_preserved(self):
        status, headers, body = self.request("/dude/denied")
        self.assertEqual(status, 401)
        self.assertEqual(dict(headers)["WWW-Authenticate"], "Bearer")
        self.assertEqual(dict(headers)["Content-Type"], "application/problem+json; charset=utf-8")
        self.assertEqual(body, b'{"error":"expired"}')

    def test_sse_first_event_arrives_before_backend_finishes_and_does_not_block_other_requests(self):
        connection = HTTPConnection(*self.portal.server_address, timeout=2)
        try:
            connection.request("GET", "/dude/stream")
            response = connection.getresponse()
            self.assertEqual(response.readline(), b"event: progress\n")
            self.assertFalse(Backend.release_stream.is_set())
            self.assertEqual(self.request("/dude/api/health")[0], 200)
            Backend.release_stream.set()
            self.assertIn(b"event: done", response.read())
        finally:
            Backend.release_stream.set()
            connection.close()

    def test_canonical_redirect_preserves_query(self):
        status, headers, _ = self.request("/dude/auth?next=1")
        self.assertEqual(status, 308)
        self.assertEqual(dict(headers)["Location"], "/dude/auth/?next=1")
        self.assertEqual(Backend.requests, [])

    def test_encoded_traversal_and_fallback_symlinks_cannot_read_outside_static(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            static = root / "static"
            static.mkdir()
            secret = root / "private.txt"
            secret.write_text("private")
            (static / "leak.html").symlink_to(secret)
            (static / "folder").mkdir()
            (static / "folder" / "index.html").symlink_to(secret)
            with patch.object(dev, "PORTAL_STATIC", static):
                for path in ("/%2e%2e/private.txt", "/leak", "/folder/"):
                    self.assertEqual(self.request(path)[0], 403)


class RunnerTests(unittest.TestCase):
    def test_database_settings_shared_and_credentials_encoded(self):
        source = {"JWT_SECRET": "t" * 32, "ADMIN_INIT_PASSWORD": "isolated-test",
                  "PGSQLPASSWORD": "test @:/?#", "JOURNAL_DB_PASSWORD": "test/?#",
                  "DB_HOST": "127.0.0.1", "DB_NAME": "test_db", "PG_DATABASE": "wrong",
                  "DATABASE_URL": "postgresql://wrong/wrong"}
        env = dev._development_environment(source)
        parsed = urlsplit(env["DATABASE_URL"])
        self.assertEqual(unquote(parsed.password), source["PGSQLPASSWORD"])
        self.assertEqual(parsed.path, "/test_db")
        self.assertEqual(urlsplit(env["JOURNAL_DATABASE_URL"]).path, "/journal")
        self.assertEqual(env["ADMIN_PORT"], "8083")
        self.assertEqual(env["ADMIN_HOST"], "127.0.0.1")
        self.assertEqual(source["DATABASE_URL"], "postgresql://wrong/wrong")

    def test_missing_configuration_does_not_fall_back_to_weak_defaults(self):
        with self.assertRaisesRegex(RuntimeError, "JWT_SECRET"):
            dev._development_environment({})

    def test_dead_backend_fails_even_if_old_health_endpoint_is_reachable(self):
        process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"])
        process.wait()
        with patch.object(dev, "_check_health", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "code 7"):
                dev._wait_for_backends([(dev.SERVICES[0], process)], timeout=1)

    def test_occupied_port_reports_without_killing_listener(self):
        with serving(Backend) as server:
            with self.assertRaisesRegex(RuntimeError, str(server.server_port)):
                dev._ensure_ports_free((server.server_port,))
            self.assertTrue(dev._check_health(f"http://127.0.0.1:{server.server_port}/"))

    def test_only_one_runner_holds_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with runner_lock(root):
                with self.assertRaisesRegex(RuntimeError, "已有"):
                    with runner_lock(root):
                        self.fail("second runner acquired lock")
            self.assertEqual((root / ".portal-dev.lock").read_text(), "")

    def test_stale_record_cannot_signal_unrelated_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".portal-dev.lock").write_text(json.dumps({"pid": os.getpid(), "root": str(root), "starttime": "not-current"}))
            with patch("signal.pidfd_send_signal") as send:
                with self.assertRaisesRegex(RuntimeError, "身份"):
                    stop_runner(root)
                send.assert_not_called()

    def test_cleanup_stops_owned_group_and_preserves_other_process(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        children = Children()
        try:
            own = children.start("test", [sys.executable, "-c", "import time; time.sleep(30)"], cwd=Path.cwd(), env=os.environ.copy())
            children.close()
            self.assertIsNotNone(own.poll())
            self.assertIsNone(other.poll())
        finally:
            children.close()
            other.terminate()
            other.wait()

    def test_cleanup_waits_for_wrapped_child_listener_to_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            port_file = Path(temporary) / "port"
            child_code = ("import socket,time,pathlib; s=socket.socket(); s.bind(('127.0.0.1',0)); "
                          "s.listen(); pathlib.Path(" + repr(str(port_file)) + ").write_text(str(s.getsockname()[1])); time.sleep(30)")
            wrapper_code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]); time.sleep(30)"
            children = Children()
            try:
                children.start("wrapper", [sys.executable, "-c", wrapper_code], cwd=Path.cwd(), env=os.environ.copy())
                deadline = time.monotonic() + 3
                while not port_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                port = int(port_file.read_text())
                children.close()
                import socket
                with socket.socket() as probe:
                    # WSL localhost forwarding can accept a TCP handshake after
                    # the Linux listener exited; verify actual port ownership.
                    probe.bind(("127.0.0.1", port))
            finally:
                children.close()


if __name__ == "__main__":
    unittest.main()
