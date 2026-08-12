import React from 'react';
import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom';
import { Navbar } from './components/layout/Navbar';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { DashboardPage } from './pages/DashboardPage';
import { UploadPage } from './pages/UploadPage';
import { ProfilePage } from './pages/ProfilePage';
import MonitoringPage from './pages/MonitoringPage';
import { GithubCallbackPage } from './pages/GithubCallbackPage';

// Authenticated layout containing the header and page content container
const AuthenticatedLayout: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-dark-950 text-dark-50">
      <Navbar />
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public auth pages */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/auth/github/callback" element={<GithubCallbackPage />} />

        {/* Protected app pages */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AuthenticatedLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            
            {/* Editor & Admin only upload page */}
            <Route element={<ProtectedRoute allowedRoles={['admin', 'editor']} />}>
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/monitoring" element={<MonitoringPage />} />
            </Route>
          </Route>
        </Route>

        {/* Fallback redirect */}
        <Route path="*" element={<LoginPage />} />
      </Routes>
    </BrowserRouter>
  );
};
