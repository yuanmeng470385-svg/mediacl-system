"""通义听悟客户端 — 拜访音频转写（ASR）

真实调用需要：
  - ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET
  - TINGWU_APP_KEY
  - 已安装 alibabacloud_tingwu20230930（requirements 已声明）

开发调试/测试用 TingwuMockClient（文本模拟）。未配置密钥或 SDK 未安装时，
真实客户端会明确报错，业务层可切换 mock。
"""
import os
import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TingwuClient:
    """通义听悟真实客户端（SDK 延迟导入，调用时才检查）"""

    def __init__(self, app_key: Optional[str] = None):
        self.app_key = app_key or os.getenv("TINGWU_APP_KEY", "")

    def _get_client(self):
        """延迟导入 SDK，未安装时给出明确报错"""
        try:
            from alibabacloud_tea_openapi.models import Config
            from alibabacloud_tingwu20230930.client import Client
            from alibabacloud_tingwu20230930 import models as t_models
        except ImportError as e:
            raise RuntimeError(
                "未安装 alibabacloud_tingwu20230930，无法调用听悟；"
                "开发调试请用 TingwuMockClient"
            ) from e

        self._models = t_models
        config = Config(
            access_key_id=os.getenv("ALIYUN_ACCESS_KEY_ID", ""),
            access_key_secret=os.getenv("ALIYUN_ACCESS_KEY_SECRET", ""),
        )
        config.endpoint = "tingwu.cn-beijing.aliyuncs.com"
        return Client(config)

    def create_task(self, audio_url: str) -> str:
        """提交转写任务，返回 task_id"""
        if not self.app_key:
            raise RuntimeError("未配置 TINGWU_APP_KEY")
        client = self._get_client()
        req = self._models.CreateTaskRequest(
            app_key=self.app_key,
            input=self._models.CreateTaskRequestInput(audio_url=audio_url),
        )
        resp = client.create_task(req)
        task_id = resp.body.data.task_id
        logger.info(f"听悟转写任务已提交: {task_id}")
        return task_id

    def get_result(self, task_id: str, timeout: int = 300) -> Dict:
        """轮询转写结果

        Returns:
            {"text": 全文, "sentences": [{"speaker_id", "text"}], "speakers": [说话人id去重]}
        """
        client = self._get_client()
        start = time.time()
        while time.time() - start < timeout:
            req = self._models.GetTaskInfoRequest(task_id=task_id)
            resp = client.get_task_info(req)
            status = resp.body.data.task_status
            if status in ("COMPLETED", "SUCCESS"):
                return self._parse_result(resp.body.data.result)
            if status in ("FAILED", "ERROR"):
                raise RuntimeError(f"听悟转写失败: {status}")
            time.sleep(3)
        raise TimeoutError(f"听悟转写超时（{timeout}s）")

    def transcribe(self, audio_url: str) -> Dict:
        """一键转写：create_task + 轮询 get_result"""
        task_id = self.create_task(audio_url)
        return self.get_result(task_id)

    def _parse_result(self, result) -> Dict:
        """从 SDK result 对象提取文本与说话人。

        听悟 GetTaskInfo（tingwu20230930）的真实 result 结构是：
            result.text（全文）+ result.sentences（句级，元素含 speaker_id/text）
        旧实现只找 transcripts 字段 —— 该字段在真实响应中不存在，text/sentences
        恒为空，转写静默"成功"但无内容（合规硬伤：拜访总结基于空转写生成）。
        这里按真实结构解析，同时保留 transcripts 嵌套的旧兼容。
        """
        result_map = result.to_map() if hasattr(result, "to_map") else result
        if not isinstance(result_map, dict):
            result_map = {}

        # 全文直读顶层 text（有全文就不再累加句子文本，避免重复拼接）
        text = str(result_map.get("text") or "")
        has_full_text = bool(text.strip())

        sentences = []
        raw_sentences = result_map.get("sentences") or []
        if not raw_sentences:
            # 旧结构兼容：transcripts[].sentences 嵌套
            for tr in (result_map.get("transcripts") or []):
                if isinstance(tr, dict):
                    raw_sentences = tr.get("sentences") or []
                if raw_sentences:
                    break
        for item in raw_sentences or []:
            s = item
            # 句元素两种形状：{"sentence": {...}} 或平铺 {"speaker_id", "text"}
            if isinstance(item, dict) and isinstance(item.get("sentence"), dict):
                s = item["sentence"]
            if not isinstance(s, dict):
                continue
            seg = str(s.get("text") or "")
            if seg and not has_full_text:
                text += seg
            sentences.append({"speaker_id": s.get("speaker_id"), "text": seg})
        # 注意：说话人 0 是合法值，不能用 if s["speaker_id"]（0 为 falsy 会被丢掉）
        speakers = sorted({s["speaker_id"] for s in sentences if s["speaker_id"] is not None})
        return {"text": text, "sentences": sentences, "speakers": speakers}


class TingwuMockClient:
    """听悟 Mock — 开发调试/测试：文本模拟转写结果，不依赖任何外部服务"""

    def __init__(self, text: str = ""):
        self.text = text

    def transcribe(self, audio_url: str = "") -> Dict:
        """直接返回预设文本，模拟一次转写完成"""
        return {
            "text": self.text,
            "sentences": [{"speaker_id": "speaker_1", "text": self.text}] if self.text else [],
            "speakers": ["speaker_1"] if self.text else [],
        }
