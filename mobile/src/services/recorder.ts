/**
 * 录音封装（react-native-audio-record 录制 WAV 16k/16bit/mono，与 ASR 协议一致）
 */
import AudioRecord from 'react-native-audio-record';
import RNFS from 'react-native-fs';

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
