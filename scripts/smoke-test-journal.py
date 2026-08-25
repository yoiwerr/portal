#!/usr/bin/env python3
import getpass
import http.cookiejar
import json
import urllib.error
import urllib.request
from datetime import date

BASE = "https://yoiwerr.site"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def request(method, path, data=None, authenticated=True):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"}
    if method in {"POST", "PUT", "DELETE"} and path != "/journal/api/login":
        headers["X-Journal-Request"] = "1"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    client = opener if authenticated else urllib.request.build_opener()
    try:
        response = client.open(req, timeout=15)
        payload = response.read()
        return response.status, response.headers, json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        payload = error.read()
        return error.code, error.headers, json.loads(payload) if payload else None

status, _, _ = request("GET", "/journal/api/entries", authenticated=False)
assert status == 401, f"unauthenticated access returned {status}"

username = input("Journal username [yoiwerr]: ").strip() or "yoiwerr"
password = getpass.getpass("Journal password: ")
status, headers, _ = request("POST", "/journal/api/login", {"username": username, "password": password})
assert status == 200, f"login returned {status}"
cookie = headers.get("Set-Cookie", "")
for flag in ("HttpOnly", "Secure", "SameSite=Strict"):
    assert flag.lower() in cookie.lower(), f"session cookie missing {flag}"

entry_id = None
try:
    payload = {"title": "deployment-smoke-test", "entry_date": date.today().isoformat(), "content": "create"}
    status, _, entry = request("POST", "/journal/api/entries", payload)
    assert status == 201
    entry_id = entry["id"]
    payload["title"] = "deployment-smoke-test-updated"
    payload["content"] = "update"
    status, _, entry = request("PUT", f"/journal/api/entries/{entry_id}", payload)
    assert status == 200 and entry["title"] == payload["title"]
    status, _, _ = request("DELETE", f"/journal/api/entries/{entry_id}")
    assert status == 204
    entry_id = None
finally:
    if entry_id is not None:
        request("DELETE", f"/journal/api/entries/{entry_id}")

status, _, _ = request("POST", "/journal/api/logout")
assert status == 200
status, _, _ = request("GET", "/journal/api/entries")
assert status == 401, f"post-logout access returned {status}"
print("[OK] Journal authentication, cookie, CRUD, and logout smoke test passed")
