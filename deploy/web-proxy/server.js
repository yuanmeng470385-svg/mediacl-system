// MedAgent web 静态 + API/WS 反代（多租户版，单脚本多实例）
// 母版（8080）不设任何 env 时行为与原版完全一致；租户实例由 systemd 注入：
//   PORT        监听端口（默认 8080）
//   API_TARGET  网关地址（默认 http://127.0.0.1:8000）
//   BRAND_NAME  /brand.json 返回的公司全称（不设回退 MedAgent，与本地开发一致）
//   BRAND_SHORT 公司简称（可选；web 前端标签页/侧栏/登录卡优先用它）
// 其余行为同原版：/api/* 反代（含 WS 升级、120s 长路由对齐）、/apk/* 下载、SPA 回退 index.html
const http = require('http');
const fs = require('fs');
const path = require('path');
const httpProxy = require('http-proxy');

const DIST = process.env.DIST_DIR || '/var/www/medagent/dist';
const APK = process.env.APK_DIR || '/var/www/medagent/apk';
const PORT = parseInt(process.env.PORT || '8080', 10);
const API_TARGET = process.env.API_TARGET || 'http://127.0.0.1:8000';
const BRAND = {
  name: process.env.BRAND_NAME || 'MedAgent',
  ...(process.env.BRAND_SHORT ? { short: process.env.BRAND_SHORT } : {}),
};

const proxy = httpProxy.createProxyServer({
  target: API_TARGET,
  ws: true,
  proxyTimeout: 120000, // 与网关 carve-out 对齐（LLM 长路由 120s）
  timeout: 130000,
});

proxy.on('error', (err, req, res) => {
  if (res && res.writeHead && !res.headersSent) {
    res.writeHead(502, { 'Content-Type': 'application/json' });
  }
  if (res && res.end) {
    res.end(JSON.stringify({ code: 5005, message: '网关不可用', data: null }));
  }
});

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.map': 'application/json',
  '.txt': 'text/plain',
  '.apk': 'application/vnd.android.package-archive',
  '.wasm': 'application/wasm',
};

function safeJoin(root, urlPath) {
  // 本代理只跑在 Linux 服务器上，URL 不含反斜杠，直接按 / 处理并拒绝 .. 逃逸
  const p = path.normalize(urlPath).replace(/^\/+/, '');
  if (p.split('/').includes('..')) return null;
  return path.join(root, p);
}

function serveFile(res, f) {
  fs.stat(f, (err, st) => {
    if (err || !st.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      return res.end('Not Found');
    }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(f).toLowerCase()] || 'application/octet-stream',
      'Content-Length': st.size,
      'Cache-Control': path.extname(f) === '.html' ? 'no-cache' : 'public, max-age=86400',
    });
    fs.createReadStream(f).pipe(res);
  });
}

const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0];
  if (url === '/brand.json') {
    // 前端启动时拉一次换标题/登录卡/版权行；no-store 保证换实例即生效
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    return res.end(JSON.stringify(BRAND));
  }
  if (url.startsWith('/api/')) return proxy.web(req, res);
  if (url.startsWith('/apk/')) {
    const f = safeJoin(APK, url.slice(5));
    if (!f) { res.writeHead(400); return res.end('Bad Request'); }
    return serveFile(res, f);
  }
  const f = safeJoin(DIST, url);
  if (!f) { res.writeHead(400); return res.end('Bad Request'); }
  fs.stat(f, (err, st) => {
    if (!err && st.isFile()) return serveFile(res, f);
    serveFile(res, path.join(DIST, 'index.html')); // SPA 回退（分享落地页深链依赖）
  });
});

server.on('upgrade', (req, socket, head) => proxy.ws(req, socket, head));

server.listen(PORT, '0.0.0.0', () => console.log(`medagent web proxy on :${PORT} -> ${API_TARGET} [${BRAND.name}]`));
