---
type: engineering_guide
scenario: API 密钥与凭证管理
triggers:
  - API Key
  - Token
  - 密钥
  - 密码
  - secret
  - 凭证
  - 环境变量
  - .env
  - 硬编码
risk_level: high
output_mode: block_if_found
checks:
  - 代码中是否硬编码了密钥/Token/密码
  - 是否通过环境变量或密钥管理服务读取凭证
  - .env 文件是否在 .gitignore 中
  - 是否有 .env.example 模板（不含真实密钥）
suggestion: |
  凭证管理原则：
  - 绝对不在代码中硬编码任何密钥
  - 使用环境变量读取敏感配置
  - 提供 `.env.example` 模板文件（值用占位符）
  - 生产环境使用密钥管理服务（如 AWS Secrets Manager / Vault）
  - CI/CD 中使用加密的环境变量
---

# API 密钥与凭证管理

## 发现硬编码密钥时的处理

如果代码中出现类似以下内容：
```python
API_KEY = "sk-abc123def456ghi789..."
PASSWORD = "admin123"
SECRET = "my-super-secret-token"
```

这是**阻断级**问题。应当：
1. 立即删除硬编码的密钥
2. 改为 `os.getenv("API_KEY")`
3. 如果密钥已经提交到 Git → 立即轮换密钥（在服务商后台重新生成）
4. 清理 Git 历史

## 正确的做法

```python
# ✅ 正确
import os
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    raise ValueError("DASHSCOPE_API_KEY 未设置")

# ❌ 错误
api_key = "sk-abc123..."  # 硬编码
```

## .env.example 模板
```bash
# 复制为 .env 后填入实际值
DASHSCOPE_API_KEY=sk-your-key-here
PGSQLPASSWORD=your-password-here
```
