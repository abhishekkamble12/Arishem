import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { LogOut, Database, Upload, User as UserIcon, MessageSquare, BarChart2 } from 'lucide-react';

export const Navbar: React.FC = () => {
  const { user, clearAuth, activeWorkspaceId, setActiveWorkspaceId } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = () => {
    clearAuth();
    navigate('/login');
  };

  const getRoleBadgeClass = (role: string) => {
    switch (role) {
      case 'admin':
        return 'bg-red-500/10 text-red-400 border-red-500/20';
      case 'editor':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      default:
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    }
  };

  const isActive = (path: string) => location.pathname === path;

  return (
    <nav className="glass-panel border-b border-dark-800/50 sticky top-0 z-50 px-6 py-4">
      <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-4">
        {/* Logo and Brand */}
        <Link to="/" className="flex items-center space-x-3 group">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-brand-400 flex items-center justify-center shadow-lg shadow-brand-500/20 group-hover:scale-105 transition-transform duration-200">
            <Database className="w-5 h-5 text-white" />
          </div>
          <div>
            <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-white via-dark-100 to-brand-400 bg-clip-text text-transparent">
              Arishem
            </span>
            <span className="text-xs block text-dark-400 font-medium -mt-1">RAG AI Platform</span>
          </div>
        </Link>

        {/* Navigation Tabs */}
        <div className="flex items-center space-x-1 bg-dark-900/60 p-1 rounded-xl border border-dark-800/40">
          <Link
            to="/"
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
              isActive('/')
                ? 'bg-brand-600 text-white shadow-md shadow-brand-600/20'
                : 'text-dark-400 hover:text-dark-100 hover:bg-dark-800/30'
            }`}
          >
            <MessageSquare className="w-4 h-4" />
            <span>Dashboard</span>
          </Link>

          {user && (user.role === 'admin' || user.role === 'editor') && (
            <Link
              to="/upload"
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                isActive('/upload')
                  ? 'bg-brand-600 text-white shadow-md shadow-brand-600/20'
                  : 'text-dark-400 hover:text-dark-100 hover:bg-dark-800/30'
              }`}
            >
              <Upload className="w-4 h-4" />
              <span>Upload S3</span>
            </Link>
          )}

          {user && (user.role === 'admin' || user.role === 'editor') && (
            <Link
              to="/monitoring"
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                isActive('/monitoring')
                  ? 'bg-brand-600 text-white shadow-md shadow-brand-600/20'
                  : 'text-dark-400 hover:text-dark-100 hover:bg-dark-800/30'
              }`}
            >
              <BarChart2 className="w-4 h-4" />
              <span>Monitoring</span>
            </Link>
          )}

          <Link
            to="/profile"
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
              isActive('/profile')
                ? 'bg-brand-600 text-white shadow-md shadow-brand-600/20'
                : 'text-dark-400 hover:text-dark-100 hover:bg-dark-800/30'
            }`}
          >
            <UserIcon className="w-4 h-4" />
            <span>Profile</span>
          </Link>
        </div>

        {/* User Stats and Logout */}
        {user && (
          <div className="flex items-center space-x-4">
            {/* Workspace Selector Dropdown */}
            {user.workspaces && user.workspaces.length > 0 && (
              <div className="flex items-center space-x-2 bg-dark-900/40 border border-dark-800/40 rounded-xl px-3 py-1.5 mr-2">
                <span className="text-xs text-dark-400 font-medium">Workspace:</span>
                <select
                  value={activeWorkspaceId || ''}
                  onChange={(e) => setActiveWorkspaceId(parseInt(e.target.value, 10))}
                  className="bg-transparent text-xs font-semibold text-brand-400 focus:outline-none cursor-pointer select-none"
                >
                  {user.workspaces.map((ws) => (
                    <option key={ws.id} value={ws.id} className="bg-dark-950 text-dark-100">
                      {ws.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="hidden sm:flex flex-col items-end text-right">
              <span className="text-sm font-semibold text-dark-100">{user.username}</span>
              <div className="flex items-center space-x-2 mt-0.5">
                <span className="text-xs text-dark-400">{user.email}</span>
                <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${getRoleBadgeClass(user.role)}`}>
                  {user.role}
                </span>
              </div>
            </div>

            {/* User Avatar */}
            <div className="w-9 h-9 rounded-full bg-dark-800 border border-dark-700 flex items-center justify-center font-bold text-sm text-brand-400 select-none shadow-inner">
              {user.username.substring(0, 2).toUpperCase()}
            </div>

            <div className="h-6 w-[1px] bg-dark-800" />

            {/* Logout button */}
            <button
              onClick={handleLogout}
              className="flex items-center justify-center p-2 rounded-lg text-dark-400 hover:text-red-400 hover:bg-red-500/10 transition-all duration-200 group"
              title="Logout"
            >
              <LogOut className="w-5 h-5 group-hover:translate-x-0.5 transition-transform duration-200" />
            </button>
          </div>
        )}
      </div>
    </nav>
  );
};
