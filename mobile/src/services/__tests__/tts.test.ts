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
  // 暴露子 mock，供竞态测试断言 play/release/stop 调用
  (SoundMock as any).__mockPlay = mockPlay;
  (SoundMock as any).__mockRelease = mockRelease;
  (SoundMock as any).__mockStop = mockStop;
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

  // 竞态用例放在 speak 成功用例之前：避免后者把 current 置为旧实例，污染 release 计数断言
  test('fetch 期间 stopSpeaking 打断后不再构造 Sound 发声', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    let resolveFetch: (r: any) => void = () => {};
    const pending = new Promise<any>((r) => { resolveFetch = r; });
    global.fetch = jest.fn().mockReturnValue(pending) as any;
    const speakP = speak('主任您好'); // NLS 合成请求挂起中
    stopSpeaking(); // 在 fetch 窗口内打断
    resolveFetch({ ok: true, arrayBuffer: async () => new Uint8Array([1, 2]).buffer });
    await speakP; // executor 门禁直接 resolve，不构造 Sound
    const SoundMock = Sound as unknown as jest.Mock & { __mockPlay: jest.Mock; __mockRelease: jest.Mock };
    expect(Sound).not.toHaveBeenCalled();
    expect(SoundMock.__mockPlay).not.toHaveBeenCalled();
    expect(SoundMock.__mockRelease).not.toHaveBeenCalled();
  });

  test('Sound 加载窗口内 stopSpeaking 打断后不播放且实例被释放', async () => {
    jest.useFakeTimers();
    try {
      (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        arrayBuffer: async () => new Uint8Array([1, 2]).buffer,
      }) as any;
      const SoundMock = Sound as unknown as jest.Mock & { __mockPlay: jest.Mock; __mockRelease: jest.Mock };
      const speakP = speak('主任您好');
      // 推进微任务直到 speak 到达 executor（new Sound 已构造，deferred cb 因 fake timers 未触发）
      for (let i = 0; i < 20 && !SoundMock.mock.calls.length; i++) {
        await Promise.resolve();
      }
      expect(Sound).toHaveBeenCalledTimes(1);
      stopSpeaking(); // Sound 加载窗口中打断
      jest.runAllTimers(); // 触发 deferred cb → 代际不匹配 → release + resolve
      await speakP; // 无效分支应正常 resolve
      expect(SoundMock.__mockPlay).not.toHaveBeenCalled();
      expect(SoundMock.__mockRelease).toHaveBeenCalledTimes(1);
    } finally {
      jest.useRealTimers();
    }
  });

  // 真实路径驱动 current：await speak 完成后 current 已置位（play 完成回调被 mock 挂起不触发）
  // 位置必须在「speak 合成 URL 带 appkey/token/text 并写文件播放」用例之前——
  // Sound mock 的 stop/release 是模块级共享 jest.fn，若其后的 speak 成功用例先跑，
  // 其 executor 的 stopCurrent() 会先 stop 掉本测试残留实例，计数被污染；
  // 本测试以 stopSpeaking 收尾（current 置 null），不污染其后的 speak 成功用例
  test('stopSpeaking 打断正在播放的 sound（stop + release）', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: async () => new Uint8Array([1, 2]).buffer,
    }) as any;
    const SoundMock = Sound as unknown as jest.Mock & { __mockPlay: jest.Mock; __mockRelease: jest.Mock; __mockStop: jest.Mock };
    await speak('主任您好');
    stopSpeaking();
    expect(SoundMock.__mockStop).toHaveBeenCalledTimes(1);
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
    // fetch 现在带第二个参数 { signal }（30s 超时 AbortController）
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('appkey=app-1'), expect.anything());
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('token=tok-1'), expect.anything());
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('text='), expect.anything());
    expect(RNFS.writeFile).toHaveBeenCalledWith('/mock/doc/tts_tmp.wav', expect.any(String), 'base64');
    expect(Sound).toHaveBeenCalled();
  });

  test('speak 合成失败抛错', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 }) as any;
    await expect(speak('x')).rejects.toThrow('500');
  });

  test('NLS 合成请求 30s 无响应 → 超时报错', async () => {
    jest.useFakeTimers();
    try {
      (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
      // fetch 永不 resolve，只监听 abort 后 reject（模拟 RN 挂起请求被 AbortController 取消）
      global.fetch = jest.fn().mockImplementation(
        (_url: string, opts?: { signal?: AbortSignal }) =>
          new Promise((_resolve, reject) => {
            opts?.signal?.addEventListener('abort', () => reject(new Error('Aborted')));
          }),
      ) as any;
      const p = speak('x');
      // 微任务冲洗：speak 此刻挂在 getTtsToken 的 await 上，30s abort 定时器尚未注册；
      // 原生 Promise 微任务不随 fake clock 的同步 tick 冲洗（与「Sound 加载窗口内」用例同款循环），
      // 不先冲洗则 advanceTimersByTime 无定时器可触发，测试永挂
      for (let i = 0; i < 20 && !(global.fetch as jest.Mock).mock.calls.length; i++) {
        await Promise.resolve();
      }
      jest.advanceTimersByTime(30_000);
      await expect(p).rejects.toThrow('超时');
    } finally {
      jest.useRealTimers();
    }
  });

  test('合成请求网络错误原样上抛（不被超时包裹吞掉）', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    global.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed')) as any;
    await expect(speak('x')).rejects.toThrow('Network request failed');
  });

  test('播放初始化失败透传底层 err.message', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: async () => new Uint8Array([1, 2]).buffer,
    }) as any;
    // 本用例内 Sound 加载回调改报错
    const origImpl = (Sound as unknown as jest.Mock).getMockImplementation();
    (Sound as unknown as jest.Mock).mockImplementationOnce(
      (_path: string, _base: string, cb: (e: Error | null) => void) => {
        setTimeout(() => cb(new Error('file not found')), 0);
        return { play: jest.fn(), release: jest.fn(), stop: jest.fn() };
      },
    );
    try {
      await expect(speak('x')).rejects.toThrow('file not found');
    } finally {
      (Sound as unknown as jest.Mock).mockImplementation(origImpl as any);
    }
  });
});
