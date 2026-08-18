/**
 * 执业资质 API（Task 2 端点契约）：
 *   - submitCert: multipart 提交（cert_type 必传 ∈ {physician, practice}；
 *     cert 首次提交必传，重提交可缺省——后端保留原证书图片）
 *   - getMyCert: 本人资质状态（无记录返回 null → 屏幕渲染"未提交"空态）
 *
 * multipart 走 client.upload（fetch body 为 FormData），与 JSON request 是两条通道。
 */
import { apiClient } from './client';
import type { DoctorCert } from '../types';

export interface DoctorCertSubmitPayload {
  cert_type: 'physician' | 'practice';
  /** react-native-document-picker 输出的文件对象 {uri,name,type} 原样 append */
  cert?: { uri: string; name: string; type: string };
}

export const doctorAPI = {
  submitCert: (payload: DoctorCertSubmitPayload) => {
    const fd = new FormData();
    fd.append('cert_type', payload.cert_type);
    if (payload.cert) {
      fd.append('cert_image', payload.cert as any);
    }
    return apiClient.upload<DoctorCert>('/api/v1/doctors/certs', fd);
  },

  getMyCert: () =>
    apiClient.request<DoctorCert | null>('GET', '/api/v1/doctors/certs/me'),
};
