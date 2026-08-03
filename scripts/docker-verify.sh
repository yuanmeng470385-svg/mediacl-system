#!/bin/bash
# ==============================================
# MedAgent Docker 验证脚本
# 检查所有服务能否正常启动
# ==============================================
set -e

echo "=============================="
echo "MedAgent Docker 验证"
echo "=============================="

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker 已安装${NC}"

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ docker-compose 未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✅ docker-compose 已安装${NC}"

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env 文件不存在，从 .env.example 复制...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}⚠️  请编辑 .env 填入真实 API Key 后重新运行${NC}"
    exit 1
fi
echo -e "${GREEN}✅ .env 文件存在${NC}"

# 构建所有服务镜像
echo ""
echo "📦 构建所有服务镜像..."
docker compose build --parallel 2>&1 | tail -20
echo -e "${GREEN}✅ 镜像构建完成${NC}"

# 启动基础设施
echo ""
echo "🗄️  启动 PostgreSQL + Redis..."
docker compose up -d postgres redis
echo "等待数据库就绪..."
sleep 8

# 检查数据库
if docker compose exec -T postgres pg_isready -U medagent 2>/dev/null; then
    echo -e "${GREEN}✅ PostgreSQL 就绪${NC}"
else
    echo -e "${RED}❌ PostgreSQL 启动失败${NC}"
    docker compose logs postgres | tail -20
    exit 1
fi

# 检查 Redis
if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    echo -e "${GREEN}✅ Redis 就绪${NC}"
else
    echo -e "${RED}❌ Redis 启动失败${NC}"
    exit 1
fi

# 启动所有微服务
echo ""
echo "🚀 启动所有微服务..."
docker compose up -d --scale specialist-service=1 --scale visit-service=1 \
    --scale knowledge-service=1 --scale compliance-service=1 \
    --scale audit-service=1 --scale hcp-service=1 gateway

echo "等待服务启动..."
sleep 10

# 验证各服务健康检查
echo ""
echo "🔍 验证服务健康状态..."

SERVICES=(
    "gateway:8000"
    "specialist-service:8001"
    "visit-service:8002"
    "knowledge-service:8003"
    "compliance-service:8004"
    "audit-service:8005"
    "hcp-service:8006"
)

ALL_OK=true
for svc in "${SERVICES[@]}"; do
    NAME="${svc%%:*}"
    PORT="${svc##*:}"
    if curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✅${NC} ${NAME} (${PORT})"
    else
        echo -e "  ${RED}❌${NC} ${NAME} (${PORT}) - 未响应"
        ALL_OK=false
    fi
done

# 验证网关路由
echo ""
echo "🔀 验证网关路由..."
if curl -sf "http://localhost:8000/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 网关健康检查通过${NC}"
else
    echo -e "${RED}❌ 网关不响应${NC}"
    ALL_OK=false
fi

echo ""
if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}=============================="
    echo "✅ 所有服务验证通过！"
    echo "==============================${NC}"
    echo ""
    echo "访问地址："
    echo "  API 网关:  http://localhost:8000"
    echo "  API 文档:  http://localhost:8000/docs"
    echo "  合规服务:  http://localhost:8004/docs"
    echo "  审计服务:  http://localhost:8005/docs"
else
    echo -e "${RED}=============================="
    echo "❌ 部分服务验证失败，请检查日志"
    echo "==============================${NC}"
    echo ""
    echo "查看日志: docker compose logs <service-name>"
    exit 1
fi
