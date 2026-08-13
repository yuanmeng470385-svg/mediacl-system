# 安全收尾操作清单（2026-08-13，人工执行）

全量修复批（B1-B7）完成后的用户侧人工操作。按顺序执行，每步独立可回滚。

## 1. 数据库迁移 008（必须，否则 visit-service 会因 status 列缺失报错）

```bash
# 先启动 Docker Desktop（WSL 引擎）
docker exec -i medagent-postgres psql -U medagent medagent \
  < scripts/migrations/008_add_visit_status.sql
# 验证：
docker exec medagent-postgres psql -U medagent medagent \
  -c "SELECT status, count(*) FROM visit_records GROUP BY status;"
# 预期：in_progress / completed 两行（无 cancelled —— 取消是 008 之后才可能出现）
```

## 2. 凭据轮换（审计遗留，建议执行）

### 2.1 admin 密码

```bash
# 随机生成新密码（或自行指定强密码）
python scripts/seed_admin.py --username admin --password <新密码> --phone <管理员手机号>
# seed_admin 会同时刷新审计日志；改完立即生效（登录走库校验）
```

### 2.2 JWT_SECRET（全局 token 签名密钥）

```bash
# 生成新密钥
openssl rand -hex 32
# 1. 更新仓库根 .env 的 JWT_SECRET
# 2. 重启全部 8 个服务（JWT_SECRET 是启动时读取，改动不热更新）
# 3. 所有用户现有 token 立即失效（7 天内的 token 也作废），需重新登录 —— 属预期
# 注意：DB_PASSWORD / INTERNAL_API_KEY / AUDIT_CLEANUP_DATABASE_URL 若还在用
#       默认值，一并轮换（生产环境 shared/common/db_session.py 会拒绝默认密码启动）
```

### 2.3 验证

```bash
# 旧 token 应 401
curl -s -H "Authorization: Bearer <旧token>" http://localhost:8000/api/v1/auth/me
```

## 3. git 历史清洗（可选，仅当历史中确有敏感内容）

2026-08-12 全量上传 GitHub（yuanmeng470385-svg/mediacl-system）时已确认**已跟踪内容零敏感**
（.env gitignored、占位符仅 .env.example / .xcode.env）。以下仅当仍不放心时执行：

```bash
# 1. 用 git filter-repo 从全部历史移除 .env 与联调凭据文件
pip install git-filter-repo
cd "/d/gongsi/medical system"
git filter-repo --invert-paths --path-glob '*.env' --path .env \
  --path-glob 't10-office3d/token*.txt' --path-glob 't10-office3d/login*.json'

# 2. 重设远端并强制推送（会改写历史 —— 先通知所有协作者）
git remote add origin https://codeup.aliyun.com/6a6c3e94e69c408bf87d8b1a/mediaclsystem.git
git remote add github https://github.com/yuanmeng470385-svg/mediacl-system.git
git push --force origin master
git push --force github master

# 3. 已泄露凭据（如曾提交过的 token）不因历史重写而失效 —— 必须按第 2 节轮换
```

## 4. 新环境变量说明（本次修复新增）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000,http://localhost:5173` | 网关跨域白名单（逗号分隔）；生产填真实前端域名 |
| `DEV_MODE` / `AUTH_DEV_MODE` | `false` | `true` 时豁免：默认 DB 密码启动守卫、console 短信通道、send-code 回传验证码 |
| `DB_USER` / `DB_PASSWORD` | 无 | 备份脚本用（backup_db.py），优先于 DATABASE_URL 解析 |

生产部署注意：`.env` 中 `DEV_MODE` 保持关闭，`DATABASE_URL` 使用真实凭据，
`AUTH_SMS_PROVIDER=aliyun` + 签名/模板，否则 auth-service 发送验证码会 fail-fast。

## 5. 回归冒烟（可选）

```bash
# 后端 8 服务全量测试（2026-08-12 基线 404 passed）
cd services/visit-service && python -m pytest tests/ -q      # 73
cd services/specialist-service && python -m pytest tests/ -q # 74
cd services/auth-service && python -m pytest tests/ -q       # 50
cd services/compliance-service && python -m pytest tests/ -q # 59
cd services/audit-service && python -m pytest tests/ -q      # 19
cd services/gateway && python -m pytest tests/ -q            # 40
cd services/hcp-service && python -m pytest tests/ -q        # 38
cd services/knowledge-service && python -m pytest tests/ -q  # 51
# 移动端 + web
cd mobile && npx jest          # 70
cd web && npm run build        # PASS
```
