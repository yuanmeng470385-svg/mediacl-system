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

/** 读 wav 文件，跳过 44 字节头，返回 PCM 数据 */
export async function readWavPcm(path: string): Promise<Uint8Array> {
  const base64 = await RNFS.readFile(path, 'base64');
  const binary = atob(base64);
  const raw = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) raw[i] = binary.charCodeAt(i);
  const HEADER = 44;
  return raw.length > HEADER ? raw.subarray(HEADER) : new Uint8Array(0);
}
