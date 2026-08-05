"""pytest 基础设施：把仓库根目录加入 sys.path（shared/ 包位于仓库根）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
