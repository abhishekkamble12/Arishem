import { useState, useEffect, useCallback, useRef } from 'react';
import { aiApi, IngestedFile } from '../api/ai';
import { useAuthStore } from '../store/authStore';
import { apiErrorMessage } from '../api/client';

export interface UseDocumentsResult {
  files: IngestedFile[];
  isLoading: boolean;
  isPolling: boolean;
  error: string | null;
  hasActiveJobs: boolean;
  activeJobsCount: number;
  refetch: () => Promise<void>;
  deleteFile: (fileId: number) => Promise<void>;
}

export function useDocuments(pollIntervalMs: number = 2500): UseDocumentsResult {
  const { activeWorkspaceId } = useAuthStore();
  const [files, setFiles] = useState<IngestedFile[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const isMountedRef = useRef(true);
  const activeWorkspaceRef = useRef(activeWorkspaceId);
  activeWorkspaceRef.current = activeWorkspaceId;

  const fetchFiles = useCallback(async (isBackground = false) => {
    if (!activeWorkspaceRef.current) {
      setFiles([]);
      setIsLoading(false);
      return;
    }

    if (!isBackground) {
      setIsLoading(true);
    } else {
      setIsPolling(true);
    }

    try {
      const resp = await aiApi.listFiles(activeWorkspaceRef.current);
      if (isMountedRef.current) {
        setFiles(resp.files || []);
        setError(null);
      }
    } catch (err) {
      if (isMountedRef.current) {
        const msg = apiErrorMessage(err, 'Failed to load documents');
        if (!isBackground) setError(msg);
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
        setIsPolling(false);
      }
    }
  }, []);

  // Initial load
  useEffect(() => {
    isMountedRef.current = true;
    fetchFiles(false);

    return () => {
      isMountedRef.current = false;
    };
  }, [activeWorkspaceId, fetchFiles]);

  // Determine if there are active ingestion jobs (pending / processing)
  const activeJobs = files.filter(f => {
    const s = (f.status || '').toLowerCase();
    return s === 'pending' || s === 'processing' || s === 'queued';
  });
  const hasActiveJobs = activeJobs.length > 0;

  // Poll while there are active jobs
  useEffect(() => {
    if (!hasActiveJobs || !activeWorkspaceId) return;

    const timer = setInterval(() => {
      fetchFiles(true);
    }, pollIntervalMs);

    return () => clearInterval(timer);
  }, [hasActiveJobs, activeWorkspaceId, pollIntervalMs, fetchFiles]);

  const deleteFile = async (fileId: number) => {
    await aiApi.deleteFile(fileId);
    await fetchFiles(false);
  };

  return {
    files,
    isLoading,
    isPolling,
    error,
    hasActiveJobs,
    activeJobsCount: activeJobs.length,
    refetch: () => fetchFiles(false),
    deleteFile,
  };
}
