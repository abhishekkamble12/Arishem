import { apiClient } from './client';

export interface IngestedFile {
  id: number;
  s3_key: string;
  file_type: string;
  chunks_stored: number;
  status: string;
  error_message?: string;
  ingested_at: string;
  uploaded_by__email: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: string;
  error?: string;
  result?: any;
}

export interface ListFilesResponse {
  files: IngestedFile[];
  total: number;
}

export interface QueryResponse {
  answer: string;
  sources: string[];
  chunks: number;
  citations?: { source: string; snippet: string }[];
  unverified?: string;
  confidence?: number;
  llm_confidence?: number;
}

export interface UploadResponse {
  message: string;
  task_id: string;
  file: {
    id: number;
    s3_key: string;
    file_type: string;
    status: string;
    chunks_stored: number;
  };
}

export const aiApi = {
  // Ingest a file that already exists in S3 by key
  upload: async (s3Key: string, workspaceId: number): Promise<UploadResponse> => {
    const response = await apiClient.post<UploadResponse>('/ai/upload', {
      s3_key: s3Key,
      workspace_id: workspaceId,
    });
    return response.data;
  },

  // Upload a local file directly — backend saves to S3 then ingests
  uploadDirect: async (file: File, workspaceId: number): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('workspace_id', workspaceId.toString());
    const response = await apiClient.post<UploadResponse>('/ai/upload-direct', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  query: async (question: string, workspaceId: number, topK?: number): Promise<QueryResponse> => {
    const payload: Record<string, unknown> = { question, workspace_id: workspaceId };
    if (topK !== undefined) payload.top_k = topK;
    const response = await apiClient.post<QueryResponse>('/ai/query', payload);
    return response.data;
  },

  listFiles: async (workspaceId: number): Promise<ListFilesResponse> => {
    const response = await apiClient.get<ListFilesResponse>('/ai/files', {
      params: { workspace_id: workspaceId },
    });
    return response.data;
  },

  checkTaskStatus: async (taskId: string): Promise<TaskStatusResponse> => {
    const response = await apiClient.get<TaskStatusResponse>(`/ai/tasks/${taskId}`);
    return response.data;
  },

  deleteFile: async (s3Key: string): Promise<{ message: string }> => {
    const response = await apiClient.delete<{ message: string }>('/ai/files/delete', {
      data: { s3_key: s3Key },
    });
    return response.data;
  },
};
