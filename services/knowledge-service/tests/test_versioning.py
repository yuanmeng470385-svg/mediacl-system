"""文档版本链：同 title+product 重复上传生成新版本"""
from app.core.document_manager import _next_revision
import pytest


def test_next_revision_from_previous():
    class _Prev:
        revision = 3
    assert _next_revision(_Prev()) == 4


def test_next_revision_none():
    assert _next_revision(None) == 1
