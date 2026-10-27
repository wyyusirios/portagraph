/** Типизированный клиент REST API PortaGraph. Токен хранится в памяти вкладки. */

export type NodeType = 'SYSTEM' | 'REPOSITORY' | 'SERVICE' | 'MODULE' | 'CLASS' | 'FUNCTION' | 'ENTITY'
  | 'API_ENDPOINT' | 'DATABASE' | 'MESSAGE_QUEUE' | 'EXTERNAL_SYSTEM';

export interface GraphNode { id: string; type: NodeType; label: string; parentId: string | null }
export interface GraphEdge { id: string; source: string; target: string; type: string; confidence: number }
export interface GraphView { nodes: GraphNode[]; edges: GraphEdge[] }

export interface Project { id: number; name: string; description?: string; repositoryCount: number; createdAt: string }
export interface Citation { fileId: number; path: string; startLine: number; endLine: number }
export interface Answer { sessionId: number; messageId: number; text: string; citations: Citation[] }
export interface RunView { id: number; status: string; progress: number; error?: string; stats: Record<string, number> }

let token: string | null = null;
export const setToken = (t: string | null) => { token = t; };

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(body.message ?? `Ошибка ${res.status}`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  login: (email: string, password: string) =>
    request<{ accessToken: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  projects: () => request<Project[]>('/projects'),
  createProject: (name: string, description?: string) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify({ name, description }) }),
  connectRepositories: (projectId: number, urls: string[], accessToken: string) =>
    request<{ url: string; connected: boolean; message: string }[]>(`/projects/${projectId}/repositories`,
      { method: 'POST', body: JSON.stringify({ urls, accessToken }) }),
  runs: (projectId: number) => request<RunView[]>(`/projects/${projectId}/analysis`),
  graph: (projectId: number, mode: 'overview' | 'detailed') =>
    request<GraphView>(`/projects/${projectId}/graph?mode=${mode}`),
  ask: (projectId: number, question: string, sessionId?: number) =>
    request<Answer>(`/projects/${projectId}/assistant/ask`, { method: 'POST', body: JSON.stringify({ question, sessionId }) }),
  impact: (projectId: number, changeDescription: string, nodeIds: number[], depth = 3) =>
    request<{ risk: string; affected: { nodeId: number; name: string; distance: number; score: number }[]; recommendation: string }>(
      `/projects/${projectId}/impact`, { method: 'POST', body: JSON.stringify({ changeDescription, nodeIds, depth }) }),
};
