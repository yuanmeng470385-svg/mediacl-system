import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AdminLayout from './layouts/AdminLayout';
import LoginPage from './pages/Login';
import RequireAuth from './components/RequireAuth';
import { AuthProvider } from './context/AuthContext';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const SpecialistList = lazy(() => import('./pages/Specialist/SpecialistList'));
const VisitList = lazy(() => import('./pages/Visit/VisitList'));
const KnowledgeList = lazy(() => import('./pages/Knowledge/KnowledgeList'));
const ComplianceList = lazy(() => import('./pages/Compliance/ComplianceList'));
const ComplianceBlocks = lazy(() => import('./pages/Compliance/Blocks'));
const ComplianceMonitor = lazy(() => import('./pages/Compliance/Monitor'));
const CardStats = lazy(() => import('./pages/Compliance/CardStats'));
const ConvSearch = lazy(() => import('./pages/Compliance/ConvSearch'));
const SpecialistMonitorList = lazy(() => import('./pages/Specialist/MonitorList'));
const AuditList = lazy(() => import('./pages/Audit/AuditList'));
const DoctorList = lazy(() => import('./pages/Doctor/DoctorList'));
const DoctorDetail = lazy(() => import('./pages/Doctor/DoctorDetail'));
const UserList = lazy(() => import('./pages/User/UserList'));
const FilingList = lazy(() => import('./pages/Filing/FilingList'));
const DoctorCertList = lazy(() => import('./pages/DoctorCert/DoctorCertList'));
const TrainingList = lazy(() => import('./pages/Training/TrainingList'));
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
                <Route path="/login" element={<LoginPage />} />
                <Route
                  element={
                    <RequireAuth>
                      <AdminLayout />
                    </RequireAuth>
                  }
                >
                  <Route index element={<Navigate to="/dashboard" replace />} />
                  <Route path="dashboard" element={<Dashboard />} />
                  <Route path="specialist/list" element={<SpecialistList />} />
                  <Route path="specialist/monitor" element={<SpecialistMonitorList />} />
                  {/* /specialist/create 已删除：新增/编辑专员均在列表页 Modal 内完成（SpecialistList 内置表单） */}
                  <Route path="visit/list" element={<VisitList />} />
                  <Route path="knowledge/list" element={<KnowledgeList />} />
                  <Route path="compliance/list" element={<ComplianceList />} />
                  <Route path="compliance/blocks" element={<ComplianceBlocks />} />
                  <Route path="compliance/monitor" element={<ComplianceMonitor />} />
                  <Route path="compliance/card-stats" element={<CardStats />} />
                  <Route path="compliance/conv-search" element={<ConvSearch />} />
                  <Route path="audit/list" element={<AuditList />} />
                  <Route path="doctor/list" element={<DoctorList />} />
                  <Route path="doctor/:id" element={<DoctorDetail />} />
                  <Route path="user/list" element={<UserList />} />
                  <Route path="filing/list" element={<FilingList />} />
                  <Route path="doctor-cert/list" element={<DoctorCertList />} />
                  <Route path="training/list" element={<TrainingList />} />
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
