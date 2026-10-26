import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore, useActiveRole } from '../store/authStore';
import { workspaceApi, type Member } from '../api/workspace';
import { apiErrorMessage } from '../api/client';
import { Settings, Database, Cpu, Users } from 'lucide-react';
import { MODELS } from '../config';

const ROLE_BADGE: Record<string, string> = {
  admin: 'bg-red-500/10 text-red-400 border border-red-500/20',
  editor: 'bg-blue-500/10 text-blue-400 border border-blue-500/20',
  viewer: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
};

// Everything here is read from the API. An earlier version showed a hardcoded
// directory of invented members and a "role simulator" that rewrote the role in
// the browser only - the server kept enforcing the real one.
export const SettingsPage: React.FC = () => {
  const { user, workspaces, activeWorkspaceId } = useAuthStore();
  const role = useActiveRole();
  const workspace = workspaces.find((w) => w.id === activeWorkspaceId);
  const [members, setMembers] = useState<Member[]>([]);
  const [membersError, setMembersError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeWorkspaceId) return;
    workspaceApi
      .listMembers(activeWorkspaceId)
      .then((list) => {
        setMembers(list);
        setMembersError(null);
      })
      .catch((err) => setMembersError(apiErrorMessage(err, 'Could not load members.')));
  }, [activeWorkspaceId]);

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8 animate-slide-up">
      <div className="border-b border-dark-800/60 pb-5">
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
          <Settings className="w-5 h-5 text-brand-400" />
          <span>Workspace settings</span>
        </h1>
        <p className="text-xs text-dark-400 mt-1">This workspace, its members, and the server it runs on</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-7 space-y-6">
          <div className="glass-panel rounded-2xl p-6 border border-dark-850">
            <h3 className="text-sm font-bold text-white mb-4 flex items-center space-x-2">
              <Database className="w-4 h-4 text-brand-400" />
              <span>Workspace</span>
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <Field label="Name" value={workspace?.name ?? 'No workspace selected'} />
              <Field label="ID" value={activeWorkspaceId ? `#${activeWorkspaceId}` : 'N/A'} mono />
              <Field label="Your role" value={role} capitalize />
            </div>
          </div>

          <div className="glass-panel rounded-2xl p-6 border border-dark-850">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-white flex items-center space-x-2">
                <Users className="w-4 h-4 text-brand-400" />
                <span>Members</span>
              </h3>
              {role === 'admin' && (
                <Link to="/members" className="text-xs font-semibold text-brand-400 hover:text-brand-300">
                  Manage members →
                </Link>
              )}
            </div>
            {membersError ? (
              <p className="text-xs text-rose-400">{membersError}</p>
            ) : (
              <div className="space-y-3">
                {members.map((m) => (
                  <div key={m.id} className="flex items-center justify-between p-3 bg-dark-950/60 rounded-xl border border-dark-800">
                    <span className="text-xs text-white font-mono">
                      {m.email}
                      {m.id === user?.id && <span className="text-dark-500 font-sans"> (you)</span>}
                    </span>
                    <span className={`text-[9px] uppercase tracking-wider font-bold px-2 py-0.5 rounded ${ROLE_BADGE[m.role]}`}>
                      {m.role}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Configuration, stated as configuration: this page cannot see whether
            each service is up, so it does not claim to. */}
        <div className="lg:col-span-5 space-y-6">
          <div className="glass-panel rounded-2xl p-6 border border-dark-850 space-y-4">
            <h3 className="text-sm font-bold text-white border-b border-dark-800/60 pb-2 flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-brand-400" />
              <span>Server configuration</span>
            </h3>
            <div className="space-y-4 text-xs">
              <Field label="Vector database" value="Qdrant, self-hosted" mono />
              <Field label="Language model" value={`Groq · ${MODELS.generator}`} mono />
              <Field label="Fallback model" value={`Groq · ${MODELS.fallback}`} mono />
              <Field label="Embeddings" value={`${MODELS.embeddings}, on the server`} mono />
              <Field label="Background jobs" value="Celery + Redis" mono />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

function Field({ label, value, mono = false, capitalize = false }: {
  label: string; value: string; mono?: boolean; capitalize?: boolean;
}) {
  return (
    <div>
      <span className="text-[10px] uppercase font-bold text-dark-500 block">{label}</span>
      <span className={`text-xs font-semibold text-white mt-1 block ${mono ? 'font-mono' : ''} ${capitalize ? 'capitalize' : ''}`}>
        {value}
      </span>
    </div>
  );
}
