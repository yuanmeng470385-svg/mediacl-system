"""阿里云 OSS 客户端（备案资质证书文件，前缀 qualifications/）"""
import os
import uuid
from datetime import datetime
from typing import Optional

import oss2

from app.config import settings


class OSSClient:
    def __init__(self):
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        self.bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET)
        self.bucket_name = settings.OSS_BUCKET
        self.endpoint = settings.OSS_ENDPOINT

    def upload_local_file(self, local_path: str, object_key: Optional[str] = None) -> str:
        if not object_key:
            suffix = os.path.splitext(local_path)[1]
            object_key = f"qualifications/{datetime.now():%Y%m%d}/{uuid.uuid4().hex}{suffix}"
        self.bucket.put_object_from_file(object_key, local_path)
        return f"https://{self.bucket_name}.{self.endpoint}/{object_key}"
