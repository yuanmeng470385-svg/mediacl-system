/**
 * 医生端认证 API 契约测试：锁定 URL/method/body（照 doctor-contract.test.ts 模式，
 * mock global.fetch；AsyncStorage/setToken 由 client 内部处理，不在此断言）。
 * 覆盖面：authAPI.sendCode / login / loginByPassword / register（部署挂账 §5）。
 */
import { authAPI } from '../auth';

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

function jsonBody(init: { body?: any }): any {
  return JSON.parse(init.body);
}

describe('authAPI 契约', () => {
  it('sendCode POST /api/v1/auth/send-code，登录场景 body 只有 phone', async () => {
    await authAPI.sendCode('13900009931');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/auth/send-code');
    expect(init.method).toBe('POST');
    expect(jsonBody(init)).toEqual({ phone: '13900009931' });
  });

  it('sendCode 注册场景 body 带 scene=register', async () => {
    await authAPI.sendCode('13900009931', 'register');
    const { init } = lastCall();
    expect(jsonBody(init)).toEqual({ phone: '13900009931', scene: 'register' });
  });

  it('login POST /api/v1/auth/login，验证码模式 body 为 phone+code', async () => {
    await authAPI.login('13900009931', '123456');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/auth/login');
    expect(init.method).toBe('POST');
    expect(jsonBody(init)).toEqual({ phone: '13900009931', code: '123456' });
  });

  it('loginByPassword POST /api/v1/auth/login，密码模式 body 为 username+password', async () => {
    await authAPI.loginByPassword('13900009931', 'Test@2026a');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/auth/login');
    expect(init.method).toBe('POST');
    expect(jsonBody(init)).toEqual({ username: '13900009931', password: 'Test@2026a' });
  });

  it('register POST /api/v1/auth/register，必填 phone/code/full_name + 选填医院三键', async () => {
    await authAPI.register({
      phone: '13900009931',
      code: '123456',
      full_name: '测试注册',
      hospital: '协和医院',
      department: '心内科',
      title: '主治医师',
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/auth/register');
    expect(init.method).toBe('POST');
    expect(jsonBody(init)).toEqual({
      phone: '13900009931',
      code: '123456',
      full_name: '测试注册',
      hospital: '协和医院',
      department: '心内科',
      title: '主治医师',
    });
  });

  it('register 未填医院信息与密码时 body 不含这些键（密码选填、验证码制）', async () => {
    await authAPI.register({
      phone: '13900009931',
      code: '123456',
      full_name: '测试注册',
    });
    const { init } = lastCall();
    const body = jsonBody(init);
    expect(body).toEqual({
      phone: '13900009931',
      code: '123456',
      full_name: '测试注册',
    });
    expect(body).not.toHaveProperty('hospital');
    expect(body).not.toHaveProperty('department');
    expect(body).not.toHaveProperty('title');
    expect(body).not.toHaveProperty('password');
  });
});
