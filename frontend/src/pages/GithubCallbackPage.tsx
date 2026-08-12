import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { authApi } from '../api/auth';
import { useAuthStore } from '../store/authStore';
import { Database, AlertCircle } from 'lucide-react';

export const GithubCallbackPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) {
      setError('No authorization code found');
      return;
    }

    const authenticate = async () => {
      try {
        const response = await authApi.githubLogin(code);
        setAuth(response.user, response.tokens.access, response.tokens.refresh);
        navigate('/');
      } catch (err: any) {
        setError(err.response?.data?.error || 'GitHub login failed');
      }
    };

    authenticate();
  }, [searchParams, navigate, setAuth]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-950 px-4 relative overflow-hidden">
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-500/10 rounded-full blur-3xl glow-purple animate-pulse-subtle pointer-events-none" />
      
      <div className="w-full max-w-md animate-slide-up text-center">
        <div className="inline-flex w-16 h-16 rounded-2xl bg-gradient-to-tr from-brand-600 to-brand-400 items-center justify-center shadow-lg shadow-brand-500/20 mb-4">
          <Database className="w-8 h-8 text-white" />
        </div>
        
        {error ? (
          <div className="glass-panel rounded-2xl p-8 mt-4 shadow-2xl relative">
            <div className="flex items-start justify-center space-x-2 bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-xl text-sm animate-fade-in">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
            <button
              onClick={() => navigate('/login')}
              className="mt-6 w-full py-3 px-4 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 text-white font-semibold rounded-xl transition-all"
            >
              Back to Login
            </button>
          </div>
        ) : (
          <div>
            <h2 className="text-xl font-bold text-white mb-4">Authenticating with GitHub...</h2>
            <div className="flex justify-center">
              <div className="w-8 h-8 border-4 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
