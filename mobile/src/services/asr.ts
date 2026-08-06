/**
 * ASR（语音转写）WebSocket 客户端
 *
 * 直连 visit-service 的 /ws/visits/{visit_id}/asr（网关不代理 WS）：
 *   - 客户端→服务端：Binary = PCM 音频分片（16k/16bit/单声道）；Text = {"type":"stop"}
 *   - 服务端→客户端：ready / sentence(index,text,final) / compliance(blocked,violations) / error / completed
 */
import { Platform } from 'react-native';

const ASR_HOST = Platform.select({
  android: '10.0.2.2:8002',
  ios: 'localhost:8002',
  default: 'localhost:8002',
});

export interface AsrCallbacks {
  onReady: () => void;
  onSentence: (text: string, final: boolean) => void;
  onCompliance: (blocked: boolean, violations: unknown[]) => void;
  onError: (message: string) => void;
  /** completed 帧：回传最后一次 final sentence 的全量文本（可能为空） */
  onCompleted: (fullText: string) => void;
}

export interface AsrSession {
  sendAudioChunk(chunk: Uint8Array): void;
  stop(): void;
  close(): void;
}

export function connectAsr(visitId: number, token: string, cbs: AsrCallbacks): AsrSession {
  const ws = new WebSocket(`ws://${ASR_HOST}/ws/visits/${visitId}/asr?token=${encodeURIComponent(token)}`);
  let finalText = '';
  // 会话已按协议终止（completed / error 帧，或已报 onerror）则不再把 onclose 当故障上报
  let done = false;

  ws.onopen = () => cbs.onReady();
  ws.onmessage = (e) => {
    try {
      const frame = JSON.parse(e.data as string);
      switch (frame.type) {
        case 'sentence':
          cbs.onSentence(frame.text ?? '', !!frame.final);
          if (frame.final) finalText = frame.text ?? '';
          break;
        case 'compliance':
          cbs.onCompliance(!!frame.blocked, frame.violations ?? []);
          break;
        case 'error':
          done = true;
          cbs.onError(frame.message || '语音转写失败');
          break;
        case 'completed':
          done = true;
          cbs.onCompleted(finalText);
          ws.close();
          break;
        default:
          break;
      }
    } catch {
      // 非 JSON 帧忽略
    }
  };
  ws.onerror = () => {
    done = true;
    cbs.onError('语音服务连接失败');
  };
  // 会话中途断开（服务重启、网络闪断）只触发 onclose；done 已置位则说明是按协议正常关闭
  ws.onclose = () => {
    if (!done) cbs.onError('语音服务连接已断开');
  };

  return {
    sendAudioChunk(chunk: Uint8Array) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(chunk.buffer.slice(chunk.byteOffset, chunk.byteOffset + chunk.byteLength) as ArrayBuffer);
      }
    },
    stop() {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop' }));
      }
    },
    close() {
      ws.close();
    },
  };
}
