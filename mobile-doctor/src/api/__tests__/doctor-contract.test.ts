/**
 * 医生端 API 契约测试：锁定 URL/method/body。
 * multipart（资质上传）走 client.upload（fetch body 为 FormData），
 * 其余走 JSON request（body 为 JSON 字符串）——两条通道分开锁。
 * 覆盖面：doctor.submitCert/getMyCert、medical.qa、twin.activate/subscribe/list/toggle/chat。
 */
import { doctorAPI } from '../doctor';
import { medicalAPI } from '../medical';
import { twinAPI } from '../twin';

/** RN 0.75 的 FormData 类型无 get 方法，断言处用最小接口替代（运行时即真实 FormData） */
type FDLike = { get(k: string): any };

const okResponse = (data: any = {}) => ({
  json: async () => ({ code: 0, message: 'success', data }),
});

let fetchMock: jest.Mock;

beforeEach(() => {
  fetchMock = jest.fn().mockResolvedValue(okResponse());
  (global as any).fetch = fetchMock;
});

function lastCall() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return {
    url: url as string,
    init: init as { method: string; headers: Record<string, string>; body?: any },
  };
}

/** JSON 通道的 body 是 client.ts JSON.stringify 的字符串 */
function jsonBody(init: { body?: any }): any {
  return JSON.parse(init.body);
}

describe('doctorAPI', () => {
  it('submitCert 用 FormData 携带 cert_type 与文件对象，走 upload 通道（无 Content-Type）', async () => {
    await doctorAPI.submitCert({
      cert_type: 'physician',
      cert: { uri: 'file:///cert.jpg', name: 'cert.jpg', type: 'image/jpeg' },
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctors/certs');
    expect(init.method).toBe('POST');
    expect(init.headers).not.toHaveProperty('Content-Type');
    const fd = init.body as unknown as FDLike;
    expect(fd.get('cert_type')).toBe('physician');
    expect(fd.get('cert_image')).toEqual({
      uri: 'file:///cert.jpg',
      name: 'cert.jpg',
      type: 'image/jpeg',
    });
  });

  it('submitCert 未选新文件时（重提交）不 append cert_image', async () => {
    await doctorAPI.submitCert({ cert_type: 'practice' });
    const { init } = lastCall();
    const fd = init.body as unknown as FDLike;
    expect(fd.get('cert_type')).toBe('practice');
    expect(fd.get('cert_image')).toBeNull();
  });

  it('getMyCert 发 GET /api/v1/doctors/certs/me（无 body）', async () => {
    await doctorAPI.getMyCert();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctors/certs/me');
    expect(init.method).toBe('GET');
    expect(init.body).toBeUndefined();
  });
});

describe('medicalAPI', () => {
  it('qa 发 POST /api/v1/medical/qa，body 为 {question} JSON', async () => {
    await medicalAPI.qa('阿司匹林的适应证？');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/medical/qa');
    expect(init.method).toBe('POST');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(jsonBody(init)).toEqual({ question: '阿司匹林的适应证？' });
  });
});

describe('twinAPI', () => {
  it('activate 发 POST /api/v1/share-links/{token}/activate；subscribe 发 POST /api/v1/twin-subscriptions 且 body 含 consent_agreed: true', async () => {
    await twinAPI.activate('abc123');
    let { url, init } = lastCall();
    expect(url).toContain('/api/v1/share-links/abc123/activate');
    expect(init.method).toBe('POST');

    await twinAPI.subscribe(42);
    ({ url, init } = lastCall());
    expect(url).toContain('/api/v1/twin-subscriptions');
    expect(init.method).toBe('POST');
    expect(jsonBody(init)).toEqual({ twin_id: 42, consent_agreed: true });
  });

  it('list 发 GET /api/v1/twin-subscriptions；toggle 发 POST .../toggle 带 status；chat 发 POST /api/v1/specialists/{id}/chat 带 question', async () => {
    await twinAPI.list();
    let { url, init } = lastCall();
    expect(url).toContain('/api/v1/twin-subscriptions');
    expect(init.method).toBe('GET');

    await twinAPI.toggle(42, 'blocked');
    ({ url, init } = lastCall());
    expect(url).toContain('/api/v1/twin-subscriptions/42/toggle');
    expect(init.method).toBe('POST');
    expect(jsonBody(init)).toEqual({ status: 'blocked' });

    await twinAPI.chat(42, '这个药的相互作用？');
    ({ url, init } = lastCall());
    expect(url).toContain('/api/v1/specialists/42/chat');
    expect(init.method).toBe('POST');
    expect(jsonBody(init)).toEqual({ question: '这个药的相互作用？' });
  });
});
