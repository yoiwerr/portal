.PHONY: dev dev-win

# Run services inside WSL (avoids Windows UNC path DLL issues)
dev:
	@wsl bash -c "cd /home/yoiwerr/portal && python3 run_dev.py"

# Run from Git Bash / Windows directly (requires uv on PATH)
dev-win:
	@python3 run_dev.py
