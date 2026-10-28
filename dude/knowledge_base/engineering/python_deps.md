---
type: engineering_guide
scenario: Python 项目依赖管理
triggers:
  - Python
  - pip
  - 依赖
  - requirements.txt
  - 虚拟环境
  - venv
  - conda
  - 新建 Python 项目
  - pyproject.toml
risk_level: medium
output_mode: suggestion
checks:
  - 是否使用了虚拟环境（venv/conda/uv）
  - 依赖是否锁定（requirements.txt 含确切版本 / uv.lock / poetry.lock）
  - 是否区分了生产依赖和开发依赖
  - Python 版本是否有明确声明（.python-version 或 pyproject.toml requires-python）
suggestion: |
  长期维护的 Python 项目建议：
  - 使用 `uv` 或 `poetry` 管理依赖（比 pip + requirements.txt 更可靠）
  - `uv sync` 或 `poetry install` 自动处理虚拟环境和依赖锁定
  - 提交 lock 文件到 Git（保证团队环境一致）
  - CI 中使用 `uv sync --frozen` 确保完全可复现
---

# Python 项目依赖管理

## 推荐方案（按项目规模）

### 个人小项目
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
- `requirements.txt` 中用 `package==1.2.3` 锁定版本
- `.venv/` 加入 `.gitignore`

### 团队 / 长期项目 — uv（推荐）
```bash
uv init
uv add fastapi langgraph
uv sync
```
- `pyproject.toml` 声明依赖
- `uv.lock` 锁定所有传递依赖
- `uv sync --frozen` 在 CI 中精确复现

### 数据科学 / 复杂环境 — conda
```bash
conda env create -f environment.yml
conda env export --no-builds > environment.yml
```

## 常见问题

1. **没用虚拟环境** → 全局 pip install 污染系统 Python
2. **依赖不锁定** → 队友/CI 装的版本不一样，出现"我这能跑"问题
3. **dev 依赖混入生产** → 镜像变大，攻击面增加
