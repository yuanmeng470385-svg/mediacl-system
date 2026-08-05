"""pytest 基础设施：把仓库根目录加入 sys.path（shared/ 包位于仓库根）"""
import os
import sys

# 本文件位于 services/hcp-service/tests/，需上溯三级到仓库根
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
