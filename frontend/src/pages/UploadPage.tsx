import React, { useState, useRef } from 'react';
import { aiApi } from '../api/ai';
import { useAuthStore } from '../store/authStore';
import { Upload, HelpCircle, CheckCircle, AlertCircle, FileText, Film, Loader2, CloudUpload, Link as LinkIcon } from 'lucide-react';

type UploadMode = 'direct' | 's3key';

const ACCEPTED = '.pdf,.docx,.pptx,.mp4,.mov,.avi,.mkv,.mp3,.wav,.flac,.ogg,.m4a';

export const UploadPage: React.FC = () => {
  const { activeWorkspaceId } = useAuthStore();
  const [mode, setMode] = useState<UploadMode>('direct');

  // Direct upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // S3 key state
  const [s3Key, setS3Key] = useState('');

  // Shared state
  const [loading, setLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [result, setResult] = useState<{ message: string; s3Key: string; taskId: string; fileId: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

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
      setErrorMsg('No active workspace selected. Please select a workspace first.');
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
    } catch (err: any) {
      setUploadStatus('error');
      const code = err.response?.status;
      let text = err.response?.data?.error || 'An unexpected error occurred.';
      if (code === 409) text = 'This file has already been ingested. Delete it first to re-ingest.';
      else if (code === 415) text = 'Unsupported file type. See the supported formats list on the right.';
      else if (code === 502) text = 'Failed to reach S3 or Bedrock. Check your AWS credentials and bucket name.';
      setErrorMsg(text);
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = mode === 'direct' ? !!selectedFile : !!s3Key.trim();

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 animate-slide-up">
      <div className="mb-8">
        <h1 className="text-3xl font-extrabold tracking-tight text-white">Upload & Ingest</h1>
        <p className="text-dark-400 mt-1">Add files to your RAG knowledge base</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* Form */}
        <div className="md:col-span-2 space-y-6">

          {/* Mode toggle */}
          <div className="flex space-x-1 bg-dark-900/60 p-1 rounded-xl border border-dark-800/40">
            <button
              type="button"
              onClick={() => { setMode('direct'); reset(); }}
              className={`flex-1 flex items-center justify-center space-x-2 py-2.5 rounded-lg text-sm font-medium transition-all ${mode === 'direct' ? 'bg-brand-600 text-white shadow-md' : 'text-dark-400 hover:text-dark-100'
                }`}
            >
              <CloudUpload className="w-4 h-4" />
              <span>Upload File Directly</span>
            </button>
            <button
              type="button"
              onClick={() => { setMode('s3key'); reset(); }}
              className={`flex-1 flex items-center justify-center space-x-2 py-2.5 rounded-lg text-sm font-medium transition-all ${mode === 's3key' ? 'bg-brand-600 text-white shadow-md' : 'text-dark-400 hover:text-dark-100'
                }`}
            >
              <LinkIcon className="w-4 h-4" />
              <span>Use S3 Key</span>
            </button>
          </div>

          <div className="glass-panel rounded-2xl p-8 shadow-xl">
            <form onSubmit={handleSubmit} className="space-y-6">

              {/* Result alerts */}
              {uploadStatus === 'success' && result && (
                <div className="flex items-start space-x-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 p-4 rounded-xl text-sm animate-fade-in">
                  <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-emerald-300">Ingestion Queued</h4>
                    <p className="mt-1 text-xs text-emerald-400/80">{result.s3Key}</p>
                    <p className="mt-2.5 text-xs text-dark-300 leading-relaxed">
                      The file has been queued for ingestion in the background (Task ID: <code className="text-brand-400 font-mono">{result.taskId.substring(0, 8)}...</code>).
                      You can monitor its status under the "Files" tab on the <strong>Dashboard</strong>.
                    </p>
                  </div>
                </div>
              )}

              {uploadStatus === 'error' && errorMsg && (
                <div className="flex items-start space-x-3 bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-xl text-sm animate-fade-in">
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-red-300">Ingestion Failed</h4>
                    <p className="mt-1 leading-relaxed">{errorMsg}</p>
                  </div>
                </div>
              )}

              {/* Direct upload: drag & drop zone */}
              {mode === 'direct' && (
                <div
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`cursor-pointer border-2 border-dashed rounded-xl p-8 text-center transition-all duration-200 ${dragging
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
                      <p className="text-sm font-bold text-white">{selectedFile.name}</p>
                      <p className="text-xs text-dark-400">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</p>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setSelectedFile(null); }}
                        className="text-xs text-dark-500 hover:text-red-400 underline mt-1"
                      >
                        Remove
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <CloudUpload className="w-8 h-8 text-dark-500 mx-auto" />
                      <p className="text-sm text-dark-300 font-medium">Drop a file here or click to browse</p>
                      <p className="text-xs text-dark-500">PDF, DOCX, PPTX, MP4, MP3 and more</p>
                    </div>
                  )}
                </div>
              )}

              {/* S3 key mode */}
              {mode === 's3key' && (
                <div className="space-y-2">
                  <label htmlFor="s3_key" className="text-sm font-semibold text-dark-200 block">
                    S3 Object Key
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-dark-500">
                      <Upload className="w-5 h-5" />
                    </div>
                    <input
                      id="s3_key"
                      type="text"
                      required
                      disabled={loading}
                      placeholder="documents/financial_report_q1.pdf"
                      value={s3Key}
                      onChange={(e) => setS3Key(e.target.value)}
                      className="w-full pl-11 pr-4 py-3 bg-dark-900/60 border border-dark-800 rounded-xl text-dark-100 placeholder-dark-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all"
                    />
                  </div>
                  <p className="text-xs text-dark-500 flex items-center gap-1.5">
                    <HelpCircle className="w-3.5 h-3.5" />
                    File must already exist in S3 bucket: <code className="text-brand-400">abhis3buck</code>
                  </p>
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !canSubmit}
                className="w-full py-3.5 px-4 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-semibold rounded-xl transition-all flex items-center justify-center space-x-2 shadow-lg shadow-brand-600/35"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Ingesting & Embedding...</span>
                  </>
                ) : (
                  <>
                    <Upload className="w-5 h-5" />
                    <span>Start Ingestion</span>
                  </>
                )}
              </button>
            </form>
          </div>

          {loading && (
            <div className="glass-panel rounded-2xl p-6 shadow-md border-l-2 border-l-brand-500 animate-pulse-subtle flex items-start space-x-4">
              <Loader2 className="w-6 h-6 text-brand-400 animate-spin flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="font-bold text-white text-sm">Ingestion in Progress</h4>
                <p className="text-xs text-dark-400 mt-1 leading-relaxed">
                  Downloading from S3 → extracting text → splitting into chunks → embedding with Bedrock → indexing in Qdrant.
                  Audio/video transcription can take 5–10 minutes. Don't close this tab.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Info sidebar */}
        <div className="md:col-span-1 space-y-6">
          <div className="glass-panel rounded-2xl p-6 shadow-md space-y-4">
            <h3 className="font-bold text-white text-sm border-b border-dark-800/60 pb-2">Supported Types</h3>
            <div className="space-y-3">
              <div className="flex items-start space-x-2.5">
                <FileText className="w-4 h-4 text-brand-400 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-bold text-dark-200">Documents</h4>
                  <p className="text-[11px] text-dark-400 mt-0.5">PDF, DOCX, PPTX</p>
                </div>
              </div>
              <div className="flex items-start space-x-2.5">
                <Film className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-bold text-dark-200">Audio & Video</h4>
                  <p className="text-[11px] text-dark-400 mt-0.5">MP4, MOV, AVI, MKV, MP3, WAV, FLAC, OGG, M4A</p>
                </div>
              </div>
            </div>
          </div>

          <div className="glass-panel rounded-2xl p-6 shadow-md border-l-2 border-l-amber-500 flex items-start space-x-3.5">
            <AlertCircle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-bold text-amber-400 text-sm">How it works</h4>
              <p className="text-xs text-dark-300 mt-1 leading-relaxed">
                <strong className="text-white">Direct upload</strong> — your file is sent to the server and saved to S3 automatically under <code className="text-brand-400">uploads/</code>.<br /><br />
                <strong className="text-white">S3 key</strong> — the file must already be in your bucket at the path you enter.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
