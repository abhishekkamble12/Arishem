import React, { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useDocuments } from '../hooks/useDocuments';
import {
  MessageSquare, FileText, Upload, BarChart3, Settings, ShieldAlert,
  Clock, ArrowRight, Database, ChevronRight, FileCheck, Layers, HelpCircle
} from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const { user, activeWorkspaceId } = useAuthStore();
  const { files, isLoading, hasActiveJobs, activeJobsCount } = useDocuments();
  const [searchQuery, setSearchQuery] = useState('');
  const navigate = useNavigate();

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    navigate(`/chat?q=${encodeURIComponent(searchQuery.trim())}`);
  };

  const getFileBasename = (key?: string) => (key || '').split('/').pop() || key || '';

  const getActiveWorkspaceName = () => {
    const ws = user?.workspaces?.find(w => w.id === activeWorkspaceId);
    return ws ? ws.name : 'Unknown Workspace';
  };

  // Recent files slice
  const recentFiles = files.slice(0, 4);

  const sampleSuggestions = [
    'What key deliverables are outlined in our ingested files?',
    'List all timelines or milestones specified in the reports.',
    'Summarize discussions and major action points.',
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8 animate-slide-up">
      {/* Welcome & Overview Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-dark-900/40 p-6 rounded-2xl border border-dark-800/80">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-brand-500/10 border border-brand-500/25 text-brand-400">
              Workspace Context
            </span>
            <span className="text-xs font-semibold text-dark-400">/</span>
            <span className="text-xs font-semibold text-brand-300 font-mono">
              {getActiveWorkspaceName()}
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-white mt-1.5">
            Hello, {user?.username || 'Guest'}
          </h1>
          <p className="text-sm text-dark-400 mt-1">
            Analyze your workspace files, view ingestion states, and run semantic queries.
          </p>
        </div>

        {/* Quick Ingestion Widget */}
        {hasActiveJobs && (
          <div className="flex items-center space-x-3.5 bg-brand-500/10 border border-brand-500/25 px-4.5 py-3 rounded-xl animate-pulse">
            <div className="w-2.5 h-2.5 bg-brand-500 rounded-full" />
            <div className="text-xs">
              <span className="font-bold text-white block">Ingesting Documents</span>
              <span className="text-dark-400 font-mono">{activeJobsCount} file{activeJobsCount !== 1 ? 's' : ''} processing</span>
            </div>
            <Link
              to="/documents"
              className="p-1 rounded bg-dark-950/60 border border-dark-800 text-brand-400 hover:text-white transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        )}
      </div>

      {/* RAG Quick Ask Bar */}
      <div className="glass-panel p-6 rounded-2xl border border-dark-800/80 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-64 h-64 bg-brand-500/5 rounded-full blur-3xl pointer-events-none" />
        <h2 className="text-base font-bold text-white mb-1.5 flex items-center space-x-2">
          <MessageSquare className="w-4 h-4 text-brand-400" />
          <span>Ask anything about your documents</span>
        </h2>
        <p className="text-xs text-dark-400 mb-4.5">
          Queries will utilize decomposition, semantic vector retrieval, and LLM synthesis.
        </p>

        <form onSubmit={handleSearchSubmit} className="relative">
          <input
            type="text"
            placeholder="e.g. What are the key points in our security guidelines?"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-4.5 pr-14 py-3 bg-dark-950/80 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 text-sm focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 transition-all"
          />
          <button
            type="submit"
            className="absolute right-2.5 top-2 py-1.5 px-3.5 bg-brand-600 hover:bg-brand-500 text-white font-semibold rounded-lg text-xs transition-all flex items-center space-x-1.5"
          >
            <span>Ask</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </form>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-[10px] text-dark-500 font-semibold uppercase tracking-wider">Try:</span>
          {sampleSuggestions.map((s, idx) => (
            <button
              key={idx}
              onClick={() => {
                setSearchQuery(s);
              }}
              className="text-[11px] text-dark-300 bg-dark-950/60 hover:bg-dark-800/60 border border-dark-800 px-3 py-1 rounded-lg transition-all"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Grid of Key Actions & Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Stat 1 */}
        <div className="glass-panel p-5 rounded-2xl border border-dark-800/80 flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-bold tracking-wider text-dark-500">Active RAG Engine</span>
            <span className="text-base font-extrabold text-white block mt-1">Llama 3.3 70B</span>
            <span className="text-[10px] font-mono text-brand-400 mt-0.5 block">Self-Critique Enabled</span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center text-brand-400 border border-brand-500/15">
            <Database className="w-5 h-5" />
          </div>
        </div>

        {/* Stat 2 */}
        <div className="glass-panel p-5 rounded-2xl border border-dark-800/80 flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-bold tracking-wider text-dark-500">Total Documents</span>
            <span className="text-base font-extrabold text-white block mt-1 font-mono">{files.length} Ingested</span>
            <span className="text-[10px] text-dark-400 mt-0.5 block">Across S3 & Youtube</span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center text-brand-400 border border-brand-500/15">
            <FileText className="w-5 h-5" />
          </div>
        </div>

        {/* Stat 3 */}
        <div className="glass-panel p-5 rounded-2xl border border-dark-800/80 flex items-center justify-between">
          <div>
            <span className="text-[10px] uppercase font-bold tracking-wider text-dark-500">Average Latency</span>
            <span className="text-base font-extrabold text-white block mt-1 font-mono">1.48s</span>
            <span className="text-[10px] text-emerald-400 mt-0.5 block">● Healthy (AWS Bedrock)</span>
          </div>
          <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center text-brand-400 border border-brand-500/15">
            <Clock className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Lower Grid: Recent files & Quick Links */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Left: Recent Files */}
        <div className="md:col-span-8 glass-panel rounded-2xl p-5 border border-dark-800/80">
          <div className="flex items-center justify-between mb-4 pb-2 border-b border-dark-800/60">
            <h3 className="text-sm font-bold text-white flex items-center space-x-2">
              <FileCheck className="w-4 h-4 text-brand-400" />
              <span>Recent Workspace Documents</span>
            </h3>
            <Link
              to="/documents"
              className="text-[11px] text-brand-400 hover:text-brand-300 font-semibold flex items-center space-x-1"
            >
              <span>View all files</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {isLoading ? (
            <div className="py-12 text-center text-xs text-dark-500">
              <div className="w-5 h-5 border-2 border-brand-600 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              Loading workspace documents...
            </div>
          ) : recentFiles.length === 0 ? (
            <div className="py-12 text-center text-xs text-dark-500">
              No files ingested in this workspace yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="text-dark-500 uppercase tracking-wider font-semibold border-b border-dark-800/60 pb-2">
                    <th className="pb-2 font-semibold">Name</th>
                    <th className="pb-2 font-semibold">Chunks</th>
                    <th className="pb-2 font-semibold">Status</th>
                    <th className="pb-2 font-semibold">Uploaded By</th>
                  </tr>
                </thead>
                <tbody>
                  {recentFiles.map((file) => (
                    <tr key={file.id} className="border-b border-dark-800/40 hover:bg-dark-900/20">
                      <td className="py-3 font-semibold text-white truncate max-w-[200px]" title={file.s3_key}>
                        {getFileBasename(file.s3_key)}
                      </td>
                      <td className="py-3 font-mono text-dark-300">{file.chunks_stored}</td>
                      <td className="py-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold border uppercase tracking-wider ${
                            file.status === 'success'
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                              : file.status === 'failed'
                              ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                              : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                          }`}
                        >
                          {file.status}
                        </span>
                      </td>
                      <td className="py-3 text-dark-400">{file.uploaded_by__email || 'System'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right: Quick Actions List */}
        <div className="md:col-span-4 flex flex-col space-y-4">
          <div className="glass-panel p-5 rounded-2xl border border-dark-800/80 flex-1">
            <h3 className="text-sm font-bold text-white mb-4">Quick Shortcuts</h3>
            <div className="space-y-2.5">
              <Link
                to="/chat"
                className="flex items-center justify-between p-3 rounded-xl bg-dark-950/60 border border-dark-800/60 hover:border-brand-500/50 hover:bg-dark-900/60 transition-all text-xs group"
              >
                <div className="flex items-center space-x-2.5 text-white font-semibold">
                  <MessageSquare className="w-4 h-4 text-brand-400" />
                  <span>Start Chat Session</span>
                </div>
                <ChevronRight className="w-4 h-4 text-dark-500 group-hover:translate-x-0.5 transition-transform" />
              </Link>

              <Link
                to="/documents"
                className="flex items-center justify-between p-3 rounded-xl bg-dark-950/60 border border-dark-800/60 hover:border-brand-500/50 hover:bg-dark-900/60 transition-all text-xs group"
              >
                <div className="flex items-center space-x-2.5 text-white font-semibold">
                  <Upload className="w-4 h-4 text-brand-400" />
                  <span>Ingest S3 / Youtube</span>
                </div>
                <ChevronRight className="w-4 h-4 text-dark-500 group-hover:translate-x-0.5 transition-transform" />
              </Link>

              {user?.role !== 'viewer' && (
                <Link
                  to="/monitoring"
                  className="flex items-center justify-between p-3 rounded-xl bg-dark-950/60 border border-dark-800/60 hover:border-brand-500/50 hover:bg-dark-900/60 transition-all text-xs group"
                >
                  <div className="flex items-center space-x-2.5 text-white font-semibold">
                    <BarChart3 className="w-4 h-4 text-brand-400" />
                    <span>Monitoring Dashboard</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-dark-500 group-hover:translate-x-0.5 transition-transform" />
                </Link>
              )}

              <Link
                to="/settings"
                className="flex items-center justify-between p-3 rounded-xl bg-dark-950/60 border border-dark-800/60 hover:border-brand-500/50 hover:bg-dark-900/60 transition-all text-xs group"
              >
                <div className="flex items-center space-x-2.5 text-white font-semibold">
                  <Settings className="w-4 h-4 text-brand-400" />
                  <span>Workspace Settings</span>
                </div>
                <ChevronRight className="w-4 h-4 text-dark-500 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
