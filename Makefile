.PHONY: dev dev-wsl stop

# Linux and WSL run directly; Windows GNU Make delegates to WSL.
ifeq ($(OS),Windows_NT)
DEV_RUN = wsl.exe bash -lc 'cd /home/yoiwerr/portal && uv run --frozen --env-file .env python run_dev.py'
STOP_RUN = wsl.exe bash -lc 'cd /home/yoiwerr/portal && python3 run_dev.py --stop'
else
DEV_RUN = uv run --frozen --env-file .env python run_dev.py
STOP_RUN = python3 run_dev.py --stop
endif

dev:
	@$(DEV_RUN)

dev-wsl:
	@wsl.exe bash -lc 'cd /home/yoiwerr/portal && uv run --frozen --env-file .env python run_dev.py'

stop:
	@$(STOP_RUN)
