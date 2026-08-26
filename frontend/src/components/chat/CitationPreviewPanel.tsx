import React from 'react';
import { X, FileText, Film, Music, CheckCircle, ExternalLink } from 'lucide-react';

interface Citation {
  source: string;
  snippet: string;
  score?: number;
}

interface CitationPreviewPanelProps {
  citations: Citation[];
  selectedCitation: Citation | null;
  onClose: () => void;
  onSelectCitation: (citation: Citation) => void;
}

export const CitationPreviewPanel: React.FC<CitationPreviewPanelProps> = ({
  citations,
  selectedCitation,
  onClose,
  onSelectCitation,
}) => {
  const getFileBasename = (path: string) => path.split('/').pop() || path;

  const getFileTypeIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (['mp4', 'mov', 'avi', 'mkv'].includes(ext || '')) {
      return <Film className="w-4 h-4 text-purple-400" />;
    }
    if (['mp3', 'wav', 'flac', 'ogg', 'm4a'].includes(ext || '')) {
      return <Music className="w-4 h-4 text-emerald-400" />;
    }
    return <FileText className="w-4 h-4 text-brand-400" />;
  };

  return (
    <div className="w-full h-full flex flex-col bg-dark-900 border-l border-dark-800/80 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-800/80 bg-dark-950/40">
        <div>
          <h3 className="text-sm font-semibold text-white">Sources used in answer</h3>
          <p className="text-[10px] text-dark-400 font-mono">
            {citations.length} document chunk{citations.length !== 1 ? 's' : ''} retrieved
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-lg text-dark-400 hover:text-white hover:bg-dark-800/60 transition-all"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {citations.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-dark-500 py-12">
            <FileText className="w-8 h-8 opacity-40 mb-2" />
            <p className="text-xs">No direct citations available</p>
          </div>
        ) : (
          citations.map((cite, index) => {
            const isSelected = selectedCitation?.snippet === cite.snippet;
            const basename = getFileBasename(cite.source);

            return (
              <div
                key={index}
                id={`citation-card-${index}`}
                onClick={() => onSelectCitation(cite)}
                className={`p-3.5 rounded-xl border text-xs cursor-pointer transition-all duration-200 select-none ${
                  isSelected
                    ? 'bg-brand-500/10 border-brand-500 shadow-md shadow-brand-500/5 ring-1 ring-brand-500'
                    : 'bg-dark-900/50 border-dark-800/70 hover:border-dark-700/80 hover:bg-dark-800/30'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center space-x-2 min-w-0">
                    <div className="p-1.5 rounded-lg bg-dark-950/80 border border-dark-800 flex-shrink-0">
                      {getFileTypeIcon(basename)}
                    </div>
                    <span className="font-semibold text-white truncate text-[11px]" title={cite.source}>
                      {basename}
                    </span>
                  </div>

                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-dark-950/80 border border-dark-800 text-brand-400 flex-shrink-0">
                    Chunk {index + 1}
                  </span>
                </div>

                <div className="bg-dark-950/80 border border-dark-800/50 rounded-lg p-2.5 font-mono text-[11px] leading-relaxed text-dark-200 overflow-x-auto select-text whitespace-pre-wrap">
                  {cite.snippet}
                </div>

                <div className="mt-2.5 flex items-center justify-between text-[10px] text-dark-400">
                  <div className="flex items-center space-x-1">
                    <CheckCircle className="w-3.5 h-3.5 text-brand-500" />
                    <span>Verified chunk reference</span>
                  </div>
                  <span className="font-mono text-dark-500">Source: S3 File Ingestion</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
