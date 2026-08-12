import React, { useEffect, useState, useRef } from 'react';
import { useChatStore } from '../store/chatStore';
import { useAuthStore } from '../store/authStore';
import { aiApi } from '../api/ai';
import {
  MessageSquare, FileText, Send, RefreshCw, Search, X,
  Copy, Check, Film, Music, Sparkles, Loader2, Trash2,
  ChevronDown, ChevronUp, GitBranch, ShieldCheck, AlertTriangle
} from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const {
    messages, files, isQuerying, isFetchingFiles,
    fileSearchQuery, selectedSourceFilter, askQuestion, fetchFiles,
    setFileSearchQuery, setSelectedSourceFilter, clearHistory
  } = useChatStore();
  const { user, activeWorkspaceId } = useAuthStore();

  const [question, setQuestion] = useState('');
  const [activeTab, setActiveTab] = useState<'chat' | 'files'>('chat');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [expandedTrace, setExpandedTrace] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isQuerying]);

  useEffect(() => {
    fetchFiles();
  }, [activeWorkspaceId]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || isQuerying) return;
    const queryText = question.trim();
    setQuestion('');
    await askQuestion(queryText);
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleDelete = async (s3Key: string) => {
    if (!confirm(`Remove "${s3Key.split('/').pop()}" from the knowledge base?`)) return;
    setDeletingKey(s3Key);
    try {
      await aiApi.deleteFile(s3Key);
      await fetchFiles();
    } catch (err: any) {
      alert(err.response?.data?.error || 'Delete failed');
    } finally {
      setDeletingKey(null);
    }
  };

  const getFileBasename = (key?: string) => (key || '').split('/').pop() || key || '';

  const getFileTypeIcon = (type?: string) => {
    const t = (type || '').toLowerCase();
    if (['mp4', 'mov', 'avi', 'mkv'].includes(t)) return <Film className="w-4 h-4 text-purple-400" />;
    if (['mp3', 'wav', 'flac', 'ogg', 'm4a'].includes(t)) return <Music className="w-4 h-4 text-emerald-400" />;
    return <FileText className="w-4 h-4 text-brand-400" />;
  };

  const getFileTypeBadgeClass = (type?: string) => {
    const t = (type || '').toLowerCase();
    if (t === 'pdf') return 'bg-red-500/10 text-red-400 border-red-500/20';
    if (['docx', 'doc'].includes(t)) return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    if (t === 'pptx') return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    if (['mp4', 'mov', 'avi', 'mkv'].includes(t)) return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
    if (['mp3', 'wav', 'flac', 'ogg', 'm4a'].includes(t)) return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
  };

  const formatDate = (dateString: string) =>
    new Date(dateString).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });

  const filteredFiles = files.filter(file => {
    const s3Key = file.s3_key || (file as any).object_key || '';
    const matchesSearch = s3Key.toLowerCase().includes(fileSearchQuery.toLowerCase());
    const matchesFilter = selectedSourceFilter ? s3Key === selectedSourceFilter : true;
    return matchesSearch && matchesFilter;
  });

  const clearAllFilters = () => {
    setFileSearchQuery('');
    setSelectedSourceFilter(null);
  };

  const suggestions = [
    'What key findings are discussed in the ingested reports?',
    'List the critical deliverables or timelines specified in the files.',
    'Summarize the discussions and decisions in the audio/video transcription.',
    'Who are the authors or speakers mentioned in these files?',
  ];

  const canDelete = user?.role === 'admin' || user?.role === 'editor';

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 h-[calc(100vh-100px)] flex flex-col">
      {/* Mobile Tab Switcher */}
      <div className="md:hidden flex space-x-2 mb-4 bg-dark-900/60 p-1 rounded-xl border border-dark-800/40">
        <button
          onClick={() => setActiveTab('chat')}
          className={`flex-1 flex items-center justify-center space-x-2 py-2.5 rounded-lg text-sm font-medium transition-all ${activeTab === 'chat' ? 'bg-brand-600 text-white shadow-lg' : 'text-dark-400 hover:text-dark-200'
            }`}
        >
          <MessageSquare className="w-4 h-4" />
          <span>Chat Agent</span>
        </button>
        <button
          onClick={() => setActiveTab('files')}
          className={`flex-1 flex items-center justify-center space-x-2 py-2.5 rounded-lg text-sm font-medium transition-all ${activeTab === 'files' ? 'bg-brand-600 text-white shadow-lg' : 'text-dark-400 hover:text-dark-200'
            }`}
        >
          <FileText className="w-4 h-4" />
          <span>Files ({files.length})</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-6 flex-1 min-h-0">

        {/* ── Left: Chat ── */}
        <div className={`md:col-span-7 flex flex-col h-full min-h-0 bg-dark-900/35 border border-dark-800/40 rounded-2xl p-4 overflow-hidden relative ${activeTab === 'chat' ? 'flex' : 'hidden md:flex'
          }`}>
          <div className="flex items-center justify-between border-b border-dark-800/60 pb-3.5 mb-4 flex-shrink-0">
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center text-brand-400">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <h2 className="font-bold text-white text-sm">Arishem RAG Agent</h2>
                <p className="text-[10px] text-dark-500">Groq Llama 3.3 70B · Query Decomposition · Self-Critique</p>
              </div>
            </div>
            {messages.length > 0 && (
              <button
                onClick={clearHistory}
                className="text-xs text-dark-500 hover:text-red-400 transition-colors px-2 py-1 bg-dark-900/50 hover:bg-red-500/10 border border-dark-800 rounded-lg"
              >
                Clear History
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto space-y-4 pr-1 mb-4">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col justify-center items-center px-6 text-center animate-fade-in py-8">
                <div className="w-16 h-16 rounded-full bg-brand-500/5 flex items-center justify-center mb-4 text-brand-400 border border-brand-500/10">
                  <Sparkles className="w-8 h-8" />
                </div>
                <h3 className="font-bold text-white text-base">Ask anything from your documents</h3>
                <p className="text-xs text-dark-400 max-w-sm mt-2 leading-relaxed">
                  Upload files and write queries. Claude will retrieve relevant passages and generate citation-supported answers.
                </p>
                <div className="mt-8 w-full max-w-md space-y-2.5">
                  <span className="text-[10px] text-dark-500 uppercase tracking-widest font-bold">Suggested Prompts</span>
                  <div className="grid grid-cols-1 gap-2">
                    {suggestions.map((s, idx) => (
                      <button
                        key={idx}
                        onClick={() => setQuestion(s)}
                        className="text-left text-xs bg-dark-900/40 hover:bg-brand-500/5 border border-dark-800 hover:border-brand-500/35 text-dark-300 hover:text-white p-3 rounded-xl transition-all duration-200"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex flex-col max-w-[85%] ${msg.role === 'user' ? 'ml-auto items-end' : 'mr-auto items-start'} animate-slide-up`}
                  >
                    <div className="flex items-center space-x-1.5 text-[10px] text-dark-500 mb-1 px-1">
                      <span>{msg.role === 'user' ? 'You' : 'Claude Agent'}</span>
                      <span>•</span>
                      <span>{formatDate(msg.timestamp)}</span>
                    </div>
                    <div className={`p-4 rounded-2xl relative group ${msg.role === 'user'
                        ? 'bg-gradient-to-tr from-brand-700 to-brand-500 text-white rounded-br-none shadow-md shadow-brand-500/10'
                        : 'glass-panel text-dark-100 rounded-bl-none shadow-lg'
                      }`}>
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                      {msg.role === 'assistant' && (
                        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                          <button
                            onClick={() => handleCopy(msg.id, msg.content)}
                            className="p-1 rounded bg-dark-950/80 hover:bg-dark-950 border border-dark-800 text-dark-400 hover:text-white transition-all"
                          >
                            {copiedId === msg.id
                              ? <Check className="w-3.5 h-3.5 text-emerald-500" />
                              : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                      )}
                      {msg.role === 'assistant' && (
                        <div className="mt-4 space-y-4">
                          {msg.citations && msg.citations.length > 0 ? (
                            <div className="pt-3.5 border-t border-dark-800/60 space-y-2">
                              <span className="text-[10px] uppercase font-bold text-brand-400 tracking-wider">
                                Sources & Evidence ({msg.citations.length} citations)
                              </span>
                              <div className="flex flex-col gap-2">
                                {msg.citations.map((cite, i) => (
                                  <div key={i} className="bg-dark-900/60 p-2.5 rounded-lg border border-dark-800">
                                    <button
                                      onClick={() => { setSelectedSourceFilter(cite.source); setActiveTab('files'); }}
                                      className={`text-[10px] mb-1.5 px-2 py-1 rounded border flex items-center space-x-1.5 transition-all w-max ${selectedSourceFilter === cite.source
                                          ? 'bg-brand-500 text-white border-brand-400'
                                          : 'bg-dark-800/40 text-brand-300 border-dark-700 hover:bg-dark-700/50 hover:text-white'
                                        }`}
                                    >
                                      <FileText className="w-3 h-3 flex-shrink-0" />
                                      <span className="truncate max-w-[150px]">{getFileBasename(cite.source)}</span>
                                    </button>
                                    <p className="text-xs text-dark-300 border-l-2 border-brand-500/30 pl-2 italic">"{cite.snippet}"</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : msg.sources && msg.sources.length > 0 && (
                            <div className="pt-3.5 border-t border-dark-800/60 space-y-2">
                              <span className="text-[10px] uppercase font-bold text-brand-400 tracking-wider">
                                Sources cited ({msg.chunks || msg.sources.length} chunks):
                              </span>
                              <div className="flex flex-wrap gap-1.5">
                                {msg.sources.map((src, i) => (
                                  <button
                                    key={i}
                                    onClick={() => { setSelectedSourceFilter(src); setActiveTab('files'); }}
                                    className={`text-[10px] px-2 py-1 rounded border flex items-center space-x-1.5 transition-all ${selectedSourceFilter === src
                                        ? 'bg-brand-500 text-white border-brand-400'
                                        : 'bg-dark-900/60 text-dark-300 border-dark-800 hover:bg-dark-800/40 hover:text-white'
                                      }`}
                                  >
                                    <FileText className="w-3 h-3 flex-shrink-0" />
                                    <span className="truncate max-w-[150px]">{getFileBasename(src)}</span>
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}

                          {msg.unverified && (
                            <div className="pt-2 border-t border-dark-800/60 space-y-1">
                              <span className="text-[10px] uppercase font-bold text-amber-500 tracking-wider flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-amber-500/50"></span> Missing / Unverified Information
                              </span>
                              <p className="text-xs text-amber-400/80 bg-amber-500/5 p-2 rounded border border-amber-500/10">
                                {msg.unverified}
                              </p>
                            </div>
                          )}

                          {msg.llm_confidence !== undefined && (
                            <div className="flex justify-end pt-1 flex-wrap gap-1.5">
                              <span className={`text-[9px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border ${
                                msg.llm_confidence >= 0.8 ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                msg.llm_confidence >= 0.5 ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                'bg-red-500/10 text-red-400 border-red-500/20'
                              }`}>
                                Confidence: {Math.round(msg.llm_confidence * 100)}%
                              </span>
                              {(msg as any).critique_verdict && (msg as any).critique_verdict !== 'SKIPPED' && (
                                <span className={`text-[9px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border flex items-center gap-1 ${
                                  (msg as any).critique_verdict === 'PASS' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                  (msg as any).critique_verdict === 'PARTIAL' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                  'bg-red-500/10 text-red-400 border-red-500/20'
                                }`}>
                                  {(msg as any).critique_verdict === 'PASS' ? <ShieldCheck className="w-2.5 h-2.5" /> : <AlertTriangle className="w-2.5 h-2.5" />}
                                  Fact-Check: {(msg as any).critique_verdict}
                                </span>
                              )}
                              {(msg as any).agentic_mode && (
                                <span className="text-[9px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border bg-brand-500/10 text-brand-400 border-brand-500/20 flex items-center gap-1">
                                  <GitBranch className="w-2.5 h-2.5" /> Agentic
                                </span>
                              )}
                            </div>
                          )}

                          {/* Collapsible Reasoning Trace */}
                          {(msg as any).reasoning_steps && (msg as any).reasoning_steps.length > 0 && (
                            <div className="pt-2 border-t border-dark-800/40">
                              <button
                                onClick={() => setExpandedTrace(expandedTrace === msg.id ? null : msg.id)}
                                className="flex items-center gap-1.5 text-[9px] uppercase font-bold text-dark-500 hover:text-brand-400 tracking-wider transition-colors"
                              >
                                {expandedTrace === msg.id ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                                Reasoning Trace ({(msg as any).reasoning_steps.length} steps)
                              </button>
                              {expandedTrace === msg.id && (
                                <div className="mt-2 space-y-1.5">
                                  {(msg as any).reasoning_steps.map((step: any, i: number) => (
                                    <div key={i} className="bg-dark-950/60 border border-dark-800/60 rounded-lg p-2 text-[10px]">
                                      <span className={`inline-block uppercase font-extrabold tracking-wider px-1.5 py-0.5 rounded text-[8px] mr-2 ${
                                        step.phase === 'decomposition' ? 'bg-violet-500/20 text-violet-400' :
                                        step.phase === 'retrieval'     ? 'bg-blue-500/20 text-blue-400' :
                                        step.phase === 'synthesis'     ? 'bg-brand-500/20 text-brand-400' :
                                        step.phase === 'self_critique' ? 'bg-emerald-500/20 text-emerald-400' :
                                        'bg-amber-500/20 text-amber-400'
                                      }`}>{step.phase}</span>
                                      {step.phase === 'decomposition' && (
                                        <span className="text-dark-300">
                                          {step.is_complex
                                            ? `Split into ${step.sub_queries?.length} sub-queries`
                                            : 'Simple — no decomposition needed'}
                                          {step.is_complex && (
                                            <ul className="mt-1 ml-3 list-disc space-y-0.5 text-dark-400">
                                              {step.sub_queries?.map((q: string, qi: number) => <li key={qi}>{q}</li>)}
                                            </ul>
                                          )}
                                        </span>
                                      )}
                                      {step.phase === 'retrieval' && (
                                        <span className="text-dark-300">{step.total_unique_chunks} unique chunks retrieved across all sub-queries</span>
                                      )}
                                      {step.phase === 'synthesis' && (
                                        <span className="text-dark-300">LLM call #{step.llm_call} — grounded answer generated</span>
                                      )}
                                      {step.phase === 'self_critique' && (
                                        <span className={step.verdict === 'PASS' ? 'text-emerald-400' : 'text-amber-400'}>
                                          Verdict: {step.verdict}
                                          {step.unsupported_claims?.length > 0 && ` — ${step.unsupported_claims.length} unsupported claim(s) flagged`}
                                        </span>
                                      )}
                                      {step.phase === 'retry_synthesis' && (
                                        <span className="text-amber-400">Conservative retry triggered (LLM call #{step.llm_call})</span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {isQuerying && (
                  <div className="flex flex-col items-start max-w-[80%] animate-pulse-subtle">
                    <div className="flex items-center space-x-1.5 text-[10px] text-dark-500 mb-1 px-1">
                      <span>Arishem Agent</span><span>•</span><span>Reasoning...</span>
                    </div>
                    <div className="glass-panel text-dark-100 p-4 rounded-2xl rounded-bl-none shadow-md flex items-center">
                      <div className="flex space-x-1 items-center py-1.5 px-1">
                        <div className="w-2.5 h-2.5 bg-brand-400 rounded-full typing-dot" />
                        <div className="w-2.5 h-2.5 bg-brand-400 rounded-full typing-dot" />
                        <div className="w-2.5 h-2.5 bg-brand-400 rounded-full typing-dot" />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSend} className="flex-shrink-0 mt-auto pt-2 border-t border-dark-800/40">
            <div className="relative flex items-center">
              <input
                type="text"
                disabled={isQuerying}
                placeholder={files.filter(f => !f.status || f.status === 'SUCCESS').length === 0 ? 'Upload and ingest documents first to start querying...' : 'Ask Claude about your ingested documents...'}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                className="w-full bg-dark-900/60 border border-dark-800 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 text-dark-100 placeholder-dark-500 pl-4 pr-12 py-3.5 rounded-xl text-sm focus:outline-none transition-all duration-200"
              />
              <button
                type="submit"
                disabled={isQuerying || !question.trim()}
                className="absolute right-2 p-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-40 text-white rounded-lg transition-colors duration-200"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
            {files.filter(f => !f.status || f.status === 'SUCCESS').length === 0 && (
              <p className="text-[10px] text-amber-500/80 text-center mt-2">
                ⚠️ No successfully ingested documents yet. Use the Upload page to add files and wait for completion.
              </p>
            )}
          </form>
        </div>

        {/* ── Right: Files ── */}
        <div className={`md:col-span-5 flex flex-col h-full min-h-0 bg-dark-900/35 border border-dark-800/40 rounded-2xl p-4 overflow-hidden ${activeTab === 'files' ? 'flex' : 'hidden md:flex'
          }`}>
          <div className="space-y-3.5 flex-shrink-0 mb-4 pb-4 border-b border-dark-800/60">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <FileText className="w-4 h-4 text-brand-400" />
                <h2 className="font-bold text-white text-sm">Ingested Files</h2>
                <span className="text-[10px] bg-brand-500/10 border border-brand-500/20 text-brand-400 px-2 py-0.5 rounded-full font-bold">
                  {files.length}
                </span>
              </div>
              <button
                onClick={fetchFiles}
                disabled={isFetchingFiles}
                className="p-1.5 text-dark-400 hover:text-brand-400 hover:bg-dark-800/50 rounded-lg transition-colors border border-dark-800"
                title="Refresh"
              >
                <RefreshCw className={`w-4 h-4 ${isFetchingFiles ? 'animate-spin' : ''}`} />
              </button>
            </div>

            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-dark-500">
                <Search className="w-4 h-4" />
              </div>
              <input
                type="text"
                placeholder="Search files..."
                value={fileSearchQuery}
                onChange={(e) => setFileSearchQuery(e.target.value)}
                className="w-full pl-9 pr-8 py-2 bg-dark-900/60 border border-dark-800 rounded-xl text-xs text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 transition-colors"
              />
              {fileSearchQuery && (
                <button onClick={() => setFileSearchQuery('')} className="absolute inset-y-0 right-0 pr-3 flex items-center text-dark-400 hover:text-white">
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {selectedSourceFilter && (
              <div className="bg-brand-500/10 border border-brand-500/25 p-2 rounded-xl text-xs flex items-center justify-between text-brand-300">
                <div className="flex items-center space-x-1.5 truncate pr-2">
                  <span className="font-semibold uppercase tracking-wider text-[9px] bg-brand-500 text-white px-1.5 py-0.5 rounded">CITED</span>
                  <span className="truncate">{getFileBasename(selectedSourceFilter)}</span>
                </div>
                <button onClick={() => setSelectedSourceFilter(null)} className="text-brand-400 hover:text-white flex-shrink-0">
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {(fileSearchQuery || selectedSourceFilter) && (
              <button onClick={clearAllFilters} className="text-[10px] text-dark-400 hover:text-white underline transition-colors block">
                Clear all filters
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
            {isFetchingFiles && files.length === 0 ? (
              <div className="py-16 flex flex-col items-center justify-center">
                <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
                <span className="text-xs text-dark-400 mt-2">Loading documents...</span>
              </div>
            ) : filteredFiles.length === 0 ? (
              <div className="py-16 text-center glass-panel rounded-2xl p-6">
                <FileText className="w-8 h-8 text-dark-500 mx-auto mb-2 opacity-55" />
                <h4 className="font-semibold text-white text-xs">
                  {files.length === 0 ? 'No files ingested yet' : 'No files matching filters'}
                </h4>
                <p className="text-[11px] text-dark-400 mt-1">
                  {files.length === 0
                    ? 'Use the Upload page to add documents.'
                    : 'Try clearing your search or filter.'}
                </p>
              </div>
            ) : (
              filteredFiles.map((file) => {
                const s3Key = file.s3_key || (file as any).object_key || '';
                const isCited = selectedSourceFilter === s3Key;
                const isDeleting = deletingKey === s3Key;
                return (
                  <div
                    key={file.id}
                    className={`p-3.5 rounded-xl border transition-all duration-200 flex flex-col space-y-2 bg-dark-900/40 ${isCited ? 'border-brand-500 shadow-md shadow-brand-500/10 bg-brand-950/10' : 'border-dark-800 hover:border-dark-700'
                      }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center space-x-2 truncate">
                        {getFileTypeIcon(file.file_type)}
                        <span className="text-xs font-bold text-dark-100 truncate" title={s3Key}>
                          {getFileBasename(s3Key)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {file.status && file.status !== 'SUCCESS' && (
                          <span className={`text-[9px] uppercase tracking-wider font-extrabold px-2 py-0.5 rounded border flex items-center gap-1 ${
                            file.status === 'PENDING' ? 'bg-slate-500/10 text-slate-400 border-slate-500/20' :
                            file.status === 'PROCESSING' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20 animate-pulse' :
                            'bg-red-500/10 text-red-400 border-red-500/20'
                          }`}>
                            {file.status === 'PROCESSING' && <Loader2 className="w-2.5 h-2.5 animate-spin" />}
                            {file.status}
                          </span>
                        )}
                        <span className={`text-[9px] uppercase tracking-wider font-extrabold px-2 py-0.5 rounded border ${getFileTypeBadgeClass(file.file_type)}`}>
                          {file.file_type}
                        </span>
                        {canDelete && (
                          <button
                            onClick={() => handleDelete(s3Key)}
                            disabled={isDeleting}
                            className="p-1 text-dark-500 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                            title="Remove from knowledge base"
                          >
                            {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                          </button>
                        )}
                      </div>
                    </div>

                    <p className="text-[10px] text-dark-500 break-all leading-tight">
                      s3://{s3Key}
                    </p>

                    {file.status === 'FAILED' && file.error_message && (
                      <p className="text-[10px] text-red-400 bg-red-500/5 p-2 rounded border border-red-500/10 leading-normal">
                        <strong>Error:</strong> {file.error_message}
                      </p>
                    )}

                    <div className="pt-2 border-t border-dark-800/40 grid grid-cols-2 gap-2 text-[10px] text-dark-400">
                      <div>
                        <span className="block text-[9px] uppercase tracking-wide font-bold text-dark-500">Chunks</span>
                        <strong className="text-dark-200">{file.chunks_stored}</strong>
                      </div>
                      <div className="text-right">
                        <span className="block text-[9px] uppercase tracking-wide font-bold text-dark-500">Ingested</span>
                        <strong className="text-dark-200">{formatDate(file.ingested_at)}</strong>
                      </div>
                      <div className="col-span-2 flex items-center space-x-1 text-[9px]">
                        <span className="text-dark-500 uppercase tracking-wide font-bold">By:</span>
                        <span className="text-dark-300 truncate">{file.uploaded_by__email}</span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
