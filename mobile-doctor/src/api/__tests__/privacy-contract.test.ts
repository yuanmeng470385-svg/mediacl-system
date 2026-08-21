/**
 * 医生端隐私中心 API 契约测试：锁定 URL/method/body。
 *   - getPrivacyPolicy: GET /api/v1/doctors/privacy-policy
 *   - getPersonalData: GET /api/v1/doctors/personal-data
 *   - createPrivacyRequest: POST /api/v1/privacy-requests {request_type, detail, fields, confirm}
 *   - getMyPrivacyRequests: GET /api/v1/privacy-requests/me[?status=]
 */
import { privacyAPI } from '../privacy';

const okResponse = (data: any = {}) => ({ json: async () => ({ code: 0, message: 'success', data }) });
let fetchMock: jest.Mock;
beforeEach(() => { fetchMock = jest.fn().mockResolvedValue(okResponse()); (global as any).fetch = fetchMock; });
function lastCall() { const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]; return { url, init }; }

describe('privacy API', () => {
  it('getPrivacyPolicy 发 GET /api/v1/doctors/privacy-policy', async () => {
    await privacyAPI.getPrivacyPolicy();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctors/privacy-policy');
    expect(init.method).toBe('GET');
  });

  it('getPersonalData 发 GET /api/v1/doctors/personal-data', async () => {
    await privacyAPI.getPersonalData();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctors/personal-data');
    expect(init.method).toBe('GET');
  });

  it('createPrivacyRequest 发 POST /api/v1/privacy-requests 带 body', async () => {
    await privacyAPI.createPrivacyRequest({
      request_type: 'correct',
      detail: '手机号换新',
      fields: { phone: '13900000001' },
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/privacy-requests');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      request_type: 'correct',
      detail: '手机号换新',
      fields: { phone: '13900000001' },
    });
  });

  it('createPrivacyRequest 注销带 confirm=true', async () => {
    await privacyAPI.createPrivacyRequest({ request_type: 'account_delete', confirm: true });
    const { init } = lastCall();
    expect(JSON.parse(init.body).confirm).toBe(true);
  });

  it('getMyPrivacyRequests 发 GET /me，可带 status 过滤', async () => {
    await privacyAPI.getMyPrivacyRequests();
    let { url, init } = lastCall();
    expect(url).toContain('/api/v1/privacy-requests/me');
    expect(url).not.toContain('status=');
    expect(init.method).toBe('GET');

    await privacyAPI.getMyPrivacyRequests('done');
    ({ url } = lastCall());
    expect(url).toContain('/api/v1/privacy-requests/me?status=done');
  });
});
