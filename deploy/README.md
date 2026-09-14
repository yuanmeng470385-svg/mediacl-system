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

## 2. 起后端（docker-compose）

```bash
# 仓库根目录执行；镜像来自阿里云 ACR（见 docker-compose.prod.yml 头部注释）
docker compose --env-file .env -f deploy/docker-compose.prod.yml up -d

# 首次部署必做：审计专用低权角色（audit-service 依赖，不执行它起不来）
docker exec -i medagent-postgres psql -U medagent medagent \
  -v audit_password='<AUDIT_DB_PASSWORD>' < scripts/migrations/002_audit_immutable.sql

# 新增迁移手跑（编号见 scripts/migrations/，跳过已跑过的）
docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/0XX_xxx.sql
```

## 3. web 管理后台（nginx）

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

- **医生自助注册**：医生端 App 登录页「立即注册」（手机号+姓名+密码，注册即登录，
  后端 `POST /api/v1/auth/register`）——给新医生装机后先走这里。
- 管理员/代表账号：admin 在 web 后台 `POST /api/v1/users` 建号，或 seed 脚本。
- 演示账号备案见根 CLAUDE.md。

## 6. 分享落地页

代表在 App 里给医生建「数字分身分享」后，share_url 形如
`{SHARE_WEB_URL_BASE}/share/twin/<token>`：微信里打开是落地页（激活码大字+复制+
「打开医生端 App」按钮）；App 深链 `medagent-doctor://twin/<token>` 仍兼容直开。
token 即激活码，医生端 TwinActivate 页支持手输。

## 7. 转正式上线（挂账）

- [ ] 域名 + TLS 证书：nginx 443，App `API_SCHEME/WS_SCHEME` 改 https/wss，
      撤两工程 release manifest 的 `usesCleartextTraffic`（换 networkSecurityConfig 白名单）
- [ ] config.ts release IP 改正式域名
- [ ] `SHARE_WEB_URL_BASE` 改 https 域名
- [ ] release 签名换正式 keystore（现为 debug）
