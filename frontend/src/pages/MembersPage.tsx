import React, { useCallback, useEffect, useState } from 'react';
import { isAxiosError } from 'axios';
import { Users, Trash2, UserPlus } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { workspaceApi, type Member, type Role } from '../api/workspace';

const ROLES: Role[] = ['viewer', 'editor', 'admin'];

const errorText = (e: unknown): string =>
  isAxiosError(e) ? (e.response?.data?.error ?? 'Request failed') : 'Request failed';

export const MembersPage: React.FC = () => {
  const { user, activeWorkspaceId, workspaces } = useAuthStore();
  const workspace = workspaces.find((w) => w.id === activeWorkspaceId);
  const [members, setMembers] = useState<Member[]>([]);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<Role>('viewer');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!activeWorkspaceId) return;
    try {
      setMembers(await workspaceApi.listMembers(activeWorkspaceId));
    } catch (e) {
      setError(errorText(e));
    }
  }, [activeWorkspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Run a mutation, then reload the list; show the server's message on failure.
  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(errorText(e));
    }
  };

  const onAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWorkspaceId || !email.trim()) return;
    await act(() => workspaceApi.addMember(activeWorkspaceId, email.trim(), role));
    setEmail('');
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="flex items-center space-x-3 mb-6">
        <Users className="w-5 h-5 text-brand-400" />
        <div>
          <h1 className="text-xl font-bold text-white">Members</h1>
          <p className="text-xs text-dark-400">{workspace?.name}</p>
        </div>
      </div>

      <form onSubmit={onAdd} className="glass-panel rounded-2xl p-4 mb-4 flex flex-wrap gap-2 items-center">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="teammate@company.com (must already have an account)"
          className="flex-1 min-w-[220px] bg-dark-950/60 border border-dark-800 rounded-lg px-3 py-2 text-xs text-dark-100 focus:outline-none focus:border-brand-500"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
          className="bg-dark-950/60 border border-dark-800 rounded-lg px-2 py-2 text-xs text-dark-100"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white rounded-lg"
        >
          <UserPlus className="w-3.5 h-3.5" />
          <span>Add</span>
        </button>
      </form>

      {error && <p className="text-xs text-red-400 mb-3">{error}</p>}

      <div className="glass-panel rounded-2xl divide-y divide-dark-800/50">
        {members.map((m) => (
          <div key={m.id} className="flex items-center justify-between px-4 py-3 text-xs">
            <span className="text-dark-100">
              {m.email}
              {m.id === user?.id && <span className="text-dark-500"> (you)</span>}
            </span>
            <div className="flex items-center space-x-2">
              <select
                value={m.role}
                onChange={(e) =>
                  activeWorkspaceId &&
                  act(() => workspaceApi.setMemberRole(activeWorkspaceId, m.id, e.target.value as Role))
                }
                className="bg-dark-950/60 border border-dark-800 rounded-lg px-2 py-1 text-xs text-dark-100"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <button
                title="Remove from workspace"
                onClick={() => activeWorkspaceId && act(() => workspaceApi.removeMember(activeWorkspaceId, m.id))}
                className="p-1.5 text-dark-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
