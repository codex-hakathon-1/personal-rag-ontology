import type { Attribute, Project, ProjectAttribute, ProjectAttributeNode, ProjectAttributeStatus, Source } from './domain'
import './project-attribute-tree.css'

type ChildNode = Exclude<ProjectAttributeNode, 'attribute'>

interface ProjectAttributeTreeProps {
  project: Project
  attributes: Attribute[]
  relations: ProjectAttribute[]
  sources: Source[]
  onOpenTuple: (attributeId: string, node: ChildNode) => void
  onRootStatusChange: (status: ProjectAttributeStatus) => void
  onNodeStatusChange: (attribute: Attribute, node: ProjectAttributeNode, status: ProjectAttributeStatus) => void
}

const statusMeta: Record<ProjectAttributeStatus, { label: string; className: string }> = {
  added: { label: 'Active', className: 'is-active' },
  suggested: { label: 'Not selected', className: 'is-unselected' },
  deactivated: { label: 'Deactivated', className: 'is-deactivated' },
}

const nodeStatusField: Record<ProjectAttributeNode, keyof Pick<ProjectAttribute, 'status' | 'valueStatus' | 'sourceStatus' | 'confidenceStatus'>> = {
  attribute: 'status',
  value: 'valueStatus',
  source: 'sourceStatus',
  confidence: 'confidenceStatus',
}

function nextStatus(status: ProjectAttributeStatus): ProjectAttributeStatus {
  if (status === 'added') return 'suggested'
  if (status === 'suggested') return 'deactivated'
  return 'added'
}

function sourceName(source?: Source) {
  if (!source) return 'Unknown'
  if (source.kind === 'codex') return 'Codex'
  if (source.kind === 'browser') return 'Browser'
  if (source.kind === 'takeout') return 'Takeout'
  return 'Manual'
}

function CircleContent({ label, detail, state }: { label: string; detail?: string; state: ProjectAttributeStatus }) {
  return (
    <>
      <span className="project-tree-node-label">{label}</span>
      {detail && <span className="project-tree-node-detail">{detail}</span>}
      <span className="sr-only">{statusMeta[state].label}</span>
    </>
  )
}

function StateCircle({ label, detail, ownState, effectiveState, kind, inherited, onStateChange }: {
  label: string
  detail?: string
  ownState: ProjectAttributeStatus
  effectiveState: ProjectAttributeStatus
  kind: 'root' | 'attribute'
  inherited: boolean
  onStateChange: (status: ProjectAttributeStatus) => void
}) {
  const next = nextStatus(ownState)
  const inheritedCopy = inherited ? ` Effective state inherited as ${statusMeta[effectiveState].label}.` : ''
  return (
    <button
      className={`project-tree-node project-tree-node-${kind} ${statusMeta[effectiveState].className} ${inherited ? 'is-inherited' : ''}`}
      onClick={() => onStateChange(next)}
      disabled={inherited}
      aria-label={`${label}: own state ${statusMeta[ownState].label}.${inheritedCopy} Change to ${statusMeta[next].label}.`}
      title={inherited ? 'Activate the parent node first' : `Change to ${statusMeta[next].label}`}
    >
      <CircleContent label={label} detail={detail} state={effectiveState} />
    </button>
  )
}

function TupleCircle({ label, detail, ownState, effectiveState, kind, inherited, onOpen, onStateChange, title }: {
  label: string
  detail: string
  ownState: ProjectAttributeStatus
  effectiveState: ProjectAttributeStatus
  kind: 'value' | 'meta'
  inherited: boolean
  onOpen: () => void
  onStateChange: (status: ProjectAttributeStatus) => void
  title?: string
}) {
  const next = nextStatus(ownState)
  return (
    <div className={`project-tree-node project-tree-node-${kind} ${statusMeta[effectiveState].className} ${inherited ? 'is-inherited' : ''}`} title={title}>
      <button className="project-tree-node-content" onClick={onOpen} aria-label={`Open ${detail.toLowerCase()} tuple. ${statusMeta[effectiveState].label}.`}>
        <CircleContent label={label} detail={detail} state={effectiveState} />
      </button>
      <button
        className="project-tree-state-toggle"
        onClick={() => onStateChange(next)}
        disabled={inherited}
        aria-label={`Change ${detail.toLowerCase()} state from ${statusMeta[ownState].label} to ${statusMeta[next].label}.`}
        title={inherited ? 'Activate the parent node first' : `Change to ${statusMeta[next].label}`}
      >↻</button>
    </div>
  )
}

export default function ProjectAttributeTree({ project, attributes, relations, sources, onOpenTuple, onRootStatusChange, onNodeStatusChange }: ProjectAttributeTreeProps) {
  const relationByAttributeId = new Map(relations.map((relation) => [relation.attributeId, relation]))
  const rootInheritedState = project.memoryStatus === 'added' ? null : project.memoryStatus

  if (attributes.length === 0) {
    return <div className="project-tree-empty">No attributes match this view.</div>
  }

  return (
    <section className="project-tree-stage" aria-label={`${project.name} attribute tree`}>
      <div className="project-tree-head" aria-hidden="true">
        <span>Project root</span>
        <span>Attributes</span>
        <span>Tuples</span>
      </div>
      <div className="project-tree-map">
        <div className="project-tree-root-wrap">
          <StateCircle
            label={project.name}
            detail="Project"
            ownState={project.memoryStatus}
            effectiveState={project.memoryStatus}
            kind="root"
            inherited={false}
            onStateChange={onRootStatusChange}
          />
        </div>
        <div className="project-tree-branches">
          {attributes.map((attribute) => {
            const relation = relationByAttributeId.get(attribute.id)
            if (!relation) return null
            const source = sources.find((item) => item.id === attribute.sourceId)
            const attributeOwnState = relation.status
            const attributeEffectiveState = rootInheritedState ?? attributeOwnState
            const childInheritedState = rootInheritedState ?? (attributeOwnState === 'added' ? null : attributeOwnState)
            const childrenInherited = childInheritedState !== null

            const childState = (node: ChildNode) => relation[nodeStatusField[node]] as ProjectAttributeStatus
            const childEffectiveState = (node: ChildNode) => childInheritedState ?? childState(node)
            const changeChildState = (node: ChildNode, status: ProjectAttributeStatus) => onNodeStatusChange(attribute, node, status)

            return (
              <div className="project-tree-branch" key={attribute.id}>
                <div className="project-tree-attribute-wrap">
                  <StateCircle
                    label={attribute.title}
                    detail={attribute.category}
                    ownState={attributeOwnState}
                    effectiveState={attributeEffectiveState}
                    kind="attribute"
                    inherited={rootInheritedState !== null}
                    onStateChange={(status) => onNodeStatusChange(attribute, 'attribute', status)}
                  />
                </div>
                <div className="project-tree-values">
                  <TupleCircle
                    label={attribute.value}
                    detail="Value"
                    ownState={childState('value')}
                    effectiveState={childEffectiveState('value')}
                    kind="value"
                    inherited={childrenInherited}
                    onOpen={() => onOpenTuple(attribute.id, 'value')}
                    onStateChange={(status) => changeChildState('value', status)}
                    title="Open value tuple"
                  />
                  <TupleCircle
                    label={sourceName(source)}
                    detail="Source"
                    ownState={childState('source')}
                    effectiveState={childEffectiveState('source')}
                    kind="meta"
                    inherited={childrenInherited}
                    onOpen={() => onOpenTuple(attribute.id, 'source')}
                    onStateChange={(status) => changeChildState('source', status)}
                    title={source?.name}
                  />
                  <TupleCircle
                    label={`${Math.round(attribute.confidence * 100)}%`}
                    detail="Confidence"
                    ownState={childState('confidence')}
                    effectiveState={childEffectiveState('confidence')}
                    kind="meta"
                    inherited={childrenInherited}
                    onOpen={() => onOpenTuple(attribute.id, 'confidence')}
                    onStateChange={(status) => changeChildState('confidence', status)}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
