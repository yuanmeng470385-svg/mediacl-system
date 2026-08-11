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

export async function getTtsToken(): Promise<{ token: string; appkey: string }> {
  // apiClient.request 返回业务 data（{code,message,data} 已解包，与 src/api/*.ts 一致）
  const data = await apiClient.request<{ token?: string; appkey?: string }>('GET', '/api/v1/nls/tts-token');
  if (!data?.token || !data?.appkey) throw new Error('NLS 语音合成未配置');
  return { token: data.token, appkey: data.appkey };
}

/** 合成并播放话术文本；正在播放时打断重播 */
export async function speak(text: string): Promise<void> {
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
    stopSpeaking();
    const s = new Sound(path, '', (err) => {
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
  if (current) {
    current.stop();
    current.release();
    current = null;
  }
}
