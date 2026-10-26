import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { Database, LogOut, ArrowRight, Shield, Layers, Plus } from 'lucide-react';
import { workspaceApi } from '../api/workspace';

export const WorkspaceSelectorPage: React.FC = () => {
  const { activeWorkspaceId, setActiveWorkspaceId, workspaces, clearAuth, refreshWorkspaces } = useAuthStore();
  const [newName, setNewName] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    // If user only belongs to 1 workspace, auto-select it and redirect to dashboard
    if (workspaces.length === 1) {
      setActiveWorkspaceId(workspaces[0].id);
      navigate('/');
    }
  }, [workspaces, setActiveWorkspaceId, navigate]);

  // Roles can change while the page is open in another tab; always show the server's view.
  useEffect(() => {
    void refreshWorkspaces();
  }, [refreshWorkspaces]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreateError(null);
    try {
      const ws = await workspaceApi.createWorkspace(newName.trim());
      await refreshWorkspaces();
      setActiveWorkspaceId(ws.id);
      navigate('/');
    } catch (err) {
      const data = (err as { response?: { data?: { error?: string } } }).response?.data;
      setCreateError(data?.error ?? 'Could not create workspace');
    }
  };

  const handleSelect = (id: number) => {
    setActiveWorkspaceId(id);
    navigate('/');
  };

  const handleLogout = () => {
    clearAuth();
    navigate('/login');
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-dark-950 px-4 relative overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-brand-500/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-[500px] h-[500px] bg-blue-500/5 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-3xl animate-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-dark-800/60 pb-6 mb-8">
          <div className="flex items-center space-x-3.5">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-brand-600 to-brand-400 flex items-center justify-center shadow-lg shadow-brand-500/25">
              <Database className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-white to-dark-300 bg-clip-text text-transparent">
                Select Workspace
              </h1>
              <p className="text-xs text-dark-400 mt-0.5">Please choose a workspace context to start querying</p>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="flex items-center space-x-1.5 px-3 py-2 text-xs text-dark-400 hover:text-red-400 hover:bg-red-500/10 border border-dark-800/80 rounded-xl transition-all"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign Out</span>
          </button>
        </div>

        {/* Card Grid */}
        {workspaces.length === 0 ? (
          <div className="glass-panel rounded-2xl p-12 text-center text-dark-400 max-w-md mx-auto">
            <Layers className="w-10 h-10 mx-auto text-dark-500 mb-3" />
            <h3 className="text-sm font-semibold text-white">No workspaces found</h3>
            <p className="text-xs text-dark-400 mt-1">
              You are not in any workspace yet. Create one below, or ask a workspace admin to add you.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {workspaces.map((ws) => {
              const isActive = activeWorkspaceId === ws.id;

              return (
                <div
                  key={ws.id}
                  onClick={() => handleSelect(ws.id)}
                  className={`glass-panel p-5 rounded-2xl border text-left cursor-pointer transition-all duration-300 flex flex-col justify-between group ${
                    isActive
                      ? 'border-brand-500 shadow-lg shadow-brand-500/10 bg-brand-500/5'
                      : 'border-dark-800/60 hover:border-brand-500/40 hover:bg-dark-900/60 hover:shadow-lg'
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between mb-4">
                      <div className="w-10 h-10 rounded-lg bg-dark-950/80 border border-dark-800 flex items-center justify-center text-brand-400 font-bold group-hover:scale-105 transition-transform">
                        {ws.name.substring(0, 2).toUpperCase()}
                      </div>
                      {isActive && (
                        <span className="text-[10px] font-semibold text-brand-400 bg-brand-500/10 border border-brand-500/20 px-2 py-0.5 rounded-full uppercase tracking-wider">
                          Active
                        </span>
                      )}
                    </div>

                    <h3 className="text-sm font-bold text-white group-hover:text-brand-300 transition-colors">
                      {ws.name}
                    </h3>
                    <p className="text-xs text-dark-400 mt-1 line-clamp-2">
                      RAG workspace for semantic analysis and smart document ingestion.
                    </p>
                  </div>

                  <div className="mt-6 pt-4 border-t border-dark-800/50 flex items-center justify-between text-xs text-dark-400">
                    <div className="flex items-center space-x-1.5">
                      <Shield className="w-3.5 h-3.5 text-brand-500" />
                      <span className="capitalize font-semibold text-brand-400">
                        {ws.role}
                      </span>
                    </div>
                    <span className="flex items-center space-x-1 font-semibold group-hover:translate-x-1 transition-transform">
                      <span>Enter Workspace</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Create a workspace for a team or project */}
        <form onSubmit={handleCreate} className="mt-6 flex items-center gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={100}
            placeholder="New workspace name, e.g. Payments team"
            className="flex-1 bg-dark-950/60 border border-dark-800 rounded-xl px-3 py-2 text-xs text-dark-100 focus:outline-none focus:border-brand-500"
          />
          <button
            type="submit"
            className="flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white rounded-xl"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create</span>
          </button>
        </form>
        {createError && <p className="text-xs text-red-400 mt-2">{createError}</p>}
      </div>
    </div>
  );
};
