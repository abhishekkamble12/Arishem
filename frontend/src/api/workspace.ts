import { apiClient } from './client';

export interface Workspace {
    id: number;
    name: string;
    created_at: string;
}

export const workspaceApi = {
    listWorkspaces: async (): Promise<Workspace[]> => {
        const response = await apiClient.get<Workspace[]>('/auth/workspaces');
        return response.data;
    },
};
