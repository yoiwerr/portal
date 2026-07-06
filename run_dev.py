#!/usr/bin/env python3
"""
Portal dev runner — start ChatLab FastAPI + MakeItSmooth, stop cleanly on Ctrl+C.

Replaces the inline shell approach in the Makefile so that:
- SIGINT / SIGTERM are caught reliably (no make signal interception issues)
- All uvicorn subprocesses are terminated before exit
- The terminal returns to a clean state every time
"""

import os
import signal
import subprocess
import sys
import time

PROCS: list[subprocess.Popen] = []


def stop(sig=None, frame=None):
    """Kill all managed subprocesses gracefully, then exit."""
    print("\n[STOP] Stopping services...")
    for p in PROCS:
        if p.poll() is None:
            p.terminate()

    # Wait up to 5 seconds for graceful shutdown
    deadline = time.time() + 5
    for p in PROCS:
        if p.poll() is None:
            remaining = max(0.1, deadline - time.time())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()

    print("[STOP] All services stopped.")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    # Ensure ~/.local/bin (uv, uvx) is on PATH for subprocesses
    local_bin = os.path.expanduser("~/.local/bin")
    env = os.environ.copy()
    env["PATH"] = f"{local_bin}:{env.get('PATH', '')}"

    # Suppress ChromaDB telemetry (avoids posthog client version mismatch)
    env.setdefault("ANONYMIZED_TELEMETRY", "False")
    env.setdefault("CHROMA_TELEMETRY_IMPL", "none")

    root = os.path.dirname(os.path.abspath(__file__))

    # Kill stale processes from a previous run
    for port in (8000, 8001):
        os.system(f"fuser -k {port}/tcp 2>/dev/null || true")
    time.sleep(0.5)

    print("[+] Starting FastAPI        on http://localhost:8000")
    print("[+] Starting MakeItSmooth    on http://localhost:8001")
    print("[+] Press Ctrl+C to stop")
    print()

    # ── ChatLab FastAPI (port 8000) ── (先启：uv sync 安装依赖)
    os.chdir(os.path.join(root, "ChatHistoryAnalyst"))

    api = subprocess.Popen(
        ["uv", "run", "--active", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=sys.stdout, stderr=sys.stderr, env=env,
    )
    PROCS.append(api)

    time.sleep(3)  # let uvicorn finish binding + uv sync

    # ── MakeItSmooth (port 8001) ──
    smooth = subprocess.Popen(
        ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"],
        cwd=os.path.join(root, "MakeItSmooth"),
        stdout=sys.stdout, stderr=sys.stderr, env=env,
    )
    PROCS.append(smooth)

    time.sleep(2)  # let MakeItSmooth finish binding

    # Wait until interrupted or a process dies unexpectedly
    try:
        while all(p.poll() is None for p in PROCS):
            time.sleep(0.5)

        # If we get here, a service died on its own
        print("\n[!] A service stopped unexpectedly.")
        stop()
    except KeyboardInterrupt:
        stop()


if __name__ == "__main__":
    main()
