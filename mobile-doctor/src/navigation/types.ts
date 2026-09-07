/**
 * MedAgent 医生端 - 导航类型定义
 */

// ========== 主导航（底部 Tab） ==========
export type MainTabParamList = {
  /** 问答 */
  MedicalQA: undefined;
  /** 分身 */
  MyTwins: undefined;
  /** 我的 */
  Profile: undefined;
};

// ========== Stack 导航 ==========
export type RootStackParamList = {
  // 认证
  Login: undefined;
  // 主 Tab
  MainTabs: undefined;
  // 分身激活（深链接场景由 Task 9 注入分享链接 token；列表入口不带 token 手动输入）
  TwinActivate: { token?: string } | undefined;
  // 分身对话
  TwinChat: { twinId: number; twinName: string };
  // 资质上传
  CertUpload: undefined;
  // 学术卡片收件箱
  Inbox: undefined;
  // 站内通知（2026-09-07 A-1：card_new 新卡片提醒，点开即读）
  Notifications: undefined;
  // 学术卡片详情（按推送记录 id 上报阅读/反馈）
  CardDetail: { pushId: number };
  // 偏好 + 个性化学术简报
  Preferences: undefined;
  // 官方广场（官方公共数字员工）
  DoctorPlaza: undefined;
  // 患教工具
  PatientEdu: undefined;
  // 患教专区（三期 M：仅 shared + approved 内容）
  PatientEduZone: undefined;
  // 收藏历史
  Favorites: undefined;
  // 隐私中心（三期 L：政策/个人信息/数据权利申请）
  PrivacyCenter: undefined;
  // 我的隐私请求（三期 L：进度查询）
  PrivacyRequests: undefined;
};
