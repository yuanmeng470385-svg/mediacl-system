import { Platform } from 'react-native';

/**
 * 集中管理后端地址（真机联调只改这里）：
 *   - 模拟器：Android 用 10.0.2.2（宿主机回环），iOS 用 localhost
 *   - 真机：改为电脑局域网 IP（如 '192.168.1.100'），并确保后端服务监听 0.0.0.0
 * 三个入口：API（REST，网关 8000）/ ASR（WS，visit-service 8002 直连）/ 聊天 WS（网关 8000）
 */
const DEV_HOST = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
// 真机联调：取消下行注释并改为电脑局域网 IP，模拟器验证时保留上行
// const DEV_HOST = '192.168.1.100';

export const API_HOST = DEV_HOST;
export const ASR_HOST = DEV_HOST;
export const GATEWAY_HOST = DEV_HOST;
