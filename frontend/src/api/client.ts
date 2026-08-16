import type { Attribute, AttributePatch, Project, ProjectAttribute, ProjectAttributeNode, ProjectAttributeStatus, ProjectPatch, Source, WorkspaceSnapshot } from '../domain'
import { createDemoApi } from './demo'

export interface OntologyApi {
  getWorkspace(): Promise<WorkspaceSnapshot>
  updateAttribute(id: string, patch: AttributePatch): Promise<Attribute>
  updateProject(projectId: string, patch: ProjectPatch): Promise<Project>
  updateProjectAttributeNode(projectId: string, attributeId: string, node: ProjectAttributeNode, status: ProjectAttributeStatus): Promise<ProjectAttribute>
  deleteAttribute(id: string): Promise<void>
  syncSources(): Promise<Source[]>
}

class RestOntologyApi implements OntologyApi {
  constructor(private readonly baseUrl: string) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })

    if (!response.ok) {
      throw new Error(`API request failed with ${response.status}`)
    }

    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  getWorkspace() {
    return this.request<WorkspaceSnapshot>('/workspace')
  }

  updateAttribute(id: string, patch: AttributePatch) {
    return this.request<Attribute>(`/attributes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  }

  updateProject(projectId: string, patch: ProjectPatch) {
    return this.request<Project>(`/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  }

  updateProjectAttributeNode(projectId: string, attributeId: string, node: ProjectAttributeNode, status: ProjectAttributeStatus) {
    return this.request<ProjectAttribute>(`/projects/${projectId}/attributes/${attributeId}`, {
      method: 'PATCH',
      body: JSON.stringify({ node, status }),
    })
  }

  deleteAttribute(id: string) {
    return this.request<void>(`/attributes/${id}`, { method: 'DELETE' })
  }

  syncSources() {
    return this.request<Source[]>('/sources/sync', { method: 'POST' })
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined

export const api: OntologyApi = apiBaseUrl
  ? new RestOntologyApi(apiBaseUrl.replace(/\/$/, ''))
  : createDemoApi()
