/**
 * 备案资质 API 契约测试：锁定 URL/method/multipart 字段。
 * multipart 走 client.upload（fetch body 为 FormData），与 JSON request 是两条通道。
 */
import { qualificationAPI } from '../qualification';

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
  return { url: url as string, init: init as { method: string; headers: Record<string, string>; body?: any } };
}

describe('qualificationAPI', () => {
  it('getMy 发 GET /api/v1/qualifications/me', async () => {
    await qualificationAPI.getMy();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/qualifications/me');
    expect(init.method).toBe('GET');
  });

  it('submit 用 FormData 携带备案字段与文件，不设 Content-Type', async () => {
    await qualificationAPI.submit({
      filing_number: 'F-2026-001',
      filing_expire_date: '2028-06-30',
      educationCert: { uri: 'file:///edu.pdf', name: 'edu.pdf', type: 'application/pdf' },
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/qualifications');
    expect(init.method).toBe('POST');
    expect(init.headers).not.toHaveProperty('Content-Type');
    const fd = init.body as FormData;
    expect(fd.get('filing_number')).toBe('F-2026-001');
    expect(fd.get('filing_expire_date')).toBe('2028-06-30');
    expect(fd.get('education_cert')).toEqual({
      uri: 'file:///edu.pdf',
      name: 'edu.pdf',
      type: 'application/pdf',
    });
  });

  it('submit 可选项不传时不 append（后端首次提交校验靠 education_cert 缺失拒绝）', async () => {
    await qualificationAPI.submit({
      educationCert: { uri: 'file:///edu.pdf', name: 'edu.pdf', type: 'application/pdf' },
    });
    const { init } = lastCall();
    const fd = init.body as FormData;
    expect(fd.get('filing_number')).toBeNull();
    expect(fd.get('filing_expire_date')).toBeNull();
    expect(fd.get('training_cert')).toBeNull();
    expect(fd.get('education_cert')).not.toBeNull();
  });
});
