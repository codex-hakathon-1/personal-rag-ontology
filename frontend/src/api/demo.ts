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
    memoryStatus: 'added',
    updatedAt: '2026-08-16T08:20:00Z',
  },
  {
    id: 'project-mac-n-cheese',
    name: 'MAC-n-CHEESE',
    description: 'Evidence-bound multi-agent reviewer for scientific papers.',
    status: 'active',
    memoryStatus: 'added',
    updatedAt: '2026-08-16T07:10:00Z',
  },
  {
    id: 'project-paw',
    name: 'PAW',
    description: 'Coordinate-aware PDF layout-surgery engine for reading, erasing, and redrawing content.',
    status: 'active',
    memoryStatus: 'added',
    updatedAt: '2026-08-15T13:45:00Z',
  },
  {
    id: 'project-open-plan-tier',
    name: 'OpenPlanTier',
    description: 'Catalog and recommender for composing Palantir-like platforms from open-source projects.',
    status: 'active',
    memoryStatus: 'added',
    updatedAt: '2026-08-14T09:30:00Z',
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
    excerpt: 'The selected world is explicit plugin configuration.',
    sourceRef: 'codex://conversation/2026-08-16/policy-model',
    observedAt: '2026-08-16T04:42:00Z',
    updatedAt: '2026-08-16T04:42:00Z',
  },
  {
    id: 'attr-06',
    title: 'Provenance is required for every fact',
    value: 'Every returned fact must include a source reference and relevant dates.',
    category: 'Principle',
    sourceId: 'src-codex',
    confidence: 0.98,
    status: 'suggested',
    excerpt: 'Treat SQL results as dated evidence, cite provenance, and state uncertainty.',
    sourceRef: 'codex://conversation/2026-08-16/global-memory',
    observedAt: '2026-08-16T03:58:00Z',
    updatedAt: '2026-08-16T03:58:00Z',
  },
  {
    id: 'attr-07',
    title: 'Freeze the deterministic audit before model review',
    value: 'Run the reproducible six-stage audit pipeline and freeze its identity and verdicts before the reviewer committee starts.',
    category: 'Architecture',
    sourceId: 'src-browser',
    confidence: 0.99,
    status: 'kept',
    excerpt: 'The committee runs only after S6 is frozen, so model output cannot perturb audit identity or verdict labels.',
    sourceRef: 'https://github.com/leejaywon/MAC-n-CHEESE#how-it-works',
    observedAt: '2026-08-16T07:08:00Z',
    updatedAt: '2026-08-16T07:08:00Z',
  },
  {
    id: 'attr-08',
    title: 'Reviewer claims must stay evidence-bound',
    value: 'Every score and criticism in the final scientific review should be traceable to manuscript text, tables, or supplied result files.',
    category: 'Principle',
    sourceId: 'src-browser',
    confidence: 0.98,
    status: 'kept',
    excerpt: 'An evidence-bound, ICML-style reviewer for scientific papers.',
    sourceRef: 'https://github.com/leejaywon/MAC-n-CHEESE#mac-n-cheese',
    observedAt: '2026-08-16T07:06:00Z',
    updatedAt: '2026-08-16T07:06:00Z',
  },
  {
    id: 'attr-09',
    title: 'Quarantine hidden reviewer-directed text',
    value: 'Prompt-injection text hidden in PDFs must be sanitized and reported rather than followed by the review agents.',
    category: 'Safety',
    sourceId: 'src-browser',
    confidence: 0.97,
    status: 'suggested',
    excerpt: 'Hidden reviewer-directed text is sanitized and reported, never obeyed.',
    sourceRef: 'https://github.com/leejaywon/MAC-n-CHEESE#how-it-works',
    observedAt: '2026-08-16T07:04:00Z',
    updatedAt: '2026-08-16T07:04:00Z',
  },
  {
    id: 'attr-10',
    title: 'Edit PDF content by page coordinates',
    value: 'Expose coordinate-aware APIs to inspect, erase, and redraw PDF text, vector art, and images.',
    category: 'Capability',
    sourceId: 'src-browser',
    confidence: 0.99,
    status: 'kept',
    excerpt: 'Read a page content with coordinates; erase text and art out of the content stream; draw replacements.',
    sourceRef: 'https://github.com/leejaywon/PAW#paw--pdf-architecture-wizard',
    observedAt: '2026-08-15T13:42:00Z',
    updatedAt: '2026-08-15T13:42:00Z',
  },
  {
    id: 'attr-11',
    title: 'Keep PAW a standalone PDF engine',
    value: 'PDF manipulation should remain an independently installable Python engine built on an open-source PDF stack.',
    category: 'Principle',
    sourceId: 'src-browser',
    confidence: 0.96,
    status: 'suggested',
    excerpt: 'PAW is designed as an independently installable PDF layout-surgery engine.',
    sourceRef: 'https://github.com/leejaywon/PAW#paw--pdf-architecture-wizard',
    observedAt: '2026-08-15T13:40:00Z',
    updatedAt: '2026-08-15T13:40:00Z',
  },
  {
    id: 'attr-12',
    title: 'Expose diagnostic scene and layer inspection',
    value: 'Provide stable paint-order objects, positioned text objects, and text-suppressed raster layers for diagnostics.',
    category: 'Capability',
    sourceId: 'src-browser',
    confidence: 0.95,
    status: 'kept',
    excerpt: 'Inspect scene objects, positioned text objects, and diagnostic raster layers without top-level text.',
    sourceRef: 'https://github.com/leejaywon/PAW#usage',
    observedAt: '2026-08-15T13:38:00Z',
    updatedAt: '2026-08-15T13:38:00Z',
  },
  {
    id: 'attr-13',
    title: 'Catalog open-source platform building blocks',
    value: 'Organize open-source projects into a searchable catalog for composing Palantir-like data platforms.',
    category: 'Capability',
    sourceId: 'src-browser',
    confidence: 0.98,
    status: 'kept',
    excerpt: 'A catalog and recommender for open-source projects that can be used to build a Palantir-like platform.',
    sourceRef: 'https://github.com/leejaywon/OpenPlanTier',
    observedAt: '2026-08-14T09:28:00Z',
    updatedAt: '2026-08-14T09:28:00Z',
  },
  {
    id: 'attr-14',
    title: 'Export reproducible stack manifests',
    value: 'Selected projects should export as machine-readable manifests and clone scripts that can reproduce a proposed stack.',
    category: 'Capability',
    sourceId: 'src-codex',
    confidence: 0.94,
    status: 'kept',
    excerpt: 'The stack builder exports JSON manifests and clone scripts for the selected catalog entries.',
    sourceRef: 'codex://conversation/2026-08-01/open-plan-tier-product-copy',
    observedAt: '2026-08-14T09:26:00Z',
    updatedAt: '2026-08-14T09:26:00Z',
  },
  {
    id: 'attr-15',
    title: 'Separate catalog metadata from installed dependencies',
    value: 'A project appearing in the catalog describes a candidate building block and does not imply that the package is installed or executed.',
    category: 'Principle',
    sourceId: 'src-codex',
    confidence: 0.97,
    status: 'suggested',
    excerpt: 'Catalog entries are product metadata, not evidence that a dependency is installed.',
    sourceRef: 'codex://conversation/2026-08-01/open-plan-tier-catalog-audit',
    observedAt: '2026-08-14T09:24:00Z',
    updatedAt: '2026-08-14T09:24:00Z',
  },
]

function projectAttribute(projectId: string, attributeIndex: number, status: ProjectAttribute['status'], childStates: Partial<Pick<ProjectAttribute, 'valueStatus' | 'sourceStatus' | 'confidenceStatus'>> = {}): ProjectAttribute {
  return {
    projectId,
    attributeId: attributes[attributeIndex].id,
    status,
    valueStatus: childStates.valueStatus ?? status,
    sourceStatus: childStates.sourceStatus ?? status,
    confidenceStatus: childStates.confidenceStatus ?? status,
    suggestedAt: attributes[attributeIndex].observedAt,
  }
}

let projectAttributes: ProjectAttribute[] = [
  projectAttribute('project-rag', 0, 'added', { confidenceStatus: 'suggested' }),
  projectAttribute('project-rag', 1, 'added'),
  projectAttribute('project-rag', 2, 'suggested', { sourceStatus: 'added' }),
  projectAttribute('project-rag', 3, 'suggested'),
  projectAttribute('project-rag', 4, 'suggested', { confidenceStatus: 'added' }),
  projectAttribute('project-rag', 5, 'suggested', { sourceStatus: 'deactivated' }),
  projectAttribute('project-mac-n-cheese', 6, 'added'),
  projectAttribute('project-mac-n-cheese', 7, 'added', { confidenceStatus: 'suggested' }),
  projectAttribute('project-mac-n-cheese', 8, 'suggested', { sourceStatus: 'added' }),
  projectAttribute('project-paw', 9, 'added'),
  projectAttribute('project-paw', 10, 'suggested', { confidenceStatus: 'added' }),
  projectAttribute('project-paw', 11, 'added'),
  projectAttribute('project-open-plan-tier', 12, 'added'),
  projectAttribute('project-open-plan-tier', 13, 'added', { sourceStatus: 'suggested' }),
  projectAttribute('project-open-plan-tier', 14, 'suggested'),
]

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
