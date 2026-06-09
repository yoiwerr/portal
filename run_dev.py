#!/usr/bin/env python3
"""
Portal dev runner — start FastAPI + Streamlit, stop cleanly on Ctrl+C.

Replaces the inline shell approach in the Makefile so that:
- SIGINT / SIGTERM are caught reliably (no make signal interception issues)
- Both uvicorn and streamlit subprocesses are terminated before exit
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

    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(os.path.join(root, "ChatHistoryAnalyst"))

    print("[+] Starting FastAPI  on http://localhost:8000")
    print("[+] Starting Streamlit on http://localhost:8501")
    print("[+] Press Ctrl+C to stop")
    print()

    # Start uvicorn first, wait a moment, then start streamlit
    # so `uv` doesn't contend for the same lock
    api = subprocess.Popen(
        ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=sys.stdout, stderr=sys.stderr,
    )
    PROCS.append(api)

    time.sleep(2)  # let uvicorn finish binding before streamlit starts

    sl = subprocess.Popen(
        [
            "uv", "run", "streamlit", "run", "front/frontend.py",
            "--server.port", "8501", "--server.headless", "true",
        ],
        stdout=sys.stdout, stderr=sys.stderr,
    )
    PROCS.append(sl)

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
