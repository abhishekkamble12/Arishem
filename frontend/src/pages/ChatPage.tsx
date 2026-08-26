import React, { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useChatStore, ChatMessage } from '../store/chatStore';
import { useAuthStore } from '../store/authStore';
import { useDocuments } from '../hooks/useDocuments';
import { ConfidenceBar } from '../components/ui/ConfidenceBar';
import { ReasoningTrace } from '../components/chat/ReasoningTrace';
import { OODMessageCard } from '../components/chat/OODMessageCard';
import { CitationPreviewPanel } from '../components/chat/CitationPreviewPanel';
import {
  MessageSquare, FileText, Send, Sparkles, Loader2, Trash2,
  ChevronRight, ArrowRight, ShieldAlert, BookOpen
} from 'lucide-react';

export const ChatPage: React.FC = () => {
  const {
    messages, askQuestion, clearHistory, isQuerying
  } = useChatStore();
  const { activeWorkspaceId } = useAuthStore();
  const { files, isLoading: isDocsLoading } = useDocuments();

  const [question, setQuestion] = useState('');
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<{ source: string; snippet: string; score?: number } | null>(null);

  const location = useLocation();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isQuerying]);

  // Handle query parameter trigger
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const q = params.get('q') || params.get('question');
    if (q && q.trim()) {
      askQuestion(q.trim());
    }
  }, [location.search, askQuestion]);

  const handleSendSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || isQuerying) return;
    const queryText = question.trim();
    setQuestion('');
    await askQuestion(queryText);
  };

  const handleCitationClick = (citation: { source: string; snippet: string; score?: number }) => {
    setSelectedCitation(citation);
    setRightPanelOpen(true);
  };

  const getFileBasename = (path: string) => path.split('/').pop() || path;

  // Gather all citations from the latest assistant response
  const getLatestCitations = () => {
    const assistantMsgs = messages.filter(m => m.role === 'assistant');
    if (assistantMsgs.length === 0) return [];
    const latest = assistantMsgs[assistantMsgs.length - 1];
    return latest.citations || [];
  };

  const isKBEmpty = !isDocsLoading && files.length === 0;

  return (
    <div className="w-full h-[calc(100vh-80px)] flex bg-dark-950 overflow-hidden">
      {/* ── Left/Center: Chat Thread (70% or full width if panel closed) ── */}
      <div className="flex-1 flex flex-col h-full min-w-0 border-r border-dark-800/40 relative">
        {/* Header bar */}
        <div className="flex items-center justify-between px-6 py-4.5 border-b border-dark-800/60 flex-shrink-0 bg-dark-900/10">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center text-brand-400 border border-brand-500/15">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="font-bold text-white text-sm">Arishem RAG Session</h2>
              <p className="text-[10px] text-dark-500 font-mono">
                Model: Groq Llama 3.3 70B · Context window: 128k
              </p>
            </div>
          </div>

          {messages.length > 0 && (
            <button
              onClick={clearHistory}
              className="text-[11px] text-dark-400 hover:text-red-400 transition-colors px-3 py-1.5 bg-dark-900/50 hover:bg-red-500/10 border border-dark-800 rounded-lg font-semibold"
            >
              Clear Session
            </button>
          )}
        </div>

        {/* Messages list */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isKBEmpty ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto py-12">
              <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 mb-4 animate-pulse">
                <ShieldAlert className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-white">Empty Knowledge Base</h3>
              <p className="text-xs text-dark-400 mt-1.5 leading-relaxed">
                There are no ingested documents in this workspace. Please upload a file or ingest an S3 resource first.
              </p>
            </div>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto py-12 text-dark-400">
              <MessageSquare className="w-10 h-10 opacity-30 mb-3 text-brand-400" />
              <p className="text-sm font-semibold text-white">Ask your workspace agent</p>
              <p className="text-xs text-dark-400 mt-1">
                Ask a question about the ingested PDFs, documents, or Youtube transcripts in this workspace.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((msg) => {
                const isUser = msg.role === 'user';
                const isOOD = msg.confidence !== undefined && msg.confidence < 0.35;

                return (
                  <div
                    key={msg.id}
                    className={`flex space-x-3.5 ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isUser && (
                      <div className="w-8 h-8 rounded-lg bg-dark-900 border border-dark-800 flex items-center justify-center text-brand-400 flex-shrink-0 font-bold text-xs select-none">
                        AI
                      </div>
                    )}

                    <div className={`max-w-[80%] space-y-2 ${isUser ? 'order-1' : 'order-2'}`}>
                      {/* Message header details */}
                      {!isUser && msg.confidence !== undefined && (
                        <div className="flex items-center space-x-2.5">
                          <ConfidenceBar score={msg.confidence} />
                          {msg.llm_confidence !== undefined && (
                            <span className="text-[10px] text-dark-500 font-mono">
                              LLM Verification: {Math.round(msg.llm_confidence * 100)}%
                            </span>
                          )}
                        </div>
                      )}

                      {/* Content block */}
                      <div
                        className={`p-4 rounded-2xl text-sm leading-relaxed ${
                          isUser
                            ? 'bg-brand-600 text-white shadow-lg shadow-brand-600/10'
                            : 'bg-dark-900/50 border border-dark-850/80 text-dark-100'
                        }`}
                      >
                        {isOOD && !isUser ? (
                          <OODMessageCard confidence={msg.confidence} />
                        ) : (
                          <p className="whitespace-pre-wrap">{msg.content}</p>
                        )}
                      </div>

                      {/* Citations chips */}
                      {!isUser && msg.citations && msg.citations.length > 0 && (
                        <div className="flex flex-wrap items-center gap-2 mt-2">
                          <span className="text-[10px] text-dark-500 font-bold uppercase tracking-wider">Citations:</span>
                          {msg.citations.map((cite, cIdx) => (
                            <button
                              key={cIdx}
                              onClick={() => handleCitationClick(cite)}
                              className="inline-flex items-center space-x-1 px-2.5 py-1 rounded bg-dark-900 hover:bg-brand-500/10 border border-dark-800 hover:border-brand-500/30 text-[10px] text-brand-400 transition-all font-mono"
                            >
                              <BookOpen className="w-3 h-3" />
                              <span>[{getFileBasename(cite.source)}]</span>
                            </button>
                          ))}
                        </div>
                      )}

                      {/* Agentic trace */}
                      {!isUser && msg.reasoning_steps && msg.reasoning_steps.length > 0 && (
                        <ReasoningTrace
                          steps={msg.reasoning_steps}
                          critiqueVerdict={msg.critique_verdict}
                          agenticMode={msg.agentic_mode}
                        />
                      )}
                    </div>
                  </div>
                );
              })}

              {/* In progress query state */}
              {isQuerying && (
                <div className="flex space-x-3.5 justify-start">
                  <div className="w-8 h-8 rounded-lg bg-dark-950 border border-dark-800 flex items-center justify-center text-brand-400 flex-shrink-0">
                    <Loader2 className="w-4 h-4 animate-spin" />
                  </div>
                  <div className="bg-dark-900/30 border border-dark-850/80 p-4 rounded-2xl text-xs text-dark-400 flex items-center space-x-2">
                    <div className="flex space-x-1">
                      <div className="w-1.5 h-1.5 bg-brand-500 rounded-full animate-bounce typing-dot" />
                      <div className="w-1.5 h-1.5 bg-brand-500 rounded-full animate-bounce typing-dot [animation-delay:0.2s]" />
                      <div className="w-1.5 h-1.5 bg-brand-500 rounded-full animate-bounce typing-dot [animation-delay:0.4s]" />
                    </div>
                    <span>Decomposing query and running vector search...</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Form */}
        <div className="p-4 border-t border-dark-800/60 bg-dark-900/10 flex-shrink-0">
          <form onSubmit={handleSendSubmit} className="relative max-w-5xl mx-auto">
            <input
              type="text"
              disabled={isKBEmpty || isQuerying}
              placeholder={isKBEmpty ? "Ingest a document first to unlock query agent" : "Ask a question..."}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              className="w-full pl-4.5 pr-14 py-3 bg-dark-950 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 text-sm focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 disabled:opacity-50 transition-all"
            />
            <button
              type="submit"
              disabled={!question.trim() || isQuerying}
              className="absolute right-2.5 top-2 p-1.5 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 disabled:opacity-40 text-white rounded-lg transition-all"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>

      {/* ── Right Panel: Citations Snippets Panel (30% width) ── */}
      {rightPanelOpen && (
        <div className="w-80 md:w-96 h-full flex-shrink-0 border-l border-dark-800/80 bg-dark-900">
          <CitationPreviewPanel
            citations={getLatestCitations()}
            selectedCitation={selectedCitation}
            onClose={() => setRightPanelOpen(false)}
            onSelectCitation={(cite) => setSelectedCitation(cite)}
          />
        </div>
      )}
    </div>
  );
};
