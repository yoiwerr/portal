"""Exercise real development HTTP routing without models or databases."""

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_dev import PortalHandler


class ProbeHandler(PortalHandler):
    def _proxy(self, method, target, *, prefix=""):
        body = json.dumps({"method": method, "target": target}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class RetirementRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, method="GET"):
        connection = HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_homepage_keeps_only_active_projects(self):
        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertNotIn(b"/chatlab", body.lower())
        self.assertIn(b'href="/dude"', body)
        self.assertIn(b'href="/journal/"', body)

    def test_old_pages_and_assets_are_gone(self):
        for path in ("/chatlab", "/chatlab/", "/chatlab.html?old=1",
                     "/css/chatlab.css", "/js/chatlab.js"):
            for method in ("GET", "POST", "PUT", "DELETE"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(path, method)[0], 410)

    def test_chatlab_api_is_never_sent_to_alfred(self):
        for path in ("/api/v1/imported_files", "/api/docs", "/api/chatter"):
            for method in ("GET", "POST", "PUT", "DELETE"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(path, method)[0], 410)

    def test_alfred_routes_and_query_strings_survive(self):
        for path, target in (
            ("/dude/", "http://127.0.0.1:8001/"),
            ("/dude/api/chat/stream?v=2", "http://127.0.0.1:8001/api/chat/stream?v=2"),
            ("/api/sessions?limit=2", "http://127.0.0.1:8001/api/sessions?limit=2"),
        ):
            with self.subTest(path=path):
                status, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["target"], target)

    def test_journal_crud_routing_survives(self):
        for method in ("GET", "POST", "PUT", "DELETE"):
            with self.subTest(method=method):
                status, body = self.request("/journal/api/entries?limit=1", method)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), {
                    "method": method,
                    "target": "http://127.0.0.1:8002/journal/api/entries?limit=1",
                })

    def test_legacy_brand_routes_keep_methods_and_query(self):
        for prefix in ("/dude", "/alfred"):
            for suffix, target in (
                ("/api/v1/auth/login?probe=1", "http://127.0.0.1:8083/api/v1/auth/login?probe=1"),
                ("/auth/static/js/auth.js?v=1", "http://127.0.0.1:8083/static/js/auth.js?v=1"),
                ("/api/chat/message?probe=1", "http://127.0.0.1:8001/api/chat/message?probe=1"),
            ):
                for method in ("GET", "POST", "PUT", "DELETE"):
                    with self.subTest(prefix=prefix, suffix=suffix, method=method):
                        status, body = self.request(prefix + suffix, method)
                        self.assertEqual(status, 200)
                        self.assertEqual(json.loads(body), {"method": method, "target": target})

    def test_static_routes_cannot_read_archived_source(self):
        self.assertEqual(self.request("/../ChatHistoryAnalyst/README.md")[0], 403)


if __name__ == "__main__":
    unittest.main()
