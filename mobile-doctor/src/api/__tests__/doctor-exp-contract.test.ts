/**
 * 医生端体验 API 契约测试：锁定 URL/method/body。
 *   - getProfile: GET /api/v1/doctor-profiles
 *   - updateProfile: PUT /api/v1/doctor-profiles
 *   - learnProfile: POST /api/v1/doctor-profiles/learn
 *   - generateEdu: POST /api/v1/patient-edu/generate {template_id}
 *   - plazaList: GET /api/v1/doctor-plaza
 *   - subscribePlaza: POST /api/v1/doctor-plaza/1/subscribe {consent:true}
 */
import { doctorExpAPI } from '../doctorExp';

const okResponse = (data: any = {}) => ({ json: async () => ({ code: 0, message: 'success', data }) });
let fetchMock: jest.Mock;
beforeEach(() => { fetchMock = jest.fn().mockResolvedValue(okResponse()); (global as any).fetch = fetchMock; });
function lastCall() { const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]; return { url, init }; }

describe('doctorExp API', () => {
  it('getProfile 发 GET /api/v1/doctor-profiles', async () => {
    await doctorExpAPI.getProfile();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctor-profiles');
    expect(init.method).toBe('GET');
  });

  it('updateProfile 发 PUT /api/v1/doctor-profiles', async () => {
    await doctorExpAPI.updateProfile({ interest_areas: ['心血管'], preferred_style: '标准' });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctor-profiles');
    expect(init.method).toBe('PUT');
  });

  it('learnProfile 发 POST /api/v1/doctor-profiles/learn', async () => {
    await doctorExpAPI.learnProfile();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctor-profiles/learn');
    expect(init.method).toBe('POST');
  });

  it('generateEdu 发 POST /api/v1/patient-edu/generate', async () => {
    await doctorExpAPI.generateEdu(1);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/patient-edu/generate');
    expect(JSON.parse(init.body)).toEqual({ template_id: 1 });
  });

  it('myEdu 发 GET /api/v1/patient-edu/mine', async () => {
    await doctorExpAPI.myEdu();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/patient-edu/mine');
    expect(init.method).toBe('GET');
  });

  it('plazaList 发 GET /api/v1/doctor-plaza', async () => {
    await doctorExpAPI.plazaList();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctor-plaza');
    expect(init.method).toBe('GET');
  });

  it('subscribePlaza 发 POST /api/v1/doctor-plaza/1/subscribe', async () => {
    await doctorExpAPI.subscribePlaza(1);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/doctor-plaza/1/subscribe');
    expect(JSON.parse(init.body)).toEqual({ consent: true });
  });

  it('publishEdu 发 POST /api/v1/patient-edu/1/publish', async () => {
    await doctorExpAPI.publishEdu(1);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/patient-edu/1/publish');
    expect(init.method).toBe('POST');
  });

  it('unpublishEdu 发 POST /api/v1/patient-edu/1/unpublish', async () => {
    await doctorExpAPI.unpublishEdu(1);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/patient-edu/1/unpublish');
    expect(init.method).toBe('POST');
  });

  it('zoneList 发 GET /api/v1/patient-edu/zone', async () => {
    await doctorExpAPI.zoneList();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/patient-edu/zone');
    expect(init.method).toBe('GET');
  });
});
