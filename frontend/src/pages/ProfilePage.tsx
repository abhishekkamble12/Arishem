import React, { useEffect, useState } from 'react';
import { useAuthStore, User } from '../store/authStore';
import { authApi } from '../api/auth';
import { User as UserIcon, Mail, Shield, Calendar, CheckCircle, Info } from 'lucide-react';

export const ProfilePage: React.FC = () => {
  const { user: storeUser, setAuth, accessToken, refreshToken } = useAuthStore();
  const [profile, setProfile] = useState<User | null>(storeUser);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchProfile = async () => {
      setLoading(true);
      try {
        const freshUser = await authApi.getMe();
        setProfile(freshUser);
        if (storeUser && accessToken && refreshToken) {
          // Keep store in sync
          setAuth(freshUser, accessToken, refreshToken);
        }
      } catch (err: any) {
        console.error('Failed to fetch profile', err);
        setError(err.response?.data?.error || 'Failed to refresh profile info');
      } finally {
        setLoading(false);
      }
    };

    fetchProfile();
  }, []);

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getRoleColor = (role?: string) => {
    switch (role) {
      case 'admin':
        return 'text-red-400 bg-red-500/10 border-red-500/20';
      case 'editor':
        return 'text-blue-400 bg-blue-500/10 border-blue-500/20';
      default:
        return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
    }
  };

  const getRoleDescription = (role?: string) => {
    switch (role) {
      case 'admin':
        return 'Full access to query documents, download files, upload S3 assets, and administer application configurations.';
      case 'editor':
        return 'Access to read, query the knowledge base, download assets, and upload/ingest new files directly from S3.';
      default:
        return 'Read-only access. You can submit queries to the RAG AI pipeline and view the list of ingested documents.';
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 animate-slide-up">
      {/* Page Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-extrabold tracking-tight text-white">Your Profile</h1>
        <p className="text-dark-400 mt-1">Manage your account settings and verify your authorization level</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* Left column: Avatar Card */}
        <div className="md:col-span-1 flex flex-col items-center">
          <div className="w-full glass-panel rounded-2xl p-6 text-center shadow-lg">
            <div className="w-24 h-24 rounded-full bg-gradient-to-tr from-brand-600 to-brand-400 flex items-center justify-center font-bold text-3xl text-white select-none shadow-lg shadow-brand-500/10 mx-auto mb-4 border border-brand-300/25">
              {profile?.username.substring(0, 2).toUpperCase() || 'US'}
            </div>
            <h2 className="text-xl font-bold text-dark-50">{profile?.username}</h2>
            <div className="mt-2 flex justify-center">
              <span className={`text-xs uppercase tracking-wider font-bold px-3 py-1 rounded-full border ${getRoleColor(profile?.role)}`}>
                {profile?.role || 'viewer'}
              </span>
            </div>
            
            <div className="mt-6 pt-6 border-t border-dark-800/60 flex items-center justify-center text-xs text-dark-400 gap-1.5">
              <CheckCircle className="w-4 h-4 text-emerald-500" />
              <span>Account Active</span>
            </div>
          </div>
        </div>

        {/* Right column: Profile details */}
        <div className="md:col-span-2 space-y-6">
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-xl text-sm flex items-center gap-2">
              <Info className="w-5 h-5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="glass-panel rounded-2xl p-8 shadow-lg space-y-6">
            <h3 className="text-lg font-bold text-white border-b border-dark-800/60 pb-3">Account Details</h3>

            {loading ? (
              <div className="py-12 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div className="space-y-1">
                  <span className="text-xs text-dark-500 uppercase tracking-wider font-bold flex items-center gap-1.5">
                    <UserIcon className="w-3.5 h-3.5" /> Username
                  </span>
                  <p className="text-sm font-semibold text-dark-100">{profile?.username}</p>
                </div>

                <div className="space-y-1">
                  <span className="text-xs text-dark-500 uppercase tracking-wider font-bold flex items-center gap-1.5">
                    <Mail className="w-3.5 h-3.5" /> Email Address
                  </span>
                  <p className="text-sm font-semibold text-dark-100">{profile?.email}</p>
                </div>

                <div className="space-y-1">
                  <span className="text-xs text-dark-500 uppercase tracking-wider font-bold flex items-center gap-1.5">
                    <Shield className="w-3.5 h-3.5" /> Role Profile
                  </span>
                  <p className="text-sm font-semibold text-dark-100 capitalize">{profile?.role}</p>
                </div>

                <div className="space-y-1">
                  <span className="text-xs text-dark-500 uppercase tracking-wider font-bold flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5" /> Date Joined
                  </span>
                  <p className="text-sm font-semibold text-dark-100">{formatDate(profile?.date_joined)}</p>
                </div>
              </div>
            )}
          </div>

          {/* Role details box */}
          <div className="glass-panel rounded-2xl p-6 shadow-md border-l-2 border-l-brand-500 flex items-start space-x-4">
            <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center flex-shrink-0 text-brand-400">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h4 className="font-bold text-white text-sm">Role Scope: {profile?.role ? profile.role.toUpperCase() : 'VIEWER'}</h4>
              <p className="text-xs text-dark-400 mt-1 leading-relaxed">{getRoleDescription(profile?.role)}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
