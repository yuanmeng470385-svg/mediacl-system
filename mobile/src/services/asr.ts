/**
 * ASR（语音转写）WebSocket 客户端
 *
 * 直连 visit-service 的 /ws/visits/{visit_id}/asr（网关不代理 WS）：
 *   - 客户端→服务端：Binary = PCM 音频分片（16k/16bit/单声道）；Text = {"type":"stop"}
 *   - 服务端→客户端：ready / sentence(index,text,final) / compliance(blocked,violations) / error / completed
 */
import { ASR_HOST } from '../config';
import { readPcmSource, pcmSourceLength } from './recorder';

export interface AsrCallbacks {
  onReady: () => void;
  /** speaker：visit-service 为 ASR 帧加的说话人标签（'rep'/'doctor'，缺省 'rep'） */
  onSentence: (text: string, final: boolean, speaker?: string) => void;
  onCompliance: (blocked: boolean, violations: unknown[]) => void;
  onError: (message: string) => void;
  /** completed 帧：回传最后一次 final sentence 的全量文本（可能为空）与说话人标签 */
  onCompleted: (fullText: string, speaker?: string) => void;
}

export interface AsrSession {
  sendAudioChunk(chunk: Uint8Array): void;
  stop(): void;
  close(): void;
}

export function connectAsr(visitId: number, token: string, cbs: AsrCallbacks): AsrSession {
  const ws = new WebSocket(`ws://${ASR_HOST}:8002/ws/visits/${visitId}/asr?token=${encodeURIComponent(token)}`);
  let finalText = '';
  // 最后一次 sentence 帧的说话人标签（visit-service 新字段，缺省 rep）
  let lastSpeaker: string | undefined;
  // 会话已按协议终止（completed / error 帧，或已报 onerror）则不再把 onclose 当故障上报
  let done = false;

  ws.onopen = () => cbs.onReady();
  ws.onmessage = (e) => {
    try {
      const frame = JSON.parse(e.data as string);
      switch (frame.type) {
        case 'sentence':
          if (frame.speaker) lastSpeaker = frame.speaker;
          cbs.onSentence(frame.text ?? '', !!frame.final, frame.speaker);
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
          cbs.onCompleted(finalText, lastSpeaker);
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
    // onerror 后不保证触发 onclose（RN 实现差异）→ 主动 close 释放连接；
    // 之后即使 onclose 到达，done 已置位也不会重复上报
    ws.close();
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

export interface AsrStreamingOptions {
  /** 轮询读录音增量间隔 ms */
  pollMs?: number;
  /** 单次推流分片字节数 */
  chunkSize?: number;
}

/**
 * 流式转写（M19 修复）：录音进行中每 pollMs 轮询读 WAV 增量 → 持续推流，
 * 替代旧的"录完一次性推全部 + 立即 stop"（与 NLS 流式识别不匹配）。
 * 服务端 asr_ws.py 已支持持续二进制 feed + stop 收尾，零改动。
 * 使用方式：录音 start 后调用，stop 录音后调用返回会话的 stop()。
 */
export function connectAsrStreaming(
  visitId: number,
  token: string,
  wavPath: string,
  cbs: AsrCallbacks,
  opts: AsrStreamingOptions = {},
): AsrSession {
  const pollMs = opts.pollMs ?? 2000;
  const chunkSize = opts.chunkSize ?? 16 * 1024;
  let offset = 0; // 已推送的 PCM 字节偏移
  let timer: ReturnType<typeof setInterval> | null = null;
  let opened = false; // WS 已 open（onReady 已触发）；open 前禁止任何发送
  let stopped = false;
  // stop 早于 open（快按快放 / 亚握手双击）：此时 flush 的分片与 stop 帧都会被 connectAsr 的
  // OPEN 门禁静默丢弃、offset 还会被白白推进 → 挂起到 open 后由 onReady 分支真正收尾
  let stopPending = false;

  const session = connectAsr(visitId, token, {
    ...cbs,
    onReady: () => {
      opened = true;
      if (stopPending) {
        // 已被 stop() 请求：跳过常规轮询，直接收尾（flush 剩余 PCM + stop 帧，此刻 OPEN 发送生效）
        stopPending = false;
        void finalizeStop();
      } else {
        start();
      }
    },
  });

  /** 推 [offset, until) 的 PCM 分片，不带 stopped 门禁（stop() 收尾 flush 专用） */
  async function flushTo(until: number) {
    while (offset < until) {
      const chunk = await readPcmSource(wavPath, offset, Math.min(chunkSize, until - offset));
      if (chunk.length === 0) break;
      session.sendAudioChunk(chunk);
      offset += chunk.length;
    }
  }

  async function pushSince(until: number) {
    while (offset < until && !stopped) {
      await flushTo(Math.min(offset + chunkSize, until));
    }
  }

  async function start() {
    try {
      const total = await pcmSourceLength(wavPath);
      await pushSince(total);
    } catch {
      // 初始读失败忽略，下一轮重试
    }
    if (stopped) return;
    timer = setInterval(async () => {
      try {
        const total = await pcmSourceLength(wavPath);
        await pushSince(total);
      } catch {
        // 读失败忽略，下一轮重试
      }
    }, pollMs);
  }

  /**
   * 收尾：推完剩余 PCM 再发 stop 帧；flush 绕过 stopped 门禁
   *（否则 stopped 置位后 pushSince 空转，最后 pollMs 内的尾音被静默丢弃）。
   * 仅在 WS 已 open 后调用（stop() 或 onReady 的 stopPending 分支保证）。
   */
  function finalizeStop(): void {
    pcmSourceLength(wavPath)
      .then((total) => flushTo(total))
      .catch(() => {})
      .finally(() => session.stop());
  }

  return {
    sendAudioChunk: session.sendAudioChunk.bind(session),
    stop() {
      if (stopped) return;
      stopped = true;
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      if (!opened) {
        // WS 尚未 open：不执行 flush/stop——发送会被 OPEN 门禁静默丢弃、服务端收不到 stop 帧
        // 且无空闲超时（asr_ws.py 接收循环永远等）→ onCompleted 永不触发 → 客户端卡死。
        // 挂起，open 后由 onReady 分支 finalizeStop（flush 全部已录 PCM + stop 帧，正常收尾路径）。
        stopPending = true;
        return;
      }
      finalizeStop();
    },
    close() {
      stopped = true;
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      session.close();
    },
  };
}
