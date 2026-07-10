---
name: wsl-unc-path-dll-issue
description: Windows uv/Python cannot load native DLLs from WSL UNC paths
metadata:
  type: project
---

When the project files live in WSL (`\\wsl.localhost\Ubuntu\home\yoiwerr\portal`) but `uv` is invoked from Windows (Git Bash, PowerShell, CMD), the created `.venv` contains Windows CPython and Windows `.pyd`/`.dll` files. Windows refuses to load native DLLs from UNC paths (`\\wsl.localhost\...`), causing `ImportError: DLL load failed while importing _multiarray_umath` (numpy) and similar failures for any package with C extensions (chromadb, langchain_postgres, etc.).

**Why:** Windows security policy blocks DLL loading from UNC paths.

**How to apply:** Always run `make dev` from inside WSL (`wsl bash`), or use `wsl bash -c "cd /home/yoiwerr/portal && make dev"` from Windows. The `.venv` created by Linux `uv` inside WSL uses native Linux Python and ELF `.so` files — no DLL issue. Never run `uv sync` or `uv run` from Windows against WSL paths. See also [[run_dev-inside-wsl]].
