---
type: engineering_guide
scenario: 数据库操作与数据安全
triggers:
  - 数据库
  - 删除
  - DROP
  - DELETE
  - 迁移
  - migration
  - PostgreSQL
  - MySQL
  - 备份
  - 生产环境
risk_level: high
output_mode: confirm_before_action
checks:
  - 执行前是否已备份数据库
  - DELETE/UPDATE 是否带了 WHERE 条件
  - 迁移脚本是否有回滚方案
  - 是否在生产环境直接操作而非先测试环境验证
  - 是否涉及用户真实数据的处理
suggestion: |
  数据操作安全规则：
  - 生产库操作前必须备份（`pg_dump` / `mysqldump`）
  - 写操作先在测试环境验证
  - DELETE/UPDATE 先用 SELECT 验证 WHERE 条件影响的行数
  - 迁移脚本必须包含回滚方案
  - 涉及用户数据的操作需要额外审批
---

# 数据库操作 — 安全红线

## 绝对不能做的事
1. 生产环境直接 DROP TABLE / DROP DATABASE
2. DELETE FROM 不带 WHERE 条件
3. 没有备份就执行数据迁移
4. 在真实用户数据上测试脚本

## 标准操作流程

### 任何写操作之前
```sql
-- 1. 先看影响范围
SELECT COUNT(*) FROM users WHERE status = 'inactive';

-- 2. 确认无误后再写
DELETE FROM users WHERE status = 'inactive';
```

### 迁移检查清单
- [ ] 备份已创建且可恢复（验证过恢复流程）
- [ ] 迁移脚本在测试环境执行成功
- [ ] 有回滚方案（写在 migration 的 down 方法中）
- [ ] 通知了相关团队成员
- [ ] 选择了低峰期执行
