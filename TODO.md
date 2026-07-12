# Portal — 部署清单

多项目统一入口，按顺序从上往下做。

---

## 步骤 1：推送最新代码

在本地开发机上执行：

```bash
cd ~/portal
git add .
git commit -m "update: portal 多项目更新"
git push origin master
```

- [ ] 已推送

---

## 步骤 2：登录服务器，安装 Docker

SSH 登录服务器后执行：

```bash
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER
newgrp docker

# 国内服务器必做：配置 Docker 镜像加速
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker

docker info | grep -A5 "Registry Mirrors"
sudo apt update && sudo apt install docker-compose-plugin -y
docker compose version
```

- [ ] Docker 已安装 + 镜像加速

---

## 步骤 3：开放防火墙端口

```bash
sudo ufw allow 80/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

云控制台安全组开放 80、22。

- [ ] 端口已开放

---

## 步骤 4：克隆项目

```bash
git clone https://github.com/yoiwerr/portal.git ~/portal
```

或直接从本地 scp 整个 `~/portal/` 目录到服务器：

```bash
# 从本地
scp -r ~/portal root@<server-ip>:~/
```

- [ ] 项目已上传到服务器

---

## 步骤 5：执行一键部署

```bash
cd ~/portal
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

- [ ] 部署成功，看到 "Deployment complete!"

---

## 步骤 6：验证

```bash
cd ~/portal
docker compose ps
# 应该看到：portal-nginx、chalab-api、chalab-streamlit、chalab-postgres、specific-api

curl http://localhost               # 首页 HTML
curl http://localhost/api/v1/imported_files  # ChatLab API
curl http://localhost/specific/api/health      # MakeItSpecific API
```

浏览器访问 `http://<服务器公网IP>`

- [ ] 首页正常
- [ ] ChatLab 正常
- [ ] MakeItSpecific 正常
- [ ] API 正常

---

## 访问地址

| 内容 | 地址 |
|------|------|
| 首页 | `http://<IP>` |
| ChatLab | `http://<IP>/chatlab` |
| MakeItSpecific | `http://<IP>/specific` |
| ChatLab API 文档 | `http://<IP>/api/docs` |
| Specific API 文档 | `http://<IP>/specific/docs` |

---

## 日常维护

```bash
cd ~/portal

docker compose logs -f              # 实时日志（全部服务）
docker compose logs api             # 只看 ChatLab API
docker compose logs specific-api      # 只看 MakeItSpecific API
docker compose restart api          # 重启 ChatLab API
docker compose restart specific-api   # 重启 MakeItSpecific
docker compose down                 # 停止全部
docker compose up -d --build        # 重建启动全部
```

## 添加新子项目

```
1. mkdir ~/portal/NewProject
2. 写 NewProject/docker-compose.yml
3. portal/docker-compose.yml → include 加一行
4. portal/nginx/default.conf → 加 location 块
5. docker compose up -d
```

## 数据备份

```bash
# ChatLab PostgreSQL
docker compose exec postgres pg_dump -U postgres chatdemopg > backup_chatlab_$(date +%Y%m%d).sql

# MakeItSpecific SQLite + ChromaDB (在 specificdata volume 中)
docker compose exec specific-api tar czf - /app/data > backup_specific_$(date +%Y%m%d).tar.gz
```
