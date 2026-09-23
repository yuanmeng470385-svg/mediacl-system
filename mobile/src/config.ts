import { Platform } from 'react-native';
import { BRAND } from './brandConfig';

/**
 * 集中管理后端地址（真机联调只改这里）：
 *   - 模拟器：Android 用 10.0.2.2（宿主机回环），iOS 用 localhost
 *   - 真机：改为电脑局域网 IP（如 '192.168.1.100'），并确保后端服务监听 0.0.0.0
 * 三个入口：API（REST，网关 8000）/ ASR（WS，visit-service 8002 直连）/ 聊天 WS（网关 8000）
 */
// 模拟器：Android 用 10.0.2.2（宿主机回环），iOS 用 localhost
// const DEV_HOST = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
// 真机联调（2026-08-27 代表端）：电脑局域网 IP（后端 --host 0.0.0.0）
// dev=模拟器宿主回环（模拟器 slirp 丢默认路由时 192.168.1.229 不通）；release=真机走宿主机局域网 IP
const DEV_HOST = __DEV__ ? '10.0.2.2' : '39.96.52.114';

/** 端口集中：品牌包全走各自 web 入口 880x（代理分流 /api/→网关、/ws/→visit-service）；
 *  母版与本地开发保持直连默认端口，单测口径不变 */
export const API_PORT = BRAND ? BRAND.apiPort : 8000;
export const ASR_PORT = BRAND ? BRAND.apiPort : 8002;

export const API_HOST = DEV_HOST;
export const ASR_HOST = DEV_HOST;
export const GATEWAY_HOST = DEV_HOST;

/** web 端（管理后台 + 静态资源）所在主机与端口：APK 下载地址 /apk/xxx.apk 挂在这里，
 *  不在网关 8000 上。部署机为 8080（80 被占用）；开发机 vite 只有 3000 且不提供 /apk/，
 *  故本地开发时下载链接打不开属正常，真机/发布版正常。 */
export const WEB_HOST = DEV_HOST;
export const WEB_PORT = BRAND ? BRAND.apiPort : 8080;

/** 传输协议：生产走 TLS 时改 'https'/'wss'（需网关/反代配证书）；
 *  本地/内网联调保持 'http'/'ws'。API_HOST 等只配地址，协议单独配。 */
export const API_SCHEME: 'http' | 'https' = 'http';
export const WS_SCHEME: 'ws' | 'wss' = 'ws';
