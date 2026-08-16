import { StrictMode, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './tree-test.css'

type NodeState = 'active' | 'unselected' | 'deactivated'

interface ValueNode {
  id: string
  label: string
  state: NodeState
}

interface AttributeBranch {
  id: string
  label: string
  category: string
  state: NodeState
  values: ValueNode[]
}

interface TestProject {
  id: string
  name: string
  description: string
  attributes: AttributeBranch[]
}

const projects: TestProject[] = [
  {
    id: 'rag',
    name: 'Personal RAG Ontology',
    description: 'Policy-bounded local context and retrieval decisions.',
    attributes: [
      {
        id: 'architecture',
        label: 'Architecture',
        category: 'Preference',
        state: 'active',
        values: [
          { id: 'local-first', label: 'Local first', state: 'active' },
          { id: 'bounded', label: 'Policy bounded', state: 'active' },
          { id: 'cloud', label: 'Cloud sync', state: 'deactivated' },
        ],
      },
      {
        id: 'query',
        label: 'Query model',
        category: 'Decision',
        state: 'active',
        values: [
          { id: 'sql', label: 'Read-only SQL', state: 'active' },
          { id: 'sqlite', label: 'SQLite', state: 'unselected' },
          { id: 'cypher', label: 'Cypher', state: 'deactivated' },
        ],
      },
      {
        id: 'scope',
        label: 'MVP scope',
        category: 'Constraint',
        state: 'unselected',
        values: [
          { id: 'days', label: '3–7 days', state: 'unselected' },
          { id: 'local-ui', label: 'Local UI', state: 'active' },
        ],
      },
      {
        id: 'provenance',
        label: 'Provenance',
        category: 'Principle',
        state: 'unselected',
        values: [
          { id: 'source', label: 'Source ref', state: 'unselected' },
          { id: 'dates', label: 'Dated facts', state: 'active' },
          { id: 'ambient', label: 'Ambient data', state: 'deactivated' },
        ],
      },
    ],
  },
  {
    id: 'japan',
    name: 'Japan autumn trip',
    description: 'Timing, lodging, and itinerary preferences for October.',
    attributes: [
      {
        id: 'timing',
        label: 'Travel window',
        category: 'Timing',
        state: 'active',
        values: [
          { id: 'october', label: 'Late October', state: 'active' },
          { id: 'november', label: 'November', state: 'unselected' },
        ],
      },
      {
        id: 'lodging',
        label: 'Lodging',
        category: 'Preference',
        state: 'unselected',
        values: [
          { id: 'quiet', label: 'Quiet area', state: 'active' },
          { id: 'small', label: 'Small hotel', state: 'unselected' },
          { id: 'central', label: 'Central Kyoto', state: 'deactivated' },
        ],
      },
      {
        id: 'route',
        label: 'Route',
        category: 'Plan',
        state: 'unselected',
        values: [
          { id: 'kyoto', label: 'Kyoto', state: 'active' },
          { id: 'kanazawa', label: 'Kanazawa', state: 'unselected' },
          { id: 'tokyo', label: 'Tokyo', state: 'unselected' },
        ],
      },
    ],
  },
  {
    id: 'studio',
    name: 'Home studio refresh',
    description: 'Space constraints and equipment choices for a compact desk.',
    attributes: [
      {
        id: 'dimensions',
        label: 'Desk size',
        category: 'Constraint',
        state: 'active',
        values: [
          { id: 'width', label: '120 cm', state: 'active' },
          { id: 'speaker', label: 'Under 25 cm', state: 'active' },
        ],
      },
      {
        id: 'monitors',
        label: 'Monitors',
        category: 'Decision',
        state: 'unselected',
        values: [
          { id: 'compact', label: 'Compact pair', state: 'unselected' },
          { id: 'large', label: 'Large pair', state: 'deactivated' },
        ],
      },
      {
        id: 'interface',
        label: 'Interface',
        category: 'Plan',
        state: 'deactivated',
        values: [
          { id: 'keep', label: 'Keep current', state: 'unselected' },
          { id: 'replace', label: 'Replace later', state: 'deactivated' },
        ],
      },
    ],
  },
]

const stateOrder: NodeState[] = ['active', 'unselected', 'deactivated']

function nextState(state: NodeState) {
  return stateOrder[(stateOrder.indexOf(state) + 1) % stateOrder.length]
}

function stateLabel(state: NodeState) {
  if (state === 'active') return 'Active'
  if (state === 'deactivated') return 'Deactivated'
  return 'Not selected'
}

export function TreeNode({ label, detail, state, size = 'value', onClick }: {
  label: string
  detail?: string
  state: NodeState
  size?: 'root' | 'attribute' | 'value'
  onClick?: () => void
}) {
  const className = `tree-node tree-node-${size} state-${state}`
  const content = (
    <>
      <span className="tree-node-label">{label}</span>
      {detail && <span className="tree-node-detail">{detail}</span>}
      <span className="sr-only">{stateLabel(state)}</span>
    </>
  )

  if (!onClick) return <div className={className}>{content}</div>

  return (
    <button className={className} onClick={onClick} aria-label={`${label}: ${stateLabel(state)}. Change state.`}>
      {content}
    </button>
  )
}

export function TreePrototype() {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [overrides, setOverrides] = useState<Record<string, NodeState>>({})
  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null

  const stateFor = (projectId: string, nodeId: string, initialState: NodeState) => {
    return overrides[`${projectId}:${nodeId}`] ?? initialState
  }

  const cycleNode = (projectId: string, nodeId: string, initialState: NodeState) => {
    const key = `${projectId}:${nodeId}`
    setOverrides((current) => ({ ...current, [key]: nextState(current[key] ?? initialState) }))
  }

  const projectStateCounts = useMemo(() => projects.map((project) => {
    const nodes = project.attributes.flatMap((attribute) => [attribute.state, ...attribute.values.map((value) => value.state)])
    return { id: project.id, active: nodes.filter((state) => state === 'active').length, total: nodes.length }
  }), [])

  if (!selectedProject) {
    return (
      <main className="prototype-shell">
        <header className="prototype-header">
          <div><span className="prototype-kicker">Isolated experiment / 01</span><h1>Project attribute tree</h1></div>
          <p>This route is a standalone UI test. Nothing here changes the main Index interface.</p>
        </header>
        <section className="project-test-list" aria-label="Test projects">
          <div className="project-test-head"><span>Choose a project</span><span>{projects.length} prototypes</span></div>
          {projects.map((project, index) => {
            const count = projectStateCounts.find((item) => item.id === project.id)
            return (
              <button className="project-test-row" key={project.id} onClick={() => setSelectedProjectId(project.id)}>
                <span className="project-test-index">{String(index + 1).padStart(2, '0')}</span>
                <span className="project-test-copy"><strong>{project.name}</strong><small>{project.description}</small></span>
                <span className="project-test-count"><b>{project.attributes.length}</b> attributes</span>
                <span className="project-test-count"><b>{count?.active ?? 0}</b> active nodes</span>
                <span className="project-test-arrow">→</span>
              </button>
            )
          })}
        </section>
      </main>
    )
  }

  return (
    <main className="prototype-shell prototype-detail">
      <header className="prototype-header detail-header">
        <div>
          <button className="back-button" onClick={() => setSelectedProjectId(null)}>← Projects</button>
          <span className="prototype-kicker">Tree UI test / Click nodes to cycle state</span>
          <h1>{selectedProject.name}</h1>
        </div>
        <div className="prototype-actions">
          <div className="state-legend" aria-label="Node state legend">
            <span><i className="legend-active" />Active</span>
            <span><i className="legend-unselected" />Not selected</span>
            <span><i className="legend-deactivated" />Deactivated</span>
          </div>
          <button className="reset-button" onClick={() => setOverrides({})}>Reset states</button>
        </div>
      </header>

      <section className="tree-stage" aria-label={`${selectedProject.name} attribute tree`}>
        <div className="tree-column-labels" aria-hidden="true"><span>Project root</span><span>Attributes</span><span>Values</span></div>
        <div className="tree-map">
          <div className="project-root-wrap">
            <TreeNode label={selectedProject.name} detail="Project" state="active" size="root" />
          </div>
          <div className="tree-branches">
            {selectedProject.attributes.map((attribute) => {
              const attributeState = stateFor(selectedProject.id, attribute.id, attribute.state)
              return (
                <div className="tree-branch" key={attribute.id}>
                  <div className="attribute-node-wrap">
                    <TreeNode
                      label={attribute.label}
                      detail={attribute.category}
                      state={attributeState}
                      size="attribute"
                      onClick={() => cycleNode(selectedProject.id, attribute.id, attribute.state)}
                    />
                  </div>
                  <div className="value-nodes">
                    {attribute.values.map((value) => (
                      <TreeNode
                        key={value.id}
                        label={value.label}
                        state={stateFor(selectedProject.id, `${attribute.id}:${value.id}`, value.state)}
                        onClick={() => cycleNode(selectedProject.id, `${attribute.id}:${value.id}`, value.state)}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>
      <p className="prototype-note">Prototype only · Active nodes use neon fill, untouched nodes stay white, and explicitly deactivated nodes turn grey.</p>
    </main>
  )
}

createRoot(document.getElementById('tree-test-root')!).render(
  <StrictMode>
    <TreePrototype />
  </StrictMode>,
)
