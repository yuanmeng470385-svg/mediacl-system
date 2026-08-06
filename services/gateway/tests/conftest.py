"""pytest 基础设施：把仓库根目录加入 sys.path（shared/ 包位于仓库根）"""
import os
import sys

# 本文件位于 services/gateway/tests/，需上溯三级到仓库根
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# 密钥守卫（app/config.py 模块级 fail-fast、shared/common/internal_auth.py）要求
# JWT_SECRET / INTERNAL_API_KEY 必须是强值。测试环境在这里显式配置，
# 不依赖根目录 .env 或外部环境变量，保证测试可复现。
os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key-not-a-default")
