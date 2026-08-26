import React, { useEffect, useState } from 'react';
import { onToast, type ToastEvent } from '../../api/client';

export const Toast: React.FC = () => {
    const [toast, setToast] = useState<ToastEvent | null>(null);

    useEffect(() => {
        const unsubscribe = onToast((event) => {
            setToast(event);
            // Auto-dismiss after 5 seconds
            setTimeout(() => {
                setToast((current) => (current === event ? null : current));
            }, 5000);
        });

        return unsubscribe;
    }, []);

    if (!toast) return null;

    return (
        <div className="fixed bottom-4 right-4 z-50 animate-slide-up">
            <div className={`
        px-4 py-3 rounded-lg shadow-lg max-w-md
        ${toast.type === 'warning' ? 'bg-amber-500/20 border border-amber-500/40 text-amber-200' : ''}
        ${toast.type === 'error' ? 'bg-red-500/20 border border-red-500/40 text-red-200' : ''}
        ${toast.type === 'success' ? 'bg-emerald-500/20 border border-emerald-500/40 text-emerald-200' : ''}
      `}>
                <p className="text-sm">{toast.message}</p>
            </div>
        </div>
    );
};