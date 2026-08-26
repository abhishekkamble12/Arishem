import React from 'react';
import { HelpCircle, Sparkles, ArrowRight, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';

interface OODMessageCardProps {
  query?: string;
  confidence?: number;
  onTryExample?: (example: string) => void;
}

export const OODMessageCard: React.FC<OODMessageCardProps> = ({
  confidence,
}) => {
  return (
    <div className="rounded-xl border border-dark-700/60 bg-dark-900/40 p-4 my-2 text-dark-200">
      <div className="flex items-start space-x-3">
        <div className="w-8 h-8 rounded-lg bg-dark-800 border border-dark-700 flex items-center justify-center flex-shrink-0 text-amber-400">
          <HelpCircle className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center space-x-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-dark-300">
              Out-of-Domain Query Filtered
            </h4>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-dark-800 text-amber-400 border border-dark-700">
              Score: {confidence !== undefined ? confidence.toFixed(2) : '< 0.35'}
            </span>
          </div>

          <p className="text-sm text-dark-300 mt-1.5 leading-relaxed">
            I couldn't find a strong match in your uploaded knowledge base. To save LLM generation costs and prevent hallucinations, synthesis was short-circuited.
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-3 pt-3 border-t border-dark-800/60">
            <Link
              to="/documents"
              className="inline-flex items-center space-x-1.5 text-xs text-brand-400 hover:text-brand-300 font-medium transition-colors"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Upload relevant documents</span>
            </Link>
            <span className="text-dark-600 text-xs">•</span>
            <span className="text-xs text-dark-400">
              Try rephrasing with specific keywords from your documents
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
