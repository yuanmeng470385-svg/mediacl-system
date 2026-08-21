"""batch-import 入口守卫（审计遗留：filename=None → AttributeError 500）"""
import asyncio
import io

import pytest

from app.api.hcps import batch_import_hcps
from shared.common.response import ParamError


class _File:
    def __init__(self, filename):
        self.filename = filename
        self.file = io.BytesIO(b"")


def test_batch_import_filename_none_param_error():
    """filename=None（部分客户端不传文件名）→ ParamError，而非 AttributeError 500"""
    with pytest.raises(ParamError):
        asyncio.run(batch_import_hcps(file=_File(None), current_user={"id": 1}, db=None))


def test_batch_import_file_size_cap(monkeypatch):
    """文件大小上限（M13）：超限 → ParamError，防超大文件/压缩炸弹占内存"""
    from app.api import hcps as hcps_api

    monkeypatch.setattr(hcps_api, "MAX_IMPORT_FILE_SIZE", 10)

    class _BigFile:
        filename = "doctors.xlsx"
        file = io.BytesIO(b"x" * 100)

    with pytest.raises(ParamError):
        asyncio.run(batch_import_hcps(file=_BigFile(), current_user={"id": 1}, db=None))
