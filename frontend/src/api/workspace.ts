import { apiClient } from './client';

export type Role = 'admin' | 'editor' | 'viewer';

export interface Workspace {
    id: number;
    name: string;
    created_at: string;
    role: Role;
}

export interface Member {
    id: number;
    email: string;
    role: Role;
    created_at: string;
}

export const workspaceApi = {
    listWorkspaces: async (): Promise<Workspace[]> => {
        const response = await apiClient.get<Workspace[]>('/auth/workspaces');
        return response.data;
    },

    createWorkspace: async (name: string): Promise<Workspace> => {
        const response = await apiClient.post<Workspace>('/auth/workspaces', { name });
        return response.data;
    },

    listMembers: async (workspaceId: number): Promise<Member[]> => {
        const response = await apiClient.get<Member[]>(`/auth/workspaces/${workspaceId}/members`);
        return response.data;
    },

    addMember: async (workspaceId: number, email: string, role: Role): Promise<Member> => {
        const response = await apiClient.post<Member>(`/auth/workspaces/${workspaceId}/members`, { email, role });
        return response.data;
    },

    setMemberRole: async (workspaceId: number, userId: number, role: Role): Promise<Member> => {
        const response = await apiClient.patch<Member>(`/auth/workspaces/${workspaceId}/members/${userId}`, { role });
        return response.data;
    },

    removeMember: async (workspaceId: number, userId: number): Promise<void> => {
        await apiClient.delete(`/auth/workspaces/${workspaceId}/members/${userId}`);
    },
};
