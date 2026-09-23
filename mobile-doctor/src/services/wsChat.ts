/**
 * 医生端分身对话 WS 流式客户端（照 rep 端 mobile/src/services/wsChat.ts 范式）
 *
 * 挂账收尾（2026-08-26）：医生端此前对话仅 REST（POST /specialists/{id}/chat），
 * 无流式。后端 WS 端点 /ws/specialists/{id}/chat 已支持 doctor 角色 + 订阅校验
 * （未订阅关 4403），协议与 rep 端一致：
 *   - 连接后首帧 {"type":"auth","token"}（B5：token 不进 query string）
 *   - 业务帧 {"type":"question","text","session_id"}
 *   - 服务端 start → delta* → done；error / 关闭码 4401/4403/4404/4500
 *
 * 连接前缓冲 question 帧（RN WebSocket 构造后先 CONNECTING）；主动 close 后
 * onclose 不再上报故障。
 */
import { GATEWAY_HOST, WS_SCHEME } from '../config';
import { API_PORT } from '../config';
import type { ChatViolation } from '../types';

export interface ChatWsDone {
  text: string;
  conversationId?: number | null;
  sessionId?: string;
  citations?: unknown[];
  /** blocked 回答：真实原因（text）+ 违规明细（violations），与 REST 路径一致 */
  blocked?: boolean;
  violations?: ChatViolation[];
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
    `${WS_SCHEME}://${GATEWAY_HOST}:${API_PORT}/api/v1/specialists/${specialistId}/chat/ws`
  );

  // open 前 sendQuestion 缓冲的 question 帧
  let pendingQuestion: string | null = null;
  // 会话已按协议/主动结束 → onclose 不再上报为故障
  let done = false;

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'auth', token }));
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
    ws.close();
  };
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
        pendingQuestion = payload;
      }
    },
    close() {
      done = true;
      pendingQuestion = null;
      ws.close();
    },
  };
}
