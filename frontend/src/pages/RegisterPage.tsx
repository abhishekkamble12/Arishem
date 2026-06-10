import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/auth';
import { Mail, Lock, UserPlus, Database, AlertCircle, Shield, User as UserIcon } from 'lucide-react';

export const RegisterPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [role, setRole] = useState<'viewer' | 'editor' | 'admin'>('viewer');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email || !password || !password2) {
      setError('Please fill in all required fields');
      return;
    }

    if (password !== password2) {
      setError('Passwords do not match');
      return;
    }

    setLoading(true);

    try {
      const response = await authApi.register(
        email,
        password,
        password2,
        role,
        username || undefined
      );
      // Log in immediately on success
      setAuth(response.user, response.tokens.access, response.tokens.refresh);
      navigate('/');
    } catch (err: any) {
      let errMsg = 'Failed to create account. Please try again.';
      if (err.response?.data) {
        const data = err.response.data;
        if (typeof data === 'object') {
          // Join validation errors nicely
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
        <div className="text-center mb-8">
          <div className="inline-flex w-16 h-16 rounded-2xl bg-gradient-to-tr from-brand-600 to-brand-400 items-center justify-center shadow-lg shadow-brand-500/20 mb-4">
            <Database className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-white via-dark-100 to-brand-400 bg-clip-text text-transparent">
            Create Account
          </h1>
          <p className="text-dark-400 mt-2">Get started with semantic search & RAG</p>
        </div>

        {/* Card Form */}
        <div className="glass-panel rounded-2xl p-8 shadow-2xl relative">
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="flex items-start space-x-2 bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-xl text-sm animate-fade-in">
                <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {/* Email Field */}
            <div className="space-y-1.5">
              <label htmlFor="email" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                Email Address <span className="text-brand-400">*</span>
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-dark-500">
                  <Mail className="w-5 h-5" />
                </div>
                <input
                  id="email"
                  type="email"
                  required
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-11 pr-4 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all duration-200 text-sm"
                />
              </div>
            </div>

            {/* Username Field */}
            <div className="space-y-1.5">
              <label htmlFor="username" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                Username <span className="text-dark-500">(Optional)</span>
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-dark-500">
                  <UserIcon className="w-5 h-5" />
                </div>
                <input
                  id="username"
                  type="text"
                  placeholder="johndoe"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full pl-11 pr-4 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all duration-200 text-sm"
                />
              </div>
            </div>

            {/* Role Field */}
            <div className="space-y-1.5">
              <label htmlFor="role" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                Assign System Role <span className="text-brand-400">*</span>
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-dark-500">
                  <Shield className="w-5 h-5" />
                </div>
                <select
                  id="role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as any)}
                  className="w-full pl-11 pr-10 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all duration-200 text-sm appearance-none cursor-pointer"
                >
                  <option value="viewer" className="bg-dark-900 text-dark-100">Viewer (Queries & lists only)</option>
                  <option value="editor" className="bg-dark-900 text-dark-100">Editor (Viewer + S3 Uploads)</option>
                  <option value="admin" className="bg-dark-900 text-dark-100">Admin (Full permissions)</option>
                </select>
                <div className="absolute inset-y-0 right-0 pr-4 flex items-center pointer-events-none text-dark-400">
                  <svg className="h-4 w-4 fill-current" viewBox="0 0 20 20">
                    <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" />
                  </svg>
                </div>
              </div>
            </div>

            {/* Password Field */}
            <div className="space-y-1.5">
              <label htmlFor="password" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                Password <span className="text-brand-400">*</span>
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-dark-500">
                  <Lock className="w-5 h-5" />
                </div>
                <input
                  id="password"
                  type="password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-11 pr-4 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all duration-200 text-sm"
                />
              </div>
            </div>

            {/* Confirm Password Field */}
            <div className="space-y-1.5">
              <label htmlFor="password2" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                Confirm Password <span className="text-brand-400">*</span>
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-dark-500">
                  <Lock className="w-5 h-5" />
                </div>
                <input
                  id="password2"
                  type="password"
                  required
                  placeholder="••••••••"
                  value={password2}
                  onChange={(e) => setPassword2(e.target.value)}
                  className="w-full pl-11 pr-4 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all duration-200 text-sm"
                />
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 mt-2 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 disabled:opacity-50 text-white font-semibold rounded-xl transition-all duration-200 flex items-center justify-center space-x-2 shadow-lg shadow-brand-600/35 hover:shadow-brand-500/40"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <UserPlus className="w-5 h-5" />
                  <span>Register Account</span>
                </>
              )}
            </button>
          </form>

          {/* Footer link */}
          <div className="mt-6 text-center text-sm text-dark-400">
            Already have an account?{' '}
            <Link to="/login" className="font-semibold text-brand-400 hover:text-brand-300 transition-colors">
              Log In
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};
