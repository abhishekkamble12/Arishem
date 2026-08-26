import React, { useState, useRef } from 'react';
import { useAuthStore } from '../store/authStore';
import { useDocuments } from '../hooks/useDocuments';
import { aiApi } from '../api/ai';
import {
  Upload, HelpCircle, CheckCircle, AlertCircle, FileText, Film, Loader2,
  CloudUpload, Link as LinkIcon, Trash2, RefreshCw, Layers, ShieldCheck, Database
} from 'lucide-react';

type UploadMode = 'direct' | 's3key';
const ACCEPTED = '.pdf,.docx,.pptx,.mp4,.mov,.avi,.mkv,.mp3,.wav,.flac,.ogg,.m4a';

export const DocumentsPage: React.FC = () => {
  const { activeWorkspaceId, user } = useAuthStore();
  const { files, isLoading, isPolling, error: pollError, refetch, deleteFile } = useDocuments();

  const [mode, setMode] = useState<UploadMode>('direct');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [s3Key, setS3Key] = useState('');

  const [loading, setLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [result, setResult] = useState<{ message: string; s3Key: string; taskId: string; fileId: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const clearInputs = () => {
    setSelectedFile(null);
    setS3Key('');
  };

  const reset = () => {
    clearInputs();
    setUploadStatus('idle');
    setResult(null);
    setErrorMsg(null);
  };

  const handleDeleteFile = async (key: string) => {
    if (!confirm(`Remove "${key.split('/').pop()}" from the knowledge base?`)) return;
    setDeletingKey(key);
    setDeleteError(null);
    try {
      await deleteFile(key);
    } catch (err: any) {
      setDeleteError(err.response?.data?.error || 'Delete failed');
    } finally {
      setDeletingKey(null);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) setSelectedFile(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setUploadStatus('idle');
    setErrorMsg(null);
    setResult(null);

    if (!activeWorkspaceId) {
      setErrorMsg('No active workspace selected.');
      setUploadStatus('error');
      setLoading(false);
      return;
    }

    try {
      let response;
      if (mode === 'direct') {
        if (!selectedFile) return;
        response = await aiApi.uploadDirect(selectedFile, activeWorkspaceId);
      } else {
        if (!s3Key.trim()) return;
        response = await aiApi.upload(s3Key.trim(), activeWorkspaceId);
      }
      setResult({
        message: response.message,
        s3Key: response.file.s3_key,
        taskId: response.task_id,
        fileId: response.file.id,
      });
      setUploadStatus('success');
      clearInputs();
      refetch();
    } catch (err: any) {
      setUploadStatus('error');
      const code = err.response?.status;
      let text = err.response?.data?.error || 'An unexpected error occurred.';
      if (code === 409) text = 'This file has already been ingested. Delete it first to re-ingest.';
      else if (code === 415) text = 'Unsupported file type.';
      else if (code === 502) text = 'Failed to reach S3 or Bedrock. Verify your credentials.';
      else if (code === 503) text = 'Ingestion queue is full. Please try again shortly.';
      setErrorMsg(text);
    } finally {
      setLoading(false);
    }
  };

  const getFileBasename = (key: string) => key.split('/').pop() || key;

  const canSubmit = mode === 'direct' ? !!selectedFile : !!s3Key.trim();
  const canDelete = user?.role === 'admin' || user?.role === 'editor';

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 animate-slide-up space-y-8">
      {/* Page Title */}
      <div className="flex items-center justify-between border-b border-dark-800/60 pb-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Documents Ingestion</h1>
          <p className="text-xs text-dark-400 mt-1">Upload directly or link S3 buckets to build RAG vector embeddings</p>
        </div>
        <button
          onClick={refetch}
          disabled={isLoading || isPolling}
          className="flex items-center space-x-1.5 px-3 py-1.5 text-xs text-dark-350 hover:text-white bg-dark-900 border border-dark-800 hover:border-dark-700 rounded-lg transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading || isPolling ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Main Content Split */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Left: Upload & Links Form (40% width) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="flex space-x-1 bg-dark-900/60 p-1 rounded-xl border border-dark-800/40">
            <button
              type="button"
              onClick={() => { setMode('direct'); reset(); }}
              className={`flex-1 flex items-center justify-center space-x-2 py-2 rounded-lg text-xs font-semibold transition-all ${
                mode === 'direct' ? 'bg-brand-600 text-white shadow-md' : 'text-dark-400 hover:text-dark-100'
              }`}
            >
              <CloudUpload className="w-3.5 h-3.5" />
              <span>Direct Upload</span>
            </button>
            <button
              type="button"
              onClick={() => { setMode('s3key'); reset(); }}
              className={`flex-1 flex items-center justify-center space-x-2 py-2 rounded-lg text-xs font-semibold transition-all ${
                mode === 's3key' ? 'bg-brand-600 text-white shadow-md' : 'text-dark-400 hover:text-dark-100'
              }`}
            >
              <LinkIcon className="w-3.5 h-3.5" />
              <span>S3 Object Key</span>
            </button>
          </div>

          <div className="glass-panel rounded-2xl p-6 shadow-xl">
            <form onSubmit={handleSubmit} className="space-y-5">
              {uploadStatus === 'success' && result && (
                <div className="flex items-start space-x-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 p-4 rounded-xl text-xs animate-fade-in">
                  <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-emerald-300">Ingestion Queued</h4>
                    <p className="mt-1 font-mono text-[10px] break-all">{result.s3Key}</p>
                    <p className="mt-2 text-dark-300 leading-relaxed">
                      Your document is processing in the background (Task ID: <code className="text-brand-400 font-mono">{result.taskId.substring(0, 8)}...</code>). Polling status is active.
                    </p>
                  </div>
                </div>
              )}

              {uploadStatus === 'error' && errorMsg && (
                <div className="flex items-start space-x-3 bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-xl text-xs animate-fade-in">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-red-300">Ingestion Failed</h4>
                    <p className="mt-1 leading-relaxed">{errorMsg}</p>
                  </div>
                </div>
              )}

              {mode === 'direct' ? (
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`cursor-pointer border-2 border-dashed rounded-xl p-8 text-center transition-all duration-200 ${
                    dragging
                      ? 'border-brand-500 bg-brand-500/5'
                      : selectedFile
                      ? 'border-emerald-500/50 bg-emerald-500/5'
                      : 'border-dark-700 hover:border-brand-500/50 hover:bg-dark-900/40'
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={ACCEPTED}
                    className="hidden"
                    onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  />
                  {selectedFile ? (
                    <div className="space-y-1">
                      <FileText className="w-8 h-8 text-emerald-400 mx-auto" />
                      <p className="text-xs font-bold text-white max-w-[250px] truncate mx-auto">{selectedFile.name}</p>
                      <p className="text-[10px] text-dark-400">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</p>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setSelectedFile(null); }}
                        className="text-[10px] text-dark-500 hover:text-red-400 underline mt-1"
                      >
                        Remove file
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <CloudUpload className="w-8 h-8 text-dark-500 mx-auto" />
                      <p className="text-xs text-dark-300 font-medium">Drop a file here or click to browse</p>
                      <p className="text-[10px] text-dark-500">PDF, DOCX, PPTX, MP4, MP3 up to 100MB</p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <label htmlFor="s3_key" className="text-xs font-semibold text-dark-200 uppercase tracking-wider block">
                    S3 Object Key Path
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-dark-500">
                      <Database className="w-4 h-4" />
                    </div>
                    <input
                      id="s3_key"
                      type="text"
                      required
                      disabled={loading}
                      placeholder="e.g. docs/annual_report.pdf"
                      value={s3Key}
                      onChange={(e) => setS3Key(e.target.value)}
                      className="w-full pl-10 pr-4 py-2.5 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/25 text-sm transition-all"
                    />
                  </div>
                  <p className="text-[10px] text-dark-500 flex items-center gap-1">
                    <HelpCircle className="w-3.5 h-3.5" />
                    <span>Bucket location: <strong>abhis3buck</strong></span>
                  </p>
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !canSubmit}
                className="w-full py-3 px-4 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-semibold rounded-xl text-xs transition-all flex items-center justify-center space-x-2 shadow-lg shadow-brand-600/35"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Processing vectors...</span>
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4" />
                    <span>Ingest File</span>
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right: Files Status List (60% width) */}
        <div className="lg:col-span-7 space-y-6">
          <div className="glass-panel rounded-2xl p-5 border border-dark-800/80">
            <h3 className="text-sm font-bold text-white mb-4 flex items-center justify-between">
              <span>Workspace Index ({files.length} items)</span>
              {isPolling && (
                <span className="text-[10px] bg-brand-500/10 border border-brand-500/20 text-brand-400 font-mono px-2 py-0.5 rounded-full animate-pulse flex items-center space-x-1.5">
                  <span className="w-1.5 h-1.5 bg-brand-500 rounded-full animate-ping" />
                  <span>Polling status live</span>
                </span>
              )}
            </h3>

            {deleteError && (
              <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 px-3 py-2 rounded-lg mb-3">
                {deleteError}
              </p>
            )}

            {isLoading ? (
              <div className="py-12 text-center text-xs text-dark-500">
                <Loader2 className="w-6 h-6 text-brand-500 animate-spin mx-auto mb-2" />
                Loading workspace index...
              </div>
            ) : files.length === 0 ? (
              <div className="py-12 text-center text-xs text-dark-500">
                No documents found. Start by uploading a document.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="text-dark-500 uppercase tracking-wider font-semibold border-b border-dark-800/60 pb-2">
                      <th className="pb-2">Name</th>
                      <th className="pb-2">Chunks</th>
                      <th className="pb-2">Status</th>
                      <th className="pb-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {files.map((file) => {
                      const isDeleting = deletingKey === file.s3_key;
                      const status = (file.status || '').toLowerCase();
                      const basename = getFileBasename(file.s3_key);

                      return (
                        <tr key={file.id} className="border-b border-dark-800/40 hover:bg-dark-900/10">
                          <td className="py-3 font-semibold text-white max-w-[220px] truncate" title={file.s3_key}>
                            {basename}
                          </td>
                          <td className="py-3 font-mono text-dark-300">{file.chunks_stored}</td>
                          <td className="py-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[9px] font-bold border uppercase tracking-wider ${
                                status === 'success' || status === 'completed'
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                  : status === 'failed'
                                  ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                                  : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                              }`}
                            >
                              {file.status}
                            </span>
                          </td>
                          <td className="py-3">
                            {canDelete && (
                              <button
                                onClick={() => handleDeleteFile(file.s3_key)}
                                disabled={isDeleting}
                                className="p-1.5 text-dark-400 hover:text-red-400 disabled:opacity-40 rounded-lg hover:bg-red-500/10 transition-colors"
                                title="Delete from knowledge base"
                              >
                                {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
};
