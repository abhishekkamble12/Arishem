import { apiClient } from './client';

export interface IngestedFile {
  id: number;
  s3_key: string;
  file_type: string;
  chunks_stored: number;
  ingested_at: string;
  uploaded_by__email: string;
}

export interface ListFilesResponse {
  files: IngestedFile[];
  total: number;
}

export interface QueryResponse {
  answer: string;
  sources: string[];
  chunks: number;
}

export interface UploadResponse {
  message: string;
  s3_key: string;
  file_type: string;
  chunks_stored: number;
  uploaded_by: string;
}

export const aiApi = {
  // Ingest a file that already exists in S3 by key
  upload: async (s3Key: string): Promise<UploadResponse> => {
    const response = await apiClient.post<UploadResponse>('/ai/upload', {
      s3_key: s3Key,
    });
    return response.data;
  },

  // Upload a local file directly — backend saves to S3 then ingests
  uploadDirect: async (file: File): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<UploadResponse>('/ai/upload-direct', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  query: async (question: string, topK?: number): Promise<QueryResponse> => {
    const payload: Record<string, unknown> = { question };
    if (topK !== undefined) payload.top_k = topK;
    const response = await apiClient.post<QueryResponse>('/ai/query', payload);
    return response.data;
  },

  listFiles: async (): Promise<ListFilesResponse> => {
    const response = await apiClient.get<ListFilesResponse>('/ai/files');
    return response.data;
  },

  deleteFile: async (s3Key: string): Promise<{ message: string }> => {
    const response = await apiClient.delete<{ message: string }>('/ai/files/delete', {
      data: { s3_key: s3Key },
    });
    return response.data;
  },
};
