import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/auth';
import { Mail, Lock, LogIn, Database, AlertCircle, UserPlus, Shield, User as UserIcon } from 'lucide-react';
import { GoogleLogin } from '@react-oauth/google';

export const LoginPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login');
  
  // Login form state
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  // Register form state
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerUsername, setRegisterUsername] = useState('');
  const [registerRole, setRegisterRole] = useState<'viewer' | 'editor' | 'admin'>('viewer');
  const [registerPassword, setRegisterPassword] = useState('');
  const [registerPassword2, setRegisterPassword2] = useState('');

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { setAuth, refreshWorkspaces } = useAuthStore();
  const navigate = useNavigate();

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginEmail || !loginPassword) {
      setError('Please fill in all fields');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await authApi.login(loginEmail, loginPassword);
      setAuth(response.user, response.tokens.access, response.tokens.refresh);
      refreshWorkspaces().catch(() => {});
      navigate('/');
    } catch (err: any) {
      setError(
        err.response?.data?.error ||
        err.response?.data?.detail ||
        'Invalid email or password. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!registerEmail || !registerPassword || !registerPassword2) {
      setError('Please fill in all required fields');
      return;
    }

    if (registerPassword !== registerPassword2) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);

    try {
      const response = await authApi.register(
        registerEmail,
        registerPassword,
        registerPassword2,
        registerRole,
        registerUsername || undefined
      );
      setAuth(response.user, response.tokens.access, response.tokens.refresh);
      refreshWorkspaces().catch(() => {});
      navigate('/');
    } catch (err: any) {
      let errMsg = 'Failed to create account. Please try again.';
      if (err.response?.data) {
        const data = err.response.data;
        if (typeof data === 'object') {
          errMsg = Object.entries(data)
            .map(([key, val]) => `${key}: ${Array.isArray(val) ? val.join(' ') : val}`)
            .join(' | ');
        } else {
          errMsg = data;
        }
      }
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-950 px-4 py-12 relative overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-500/10 rounded-full blur-3xl glow-purple animate-pulse-subtle pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl glow-blue pointer-events-none" />

      <div className="w-full max-w-md animate-slide-up">
        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="inline-flex w-14 h-14 rounded-xl bg-gradient-to-tr from-brand-600 to-brand-400 items-center justify-center shadow-lg shadow-brand-500/20 mb-4">
            <Database className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-white via-dark-100 to-brand-400 bg-clip-text text-transparent">
            {activeTab === 'login' ? 'Welcome Back' : 'Create Account'}
          </h1>
          <p className="text-dark-400 mt-2 text-sm">
            {activeTab === 'login'
              ? 'Log in to query your knowledge base'
              : 'Get started with semantic search & RAG'}
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex bg-dark-900/60 p-1 rounded-xl border border-dark-800/40 mb-6">
          <button
            onClick={() => {
              setActiveTab('login');
              setError(null);
            }}
            className={`flex-1 flex items-center justify-center space-x-2 py-2.5 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'login'
                ? 'bg-brand-600 text-white shadow-lg'
                : 'text-dark-400 hover:text-dark-200'
            }`}
          >
            <LogIn className="w-4 h-4" />
            <span>Sign In</span>
          </button>
          <button
            onClick={() => {
              setActiveTab('register');
              setError(null);
            }}
            className={`flex-1 flex items-center justify-center space-x-2 py-2.5 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'register'
                ? 'bg-brand-600 text-white shadow-lg'
                : 'text-dark-400 hover:text-dark-200'
            }`}
          >
            <UserPlus className="w-4 h-4" />
            <span>Register</span>
          </button>
        </div>

        {/* Card Form */}
        <div className="glass-panel rounded-2xl p-7 shadow-2xl relative">
          {error && (
            <div className="flex items-start space-x-2 bg-red-500/10 border border-red-500/20 text-red-400 p-3.5 rounded-xl text-xs mb-5 animate-fade-in">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {activeTab === 'login' ? (
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="email" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                  Email Address
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-dark-500">
                    <Mail className="w-4 h-4" />
                  </div>
                  <input
                    id="email"
                    type="email"
                    required
                    placeholder="name@company.com"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 text-sm transition-all duration-200"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="password" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                  Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-dark-500">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    id="password"
                    type="password"
                    required
                    placeholder="••••••••"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 text-sm transition-all duration-200"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 mt-6 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 disabled:opacity-50 text-white font-semibold rounded-xl text-sm transition-all duration-200 flex items-center justify-center space-x-2 shadow-lg shadow-brand-600/35"
              >
                {loading ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <LogIn className="w-4 h-4" />
                    <span>Sign In</span>
                  </>
                )}
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegisterSubmit} className="space-y-3.5">
              <div className="space-y-1">
                <label htmlFor="regEmail" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                  Email Address <span className="text-brand-400">*</span>
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-dark-500">
                    <Mail className="w-4 h-4" />
                  </div>
                  <input
                    id="regEmail"
                    type="email"
                    required
                    placeholder="name@company.com"
                    value={registerEmail}
                    onChange={(e) => setRegisterEmail(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 text-sm transition-all duration-200"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label htmlFor="regUser" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                  Username
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-dark-500">
                    <UserIconIcon className="w-4 h-4" />
                  </div>
                  <input
                    id="regUser"
                    type="text"
                    placeholder="username"
                    value={registerUsername}
                    onChange={(e) => setRegisterUsername(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 text-sm transition-all duration-200"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                  Preferred Role <span className="text-brand-400">*</span>
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-dark-500">
                    <Shield className="w-4 h-4" />
                  </div>
                  <select
                    value={registerRole}
                    onChange={(e) => setRegisterRole(e.target.value as any)}
                    className="w-full pl-10 pr-4 py-2.5 bg-dark-900/80 border border-dark-800 rounded-xl text-dark-100 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 text-sm cursor-pointer select-none"
                  >
                    <option value="viewer" className="bg-dark-950 text-dark-100">Viewer (Read Only)</option>
                    <option value="editor" className="bg-dark-950 text-dark-100">Editor (Read + Upload)</option>
                    <option value="admin" className="bg-dark-950 text-dark-100">Administrator (Full Access)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label htmlFor="regPass" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                    Password
                  </label>
                  <input
                    id="regPass"
                    type="password"
                    required
                    placeholder="••••••••"
                    value={registerPassword}
                    onChange={(e) => setRegisterPassword(e.target.value)}
                    className="w-full px-3 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 text-sm transition-all duration-200"
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="regPass2" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                    Confirm
                  </label>
                  <input
                    id="regPass2"
                    type="password"
                    required
                    placeholder="••••••••"
                    value={registerPassword2}
                    onChange={(e) => setRegisterPassword2(e.target.value)}
                    className="w-full px-3 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 text-sm transition-all duration-200"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 mt-6 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 disabled:opacity-50 text-white font-semibold rounded-xl text-sm transition-all duration-200 flex items-center justify-center space-x-2 shadow-lg shadow-brand-600/35"
              >
                {loading ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <UserPlus className="w-4 h-4" />
                    <span>Create Account</span>
                  </>
                )}
              </button>
            </form>
          )}

          {/* Social Signin divider */}
          <div className="mt-6 flex flex-col gap-4">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-dark-800/80" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-dark-900/90 px-2.5 text-dark-400">Or continue with</span>
              </div>
            </div>

            <div className="flex justify-center">
              <GoogleLogin
                onSuccess={async (credentialResponse) => {
                  if (credentialResponse.credential) {
                    try {
                      setLoading(true);
                      const response = await authApi.googleLogin(credentialResponse.credential);
                      setAuth(response.user, response.tokens.access, response.tokens.refresh);
                      refreshWorkspaces().catch(() => {});
                      navigate('/');
                    } catch (err: any) {
                      setError(err.response?.data?.error || 'Google login failed');
                    } finally {
                      setLoading(false);
                    }
                  }
                }}
                onError={() => {
                  setError('Google Login Failed');
                }}
                theme="filled_black"
                shape="rectangular"
                text="signin_with"
                size="large"
              />
            </div>

            <button
              onClick={() => {
                const clientId = import.meta.env.VITE_GITHUB_CLIENT_ID;
                if (!clientId || clientId === 'null') {
                  setError('GitHub Login is not configured (missing Client ID)');
                  return;
                }
                window.location.href = `https://github.com/login/oauth/authorize?client_id=${clientId}&scope=user:email`;
              }}
              disabled={loading}
              className="w-full py-2.5 px-4 bg-[#24292F] hover:bg-[#24292F]/90 text-white font-semibold rounded-xl text-xs transition-all duration-200 flex items-center justify-center space-x-2"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
              </svg>
              <span>Sign in with GitHub</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// Simple alias wrapper to handle rename/icon overlap
const UserIconIcon: React.FC<{ className?: string }> = ({ className }) => (
  <UserIcon className={className} />
);
