import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { loadBrand } from './brand';

// 先取品牌再渲染，避免登录页/标签页标题先闪一下 MedAgent（brand.json 由本机代理直出，毫秒级）
loadBrand().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
