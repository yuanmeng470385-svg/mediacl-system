#!/bin/bash
# MedAgent 多租户开通：5 家公司各自独立后端（独立 PG 库 / Redis db / 端口块 / web 入口）。
# Python 代码与 venv 与母版共用，仅靠 systemd EnvironmentFile 隔离配置；root 下运行，幂等可重跑。
# 布局：端口块 8100+i*10（8 个服务连号，映射关系同母版 8000-8007）；web 入口 8801+i（公网）；
#       Redis db 1+i；库 medagent_<slug>；JWT_SECRET 每租户独立（跨租户 token 不通用）。
set -euo pipefail

PUB_IP=39.96.52.114
MASTER_ENV=/opt/medagent/.env
TENANT_DIR=/opt/medagent/tenants
# slug|公司全称|简称|主色|字标（App 端 build-brands.sh 用同一张表，改这里要同步）
TENANTS=(
  "zunpin|北京尊品科技有限公司|尊品科技|#2F54EB|尊"
  "xiluoli|北京希洛利科技有限公司|希洛利科技|#0E9488|希"
  "chenglin|郑州成琳网络科技有限公司|成琳网络|#D97706|成"
  "qiyijia|北京琪宜嘉科技有限公司|琪宜嘉科技|#7C3AED|琪"
  "jidian|集典（北京）信息科技有限公司|集典信息|#BE123C|典"
)
# 单元名|代码目录|端口偏移（相对块首，同母版 8000-8007 的分配）
SVCS=(
  "gateway|gateway|0"
  "specialist|specialist-service|1"
  "visit|visit-service|2"
  "knowledge|knowledge-service|3"
  "compliance|compliance-service|4"
  "audit|audit-service|5"
  "hcp|hcp-service|6"
  "auth|auth-service|7"
)

mkdir -p "$TENANT_DIR" /var/log/medagent

i=0
for row in "${TENANTS[@]}"; do
  IFS='|' read -r slug full short color char <<<"$row"
  base=$((8100 + i*10))
  webport=$((8801 + i))
  redisi=$((i+1))
  jwt=$(openssl rand -hex 32)
  envf="$TENANT_DIR/$slug.env"

  # 1) 租户 .env：母版全量改写隔离键（systemd 注入的进程 env 优先级高于应用自读 .env；
  #    qwen/百炼/OSS 等键保持母版值 = 各租户共享凭证）
  awk -v db="medagent_$slug" -v ri="$redisi" -v sw="http://$PUB_IP:$webport" -v js="$jwt" -v b="$base" '
    /^DATABASE_URL=|^AUDIT_DATABASE_URL=/ { sub(/medagent$/, db) }
    /^REDIS_URL=/ { sub(/6379\/0$/, "6379/" ri) }
    /^SHARE_WEB_URL_BASE=/ { print "SHARE_WEB_URL_BASE=" sw; next }
    /^JWT_SECRET=/ { print "JWT_SECRET=" js; next }
    /^GATEWAY_PORT=/ { print "GATEWAY_PORT=" b; next }
    /^SPECIALIST_SERVICE_PORT=/ { print "SPECIALIST_SERVICE_PORT=" b+1; next }
    /^VISIT_SERVICE_PORT=/ { print "VISIT_SERVICE_PORT=" b+2; next }
    /^KNOWLEDGE_SERVICE_PORT=/ { print "KNOWLEDGE_SERVICE_PORT=" b+3; next }
    /^COMPLIANCE_SERVICE_PORT=/ { print "COMPLIANCE_SERVICE_PORT=" b+4; next }
    /^AUDIT_SERVICE_PORT=/ { print "AUDIT_SERVICE_PORT=" b+5; next }
    /^HCP_SERVICE_PORT=/ { print "HCP_SERVICE_PORT=" b+6; next }
    { print }
    END {
      # 网关经 *_SERVICE_URL 找兄弟服务（母版 .env 无此键、靠代码默认值），租户须显式指向本块
      print "AUTH_SERVICE_URL=http://localhost:" b+7
      print "SPECIALIST_SERVICE_URL=http://localhost:" b+1
      print "VISIT_SERVICE_URL=http://localhost:" b+2
      print "KNOWLEDGE_SERVICE_URL=http://localhost:" b+3
      print "COMPLIANCE_SERVICE_URL=http://localhost:" b+4
      print "AUDIT_SERVICE_URL=http://localhost:" b+5
      print "HCP_SERVICE_URL=http://localhost:" b+6
    }
  ' "$MASTER_ENV" > "$envf"
  chmod 600 "$envf"
  mkdir -p "/var/www/medagent/apk-$slug"   # 各租户专属 APK 目录（web 入口 /apk/ 指向这里）

  # 2) 租户库：母版 dump 一次逐租户恢复（角色是集群级已存在，ACL 随 dump 带过）
  if ! runuser -u postgres -- psql -lqt | cut -d'|' -f1 | grep -qw "medagent_$slug"; then
    [ -f /tmp/medagent-master.dump ] || runuser -u postgres -- pg_dump -Fc medagent -f /tmp/medagent-master.dump
    runuser -u postgres -- createdb -O medagent "medagent_$slug"
    runuser -u postgres -- pg_restore -d "medagent_$slug" /tmp/medagent-master.dump
    echo "restored medagent_$slug"
  fi

  # 3) systemd：8 服务（仅绑 127.0.0.1，公网统一走各租户 web 入口）
  for spec in "${SVCS[@]}"; do
    IFS='|' read -r unit dir off <<<"$spec"
    port=$((base+off))
    cat > "/etc/systemd/system/medagent-$slug-$unit.service" <<UNIT
[Unit]
Description=MedAgent tenant $slug $unit service
After=network.target postgresql-15.service redis.service
[Service]
WorkingDirectory=/opt/medagent/services/$dir
EnvironmentFile=$envf
ExecStart=/bin/bash -c 'exec /opt/medagent/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $port >>/var/log/medagent/$slug-$unit.log 2>&1'
Restart=always
RestartSec=3
Environment=MALLOC_ARENA_MAX=2
[Install]
WantedBy=multi-user.target
UNIT
  done

  # 4) web 入口（公网 880x）：同一 server.js，env 注入品牌与网关指向
  cat > "/etc/systemd/system/medagent-web-$slug.service" <<UNIT
[Unit]
Description=MedAgent web proxy $slug ($webport)
After=network.target
[Service]
WorkingDirectory=/opt/medagent-web
Environment=PORT=$webport
Environment=API_TARGET=http://127.0.0.1:$base
Environment=ASR_TARGET=http://127.0.0.1:$((base+2))
Environment="BRAND_NAME=$full"
Environment="BRAND_SHORT=$short"
Environment="BRAND_PRIMARY=$color"
Environment="BRAND_LOGO_CHAR=$char"
Environment="BRAND_TAGLINE=药企 AI 数字员工系统"
Environment=APK_DIR=/var/www/medagent/apk-$slug
ExecStart=/usr/local/bin/node server.js
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT

  i=$((i+1))
done

systemctl daemon-reload
for row in "${TENANTS[@]}"; do
  IFS='|' read -r slug _ <<<"$row"
  for spec in "${SVCS[@]}"; do
    IFS='|' read -r unit _ <<<"$spec"
    systemctl enable "medagent-$slug-$unit.service" >/dev/null 2>&1
    systemctl restart "medagent-$slug-$unit.service" 2>/dev/null || true
  done
  systemctl enable "medagent-web-$slug.service" >/dev/null 2>&1
  systemctl restart "medagent-web-$slug.service"   # 重跑必须 restart，否则旧进程带旧 env 继续跑
done
echo "OK: 5 tenants enabled (web 8801-8805)"
