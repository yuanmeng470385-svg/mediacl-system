/**
 * NLS 语音合成（TTS）：服务端换发临时 token → NLS REST 一次性合成 → 本地播放。
 * 未配 NLS_APPKEY 时后端 tts-token 报业务错误（code 4xxx），speak 抛错由调用方提示。
 */
import RNFS from 'react-native-fs';
import Sound from 'react-native-sound';
import { apiClient } from '../api/client';

// tsconfig lib 为 es2022（无 DOM），RN 运行时自带 btoa（与 recorder.ts 的 atob 同先例）
declare const btoa: (s: string) => string;

const TTS_URL = 'https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts';

let current: Sound | null = null;
/** 代际计数：speak 入口抢占本代，stopSpeaking / 更新的 speak 推进计数，使进行中的旧 speak 失效 */
let speakEpoch = 0;

export async function getTtsToken(): Promise<{ token: string; appkey: string }> {
  // apiClient.request 返回业务 data（{code,message,data} 已解包，与 src/api/*.ts 一致）
  const data = await apiClient.request<{ token?: string; appkey?: string }>('GET', '/api/v1/nls/tts-token');
  if (!data?.token || !data?.appkey) throw new Error('NLS 语音合成未配置');
  return { token: data.token, appkey: data.appkey };
}

/**
 * 合成并播放话术文本；正在播放时打断重播，fetch/加载期间被 stopSpeaking 打断后不再发声。
 * 代际计数（speakEpoch）：speak 入口即抢占本代，stopSpeaking / 更新的 speak 推进会计数，
 * 使仍在 fetch/加载中的旧 speak 在回调里发现代际不匹配而丢弃实例（release）不播放——
 * 修复"停止后仍发声"以及两个 speak 加载窗口重叠时双播的竞态。
 */
export async function speak(text: string): Promise<void> {
  const epoch = ++speakEpoch; // 在 fetch 之前抢占本代，stopSpeaking 才有机会在 fetch 期间使其失效
  const { token, appkey } = await getTtsToken();
  const url = `${TTS_URL}?appkey=${encodeURIComponent(appkey)}&token=${encodeURIComponent(token)}&text=${encodeURIComponent(text)}&format=wav&sample_rate=16000`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`语音合成失败(${resp.status})`);
  const bytes = new Uint8Array(await resp.arrayBuffer());
  let bin = '';
  bytes.forEach((b) => { bin += String.fromCharCode(b); });
  const b64 = btoa(bin);
  const path = `${RNFS.DocumentDirectoryPath}/tts_tmp.wav`;
  await RNFS.writeFile(path, b64, 'base64');

  await new Promise<void>((resolve, reject) => {
    stopCurrent(); // 立即打断正在播放的旧 sound（本 speak 已自持本代，不 bump 计数）
    const s = new Sound(path, '', (err) => {
      if (epoch !== speakEpoch) {
        // 本代已被更新的 speak / stopSpeaking() 抢占：无论加载成败都丢弃实例，不再发声
        s.release();
        resolve();
        return;
      }
      if (err) {
        reject(new Error('音频播放初始化失败'));
        return;
      }
      current = s;
      s.play(() => {
        s.release();
        if (current === s) current = null;
      });
      resolve();
    });
  });
}

export function stopSpeaking(): void {
  speakEpoch += 1; // 使进行中的 speak（fetch/加载阶段）失效，回调将丢弃实例不再发声
  stopCurrent();
}

/** 停掉当前正在播放的 sound（不 bump 代际计数——speak 自持本代时直接调用） */
function stopCurrent(): void {
  if (current) {
    current.stop();
    current.release();
    current = null;
  }
}
