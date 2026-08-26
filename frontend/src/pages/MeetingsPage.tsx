import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { aiApi, IngestedFile } from '../api/ai';
import { 
  Video, 
  Youtube, 
  Sparkles, 
  FileText, 
  CheckSquare, 
  HelpCircle, 
  Award, 
  MessageSquare, 
  Send, 
  Loader2,
  RefreshCw,
  Clock
} from 'lucide-react';

interface MeetingAnalysis {
  file_id: number;
  title: string;
  summary: string;
  action_items: string[];
  key_decisions: string[];
  open_questions: string[];
  full_transcript: string;
  created_at: string;
}

export const MeetingsPage: React.FC = () => {
  const { activeWorkspaceId } = useAuthStore();
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [isIngesting, setIsIngesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [files, setFiles] = useState<IngestedFile[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null);

  const [analysis, setAnalysis] = useState<MeetingAnalysis | null>(null);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState(false);

  // Meeting Chat state
  const [chatQuestion, setChatQuestion] = useState('');
  const [chatHistory, setChatHistory] = useState<{ role: 'user' | 'assistant'; content: string }[]>([]);
  const [isAsking, setIsAsking] = useState(false);

  useEffect(() => {
    if (activeWorkspaceId) {
      fetchMeetingFiles();
    }
  }, [activeWorkspaceId]);

  const fetchMeetingFiles = async () => {
    if (!activeWorkspaceId) return;
    setIsLoadingFiles(true);
    try {
      const res = await aiApi.listFiles(activeWorkspaceId);
      setFiles(res.files || []);
      if (res.files && res.files.length > 0 && !selectedFileId) {
        handleSelectFile(res.files[0].id);
      }
    } catch (err: any) {
      console.error('Failed to fetch files:', err);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const handleSelectFile = async (fileId: number) => {
    setSelectedFileId(fileId);
    setAnalysis(null);
    setIsLoadingAnalysis(true);
    setChatHistory([]);
    try {
      const data = await aiApi.getMeetingAnalysis(fileId);
      setAnalysis(data);
    } catch (err: any) {
      console.log('No analysis found yet for this file or still processing.');
    } finally {
      setIsLoadingAnalysis(false);
    }
  };

  const handleIngestYoutube = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!youtubeUrl.trim() || !activeWorkspaceId) return;

    setIsIngesting(true);
    setError(null);
    setSuccess(null);

    try {
      const res = await aiApi.ingestYoutube(youtubeUrl, activeWorkspaceId);
      setSuccess(res.message || 'YouTube audio downloaded & ingested successfully!');
      setYoutubeUrl('');
      await fetchMeetingFiles();
      if (res.file_id) {
        handleSelectFile(res.file_id);
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to process YouTube URL');
    } finally {
      setIsIngesting(false);
    }
  };

  const handleAskQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatQuestion.trim() || !activeWorkspaceId) return;

    const userMessage = chatQuestion.trim();
    setChatQuestion('');
    setChatHistory(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsAsking(true);

    try {
      const res = await aiApi.query(userMessage, activeWorkspaceId);
      setChatHistory(prev => [...prev, { role: 'assistant', content: res.answer }]);
    } catch (err: any) {
      setChatHistory(prev => [
        ...prev, 
        { role: 'assistant', content: 'Sorry, I ran into an error while processing your query.' }
      ]);
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <Video className="w-8 h-8 text-brand-400" />
            Meeting Intelligence
          </h1>
          <p className="text-dark-400 text-sm mt-1">
            Transcribe YouTube & local recordings, generate auto-summaries, extract action items, and chat with meetings.
          </p>
        </div>
        <button
          onClick={fetchMeetingFiles}
          className="p-2 rounded-xl bg-dark-900 border border-dark-800 text-dark-300 hover:text-white hover:bg-dark-800 transition-all flex items-center gap-2 text-sm"
        >
          <RefreshCw className={`w-4 h-4 ${isLoadingFiles ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* YouTube Ingestion Form */}
      <div className="glass-panel p-6 rounded-2xl border border-dark-800/60 mb-8">
        <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
          <Youtube className="w-5 h-5 text-red-500" />
          Ingest YouTube Meeting / Webinar
        </h2>
        <form onSubmit={handleIngestYoutube} className="flex gap-4">
          <input
            type="url"
            value={youtubeUrl}
            onChange={(e) => setYoutubeUrl(e.target.value)}
            placeholder="Paste YouTube URL (e.g. https://www.youtube.com/watch?v=...)"
            className="flex-1 bg-dark-950 border border-dark-800 rounded-xl px-4 py-2.5 text-sm text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 transition-colors"
            required
          />
          <button
            type="submit"
            disabled={isIngesting}
            className="bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-medium px-6 py-2.5 rounded-xl shadow-lg shadow-brand-600/20 transition-all flex items-center gap-2 text-sm whitespace-nowrap"
          >
            {isIngesting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Transcribing & Analyzing...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Analyse Meeting
              </>
            )}
          </button>
        </form>

        {error && (
          <div className="mt-3 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}
        {success && (
          <div className="mt-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
            {success}
          </div>
        )}
      </div>

      {/* Main Grid: Left Files Sidebar | Right Analysis & Chat */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Meeting Files List */}
        <div className="lg:col-span-4 space-y-4">
          <div className="glass-panel p-5 rounded-2xl border border-dark-800/60">
            <h3 className="text-md font-semibold text-white mb-4 flex items-center gap-2">
              <FileText className="w-4 h-4 text-brand-400" />
              Ingested Recordings
            </h3>

            {isLoadingFiles ? (
              <div className="flex justify-center py-8 text-dark-400">
                <Loader2 className="w-6 h-6 animate-spin" />
              </div>
            ) : files.length === 0 ? (
              <div className="text-center py-8 text-dark-400 text-sm">
                No meeting files ingested yet. Ingest a YouTube URL or upload a file above.
              </div>
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
                {files.map((file) => {
                  const isSelected = selectedFileId === file.id;
                  return (
                    <button
                      key={file.id}
                      onClick={() => handleSelectFile(file.id)}
                      className={`w-full text-left p-3.5 rounded-xl border transition-all ${
                        isSelected
                          ? 'bg-brand-600/10 border-brand-500/40 text-white'
                          : 'bg-dark-900/40 border-dark-800/40 text-dark-300 hover:bg-dark-800/40 hover:text-white'
                      }`}
                    >
                      <div className="font-medium text-sm truncate">
                        {file.s3_key.split('/').pop()}
                      </div>
                      <div className="flex items-center justify-between text-xs text-dark-500 mt-2">
                        <span className="uppercase px-2 py-0.5 rounded bg-dark-950 border border-dark-800">
                          {file.file_type}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {new Date(file.ingested_at).toLocaleDateString()}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Structured Insights & Chat */}
        <div className="lg:col-span-8 space-y-6">
          {isLoadingAnalysis ? (
            <div className="glass-panel p-12 rounded-2xl border border-dark-800/60 flex flex-col items-center justify-center text-dark-400">
              <Loader2 className="w-8 h-8 animate-spin text-brand-400 mb-3" />
              <p className="text-sm">Running Map-Reduce Summarisation & Structured Extractions...</p>
            </div>
          ) : analysis ? (
            <>
              {/* Meeting Header & Executive Summary */}
              <div className="glass-panel p-6 rounded-2xl border border-dark-800/60">
                <h2 className="text-2xl font-bold text-white mb-3">
                  {analysis.title || 'Meeting Summary'}
                </h2>
                <div className="prose prose-invert max-w-none text-dark-200 text-sm leading-relaxed whitespace-pre-line">
                  {analysis.summary}
                </div>
              </div>

              {/* 3 Columns: Action Items | Key Decisions | Open Questions */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Action Items */}
                <div className="glass-panel p-4 rounded-xl border border-dark-800/60 bg-blue-950/10 border-blue-500/20">
                  <h4 className="text-sm font-semibold text-blue-400 mb-3 flex items-center gap-2">
                    <CheckSquare className="w-4 h-4" />
                    Action Items ({analysis.action_items.length})
                  </h4>
                  {analysis.action_items.length === 0 ? (
                    <p className="text-xs text-dark-500 italic">No explicit action items found.</p>
                  ) : (
                    <ul className="space-y-2">
                      {analysis.action_items.map((item, idx) => (
                        <li key={idx} className="text-xs text-dark-200 bg-dark-950/60 p-2 rounded-lg border border-dark-800">
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Key Decisions */}
                <div className="glass-panel p-4 rounded-xl border border-dark-800/60 bg-emerald-950/10 border-emerald-500/20">
                  <h4 className="text-sm font-semibold text-emerald-400 mb-3 flex items-center gap-2">
                    <Award className="w-4 h-4" />
                    Key Decisions ({analysis.key_decisions.length})
                  </h4>
                  {analysis.key_decisions.length === 0 ? (
                    <p className="text-xs text-dark-500 italic">No key decisions recorded.</p>
                  ) : (
                    <ul className="space-y-2">
                      {analysis.key_decisions.map((item, idx) => (
                        <li key={idx} className="text-xs text-dark-200 bg-dark-950/60 p-2 rounded-lg border border-dark-800">
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Open Questions */}
                <div className="glass-panel p-4 rounded-xl border border-dark-800/60 bg-amber-950/10 border-amber-500/20">
                  <h4 className="text-sm font-semibold text-amber-400 mb-3 flex items-center gap-2">
                    <HelpCircle className="w-4 h-4" />
                    Open Questions ({analysis.open_questions.length})
                  </h4>
                  {analysis.open_questions.length === 0 ? (
                    <p className="text-xs text-dark-500 italic">No open questions flagged.</p>
                  ) : (
                    <ul className="space-y-2">
                      {analysis.open_questions.map((item, idx) => (
                        <li key={idx} className="text-xs text-dark-200 bg-dark-950/60 p-2 rounded-lg border border-dark-800">
                          {item}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              {/* Interactive RAG Chat with the Meeting */}
              <div className="glass-panel p-6 rounded-2xl border border-dark-800/60">
                <h3 className="text-md font-semibold text-white mb-4 flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-brand-400" />
                  Chat with this Meeting
                </h3>

                {/* Chat History */}
                <div className="space-y-3 mb-4 max-h-[300px] overflow-y-auto pr-1">
                  {chatHistory.length === 0 ? (
                    <p className="text-xs text-dark-500 italic text-center py-4">
                      Ask any specific question about what was discussed in this meeting.
                    </p>
                  ) : (
                    chatHistory.map((msg, idx) => (
                      <div
                        key={idx}
                        className={`p-3 rounded-xl text-sm ${
                          msg.role === 'user'
                            ? 'bg-brand-600/20 text-brand-200 border border-brand-500/30 ml-8'
                            : 'bg-dark-900 text-dark-200 border border-dark-800 mr-8'
                        }`}
                      >
                        <span className="text-[10px] font-bold uppercase tracking-wider block text-dark-400 mb-1">
                          {msg.role === 'user' ? 'You' : 'AI Assistant'}
                        </span>
                        {msg.content}
                      </div>
                    ))
                  )}
                  {isAsking && (
                    <div className="flex items-center gap-2 text-xs text-dark-400 p-2">
                      <Loader2 className="w-4 h-4 animate-spin text-brand-400" />
                      Searching meeting vectors...
                    </div>
                  )}
                </div>

                {/* Chat Input */}
                <form onSubmit={handleAskQuestion} className="flex gap-3">
                  <input
                    type="text"
                    value={chatQuestion}
                    onChange={(e) => setChatQuestion(e.target.value)}
                    placeholder="e.g. What did the team decide about the launch date?"
                    className="flex-1 bg-dark-950 border border-dark-800 rounded-xl px-4 py-2 text-sm text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 transition-colors"
                  />
                  <button
                    type="submit"
                    disabled={isAsking || !chatQuestion.trim()}
                    className="bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white p-2.5 rounded-xl transition-all"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </form>
              </div>
            </>
          ) : (
            <div className="glass-panel p-12 rounded-2xl border border-dark-800/60 text-center text-dark-400">
              Select a meeting recording from the list on the left to view summary, action items, and key decisions.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
