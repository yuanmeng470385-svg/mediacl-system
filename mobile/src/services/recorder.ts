/**
 * 录音封装（react-native-audio-record 录制 WAV 16k/16bit/mono，与 ASR 协议一致）
 *
 * 平台差异（react-native-audio-record 0.2.2 源码，2026-08-11 复核）：
 *  - Android：录音中把裸 PCM（无 44 字节头）写入 getFilesDir()/temp.pcm，stop 时才
 *    saveAsWav() 生成 wav（加 44 字节头）并删除 temp（RNAudioRecordModule.java:78,105,120,156）；
 *    getFilesDir() 与 RNFS.DocumentDirectoryPath 同址。
 *  - iOS：start 即创建 wav 并增量追加（RNAudioRecord.m start 段），无 temp 文件。
 *  → 流式推流的增量读源须按平台/生命周期切换：Android 录音中读 temp.pcm（文件字节偏移），
 *    Android stop 后与 iOS 读 wav（偏移 + 44）。
 */
import AudioRecord from 'react-native-audio-record';
import RNFS from 'react-native-fs';
import { Platform } from 'react-native';

// tsconfig lib 为 es2022（无 DOM），RN 运行时自带 atob
declare const atob: (s: string) => string;

const RECORD_OPTIONS = {
  sampleRate: 16000,
  channels: 1,
  bitsPerSample: 16,
  wavFile: 'medagent_rec.wav',
  audioSource: 1, // Android MIC
};

export async function startRecording(): Promise<void> {
  AudioRecord.init(RECORD_OPTIONS);
  AudioRecord.start();
}

export async function stopRecording(): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    AudioRecord.stop()
      .then((path: string) => resolve(path))
      .catch(reject);
  });
}

/** 录音文件完整路径（react-native-audio-record 按 DocumentDirectoryPath + wavFile 落盘；流式推流在 stop 前就需要路径） */
export function recordingPath(): string {
  return `${RNFS.DocumentDirectoryPath}/${RECORD_OPTIONS.wavFile}`;
}

/** 读 wav 文件，跳过 44 字节头，返回 PCM 数据 */
export async function readWavPcm(path: string): Promise<Uint8Array> {
  const base64 = await RNFS.readFile(path, 'base64');
  const binary = atob(base64);
  const raw = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) raw[i] = binary.charCodeAt(i);
  const HEADER = 44;
  return raw.length > HEADER ? raw.subarray(HEADER) : new Uint8Array(0);
}

/**
 * 读 wav 文件从 offset（PCM 字节偏移，跳过 44 字节头）起的 PCM 数据；
 * length=0 表示读到文件末尾。录音进行中轮询增量读取用（边录边推）。
 */
export async function readWavPcmFrom(path: string, offset: number, length = 0): Promise<Uint8Array> {
  // RNFS 2.20 的 readFile 不支持 position/length（总是整文件读），增量读须用 read(path, length, position)；
  // 且 read 的 length=0 在 Android 端读 0 字节（iOS 读到 EOF）→ 为统一"length=0 读至 EOF"语义显式算剩余长度
  const len = length > 0 ? length : Math.max(0, (await wavDataLength(path)) - offset);
  const base64 = await RNFS.read(path, len, offset + 44, 'base64');
  const binary = atob(base64);
  const raw = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) raw[i] = binary.charCodeAt(i);
  return raw;
}

/** wav 文件 PCM 数据总长度（文件字节 - 44 字节头） */
export async function wavDataLength(path: string): Promise<number> {
  const st = await RNFS.stat(path);
  return Math.max(0, st.size - 44);
}

/**
 * Android 录音期间的临时裸 PCM 文件（与 wav 同目录；文件名与原生端 temp.pcm 一致）。
 * 存在 = 正在录音（wav 尚未生成）；删除 = stop 完成（wav 已落盘）。
 */
const TEMP_PCM_PATH = `${RNFS.DocumentDirectoryPath}/temp.pcm`;

/** temp.pcm 是否仍存在（决定增量读源：裸 PCM 的 temp.pcm vs 带头的 wav） */
async function tempPcmExists(): Promise<boolean> {
  try {
    await RNFS.stat(TEMP_PCM_PATH);
    return true;
  } catch {
    return false;
  }
}

/** base64 → Uint8Array（RNFS read 以 base64 返回） */
function base64ToBytes(base64: string): Uint8Array {
  const binary = atob(base64);
  const raw = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) raw[i] = binary.charCodeAt(i);
  return raw;
}

/**
 * 增量读源总长（PCM 字节口径；流式轮询每轮动态判断源）：
 *  - Android 且 temp.pcm 存在（录音中）→ temp.pcm 文件字节数（裸 PCM，无头）
 *  - 其余（Android stop 后 temp 已删 / iOS 恒为 wav）→ wav 字节数 - 44
 * 口径连续：temp.pcm 有 N 字节 → wav 有 N+44 字节（saveAsWav 先写 wav 后删 temp），
 * 故 connectAsrStreaming 的 offset 在切源前后无需任何换算。
 */
export async function pcmSourceLength(wavPath: string): Promise<number> {
  if (Platform.OS === 'android' && (await tempPcmExists())) {
    const st = await RNFS.stat(TEMP_PCM_PATH);
    return Math.max(0, st.size);
  }
  return wavDataLength(wavPath);
}

/**
 * 从增量读源读 [offset, offset+length) 的 PCM 字节（length=0 → 读到源末尾；offset 为 PCM 字节
 * 偏移，与 pcmSourceLength 同一口径，切源前后连续）：
 *  - Android 且 temp.pcm 存在 → 按文件字节偏移直接读 temp.pcm（无头，不加 44）
 *  - 其余 → 读 wav（文件偏移 offset + 44，跳过头部）
 */
export async function readPcmSource(wavPath: string, offset: number, length = 0): Promise<Uint8Array> {
  if (Platform.OS === 'android' && (await tempPcmExists())) {
    const len = length > 0 ? length : Math.max(0, (await RNFS.stat(TEMP_PCM_PATH)).size - offset);
    const base64 = await RNFS.read(TEMP_PCM_PATH, len, offset, 'base64');
    return base64ToBytes(base64);
  }
  return readWavPcmFrom(wavPath, offset, length);
}
