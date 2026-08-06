/**
 * 对话 WS 流式客户端（走网关 8000）
 * 协议见 specs 3.1/3.3：发 question 帧，收 start/delta/done/error 帧
 */
import { Platform } from 'react-native';

const GATEWAY_HOST = Platform.select({
  android: '10.0.2.2:8000',
  ios: 'localhost:8000',
  default: 'localhost:8000',
});

export interface ChatWsDone {
  text: string;
  conversationId?: number | null;
  sessionId?: string;
  citations?: unknown[];
  /** blocked 回答：真实原因（text）+ 违规明细（violations），与 REST 路径一致 */
  blocked?: boolean;
  violations?: unknown[];
  evidenceLevel?: string | null;
}

export interface ChatWsCallbacks {
  onStart: () => void;
  onDelta: (text: string) => void;
  onDone: (done: ChatWsDone) => void;
  onError: (message: string) => void;
}

export interface ChatWsSession {
  sendQuestion(text: string, sessionId?: string): void;
  close(): void;
}

export function openChatWs(
  specialistId: number,
  token: string,
  cbs: ChatWsCallbacks
): ChatWsSession {
  const ws = new WebSocket(
    `ws://${GATEWAY_HOST}/api/v1/specialists/${specialistId}/chat/ws?token=${encodeURIComponent(token)}`
  );

  // open 前 sendQuestion 缓冲的 question 帧（真实 RN WebSocket 构造后先 CONNECTING）
  let pendingQuestion: string | null = null;
  // 会话已按协议/主动结束（done、error 帧、onerror、close()）→ onclose 不再上报为故障
  let done = false;

  ws.onopen = () => {
    // open 前缓冲的 question 补发；若 open 前已 close() 则 pendingQuestion 已被清空
    if (pendingQuestion !== null) {
      ws.send(pendingQuestion);
      pendingQuestion = null;
    }
  };
  ws.onmessage = (e) => {
    try {
      const frame = JSON.parse(e.data as string);
      switch (frame.type) {
        case 'start':
          cbs.onStart();
          break;
        case 'delta':
          cbs.onDelta(frame.text ?? '');
          break;
        case 'done':
          done = true;
          cbs.onDone({
            text: frame.text ?? '',
            conversationId: frame.conversation_id ?? null,
            sessionId: frame.session_id,
            citations: frame.citations ?? [],
            blocked: frame.blocked ?? false,
            violations: frame.violations ?? [],
            evidenceLevel: frame.evidence_level ?? null,
          });
          ws.close();
          break;
        case 'error':
          done = true;
          cbs.onError(frame.message || '对话服务异常');
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
    cbs.onError('对话服务连接失败');
    // onerror 后不保证触发 onclose（RN 实现差异）→ 主动 close 释放连接；
    // 之后即使 onclose 到达，done 已置位也不会重复上报
    ws.close();
  };
  // 中途断开（专员/网络异常）只触发 onclose；done 已置位说明是按协议或主动关闭，不上报
  ws.onclose = () => {
    if (!done) cbs.onError('对话连接已断开');
  };

  return {
    sendQuestion(text: string, sessionId?: string) {
      const payload = JSON.stringify({
        type: 'question',
        text,
        ...(sessionId ? { session_id: sessionId } : {}),
      });
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(payload);
      } else if (ws.readyState === WebSocket.CONNECTING) {
        // 连接尚未建立：缓冲，onopen 后补发
        pendingQuestion = payload;
      }
      // CLOSING/CLOSED：直接丢弃
    },
    close() {
      done = true;             // 主动关闭：onclose 不上报故障
      pendingQuestion = null;  // 未 open 即关闭 → 丢弃缓冲的 question
      ws.close();
    },
  };
}
