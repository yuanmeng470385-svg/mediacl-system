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
  // 分身激活
  TwinActivate: undefined;
  // 分身对话
  TwinChat: { twinId: number; twinName: string };
  // 资质上传
  CertUpload: undefined;
};
