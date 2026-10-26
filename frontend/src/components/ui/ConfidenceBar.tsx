import React from 'react';
import { ShieldCheck, AlertCircle, CheckCircle2 } from 'lucide-react';

interface ConfidenceBarProps {
  score?: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

export const ConfidenceBar: React.FC<ConfidenceBarProps> = ({
  score = 0,
  showLabel = true,
  className = '',
}) => {
  const percentage = Math.min(100, Math.max(0, Math.round(score * 100)));

  // The score is the mean cosine similarity of the retrieved chunks, not a
  // probability. Bands come from the evaluation's answerable questions
  // (evals/golden_set.json, 53 questions): Q1 0.31, median 0.37, Q3 0.45. The old
  // bands (red below 0.35) dated from a retired embedding model and labelled 20
  // of those 53 correct answers "Low Match". Weak is amber, not red: anything
  // shown here has already cleared the refusal threshold.
  let label = 'Weak match';
  let barColor = 'bg-amber-500';
  let textColor = 'text-amber-400';
  let bgColor = 'bg-amber-500/10 border-amber-500/20';
  let Icon = AlertCircle;

  if (score >= 0.45) {
    label = 'Strong match';
    barColor = 'bg-emerald-400';
    textColor = 'text-emerald-400';
    bgColor = 'bg-emerald-500/10 border-emerald-500/20';
    Icon = ShieldCheck;
  } else if (score >= 0.30) {
    label = 'Typical match';
    barColor = 'bg-brand-400';
    textColor = 'text-brand-300';
    bgColor = 'bg-brand-500/10 border-brand-500/20';
    Icon = CheckCircle2;
  }

  return (
    <div className={`inline-flex items-center space-x-2.5 px-2.5 py-1 rounded-lg border text-xs ${bgColor} ${className}`}>
      <Icon className={`w-3.5 h-3.5 ${textColor} flex-shrink-0`} />
      
      {/* Progress Bar Track */}
      <div className="w-14 h-1.5 bg-dark-800/80 rounded-full overflow-hidden flex-shrink-0">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${percentage}%` }}
        />
      </div>

      {/* Monospace score & label */}
      <span className={`font-mono font-semibold text-[11px] ${textColor}`}>
        {(score).toFixed(2)}
      </span>

      {showLabel && (
        <span className="text-[10px] text-dark-400 font-medium hidden sm:inline">
          ({label})
        </span>
      )}
    </div>
  );
};
