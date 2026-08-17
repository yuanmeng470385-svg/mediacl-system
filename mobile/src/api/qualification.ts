/**
 * 备案与资质 API（需求文档 4.2）：
 *   - getMy: 本人备案资质状态（无记录返回 null → 屏幕渲染"未备案"空态）
 *   - submit: multipart 提交（react-native-document-picker 输出的文件对象
 *     {uri,name,type} 原样 append；RN 运行时提供 FormData，若 tsc 报未定义
 *     改用 (globalThis as any).FormData）
 */
import { apiClient } from './client';
import type { Qualification } from '../types';

export interface QualificationSubmitPayload {
  filing_number?: string;
  /** YYYY-MM-DD */
  filing_expire_date?: string;
  educationCert?: { uri: string; name: string; type: string };
  trainingCert?: { uri: string; name: string; type: string };
}

export const qualificationAPI = {
  getMy: () => apiClient.request<Qualification | null>('GET', '/api/v1/qualifications/me'),

  submit: (payload: QualificationSubmitPayload) => {
    const fd = new FormData();
    if (payload.filing_number) {
      fd.append('filing_number', payload.filing_number);
    }
    if (payload.filing_expire_date) {
      fd.append('filing_expire_date', payload.filing_expire_date);
    }
    if (payload.educationCert) {
      fd.append('education_cert', payload.educationCert as any);
    }
    if (payload.trainingCert) {
      fd.append('training_cert', payload.trainingCert as any);
    }
    return apiClient.upload<Qualification>('/api/v1/qualifications', fd);
  },
};
