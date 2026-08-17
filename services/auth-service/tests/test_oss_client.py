"""OSS 客户端测试：对象键前缀与 URL 格式（不真连 OSS，stub oss2.Bucket）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["OSS_ACCESS_KEY_ID"] = "test-ak"
os.environ["OSS_ACCESS_KEY_SECRET"] = "test-sk"
os.environ["OSS_ENDPOINT"] = "oss-cn-hangzhou.aliyuncs.com"
os.environ["OSS_BUCKET"] = "test-bucket"


class _FakeBucket:
    def __init__(self):
        self.puts = []

    def put_object_from_file(self, object_key, local_path):
        self.puts.append((object_key, local_path))


def test_upload_uses_qualifications_prefix_and_returns_url(monkeypatch):
    import oss2 as real_oss2
    from app.services.oss_client import OSSClient

    fake_bucket = _FakeBucket()
    monkeypatch.setattr(real_oss2, "Bucket", lambda *a, **k: fake_bucket)
    client = OSSClient()
    url = client.upload_local_file("C:/tmp/cert.pdf")

    assert fake_bucket.puts
    object_key = fake_bucket.puts[0][0]
    assert object_key.startswith("qualifications/")
    assert object_key.endswith(".pdf")
    assert url == f"https://test-bucket.oss-cn-hangzhou.aliyuncs.com/{object_key}"
