import type {
  Attribute,
  Project,
  ProjectAttribute,
  Source,
  WorkspaceSnapshot,
} from '../domain'
import type { OntologyApi } from './client'

const sources: Source[] = [
  {
    id: 'src-codex',
    name: 'Codex conversations',
    kind: 'codex',
    description: 'Plans, decisions, and preferences from local conversation history.',
    itemCount: 1248,
    lastSyncedAt: '2026-08-16T07:42:00Z',
    status: 'connected',
  },
  {
    id: 'src-browser',
    name: 'Browser history',
    kind: 'browser',
    description: 'Visited pages and topics from Chromium history.',
    itemCount: 3842,
    lastSyncedAt: '2026-08-16T07:39:00Z',
    status: 'connected',
  },
  {
    id: 'src-takeout',
    name: 'Google Takeout',
    kind: 'takeout',
    description: 'Saved places and trip context from a local export.',
    itemCount: 318,
    lastSyncedAt: '2026-08-15T18:10:00Z',
    status: 'connected',
  },
  {
    id: 'src-manual',
    name: 'Manual notes',
    kind: 'manual',
    description: 'Facts and preferences added directly by you.',
    itemCount: 26,
    lastSyncedAt: '2026-08-14T09:18:00Z',
    status: 'connected',
  },
]

const projects: Project[] = [
  {
    id: 'project-rag',
    name: 'Personal RAG Ontology',
    description: 'Local, policy-bounded memory graph for Codex.',
    status: 'active',
    updatedAt: '2026-08-16T08:20:00Z',
  },
  {
    id: 'project-japan',
    name: 'Japan autumn trip',
    description: 'Ideas, bookings, and preferences for October.',
    status: 'active',
    updatedAt: '2026-08-14T12:00:00Z',
  },
  {
    id: 'project-studio',
    name: 'Home studio refresh',
    description: 'Research and decisions for a compact music setup.',
    status: 'active',
    updatedAt: '2026-08-12T06:30:00Z',
  },
]

let attributes: Attribute[] = [
  {
    id: 'attr-01',
    title: 'Prefers local-first architecture',
    value: 'Use local storage and local processing as the default unless a cloud dependency is explicitly justified.',
    category: 'Preference',
    sourceId: 'src-codex',
    confidence: 0.96,
    status: 'kept',
    projectIds: ['project-rag'],
    excerpt: 'Keep the graph, policy evaluation, and capability database entirely on-device.',
    sourceRef: 'codex://conversation/2026-08-16/architecture-review',
    observedAt: '2026-08-16T06:12:00Z',
    updatedAt: '2026-08-16T06:12:00Z',
  },
  {
    id: 'attr-02',
    title: 'SQL is the model-facing query language',
    value: 'The model should query a bounded SQLite capability database using read-only SQL.',
    category: 'Decision',
    sourceId: 'src-codex',
    confidence: 0.99,
    status: 'kept',
    projectIds: ['project-rag'],
    excerpt: 'SQL only when it decides context is needed. No generated Cypher or SPARQL.',
    sourceRef: 'codex://conversation/2026-08-16/mvp-spec',
    observedAt: '2026-08-16T05:46:00Z',
    updatedAt: '2026-08-16T05:46:00Z',
  },
  {
    id: 'attr-03',
    title: 'MVP should fit in a 3–7 day build',
    value: 'Constrain the first usable implementation to a single hackathon week.',
    category: 'Constraint',
    sourceId: 'src-codex',
    confidence: 0.94,
    status: 'suggested',
    projectIds: ['project-rag'],
    excerpt: 'The implementation should remain small enough to complete and explain in three to seven days.',
    sourceRef: 'codex://conversation/2026-08-16/scope',
    observedAt: '2026-08-16T05:24:00Z',
    updatedAt: '2026-08-16T05:24:00Z',
  },
  {
    id: 'attr-04',
    title: 'Avoid ambient personal context',
    value: 'Start sessions without personal facts and query only when historical context is useful.',
    category: 'Principle',
    sourceId: 'src-codex',
    confidence: 0.98,
    status: 'suggested',
    projectIds: ['project-rag'],
    excerpt: 'No entity match means no personal data is retrieved or injected.',
    sourceRef: 'codex://conversation/2026-08-16/product-thesis',
    observedAt: '2026-08-16T04:55:00Z',
    updatedAt: '2026-08-16T04:55:00Z',
  },
  {
    id: 'attr-05',
    title: 'Use explicit world boundaries',
    value: 'A session selects one world and cannot infer, widen, enumerate, or merge other worlds.',
    category: 'Decision',
    sourceId: 'src-codex',
    confidence: 0.97,
    status: 'suggested',
    projectIds: ['project-rag'],
    excerpt: 'The selected world is explicit plugin configuration.',
    sourceRef: 'codex://conversation/2026-08-16/policy-model',
    observedAt: '2026-08-16T04:42:00Z',
    updatedAt: '2026-08-16T04:42:00Z',
  },
  {
    id: 'attr-06',
    title: 'October is the preferred travel window',
    value: 'Plan Japan travel for the second half of October when possible.',
    category: 'Timing',
    sourceId: 'src-takeout',
    confidence: 0.82,
    status: 'suggested',
    projectIds: ['project-japan'],
    excerpt: 'Saved Kyoto, Kanazawa, and Tokyo lists were edited repeatedly for October.',
    sourceRef: 'takeout://maps/saved-places/295',
    observedAt: '2026-08-14T09:31:00Z',
    updatedAt: '2026-08-14T09:31:00Z',
  },
  {
    id: 'attr-07',
    title: 'Interested in a quieter Kyoto stay',
    value: 'Prefer a small hotel outside the busiest central Kyoto areas.',
    category: 'Preference',
    sourceId: 'src-browser',
    confidence: 0.73,
    status: 'suggested',
    projectIds: ['project-japan'],
    excerpt: 'Repeated visits to small hotels around Demachiyanagi and Okazaki.',
    sourceRef: 'browser://history/query/kyoto-hotels',
    observedAt: '2026-08-13T14:05:00Z',
    updatedAt: '2026-08-13T14:05:00Z',
  },
  {
    id: 'attr-08',
    title: 'Compact monitors are a hard constraint',
    value: 'Studio monitors must fit on a desk no wider than 120 cm.',
    category: 'Constraint',
    sourceId: 'src-manual',
    confidence: 1,
    status: 'kept',
    projectIds: ['project-studio'],
    excerpt: 'Desk is 120 cm. Keep speakers under 25 cm wide.',
    sourceRef: 'manual://note/studio-dimensions',
    observedAt: '2026-08-12T03:30:00Z',
    updatedAt: '2026-08-12T03:30:00Z',
  },
  {
    id: 'attr-09',
    title: 'Consider replacing the audio interface',
    value: 'The current two-input interface may be replaced after monitor selection.',
    category: 'Plan',
    sourceId: 'src-browser',
    confidence: 0.68,
    status: 'ignored',
    projectIds: ['project-studio'],
    excerpt: 'Compared six compact interfaces across several product pages.',
    sourceRef: 'browser://history/query/audio-interfaces',
    observedAt: '2026-08-11T10:14:00Z',
    updatedAt: '2026-08-11T10:14:00Z',
  },
  {
    id: 'attr-10',
    title: 'Provenance is required for every fact',
    value: 'Every returned fact must include a source reference and relevant dates.',
    category: 'Principle',
    sourceId: 'src-codex',
    confidence: 0.98,
    status: 'suggested',
    projectIds: ['project-rag'],
    excerpt: 'Treat SQL results as dated evidence, cite provenance, and state uncertainty.',
    sourceRef: 'codex://conversation/2026-08-16/global-memory',
    observedAt: '2026-08-16T03:58:00Z',
    updatedAt: '2026-08-16T03:58:00Z',
  },
]

let projectAttributes: ProjectAttribute[] = attributes.flatMap((attribute) =>
  attribute.projectIds.map((projectId) => ({
    projectId,
    attributeId: attribute.id,
    status: attribute.status === 'kept' ? 'added' : 'suggested',
    suggestedAt: attribute.observedAt,
  })),
)

const clone = <T,>(value: T): T => structuredClone(value)
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

    async updateProjectAttribute(projectId, attributeId, status) {
      await pause()
      const index = projectAttributes.findIndex((item) => item.projectId === projectId && item.attributeId === attributeId)
      const updated: ProjectAttribute = {
        projectId,
        attributeId,
        status,
        suggestedAt: index >= 0 ? projectAttributes[index].suggestedAt : new Date().toISOString(),
      }
      if (index >= 0) projectAttributes[index] = updated
      else projectAttributes = [...projectAttributes, updated]
      return clone(updated)
    },

    async deleteAttribute(id) {
      await pause()
      attributes = attributes.filter((attribute) => attribute.id !== id)
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
