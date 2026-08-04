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
  (error) => {
    const status = error.response?.status;
    if (status === 401) {
      // 未登录：静默处理，各页面自行处理空数据状态
      console.warn('API 401: 未登录');
    } else if (status >= 500) {
      message.error('服务器错误，请稍后重试');
    }
    return Promise.reject(error);
  }
);

export default client;
