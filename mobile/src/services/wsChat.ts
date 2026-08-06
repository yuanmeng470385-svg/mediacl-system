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
          cbs.onDone({
            text: frame.text ?? '',
            conversationId: frame.conversation_id ?? null,
            sessionId: frame.session_id,
            citations: frame.citations ?? [],
          });
          ws.close();
          break;
        case 'error':
          cbs.onError(frame.message || '对话服务异常');
          break;
        default:
          break;
      }
    } catch {
      // 非 JSON 帧忽略
    }
  };
  ws.onerror = () => cbs.onError('对话服务连接失败');

  return {
    sendQuestion(text: string, sessionId?: string) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'question',
          text,
          ...(sessionId ? { session_id: sessionId } : {}),
        }));
      }
    },
    close() {
      ws.close();
    },
  };
}
