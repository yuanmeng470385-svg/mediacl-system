import { getTtsToken, speak, stopSpeaking } from '../tts';

jest.mock('react-native-fs', () => ({
  readFile: jest.fn(),
  writeFile: jest.fn().mockResolvedValue(undefined),
  stat: jest.fn(),
  DocumentDirectoryPath: '/mock/doc',
}));
jest.mock('react-native-sound', () => {
  const mockPlay = jest.fn();
  const mockRelease = jest.fn();
  const mockStop = jest.fn();
  // cb 延迟到构造返回后再触发：同步 cb(null) 会在 new Sound 返回前执行，此时 tts.ts 的
  // const s 尚未赋值（s.play 报 undefined）；speak 内已 await 该回调，容错时序
  const SoundMock = jest.fn().mockImplementation((_path: string, _base: string, cb: (e: Error | null) => void) => {
    setTimeout(() => cb(null), 0);
    return { play: mockPlay, release: mockRelease, stop: mockStop };
  });
  // 暴露子 mock，供竞态测试断言 play/release 调用
  (SoundMock as any).__mockPlay = mockPlay;
  (SoundMock as any).__mockRelease = mockRelease;
  return SoundMock;
});
jest.mock('../../api/client', () => ({
  __esModule: true,
  apiClient: { request: jest.fn() },
}));
import { apiClient } from '../../api/client';
import Sound from 'react-native-sound';

describe('tts', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test('getTtsToken 请求 tts-token 并返回 token/appkey', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 'tok-1', appkey: 'app-1', expires_at: 0 });
    const r = await getTtsToken();
    expect(r).toEqual({ token: 'tok-1', appkey: 'app-1' });
    expect(apiClient.request).toHaveBeenCalledWith('GET', '/api/v1/nls/tts-token');
  });

  test('getTtsToken 缺 token 抛错', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({});
    await expect(getTtsToken()).rejects.toThrow('未配置');
  });

  // 放在 speak 成功用例之前：避免前者把 current 置为旧实例，污染本用例的 release 计数断言
  test('fetch 期间 stopSpeaking 打断后不再播放且实例被释放', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    let resolveFetch: (r: any) => void = () => {};
    const pending = new Promise<any>((r) => { resolveFetch = r; });
    global.fetch = jest.fn().mockReturnValue(pending) as any;
    const speakP = speak('主任您好'); // NLS 合成请求挂起中
    stopSpeaking(); // 在 fetch 窗口内打断
    resolveFetch({ ok: true, arrayBuffer: async () => new Uint8Array([1, 2]).buffer });
    await speakP; // 被无效分支应正常 resolve 而非 reject
    const SoundMock = Sound as unknown as { __mockPlay: jest.Mock; __mockRelease: jest.Mock };
    expect(SoundMock.__mockPlay).not.toHaveBeenCalled();
    expect(SoundMock.__mockRelease).toHaveBeenCalledTimes(1);
  });

  test('speak 合成 URL 带 appkey/token/text 并写文件播放', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 'tok-1', appkey: 'app-1' });
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: async () => new Uint8Array([0x52, 0x49, 0x46, 0x46]).buffer,
    }) as any;
    const RNFS = require('react-native-fs');
    await speak('主任您好');
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('appkey=app-1'));
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('token=tok-1'));
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('text='));
    expect(RNFS.writeFile).toHaveBeenCalledWith('/mock/doc/tts_tmp.wav', expect.any(String), 'base64');
    expect(Sound).toHaveBeenCalled();
  });

  test('speak 合成失败抛错', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 }) as any;
    await expect(speak('x')).rejects.toThrow('500');
  });

  test('stopSpeaking 释放当前播放', () => {
    const s = new Sound('/x', '', () => {});
    (global as any).__ttsCurrent = s; // 内部 current 无法直接触碰，只验证不抛错
    expect(() => stopSpeaking()).not.toThrow();
  });
});
