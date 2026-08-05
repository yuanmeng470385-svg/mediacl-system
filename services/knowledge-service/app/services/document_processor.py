"""文档正文解析与切分（方案 9.1 的简化落地：表格/OCR 由百炼托管处理，本地只做正文抽取）"""
import logging
from typing import List

logger = logging.getLogger(__name__)


def extract_text(local_path: str) -> str:
    """按扩展名抽取正文（pdf/docx/pptx/txt），失败返回空串"""
    suffix = local_path.rsplit(".", 1)[-1].lower() if "." in local_path else ""
    try:
        if suffix == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(local_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if suffix in ("docx", "doc"):
            from docx import Document
            doc = Document(local_path)
            return "\n".join(p.text for p in doc.paragraphs)
        if suffix in ("pptx", "ppt"):
            from pptx import Presentation
            prs = Presentation(local_path)
            texts = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        texts.append(shape.text_frame.text)
            return "\n".join(texts)
        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as exc:
        logger.warning("文档解析失败（%s），返回空正文: %s", suffix, exc)
        return ""


def chunk_text(text: str, size: int = 512) -> List[str]:
    """按段落切分，合并至 size 字符（保守：汉字按 1 字符计）"""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 > size:
            if current:
                chunks.append(current)
            # 超长段落硬切：避免单个段落超过 size（与 docstring「合并至 size 字符」一致）
            while len(para) > size:
                chunks.append(para[:size])
                para = para[size:]
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks
