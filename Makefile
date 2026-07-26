.PHONY: dev dev-wsl stop

# Auto-detect: runs inside WSL directly, or from Windows via `wsl.exe` command
dev:
	@if [ -f /proc/sys/fs/binfmt_misc/WSLInterop ] 2>/dev/null; then \
		uv run python run_dev.py; \
	else \
		wsl.exe bash -c "cd /home/yoiwerr/portal && uv run python run_dev.py"; \
	fi

# Force run from Windows side via `wsl.exe` (even if already in WSL)
dev-wsl:
	@wsl.exe bash -c "cd /home/yoiwerr/portal && uv run python run_dev.py"

# Kill all dev servers
stop:
	@fuser -k 8080/tcp 2>/dev/null || true
	@fuser -k 8000/tcp 2>/dev/null || true
	@fuser -k 8001/tcp 2>/dev/null || true
	@echo "All dev servers stopped."
