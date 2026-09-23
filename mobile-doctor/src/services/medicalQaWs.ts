/**
 * 医学问答流式 WS 客户端（v1.1，2026-09-23）
 * 协议与分身对话 wsChat 同款：连接后首帧 {"type":"auth","token"}，
 * 发 {"type":"question","text"}，收 start / delta* / done / error。
 * 上游链路：App → 网关 /api/v1/medical/qa/ws → specialist-service /ws/medical/qa。
 */
import { WS_SCHEME, API_HOST, API_PORT } from '../config';

export interface MedicalQaDone {
  answer: string;
  citations?: { title: string; url?: string; doc_id?: string }[];
  disclaimer?: string;
  blocked?: boolean;
  violations?: unknown[];
  knowledge_empty?: boolean;
  latency_ms?: number | null;
}

export interface MedicalQaCallbacks {
  onStart: () => void;
  onDelta: (text: string) => void;
  onDone: (done: MedicalQaDone) => void;
  onError: (message: string) => void;
}

export interface MedicalQaWsSession {
  sendQuestion(text: string): void;
  close(): void;
}

export function openMedicalQaWs(token: string, cbs: MedicalQaCallbacks): MedicalQaWsSession {
  const ws = new WebSocket(`${WS_SCHEME}://${API_HOST}:${API_PORT}/api/v1/medical/qa/ws`);

  let pendingQuestion: string | null = null;
  let done = false;

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'auth', token }));
    if (pendingQuestion !== null) {
      ws.send(JSON.stringify({ type: 'question', text: pendingQuestion }));
      pendingQuestion = null;
    }
  };

  ws.onmessage = (ev) => {
    try {
      const frame = JSON.parse(ev.data as string);
      if (frame.type === 'start') return cbs.onStart();
      if (frame.type === 'delta') return cbs.onDelta(String(frame.text || ''));
      if (frame.type === 'done') {
        done = true;
        return cbs.onDone(frame as MedicalQaDone);
      }
      if (frame.type === 'error') {
        done = true;
        return cbs.onError(String(frame.message || '生成失败'));
      }
    } catch {
      // 非 JSON 帧忽略
    }
  };

  ws.onerror = () => {
    if (!done) cbs.onError('连接失败');
  };

  ws.onclose = () => {
    if (!done) cbs.onError('连接已断开');
  };

  return {
    sendQuestion(text: string) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'question', text }));
      } else {
        pendingQuestion = text;
      }
    },
    close() {
      done = true;
      try { ws.close(); } catch { /* 已关闭 */ }
    },
  };
}
