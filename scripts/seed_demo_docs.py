"""知识库示例文档种子：生成 3 个示例 txt → 上传 → 离线上架（跳过百炼）→ 向量化

用法（在仓库根目录，需先建库 + 配置 .env 的 OSS/DASHVECTOR/DASHSCOPE）：
    python scripts/seed_demo_docs.py

输出：每个文档的 id/状态/向量化 chunk 数；失败项列出原因（不中断其余项）。
"""
import os
import sys
import logging
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# 服务目录名带连字符（knowledge-service），无法作为 Python 模块用点号导入；
# 按仓库约定（Dockerfile: PYTHONPATH=/app + from app.core.*）把服务根加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "knowledge-service"))

from shared.common.db_session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEMO_DOCS = [
    {
        "title": "示例产品说明书 v1",
        "doc_type": "product",
        "content": (
            "【药品名称】示例注射液\n"
            "【适应症】本品适用于 XX 肿瘤的辅助治疗。\n"
            "【用法用量】推荐剂量按体重计算，每 3 周一次静脉输注。\n"
            "【不良反应】常见：疲劳、恶心。严重：过敏反应（罕见）。\n"
            "【禁忌】对本品任何成分过敏者禁用。\n"
            "【证据等级】B\n"
            "请勿承诺疗效，具体方案由医生根据患者情况决定。"
        ),
    },
    {
        "title": "示例临床指南摘要",
        "doc_type": "guideline",
        "content": (
            "本指南基于 III 期临床试验数据制定。\n"
            "一线治疗推荐：免疫联合化疗。\n"
            "二线治疗：单药或联合方案需评估 PD-L1 表达水平。\n"
            "用药期间需监测肝功能。\n"
            "证据等级：A（随机对照试验荟萃分析）。"
        ),
    },
    {
        "title": "示例竞品对比材料（内部参考）",
        "doc_type": "competitor",
        "content": (
            "本品与竞品在主要终点上的对比：\n"
            "本品中位无进展生存期 11.2 个月，竞品 9.8 个月（III 期 RCT）。\n"
            "安全性：两组不良事件发生率无显著差异。\n"
            "结论仅供内部参考，禁止对外贬低竞品。"
        ),
    },
]


def main():
    from app.core.document_manager import DocumentManager
    from app.db.repositories.knowledge_repo import KnowledgeRepository

    db = SessionLocal()
    manager = DocumentManager(db)
    repo = KnowledgeRepository(db)

    uploaded = []
    for spec in DEMO_DOCS:
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
                f.write(spec["content"])
                local_path = f.name
            doc = manager.create_from_upload(
                local_path=local_path,
                title=spec["title"],
                doc_type=spec["doc_type"],
                uploader_id=None,
                evidence_level="B",
                source="demo-seed",
            )
            manager.approve_without_bailian(doc.id, reviewer_id=None)
            doc = repo.get(doc.id)
            uploaded.append({"id": doc.id, "title": doc.title, "status": doc.status, "has_content": bool(doc.content)})
            logger.info("OK 文档 %s → id=%s status=%s content=%d 字", spec["title"], doc.id, doc.status, len(doc.content or ""))
            os.unlink(local_path)
        except Exception as exc:
            logger.error("FAIL %s: %s", spec["title"], exc)
            uploaded.append({"title": spec["title"], "error": str(exc)})

    db.close()
    logger.info("种子完成：%s", uploaded)


if __name__ == "__main__":
    main()
