"""
Portal Local Dev Server — zero deps, Python stdlib only.
Usage:   python dev_server.py
  - /          → portal/static/index.html (homepage)
  - /chatlab/  → ChatHistoryAnalyst/frontend/ (ChatLab tool)
  - /api/*     → proxy to FastAPI :8000

From either portal/ or ChatHistoryAnalyst/ directory.
"""

import http.server
import socketserver
import urllib.request
import urllib.error
import os
import sys
import webbrowser
from pathlib import Path

PORT = 8080
API_PORT = 8000

# Auto-detect project roots
SCRIPT_DIR = Path(__file__).parent.resolve()

# If we're inside ChatHistoryAnalyst, portal is parent; otherwise we ARE portal
if SCRIPT_DIR.name == 'ChatHistoryAnalyst':
    PORTAL_ROOT = SCRIPT_DIR.parent
else:
    PORTAL_ROOT = SCRIPT_DIR

PORTAL_STATIC = PORTAL_ROOT / 'static'
CHATLAB_FRONTEND = PORTAL_ROOT / 'ChatHistoryAnalyst' / 'frontend'

print(f"Portal root:   {PORTAL_ROOT}")
print(f"Portal static: {PORTAL_STATIC}")
print(f"ChatLab front: {CHATLAB_FRONTEND}")


class PortalHandler(http.server.SimpleHTTPRequestHandler):

    def route_path(self):
        """Resolve URL path to filesystem path, handling / and /chatlab/ routing."""
        p = self.path.split('?')[0]

        # API proxy
        if p.startswith('/api'):
            return None

        # ChatLab tool pages → ChatHistoryAnalyst/frontend/
        if p.startswith('/chatlab'):
            rel = p[len('/chatlab'):] or '/chatlab.html'
            if rel.startswith('/'): rel = rel[1:]
            return CHATLAB_FRONTEND / rel

        # Portal homepage → portal/static/
        clean = p.lstrip('/')
        if not clean:
            clean = 'index.html'
        return PORTAL_STATIC / clean

    def do_GET(self):
        if self.path.startswith('/api'):
            self._proxy('GET')
            return

        filepath = self.route_path()
        self._serve_file(filepath)

    def do_POST(self):
        if self.path.startswith('/api'):
            self._proxy('POST')
            return
        # No POST handling for static; 405
        self.send_response(405)
        self.end_headers()

    def _serve_file(self, filepath):
        if filepath is None:
            self.send_error(404)
            return

        try:
            content = filepath.read_bytes()
        except FileNotFoundError:
            # Try .html extension fallback
            fp2 = filepath.with_suffix(filepath.suffix + '.html')
            try:
                content = fp2.read_bytes()
            except FileNotFoundError:
                self.send_error(404)
                return
        except IsADirectoryError:
            fp2 = filepath / 'index.html'
            try:
                content = fp2.read_bytes()
            except FileNotFoundError:
                self.send_error(404)
                return
        except PermissionError:
            self.send_error(403)
            return

        # Content-Type
        ext = filepath.suffix.lower() if filepath.suffix else '.html'
        ct = {
            '.html': 'text/html; charset=utf-8',
            '.css': 'text/css; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8',
            '.json': 'application/json; charset=utf-8',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml',
            '.ico': 'image/x-icon',
        }.get(ext, 'application/octet-stream')

        self.send_response(200)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)

    def _proxy(self, method):
        api_url = f'http://127.0.0.1:{API_PORT}{self.path}'
        body = None
        cl = int(self.headers.get('Content-Length', 0))
        if cl > 0:
            body = self.rfile.read(cl)

        try:
            req = urllib.request.Request(api_url, data=body, method=method)
            for h in ['Content-Type', 'Authorization']:
                if h in self.headers:
                    req.add_header(h, self.headers[h])

            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                ct = resp.headers.get('Content-Type', 'application/json')
                self.send_header('Content-Type', ct)
                self.end_headers()
                self.wfile.write(resp.read())

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(e.read())
        except urllib.error.URLError:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":"Backend not running. Run: uvicorn src.main:app --reload"}')

    def log_message(self, fmt, *args):
        print(f"  [{self.command}] {args[0]}")


if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer(('', PORT), PortalHandler) as httpd:
        print(f"""
╔══════════════════════════════════════════════╗
║          Portal — Local Dev Server           ║
╠══════════════════════════════════════════════╣
║                                              ║
║   Homepage   http://localhost:{PORT}             ║
║   ChatLab    http://localhost:{PORT}/chatlab      ║
║   API Proxy  /api/* → localhost:{API_PORT}       ║
║                                              ║
║   Press Ctrl+C to stop                       ║
╚══════════════════════════════════════════════╝
""")
        webbrowser.open(f'http://localhost:{PORT}')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nShutting down...')
