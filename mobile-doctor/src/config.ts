import { Platform } from 'react-native';

/**
 * 集中管理后端地址（真机联调只改这里）：
 *   - 模拟器：Android 用 10.0.2.2（宿主机回环），iOS 用 localhost
 *   - 真机：改为电脑局域网 IP（如 '192.168.1.100'），并确保后端服务监听 0.0.0.0
 * 三个入口：API（REST，网关 8000）/ ASR（WS，visit-service 8002 直连）/ 聊天 WS（网关 8000）
 */
// 模拟器：Android 用 10.0.2.2（宿主机回环），iOS 用 localhost
// const DEV_HOST = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
// 真机联调（2026-08-26）：电脑局域网 IP（后端 --host 0.0.0.0）
// dev=模拟器宿主回环（与 mobile 端同态）；release=真机走宿主机局域网 IP 192.168.1.229
const DEV_HOST = __DEV__ ? '10.0.2.2' : '39.96.52.114';

export const API_HOST = DEV_HOST;
export const ASR_HOST = DEV_HOST;
export const GATEWAY_HOST = DEV_HOST;

/** 传输协议：生产走 TLS 时改 'https'/'wss'（需网关/反代配证书）；
 *  本地/内网联调保持 'http'/'ws'。API_HOST 等只配地址，协议单独配。 */
export const API_SCHEME: 'http' | 'https' = 'http';
export const WS_SCHEME: 'ws' | 'wss' = 'ws';
