/**
 * MedAgent Web 后台 - App 入口
 */
import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';

// TODO: 替换为真实页面
const Dashboard = () => <div>仪表盘 (开发中)</div>;
const Specialists = () => <div>数字专员管理 (开发中)</div>;
const Knowledge = () => <div>知识库管理 (开发中)</div>;
const Doctors = () => <div>医生管理 (开发中)</div>;
const Compliance = () => <div>合规规则管理 (开发中)</div>;
const Audit = () => <div>审计查询 (开发中)</div>;
const System = () => <div>系统配置 (开发中)</div>;

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/specialists" element={<Specialists />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/doctors" element={<Doctors />} />
          <Route path="/compliance" element={<Compliance />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/system" element={<System />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}
