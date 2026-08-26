import React, { useState } from 'react';
import { useAuthStore } from '../store/authStore';
import {
  Settings, User, Shield, Key, Database, Cpu, CheckCircle2,
  AlertTriangle, RefreshCw, Radio, HardDrive, ToggleLeft
} from 'lucide-react';

interface Member {
  id: number;
  username: string;
  email: string;
  role: 'admin' | 'editor' | 'viewer';
  date_joined: string;
}

export const SettingsPage: React.FC = () => {
  const { user, activeWorkspaceId, setAuth, accessToken, refreshToken } = useAuthStore();
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Mock members representing typical RAG workspace members
  const [members, setMembers] = useState<Member[]>([
    { id: 1, username: 'Abhishek', email: 'abhishek@arishem.ai', role: 'admin', date_joined: '2026-08-01' },
    { id: 2, username: 'Sarah Jenkins', email: 'sarah.j@company.com', role: 'editor', date_joined: '2026-08-05' },
    { id: 3, username: 'John Doe', email: 'john.doe@viewer.com', role: 'viewer', date_joined: '2026-08-10' }
  ]);

  const getActiveWorkspaceName = () => {
    const ws = user?.workspaces?.find(w => w.id === activeWorkspaceId);
    return ws ? ws.name : 'Unknown Workspace';
  };

  // Recruiters can swap role instantly in settings to test RBAC logic (very cool)
  const handleRoleSimulation = (newRole: 'admin' | 'editor' | 'viewer') => {
    if (!user || !accessToken || !refreshToken) return;
    const updatedUser = {
      ...user,
      role: newRole
    };
    setAuth(updatedUser, accessToken, refreshToken);
    setSuccessMsg(`Simulating role swap: successfully switched to "${newRole.toUpperCase()}"`);
    setTimeout(() => setSuccessMsg(null), 3000);
  };

  const getRoleBadge = (role: string) => {
    switch (role) {
      case 'admin':
        return 'bg-red-500/10 text-red-400 border border-red-500/20';
      case 'editor':
        return 'bg-blue-500/10 text-blue-400 border border-blue-500/20';
      default:
        return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8 animate-slide-up">
      {/* Header */}
      <div className="border-b border-dark-800/60 pb-5">
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          <Settings className="w-5 h-5 text-brand-400" />
          <span>Workspace Settings</span>
        </h1>
        <p className="text-xs text-dark-400 mt-1">Configure workspace variables, simulator roles, and system endpoints</p>
      </div>

      {successMsg && (
        <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/25 rounded-xl text-emerald-400 text-xs font-semibold animate-fade-in flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4" />
          <span>{successMsg}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Left: Settings Forms & Simulator */}
        <div className="lg:col-span-7 space-y-6">
          
          {/* Workspace Details */}
          <div className="glass-panel rounded-2xl p-6 border border-dark-850">
            <h3 className="text-sm font-bold text-white mb-4 flex items-center space-x-2">
              <Database className="w-4 h-4 text-brand-400" />
              <span>Workspace Parameters</span>
            </h3>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-[10px] uppercase font-bold text-dark-500 block">Workspace Name</span>
                  <span className="text-xs font-semibold text-white mt-1 block">{getActiveWorkspaceName()}</span>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-bold text-dark-500 block">Workspace ID</span>
                  <span className="text-xs font-mono font-semibold text-brand-400 mt-1 block">#{activeWorkspaceId || 'N/A'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* RBAC Simulator Box */}
          <div className="glass-panel rounded-2xl p-6 border border-dark-850 bg-brand-500/[0.02]">
            <h3 className="text-sm font-bold text-white mb-2 flex items-center space-x-2">
              <Shield className="w-4 h-4 text-brand-400" />
              <span>Recruiter RBAC Simulator</span>
            </h3>
            <p className="text-xs text-dark-400 mb-4">
              Switch your profile role instantaneously to test role-based access control (RBAC). 
              For example, switching to <strong>Viewer</strong> will disable file uploads and deletions in the dashboard.
            </p>

            <div className="flex flex-wrap gap-2.5">
              {(['viewer', 'editor', 'admin'] as const).map((r) => {
                const isActive = user?.role === r;

                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => handleRoleSimulation(r)}
                    className={`px-4 py-2 rounded-xl text-xs font-semibold border transition-all ${
                      isActive
                        ? 'bg-brand-600 border-brand-500 text-white shadow-md shadow-brand-600/25'
                        : 'bg-dark-900 border-dark-800/80 text-dark-400 hover:text-dark-200'
                    }`}
                  >
                    <span>Simulate {r.toUpperCase()}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Members list */}
          <div className="glass-panel rounded-2xl p-6 border border-dark-850">
            <h3 className="text-sm font-bold text-white mb-4">Workspace Directory</h3>
            <div className="space-y-3.5">
              {members.map((m) => (
                <div key={m.id} className="flex items-center justify-between p-3 bg-dark-950/60 rounded-xl border border-dark-800">
                  <div className="flex items-center space-x-3">
                    <div className="w-8 h-8 rounded-full bg-dark-900 border border-dark-800 flex items-center justify-center font-bold text-xs text-brand-400">
                      {m.username.substring(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <span className="text-xs font-bold text-white block">{m.username}</span>
                      <span className="text-[10px] text-dark-500 font-mono mt-0.5 block">{m.email}</span>
                    </div>
                  </div>

                  <span className={`text-[9px] uppercase tracking-wider font-bold px-2 py-0.5 rounded ${getRoleBadge(m.role)}`}>
                    {m.role}
                  </span>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* Right: Technical Endpoints info */}
        <div className="lg:col-span-5 space-y-6">
          <div className="glass-panel rounded-2xl p-6 border border-dark-850 space-y-4.5">
            <h3 className="text-sm font-bold text-white border-b border-dark-800/60 pb-2 flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-brand-400" />
              <span>Engine Status</span>
            </h3>

            <div className="space-y-4 text-xs">
              {/* Endpoint 1 */}
              <div>
                <span className="text-[10px] uppercase font-bold text-dark-500 block">Vector Database</span>
                <div className="flex items-center justify-between mt-1">
                  <span className="font-mono text-dark-200">Qdrant Cloud API</span>
                  <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/10">CONNECTED</span>
                </div>
              </div>

              {/* Endpoint 2 */}
              <div>
                <span className="text-[10px] uppercase font-bold text-dark-500 block">LLM Engine</span>
                <div className="flex items-center justify-between mt-1">
                  <span className="font-mono text-dark-200">Groq SDK (Llama-3.3-70b)</span>
                  <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/10">CONNECTED</span>
                </div>
              </div>

              {/* Endpoint 3 */}
              <div>
                <span className="text-[10px] uppercase font-bold text-dark-500 block">Embedding Engine</span>
                <div className="flex items-center justify-between mt-1">
                  <span className="font-mono text-dark-200">AWS Bedrock (Titan V2)</span>
                  <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/10">CONNECTED</span>
                </div>
              </div>

              {/* Endpoint 4 */}
              <div>
                <span className="text-[10px] uppercase font-bold text-dark-500 block">Task Queue Broker</span>
                <div className="flex items-center justify-between mt-1">
                  <span className="font-mono text-dark-200">Celery + Redis</span>
                  <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/10">ACTIVE</span>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};
