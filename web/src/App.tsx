import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AdminLayout from './layouts/AdminLayout';
import { AuthProvider } from './context/AuthContext';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const SpecialistList = lazy(() => import('./pages/Specialist/SpecialistList'));
const SpecialistForm = lazy(() => import('./pages/Specialist/SpecialistForm'));
const KnowledgeList = lazy(() => import('./pages/Knowledge/KnowledgeList'));
const ComplianceList = lazy(() => import('./pages/Compliance/ComplianceList'));
const AuditList = lazy(() => import('./pages/Audit/AuditList'));
const DoctorList = lazy(() => import('./pages/Doctor/DoctorList'));
const DoctorDetail = lazy(() => import('./pages/Doctor/DoctorDetail'));
const UserList = lazy(() => import('./pages/User/UserList'));
const SystemConfig = lazy(() => import('./pages/System/SystemConfig'));

const Loading = () => (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
    <Spin size="large" />
  </div>
);

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          colorBgLayout: '#f0f2f5',
        },
      }}
    >
      <AntApp>
        <AuthProvider>
          <BrowserRouter>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route element={<AdminLayout />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="specialist/list" element={<SpecialistList />} />
                <Route path="specialist/create" element={<SpecialistForm />} />
                <Route path="knowledge/list" element={<KnowledgeList />} />
                <Route path="compliance/list" element={<ComplianceList />} />
                <Route path="audit/list" element={<AuditList />} />
                <Route path="doctor/list" element={<DoctorList />} />
                <Route path="doctor/:id" element={<DoctorDetail />} />
                <Route path="user/list" element={<UserList />} />
                <Route path="system/config" element={<SystemConfig />} />
              </Route>
            </Routes>
          </Suspense>
          </BrowserRouter>
        </AuthProvider>
      </AntApp>
    </ConfigProvider>
  );
}
