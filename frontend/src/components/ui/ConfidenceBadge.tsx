import React from 'react';

interface ConfidenceBadgeProps {
    confidence?: number;
    llm_confidence?: number;
}

function getConfidenceClass(value: number): string {
    if (value >= 0.8) return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
    if (value >= 0.5) return 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
    return 'bg-red-500/10 text-red-400 border border-red-500/20';
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ confidence, llm_confidence }) => {
    // Return null if both are undefined
    if (confidence === undefined && llm_confidence === undefined) {
        return null;
    }

    const showWarning =
        (confidence !== undefined && confidence < 0.5) &&
        (llm_confidence !== undefined && llm_confidence < 0.5);

    return (
        <div className="flex flex-wrap items-center gap-2 mt-1">
            {confidence !== undefined && (
                <span className={`text-xs px-2 py-0.5 rounded-full ${getConfidenceClass(confidence)}`}>
                    Retrieval: {Math.round(confidence * 100)}%
                </span>
            )}
            {llm_confidence !== undefined && (
                <span className={`text-xs px-2 py-0.5 rounded-full ${getConfidenceClass(llm_confidence)}`}>
                    LLM: {Math.round(llm_confidence * 100)}%
                </span>
            )}
            {showWarning && (
                <span className="text-xs text-amber-400">⚠ Possible out-of-domain response</span>
            )}
        </div>
    );
};