import React from 'react';
import { FEATURES } from './config';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Navbar } from './components/layout/Navbar';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { Toast } from './components/ui/Toast';
import { LoginPage } from './pages/LoginPage';
import { WorkspaceSelectorPage } from './pages/WorkspaceSelectorPage';
import { DashboardPage } from './pages/DashboardPage';
import { ChatPage } from './pages/ChatPage';
import { DocumentsPage } from './pages/DocumentsPage';
import { MeetingsPage } from './pages/MeetingsPage';
import { MembersPage } from './pages/MembersPage';
import MonitoringPage from './pages/MonitoringPage';
import { SettingsPage } from './pages/SettingsPage';
import { GithubCallbackPage } from './pages/GithubCallbackPage';
import { LandingPage } from './pages/LandingPage';

// Authenticated layout containing the header and page content container
const AuthenticatedLayout: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-dark-950 text-dark-50">
      <Navbar />
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
      <Toast />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public auth pages */}
        <Route path="/home" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/github/callback" element={<GithubCallbackPage />} />

        {/* Protected app pages */}
        <Route element={<ProtectedRoute />}>
          {/* Workspace context selector */}
          <Route path="/workspaces" element={<WorkspaceSelectorPage />} />

          <Route element={<AuthenticatedLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/chat" element={<ChatPage />} />
            {FEATURES.meetings && <Route path="/meetings" element={<MeetingsPage />} />}
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/profile" element={<Navigate to="/settings" replace />} />
            <Route path="/upload" element={<Navigate to="/documents" replace />} />

            {/* Editor & Admin only pages */}
            <Route element={<ProtectedRoute allowedRoles={['admin', 'editor']} />}>
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/monitoring" element={<MonitoringPage />} />
            </Route>

            {/* Workspace admins only */}
            <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
              <Route path="/members" element={<MembersPage />} />
            </Route>
          </Route>
        </Route>

        {/* Fallback redirect */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
