#!/usr/bin/env python3
"""Portal dev runner — uses uv run --no-sync for each subproject."""

import os, signal, subprocess, sys, time

PROCS = []

def stop(sig=None, frame=None):
    print("\n[STOP] Stopping...")
    for p in PROCS:
        if p.poll() is None: p.terminate()
    deadline = time.time() + 5
    for p in PROCS:
        if p.poll() is None:
            try: p.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired: p.kill(); p.wait()
    print("[STOP] All services stopped.")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    root = os.path.dirname(os.path.abspath(__file__))

    # Strip VIRTUAL_ENV — uv resolves its own venv from cwd
    env = os.environ.copy()
    for key in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT", "PIP_REQUIRE_VIRTUALENV"):
        env.pop(key, None)

    for port in (8000, 8001):
        os.system(f"fuser -k {port}/tcp 2>/dev/null || true")
    time.sleep(0.5)

    print("[+] FastAPI       http://localhost:8000")
    print("[+] MakeItSpecific http://localhost:8001")
    print("[+] Ctrl+C to stop\n")

    api = subprocess.Popen(
        ["uv", "run", "--no-sync", "python", "-m", "uvicorn",
         "src.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=os.path.join(root, "ChatHistoryAnalyst"),
        env=env,
        stdout=sys.stdout, stderr=sys.stderr,
    )
    PROCS.append(api)
    time.sleep(3)

    mis = subprocess.Popen(
        ["uv", "run", "--no-sync", "python", "-m", "uvicorn",
         "app:app", "--host", "0.0.0.0", "--port", "8001"],
        cwd=os.path.join(root, "MakeItSpecific"),
        env=env,
        stdout=sys.stdout, stderr=sys.stderr,
    )
    PROCS.append(mis)
    time.sleep(3)

    try:
        while all(p.poll() is None for p in PROCS): time.sleep(0.5)
        print("\n[!] A service stopped unexpectedly.")
        stop()
    except KeyboardInterrupt:
        stop()


if __name__ == "__main__":
    main()
