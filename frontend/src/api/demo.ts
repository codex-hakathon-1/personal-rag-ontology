import realisticWorkspace from '../data/realistic-workspace.json'
import type {
  Attribute,
  Project,
  ProjectAttribute,
  Source,
  WorkspaceSnapshot,
} from '../domain'
import type { OntologyApi } from './client'

const clone = <T,>(value: T): T => structuredClone(value)
const initialWorkspace = realisticWorkspace as WorkspaceSnapshot

const sources: Source[] = clone(initialWorkspace.sources)
let attributes: Attribute[] = clone(initialWorkspace.attributes)
const projects: Project[] = clone(initialWorkspace.projects)
let projectAttributes: ProjectAttribute[] = clone(initialWorkspace.projectAttributes)

const pause = () => new Promise((resolve) => window.setTimeout(resolve, 140))

export function createDemoApi(): OntologyApi {
  return {
    async getWorkspace(): Promise<WorkspaceSnapshot> {
      await pause()
      return clone({ sources, attributes, projects, projectAttributes })
    },

    async updateAttribute(id, patch) {
      await pause()
      const index = attributes.findIndex((attribute) => attribute.id === id)
      if (index < 0) throw new Error('Attribute not found')
      attributes[index] = {
        ...attributes[index],
        ...patch,
        updatedAt: new Date().toISOString(),
      }
      return clone(attributes[index])
    },

    async updateProject(projectId, patch) {
      await pause()
      const index = projects.findIndex((project) => project.id === projectId)
      if (index < 0) throw new Error('Project not found')
      projects[index] = { ...projects[index], ...patch, updatedAt: new Date().toISOString() }
      return clone(projects[index])
    },

    async updateProjectAttributeNode(projectId, attributeId, node, status) {
      await pause()
      const index = projectAttributes.findIndex((item) => item.projectId === projectId && item.attributeId === attributeId)
      if (index < 0) throw new Error('Project attribute not found')
      const field = {
        attribute: 'status',
        value: 'valueStatus',
        source: 'sourceStatus',
        confidence: 'confidenceStatus',
      } as const
      const statusField = field[node]
      const updated = { ...projectAttributes[index], [statusField]: status }
      projectAttributes[index] = updated
      return clone(updated)
    },

    async deleteAttribute(id) {
      await pause()
      attributes = attributes.filter((attribute) => attribute.id !== id)
      projectAttributes = projectAttributes.filter((item) => item.attributeId !== id)
    },

    async syncSources() {
      await new Promise((resolve) => window.setTimeout(resolve, 700))
      const now = new Date().toISOString()
      sources.forEach((source) => {
        source.lastSyncedAt = now
        source.status = 'connected'
      })
      return clone(sources)
    },
  }
}
