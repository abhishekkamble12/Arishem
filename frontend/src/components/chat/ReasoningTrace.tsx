import React, { useState } from 'react';
import { ReasoningStep } from '../../api/ai';
import { ChevronDown, ChevronUp, GitBranch, ShieldCheck, AlertTriangle, Layers, CheckCircle2 } from 'lucide-react';

interface ReasoningTraceProps {
  steps?: ReasoningStep[];
  critiqueVerdict?: string;
  agenticMode?: boolean;
}

export const ReasoningTrace: React.FC<ReasoningTraceProps> = ({
  steps = [],
  critiqueVerdict,
  agenticMode,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="mt-3 border border-dark-800/80 bg-dark-900/60 rounded-xl overflow-hidden text-xs">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3.5 py-2 hover:bg-dark-800/40 transition-colors text-left"
      >
        <div className="flex items-center space-x-2">
          <div className="w-5 h-5 rounded bg-brand-500/10 flex items-center justify-center text-brand-400">
            <GitBranch className="w-3 h-3" />
          </div>
          <span className="font-medium text-dark-200">
            Agentic Reasoning Trace ({steps.length} {steps.length === 1 ? 'step' : 'steps'})
          </span>
          {critiqueVerdict && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono uppercase font-semibold ${
                critiqueVerdict === 'PASSED'
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : critiqueVerdict === 'REVISED'
                  ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                  : 'bg-dark-800 text-dark-400'
              }`}
            >
              Critique: {critiqueVerdict}
            </span>
          )}
        </div>
        <div className="text-dark-400">
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {isOpen && (
        <div className="px-3.5 pb-3 pt-1 border-t border-dark-800/60 space-y-2.5 bg-dark-950/40">
          {steps.map((step, idx) => (
            <div key={idx} className="p-2.5 rounded-lg bg-dark-900/80 border border-dark-800/50">
              <div className="flex items-center justify-between text-dark-300 font-mono text-[11px] mb-1.5">
                <span className="capitalize font-semibold text-brand-400">
                  Phase {idx + 1}: {step.phase.replace('_', ' ')}
                </span>
                {step.total_unique_chunks !== undefined && (
                  <span className="text-dark-500">{step.total_unique_chunks} chunks retrieved</span>
                )}
              </div>

              {step.sub_queries && step.sub_queries.length > 0 && (
                <div className="mt-1 space-y-1">
                  <span className="text-[10px] text-dark-400 uppercase tracking-wider block">
                    Decomposed Sub-queries:
                  </span>
                  <ul className="list-disc list-inside text-dark-300 text-[11px] space-y-0.5 pl-1">
                    {step.sub_queries.map((sq, sqIdx) => (
                      <li key={sqIdx} className="font-mono text-dark-200">{sq}</li>
                    ))}
                  </ul>
                </div>
              )}

              {step.verdict && (
                <div className="mt-1 text-[11px] flex items-center space-x-1.5">
                  <span className="text-dark-400">Self-Critique Verdict:</span>
                  <span className="font-mono font-semibold text-emerald-400">{step.verdict}</span>
                </div>
              )}

              {step.unsupported_claims && step.unsupported_claims.length > 0 && (
                <div className="mt-1.5 p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[11px]">
                  <span className="font-semibold block mb-0.5">Critique Flagged Unsupported Claims:</span>
                  <ul className="list-disc list-inside space-y-0.5 text-amber-200/90">
                    {step.unsupported_claims.map((claim, cIdx) => (
                      <li key={cIdx}>{claim}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
