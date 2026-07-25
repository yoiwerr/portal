---
type: engineering_guide
scenario: 公开提交 Git 仓库
triggers:
  - 上传 GitHub
  - 公开仓库
  - git push
  - 提交代码
  - 开源
  - 发布到 GitHub
risk_level: high
output_mode: confirm_before_action
checks:
  - .env 或配置文件是否包含真实密钥/Token/密码
  - 是否包含个人信息（邮箱/手机号/地址）
  - 是否配置了 .gitignore
  - Git 历史中是否存在敏感内容（曾提交过密钥后又删除）
  - 是否有大于 10MB 的二进制文件被提交
suggestion: |
  提交前建议检查：
  - `.env` 和含密钥的文件已在 `.gitignore` 中
  - 没有真实用户数据、API Key、Token 被提交
  - 如果不小心提交了密钥，使用 `git filter-branch` 或 `BFG Repo-Cleaner` 清理历史
  - 考虑使用 `git-secrets` 或 pre-commit hook 自动扫描
---

# 公开提交 Git 仓库 — 安全检查清单

## 触发场景
用户提到要上传代码到 GitHub、公开仓库、开源项目等。

## 检查项

### 1. 敏感信息扫描
在 `git push` 前确认以下内容不在仓库中：
- `.env` 文件（或确认 .env.example 不含真实密钥）
- API Key / Token / Secret
- 数据库密码
- 个人信息（邮箱、手机号、家庭地址）
- 客户的真实数据

### 2. .gitignore 配置
```
.env
*.log
node_modules/
__pycache__/
*.pyc
.DS_Store
.vscode/
.idea/
*.pem
*.key
```

### 3. 历史清理
如果敏感信息曾经被提交（即使后来删除了文件），Git 历史中仍保留。需要：
- `git log --all --full-history -- "*.env"` 检查历史
- 使用 `git filter-branch` 或 `BFG Repo-Cleaner` 清理
- 清理后强制推送前通知所有协作者

### 4. 预防措施
- 安装 pre-commit hook 自动扫描
- 使用 `.gitattributes` 标记大文件用 LFS
- CI 中加入密钥扫描步骤
