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
