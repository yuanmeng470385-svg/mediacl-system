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

## 2c. 多租户白标（2026-09-23：5 家公司独立后端）

5 家演示公司各有一套"自己的系统"：**一套代码 + 5 套运行时**（独立 PG 库 / Redis db /
端口块 / JWT 密钥 / web 入口，互不可见）；品牌标签走 `/brand.json`——web 代理按实例返回
公司名，前端启动时换标签页标题/登录卡/侧栏/版权行（母版与本地开发无 brand.json 时回退 MedAgent）。

| 租户 slug | 公司 | web 入口（公网） | 服务端口块 | PG 库 | Redis |
|---|---|---|---|---|---|
| zunpin | 北京尊品科技有限公司 | :8801 | 8100-8107 | medagent_zunpin | db1 |
| xiluoli | 北京希洛利科技有限公司 | :8802 | 8110-8117 | medagent_xiluoli | db2 |
| chenglin | 郑州成琳网络科技有限公司 | :8803 | 8120-8127 | medagent_chenglin | db3 |
| qiyijia | 北京琪宜嘉科技有限公司 | :8804 | 8130-8137 | medagent_qiyijia | db4 |
| jidian | 集典（北京）信息科技有限公司 | :8805 | 8140-8147 | medagent_jidian | db5 |

- 开通/重建：`deploy/multi-tenant/setup-tenants.sh`（服务器 root 运行，幂等）。租户 env 在
  `/opt/medagent/tenants/<slug>.env`（覆盖库/Redis/端口/JWT/SHARE_WEB_URL_BASE，并显式写全
  8 个 `*_SERVICE_URL` 指向本块）；unit 命名 `medagent-<slug>-<svc>` ×8 + `medagent-web-<slug>`，
  服务只绑 127.0.0.1，公网统一走各自 web 入口。qwen/百炼/OSS 等凭证母版共享（一本账）。
- web 代理多实例化：`deploy/web-proxy/server.js`（`PORT`/`API_TARGET`/`BRAND_NAME`/`BRAND_SHORT`
  由 systemd 注入；母版 8080 不设 env 行为与旧版一致；服务器旧版备份 server.js.bak-multitenant）。
- 隔离已验证：A 租户 token 在 B 租户 401（JWT_SECRET 每租户随机）；各租户 demo_rep 可登录。
- **安全组需放行 8801-8805**（阿里云控制台，人工操作；服务端口块不出公网）。
- App 品牌包见下方「App 端品牌包」。

### App 端品牌包（10 个 APK）

- 一键构建：`deploy/multi-tenant/build-brands.sh`（5 品牌 × 代表/医生两端）。每品牌注入四件套后
  assembleRelease，构建完 `git checkout` 还原源文件，母版/开发行为不变：
  1. `<app>/src/brandConfig.ts` → 登录页品牌块（主色字标 + `<简称>数字员工/医生` + 公司全称）
     + 全流量走该租户 web 入口 880x（REST/聊天 WS 走 `/api/`，ASR 走 `/ws/` 由代理分流）；
  2. `strings.xml` app_name → `尊品数字员工`/`尊品医生`（桌面名）；
  3. 桌面图标 PIL 重生成（主色字标，`gen_brand_icon.py`）；
  4. `-PBRAND_SUFFIX=.<slug>` 包名后缀 → **5 家 App 可同机共存**。
- 上传映射：`out/medagent-rep-<slug>.apk → /var/www/medagent/apk-<slug>/medagent-rep.apk`（医生端同理），
  即各租户 `http://<ip>:880x/apk/medagent-rep.apk` 下载的是自家包；App 内更新检查也按此自洽。
- 端口接线：`src/config.ts` 新增 `API_PORT/ASR_PORT`（BRAND 为 null 时保持 8000/8002 直连，单测口径不变）。

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
- [x] ~~安全组 8080/8000/8002 待用户在阿里云控制台开放~~（2026-09-15 已开放，公网冒烟 11/11 全绿）
- [ ] 服务器 DB/Redis 密码沿用开发值（仅监听 127.0.0.1）——转正式前换强随机
- [ ] 服务器代码为 git archive 快照（非 git 检出）——更新需重新打包上传，或改 git clone
- [ ] 服务器未配备份 cron（`scripts/backup_db.py`，前置 007 序列授权）
- [ ] 域名 + TLS 证书：nginx 443，App `API_SCHEME/WS_SCHEME` 改 https/wss，
      撤两工程 release manifest 的 `usesCleartextTraffic`（换 networkSecurityConfig 白名单）
- [ ] config.ts release IP 改正式域名
- [ ] `SHARE_WEB_URL_BASE` 改 https 域名
- [ ] release 签名换正式 keystore（现为 debug）
