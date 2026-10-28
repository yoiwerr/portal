"""Serve Portal and proxy to already-running backends; use `make dev` to start them."""

from http.server import ThreadingHTTPServer

from run_dev import PortalHandler


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 8080), PortalHandler) as server:
        print("Portal frontend: http://localhost:8080/ (backends must already be running)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
