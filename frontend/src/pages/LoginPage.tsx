import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/auth';
import { Mail, Lock, LogIn, Database, AlertCircle } from 'lucide-react';
import { GoogleLogin } from '@react-oauth/google';


export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please fill in all fields');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await authApi.login(email, password);
      setAuth(response.user, response.tokens.access, response.tokens.refresh);
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

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-950 px-4 relative overflow-hidden">
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
            Welcome back
          </h1>
          <p className="text-dark-400 mt-2">Log in to query your knowledge base</p>
        </div>

        {/* Card Form */}
        <div className="glass-panel rounded-2xl p-8 shadow-2xl relative">
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="flex items-start space-x-2 bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-xl text-sm animate-fade-in">
                <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {/* Email Field */}
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-semibold text-dark-200 block">
                Email Address
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
                  className="w-full pl-11 pr-4 py-3 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all duration-200"
                />
              </div>
            </div>

            {/* Password Field */}
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-semibold text-dark-200 block">
                Password
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
                  className="w-full pl-11 pr-4 py-3 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all duration-200"
                />
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 px-4 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 disabled:opacity-50 text-white font-semibold rounded-xl transition-all duration-200 flex items-center justify-center space-x-2 shadow-lg shadow-brand-600/35 hover:shadow-brand-500/40"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <LogIn className="w-5 h-5" />
                  <span>Sign In</span>
                </>
              )}
            </button>
          </form>

          {/* Footer details */}
          <div className="mt-8 text-center text-sm text-dark-400">
            Don't have an account?{' '}
            <Link to="/register" className="font-semibold text-brand-400 hover:text-brand-300 transition-colors">
              Create one now
            </Link>
          </div>

          <div className="mt-6 flex flex-col gap-4">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-dark-800" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="bg-dark-900 px-2 text-dark-400">Or continue with</span>
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
              className="w-full py-3 px-4 bg-[#24292F] hover:bg-[#24292F]/90 text-white font-semibold rounded-xl transition-all duration-200 flex items-center justify-center space-x-2"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
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
