import axios from 'axios';
import { message } from 'antd';

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('medagent_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status;
    if (status === 401) {
      localStorage.removeItem('medagent_token');
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    } else if (status >= 500) {
      message.error('服务器错误，请稍后重试');
    } else if (status >= 400 && status < 500) {
      // 403/400/404/422 等：显示后端 message，消除静默失败。
      // Wave 1 后 404/422 统一返回 {code,message,data}，无 message 时兜底「请求失败」
      let msg: string | undefined = error.response?.data?.message;
      if (!msg && error.response?.data instanceof Blob) {
        // 导出等 blob 响应出错时，错误体也是 Blob，需解析 JSON 取 message
        try {
          msg = JSON.parse(await error.response.data.text())?.message;
        } catch {
          /* 非 JSON 错误体，忽略 */
        }
      }
      message.error(msg || '请求失败');
    } else if (!error.response) {
      // 网络层错误（断网/网关进程挂/超时）：error.response 为 undefined，
      // 页面级 catch 已不弹窗（终审 F3 发现），统一在此兜底
      message.error('网络异常，请检查网络连接');
    }
    return Promise.reject(error);
  }
);

export default client;
