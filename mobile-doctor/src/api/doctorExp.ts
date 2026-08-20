/**
 * 医生端体验 API（二期 I 端点契约）：
 *   - getProfile/updateProfile/learnProfile/getBriefing: 偏好画像 + 自动学习 + 学术简报
 *   - listTemplates/generateEdu/myEdu: 患教模板选择 → 生成卡片 → 本人历史
 *   - plazaList/subscribePlaza: 官方公共数字员工广场（浏览/添加）
 *
 * 契约铁律：请求体/响应形状以本文件为唯一映射点（snake_case、分页解包在此做）。
 */
import { apiClient } from './client';
import type {
  DoctorProfile,
  DoctorBriefing,
  PatientEduTemplate,
  EduCard,
  PlazaTwin,
  PaginatedResponse,
  TwinSubscription,
} from '../types';

export const doctorExpAPI = {
  /** 本人偏好画像（无画像返回 null） */
  getProfile: () =>
    apiClient.request<DoctorProfile | null>('GET', '/api/v1/doctor-profiles'),

  /** 全量更新偏好（PUT 全量，后端对每个字段单独校验白名单） */
  updateProfile: (data: Record<string, any>) =>
    apiClient.request<DoctorProfile>('PUT', '/api/v1/doctor-profiles', data),

  /** 从本人 medical_qa 历史自动学习偏好 */
  learnProfile: () =>
    apiClient.request<DoctorProfile>('POST', '/api/v1/doctor-profiles/learn', {}),

  /** 个性化学术简报（无画像/关闭个性化时 personalized=false） */
  getBriefing: () =>
    apiClient.request<DoctorBriefing>('GET', '/api/v1/doctor-profiles/briefing'),

  /** 患教模板分页列表（医生端仅 approved） */
  listTemplates: () =>
    apiClient.request<PaginatedResponse<PatientEduTemplate>>(
      'GET',
      '/api/v1/patient-edu/templates'
    ),

  /** 选模板生成患教卡片（AI 生成 + 合规预检，默认仅本人可见） */
  generateEdu: (templateId: number) =>
    apiClient.request<EduCard>('POST', '/api/v1/patient-edu/generate', {
      template_id: templateId,
    }),

  /** 本人患教历史分页 */
  myEdu: () =>
    apiClient.request<PaginatedResponse<EduCard>>('GET', '/api/v1/patient-edu/mine'),

  /** 官方公共数字员工广场（is_official + active，item 带 added_count） */
  plazaList: () =>
    apiClient.request<PaginatedResponse<PlazaTwin>>('GET', '/api/v1/doctor-plaza'),

  /** 添加官方分身（知情同意后，后端幂等） */
  subscribePlaza: (twinId: number) =>
    apiClient.request<TwinSubscription>(
      'POST',
      `/api/v1/doctor-plaza/${twinId}/subscribe`,
      { consent: true }
    ),
};
