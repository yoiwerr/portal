# ControlWeb — Portal 服务器运维手册

> 从零到正常网址：服务器管理 + 域名 + HTTPS + 日常更新。

---

## 总览：你的系统长什么样

```
互联网用户
    │
    ▼
https://your-domain.com  ← 你的域名（HTTPS，有绿锁）
    │
    ▼
[你的云服务器]  ← 公网 IP（例: 1.2.3.4）
    │
    ├── nginx (port 80/443)
    │     ├── /         → 首页 static/index.html
    │     ├── /chatlab  → static/chatlab.html
    │     ├── /css/*    → static/css/
    │     ├── /js/*     → static/js/
    │     ├── /bgm/*    → static/bgm/
    │     ├── /photo/*  → static/photo/
    │     └── /api/*    → proxy → chalab-api:8000
    │
    ├── chalab-api (FastAPI :8000)
    ├── chalab-streamlit (Streamlit :8501)
    └── chalab-postgres (PostgreSQL + pgvector)
```

---

## 第一部分：服务器初始部署

### 1. 准备一台云服务器

推荐配置：**2 核 4G，40G SSD 以上**

几家常用云厂商：
| 厂商 | 产品 | 参考价格 |
|------|------|----------|
| 阿里云 | ECS 轻量应用服务器 | ¥68/月 |
| 腾讯云 | 轻量应用服务器 | ¥68/月 |
| 华为云 | HECS | ¥68/月 |
| BandwagonHost | KVM VPS | $50/年 |

系统选 **Ubuntu 22.04 LTS**。

### 2. 登录服务器

```bash
ssh root@<你的服务器公网IP>
```

### 3. 安装 Docker（一次性）

```bash
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER
```

**退出 SSH 重新登录**让 docker 权限生效，然后：

```bash
# 国内服务器推荐配置镜像加速
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
EOF
sudo systemctl daemon-reload && sudo systemctl restart docker

# 安装 docker compose 插件
sudo apt update && sudo apt install docker-compose-plugin -y
```

### 4. 开放防火墙

```bash
# 服务器防火墙
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable

# 云控制台安全组也要开放 80、443、22
```

**重要：** 云厂商网页控制台的安全组/防火墙规则也要放行这三个端口，否则外部访问不了。

### 5. 上传代码

**方式 A — 用 Git（推荐，便于后续更新）：**

```bash
# 服务器上
git clone https://github.com/yoiwerr/portal.git ~/portal
```

**方式 B — 从本机 scp：**

```bash
# 你本地电脑执行
scp -r ~/portal root@<server-ip>:~/
```

### 6. 配置环境变量

```bash
cd ~/portal
cp .env.example .env
vim .env
```

填入你的真实密钥：
```ini
DASHSCOPE_API_KEY=sk-xxxxxxxx
TAVILY_API_KEY=tvly-xxxxxxxx
LANGSMITH_API_KEY=lsv2_xxxxxxxx
PGSQLPASSWORD=你设一个强密码
```

### 7. 一键部署

```bash
cd ~/portal
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

看到 `Deployment complete!` 就是成功了。

### 8. 验证

```bash
curl http://localhost          # 返回首页 HTML
curl http://localhost/api/v1/imported_files  # 返回 JSON
```

浏览器访问 `http://<公网IP>` 应该能看到首页。

---

## 第二部分：配置域名（像正常网址一样用）

### 9. 买域名

推荐域名注册商：
| 注册商 | 特点 |
|--------|------|
| Cloudflare Registrar | 最便宜（按成本价），域名管理最强大 |
| NameSilo | 便宜，免费隐私保护 |
| Namesilo / Porkbun | 便宜靠谱 |

去其中一家买一个你喜欢的域名，比如 `yoiwerr.me`。

**在 Cloudflare 买的好处**：后续配 CDN、DNS、HTTPS 一条龙，而且不需要额外付费。

### 10. 配置 DNS 解析

登录你的域名 DNS 管理面板，添加一条 **A 记录**：

| 类型 | 主机记录 | 记录值 | TTL |
|------|----------|--------|-----|
| A | @ | 你的服务器公网IP | 自动 |
| A | www | 你的服务器公网IP | 自动 |

| 主机记录 | 效果 |
|----------|------|
| `@` | `yoiwerr.me` |
| `www` | `www.yoiwerr.me` |

添加后等 **1-10 分钟** DNS 生效。

验证：
```bash
nslookup yoiwerr.me       # 应该返回你的服务器IP
ping yoiwerr.me            # 应该通
```

### 11. 配置 HTTPS（绿锁）

用的是免费的 Let's Encrypt 证书 + Certbot 工具。

```bash
# 安装 certbot
sudo apt install certbot -y

# 申请证书（standalone 模式，需要临时停掉 nginx）
cd ~/portal
docker compose stop nginx
sudo certbot certonly --standalone -d yoiwerr.me -d www.yoiwerr.me
docker compose start nginx
```

证书存在 `/etc/letsencrypt/live/yoiwerr.me/`。

### 12. 更新 nginx 配置支持 HTTPS

编辑 `~/portal/nginx/default.conf`，替换为：

```nginx
resolver 127.0.0.11 valid=30s ipv6=off;

# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name yoiwerr.me www.yoiwerr.me;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yoiwerr.me www.yoiwerr.me;

    ssl_certificate     /etc/letsencrypt/live/yoiwerr.me/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yoiwerr.me/privkey.pem;

    # Portal Homepage
    location / {
        root /usr/share/nginx/html;
        index index.html;
    }

    # Static assets
    location /css/   { root /usr/share/nginx/html; expires 7d; }
    location /js/    { root /usr/share/nginx/html; expires 7d; }
    location /bgm/   { root /usr/share/nginx/html; expires 1d; }
    location /photo/ { root /usr/share/nginx/html; expires 7d; }

    # ChatLab
    location /chatlab {
        alias /usr/share/nginx/html;
        try_files /chatlab.html =404;
    }

    # API proxy
    location /api {
        set $upstream api:8000;
        proxy_pass http://$upstream;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

同时更新 `docker-compose.yml`，把证书目录和 nginx 配置挂载进去。

### 13. HTTPS 证书自动续期

Let's Encrypt 证书 90 天过期，设个 crontab：

```bash
sudo crontab -e
# 加这一行：每月 1 号凌晨 3 点续期
0 3 1 * * certbot renew --quiet --pre-hook "cd ~/portal && docker compose stop nginx" --post-hook "cd ~/portal && docker compose start nginx"
```

### 14. 最终效果

访问：
- `https://yoiwerr.me` → 首页
- `https://yoiwerr.me/chatlab` → ChatLab
- `https://yoiwerr.me/api/docs` → API 文档

浏览器地址栏有 **🔒 绿锁**。

---

## 第三部分：更新服务器代码

你本地改了代码，push 到 GitHub，然后服务器拉取并重新部署。

### 标准更新流程

```bash
# 1. SSH 登录服务器
ssh root@<server-ip>

# 2. 拉取最新代码
cd ~/portal
git pull origin master

# 3. 重建并启动（修改过的容器会自动重建）
docker compose up -d --build

# 4. 等几秒后验证
curl -s https://localhost | head -5
```

或者我帮你写一个 **一键更新脚本**：创建 `~/portal/scripts/update.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "[UPDATE] Pulling latest code..."
cd ~/portal
git pull origin master
echo "[UPDATE] Rebuilding & restarting..."
docker compose up -d --build
echo "[UPDATE] Done! Services status:"
docker compose ps
```

```bash
chmod +x ~/portal/scripts/update.sh
# 以后每次更新只跑一条命令：
./scripts/update.sh
```

---

## 第四部分：日常运维命令速查

```bash
cd ~/portal

# ── 查看状态 ──
docker compose ps                          # 所有容器状态
docker compose logs --tail=50              # 最近 50 行日志
docker compose logs -f api                 # 实时看 API 日志
docker compose logs -f                     # 实时看所有日志

# ── 重启服务 ──
docker compose restart api                 # 只重启 API
docker compose restart nginx               # 只重启 nginx
docker compose down && docker compose up -d  # 全部重启

# ── 更新部署 ──
git pull origin master
docker compose up -d --build

# ── 数据库备份 ──
docker compose exec postgres pg_dump -U postgres chatdemopg > backup_$(date +%Y%m%d).sql

# ── 恢复数据库 ──
docker compose exec -T postgres psql -U postgres chatdemopg < backup_20250101.sql

# ── 查看磁盘占用 ──
docker system df                           # Docker 占用
df -h                                      # 磁盘使用

# ── 清理空间 ──
docker system prune -a                     # 清理无用的镜像/容器（谨慎）

# ── 进入容器调试 ──
docker compose exec api bash               # 进 API 容器
docker compose exec postgres psql -U postgres chatdemopg  # 进数据库
```

---

## 第五部分：故障排查

| 现象 | 排查命令 | 常见原因 |
|------|----------|----------|
| 502 Bad Gateway | `docker compose logs api` | API 容器挂了或 `.env` 密钥不对 |
| 404 Not Found | `docker compose ps` | nginx 配置有误，`/chatlab.html` 没挂载 |
| 首页能开，ChatLab 打不开 | `curl localhost/api/v1/imported_files` | Streamlit 或 API 没起来 |
| HTTPS 红锁 | `sudo certbot certificates` | 证书过期，手动续期 |
| 连不上服务器 | `ping <IP>` | 安全组没开 80/443 端口 |
| fetch 失败 | F12 → Network 看请求 URL | API_BASE_URL 配错了 |

---

## 第六部分：用 Cloudflare CDN（进阶）

把域名托管到 Cloudflare 后可以免费开启：

1. **CDN 加速** — 静态文件（CSS/JS/图片）全球缓存，访问更快
2. **DDoS 防护** — 自动拦截攻击流量
3. **防火墙规则** — 按国家/UA/IP 拦截
4. **SSL 终结** — Cloudflare 边缘处理 HTTPS，源服务器不用配证书

操作步骤：
1. 把域名的 NS 服务器换成 Cloudflare 给出的两个地址
2. DNS 记录里的 A 记录打开橙色云朵（代理）
3. SSL/TLS 设为 **Full (strict)** 或 **Full**

Cloudflare 会负责 HTTPS，你的 nginx 只需要处理 80 端口即可。

---

## 附录 A：所有端口一览

| 端口 | 用途 | 公网暴露 |
|------|------|----------|
| 80 | HTTP (nginx) | ✅ 是 |
| 443 | HTTPS (nginx) | ✅ 是 |
| 22 | SSH | ✅ 是 |
| 8000 | FastAPI | ❌ 否（只有 docker 内网） |
| 8501 | Streamlit | ❌ 否（只有 docker 内网） |
| 5432 | PostgreSQL | ❌ 否（只有 docker 内网） |

## 附录 B：发现 BGM 不响？

服务器上访问 `/bgm/` 路径的文件名不能有空格。如果文件是 `Frank Ocean - Self Control.mp3`，需要改成 `Frank_Ocean_-_Self_Control.mp3` 或类似的。

```bash
cd ~/portal/static/bgm
for f in *.mp3; do mv "$f" "$(echo "$f" | sed 's/ /_/g')"; done
```

然后更新 `static/index.html` 里 BGM 播放器的文件路径。
