# MedAgent 生产部署手册

> 演示期拓扑：服务器跑 8 个 FastAPI 服务（docker-compose）+ nginx 托管 web 构建产物；
> App 为局域网 HTTP 直连，正式上线需换 TLS（见文末「转正式上线」）。

## 1. 后端 .env（生产值）

从根目录 `.env.example` 复制，按 `deploy/env.production.example` 对齐，关键差异：

| 键 | 生产值 | 说明 |
|---|---|---|
| `AUTH_DEV_MODE` | `false` | auth-service 启动时校验：`DEPLOY_ENV=production` 下为 true 会**拒绝启动** |
| `DEPLOY_ENV` | `production` | 生产守卫开关（见上） |
| `SHARE_WEB_URL_BASE` | `http://<服务器IP或域名>` | 数字分身分享链接改走 web 落地页（不设则退回 App 深链 `medagent-doctor://`） |
| `JWT_SECRET` | 重新生成强随机 | `python -c "import secrets; print(secrets.token_urlsafe(48))"`，勿沿用开发值 |
| `DB_PASSWORD` / `REDIS_PASSWORD` / `AUDIT_DB_PASSWORD` | 强随机 | compose 对这三个键 `:?` 强制必填，缺失直接拒起 |

## 2. 起后端（docker-compose —— 未走通，仅备档）

> ⚠️ 本节路线**从未实际执行**：compose 引用的 ACR 镜像从未构建推送过。
> 2026-09-15 首次服务器部署走的是 §2b 的 venv 路线，以那边为准。

```bash
# 仓库根目录执行；镜像来自阿里云 ACR（见 docker-compose.prod.yml 头部注释）
docker compose --env-file .env -f deploy/docker-compose.prod.yml up -d

# 首次部署必做：审计专用低权角色（audit-service 依赖，不执行它起不来）
docker exec -i medagent-postgres psql -U medagent medagent \
  -v audit_password='<AUDIT_DB_PASSWORD>' < scripts/migrations/002_audit_immutable.sql

# 新增迁移手跑（编号见 scripts/migrations/，跳过已跑过的）
docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/0XX_xxx.sql
```

## 2b. 实际部署路线（2026-09-15 首次上机，以此为准）

> 服务器：阿里云 ECS `39.96.52.114`（Alibaba Cloud Linux 3，2C/1.8G 内存 + 3G swap），
> 80 端口被同机既有站点（node）占用，**MedAgent web 走 8080**。

| 组件 | 部署方式 | 路径 / 备注 |
|---|---|---|
| PostgreSQL 15 | PGDG 源（repo 文件 `rhel-$releasever`→`rhel-8` 补丁）+ systemd `postgresql-15` | 只监听 127.0.0.1 |
| Redis 6.2 | dnf 原生 + systemd `redis` | 同上 |
| Python | `python3.11 -m venv /opt/medagent/venv`，pip 走 aliyun 镜像，`services/*/requirements.txt` 并集一次装齐 | |
| 代码 | `git archive HEAD` 打包上传解压到 `/opt/medagent`（非 git 检出） | `.env` 放 `/opt/medagent/.env`（chmod 600） |
| 8 服务 | systemd `medagent-{gateway,specialist,visit,knowledge,compliance,audit,hcp,auth}.service`，`uvicorn --host 0.0.0.0 --port 800X` | 日志 `/var/log/medagent/<name>.log` |
| 数据 | 开发库 `pg_dump -Fc` → 服务器 `pg_restore`（演示数据/账号全量带走） | 见下方**角色坑** |
| web | node http-proxy `/opt/medagent-web/server.js`（systemd `medagent-web`，监听 **8080**）：`/api/`→8000 含 WS、`/apk/`、SPA 回退 | 静态 `/var/www/medagent/{dist,apk}`；nginx 不在 alinux3 源、nginx.org 源失败 |

**角色坑（restore 前必须建齐角色）**：dump 引用的角色 pg_restore 不会创建。漏建
`medagent_audit_owner` 会让 `audit_logs` 归属落回 `postgres` 且 ACL 丢弃（报
"errors ignored on restore: 3"），audit-service 写审计全失败。四个角色：
`medagent`、`medagent_audit`、`medagent_audit_cleanup`、`medagent_audit_owner`，
然后重跑 002 的 §2-§4（OWNER/GRANT 块）。

**安全组**（阿里云控制台，用户操作）：开 **8080（web）/ 8000（网关 API）/ 8002（ASR WS）**；22 已开。
APK 下载：`http://39.96.52.114:8080/apk/medagent-rep.apk`、`/apk/medagent-doctor.apk`。

**服务器 .env 与本地差异**：`DATABASE_URL`/`AUDIT_DATABASE_URL`/`REDIS_URL` 主机改
`127.0.0.1`；`SHARE_WEB_URL_BASE=http://39.96.52.114:8080`；`DEPLOY_ENV=dev`
（短信 console + `AUTH_DEV_MODE=true` 下生产守卫要求）；其余（qwen/NLS/百炼/密钥）原样。

**已知良性报错**：audit-service 每次启动会打一条「审计日志清理失败 InsufficientPrivilege」——
清理需 `AUDIT_CLEANUP_DATABASE_URL`（medagent_audit_cleanup 专用账号，见 005），未配置时
与本地开发机行为一致，可忽略；要消除则按 005 配该 env。

## 3. web 管理后台（nginx）

> 注：首次部署实际用的是 §2b 的 node 代理（等效功能）；本节 nginx 路线留给
> 换 nginx 的环境参考。

```bash
cd web && npm run build          # 产物 dist/（vite 默认 outDir、base=/）
# dist/ 拷到服务器（如 /var/www/medagent-web/dist），然后：
cp deploy/nginx/medagent-web.conf /etc/nginx/conf.d/   # 改 server_name/root 后
nginx -t && nginx -s reload
```

配置要点：SPA `try_files` 回退（BrowserRouter 深链如 `/share/twin/:token` 分享落地页依赖它）、
`/api/` 反代 127.0.0.1:8000 并透传 WS 升级头、`client_max_body_size 20m`（图片上传）。

## 4. App（APK）

```bash
# 两工程都出 release APK（签名复用 debug keystore，仅演示期）
cd mobile/android && ./gradlew.bat assembleRelease        # app/build/outputs/apk/release/
cd mobile-doctor/android && ./gradlew.bat assembleRelease
```

release 包已放开明文流量（`app/src/release/AndroidManifest.xml`），API 指向
`mobile*/src/config.ts` 里 release 分支的局域网 IP —— **服务器 IP 变了要改这两处再打包**。

## 5. 账号入口

- **医生自助注册**：医生端 App 登录页「立即注册」（验证码制：手机号→获取验证码→
  姓名+选填医院信息，注册即登录，后端 `POST /api/v1/auth/register`；验证码走
  `send-code` 的 `scene=register`，只对未注册号下发）——给新医生装机后先走这里。
- 管理员/代表账号：admin 在 web 后台 `POST /api/v1/users` 建号，或 seed 脚本。
- 演示账号备案见根 CLAUDE.md。

## 6. 分享落地页

代表在 App 里给医生建「数字分身分享」后，share_url 形如
`{SHARE_WEB_URL_BASE}/share/twin/<token>`：微信里打开是落地页（激活码大字+复制+
「打开医生端 App」按钮）；App 深链 `medagent-doctor://twin/<token>` 仍兼容直开。
token 即激活码，医生端 TwinActivate 页支持手输。

## 7. 转正式上线（挂账）

- [ ] **阿里云短信签名+模板未办（2026-09-15 挂账，用户拍板先不做）**：
      `AUTH_SMS_PROVIDER` 仍为 console（验证码走 DEV 回显/服务日志），
      `AUTH_DEV_MODE=true` → 服务器 `DEPLOY_ENV` 必须保持 `dev`（生产守卫会拒启）。
      办好后改：`AUTH_SMS_PROVIDER=aliyun` + `AUTH_SMS_SIGN_NAME`/`AUTH_SMS_TEMPLATE_CODE`
      + `AUTH_DEV_MODE=false` + `DEPLOY_ENV=production`
- [ ] **安全组 8080/8000/8002 待用户在阿里云控制台开放**（首次部署后公网才可达）
- [ ] 服务器 DB/Redis 密码沿用开发值（仅监听 127.0.0.1）——转正式前换强随机
- [ ] 服务器代码为 git archive 快照（非 git 检出）——更新需重新打包上传，或改 git clone
- [ ] 服务器未配备份 cron（`scripts/backup_db.py`，前置 007 序列授权）
- [ ] 域名 + TLS 证书：nginx 443，App `API_SCHEME/WS_SCHEME` 改 https/wss，
      撤两工程 release manifest 的 `usesCleartextTraffic`（换 networkSecurityConfig 白名单）
- [ ] config.ts release IP 改正式域名
- [ ] `SHARE_WEB_URL_BASE` 改 https 域名
- [ ] release 签名换正式 keystore（现为 debug）
