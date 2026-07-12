.PHONY: dev dev-wsl

# Auto-detect: runs inside WSL directly, or from Windows via `wsl.exe` command
dev:
	@if [ -f /proc/sys/fs/binfmt_misc/WSLInterop ] 2>/dev/null; then \
		VIRTUAL_ENV= VIRTUAL_ENV_PROMPT= python3 run_dev.py; \
	else \
		wsl.exe bash -c "cd /home/yoiwerr/portal && VIRTUAL_ENV= VIRTUAL_ENV_PROMPT= python3 run_dev.py"; \
	fi

# Force run from Windows side via `wsl.exe` (even if already in WSL)
dev-wsl:
	@wsl.exe bash -c "cd /home/yoiwerr/portal && VIRTUAL_ENV= VIRTUAL_ENV_PROMPT= python3 run_dev.py"
