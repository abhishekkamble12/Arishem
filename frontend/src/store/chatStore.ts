import { create } from 'zustand';
import { aiApi, IngestedFile, QueryResponse } from '../api/ai';
import { useAuthStore } from './authStore';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  chunks?: number;
  timestamp: string;
}

interface ChatState {
  messages: ChatMessage[];
  files: IngestedFile[];
  isQuerying: boolean;
  isFetchingFiles: boolean;
  error: string | null;
  fileSearchQuery: string;
  selectedSourceFilter: string | null;
  
  // Actions
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => void;
  clearHistory: () => void;
  askQuestion: (question: string, topK?: number) => Promise<void>;
  fetchFiles: () => Promise<void>;
  setFileSearchQuery: (query: string) => void;
  setSelectedSourceFilter: (source: string | null) => void;
}

export const useChatStore = create<ChatState>((set, get) => {
  // Load initial chat history from localStorage if present
  const storedHistory = localStorage.getItem('chat_history');
  let messages: ChatMessage[] = [];
  if (storedHistory) {
    try {
      messages = JSON.parse(storedHistory);
    } catch (e) {
      console.error('Failed to parse chat history', e);
    }
  }

  return {
    messages,
    files: [],
    isQuerying: false,
    isFetchingFiles: false,
    error: null,
    fileSearchQuery: '',
    selectedSourceFilter: null,

    addMessage: (msg: Omit<ChatMessage, 'id' | 'timestamp'>) => {
      const newMsg: ChatMessage = {
        ...msg,
        id: Math.random().toString(36).substring(2, 9),
        timestamp: new Date().toISOString(),
      };
      const newMessages = [...get().messages, newMsg];
      localStorage.setItem('chat_history', JSON.stringify(newMessages));
      set({ messages: newMessages });
    },

    clearHistory: () => {
      localStorage.removeItem('chat_history');
      set({ messages: [] });
    },

    askQuestion: async (question: string, topK?: number) => {
      // Add user message
      get().addMessage({ role: 'user', content: question });
      
      const workspaceId = useAuthStore.getState().activeWorkspaceId;
      if (!workspaceId) {
        get().addMessage({
          role: 'assistant',
          content: '⚠️ Error: No active workspace selected.',
        });
        return;
      }

      set({ isQuerying: true, error: null });
      try {
        const response: QueryResponse = await aiApi.query(question, workspaceId, topK);
        
        // Add Claude response
        get().addMessage({
          role: 'assistant',
          content: response.answer,
          sources: response.sources,
          chunks: response.chunks,
        });
      } catch (err: any) {
        const errMsg = err.response?.data?.error || err.message || 'Failed to query the AI agent';
        set({ error: errMsg });
        
        get().addMessage({
          role: 'assistant',
          content: `⚠️ Error: ${errMsg}. Please try again.`,
        });
      } finally {
        set({ isQuerying: false });
      }
    },

    fetchFiles: async () => {
      const workspaceId = useAuthStore.getState().activeWorkspaceId;
      if (!workspaceId) {
        set({ files: [], isFetchingFiles: false });
        return;
      }

      set({ isFetchingFiles: true });
      try {
        const response = await aiApi.listFiles(workspaceId);
        set({ files: response.files, error: null });
      } catch (err: any) {
        const errMsg = err.response?.data?.error || err.message || 'Failed to retrieve ingested files';
        set({ error: errMsg });
      } finally {
        set({ isFetchingFiles: false });
      }
    },

    setFileSearchQuery: (query: string) => set({ fileSearchQuery: query }),
    setSelectedSourceFilter: (source: string | null) => set({ selectedSourceFilter: source }),
  };
});
