import { useEffect, useState } from 'react'
import { api } from './api/client'
import type { Attribute, AttributePatch, Project, ProjectAttribute, ProjectAttributeNode, ProjectAttributeStatus, Source, WorkspaceSnapshot } from './domain'
import JellyPet from './JellyPet'
import ProjectAttributeTree from './ProjectAttributeTree'

type View = 'projects' | 'review' | 'sources'
type ProjectFilter = 'all' | 'active' | 'unselected' | 'deactivated'
type TupleNode = Exclude<ProjectAttributeNode, 'attribute'>

interface TupleSelection {
  projectId: string
  attributeId: string
  node: TupleNode
}
type IconName = View | 'search' | 'close' | 'more' | 'chevron' | 'check' | 'minus' | 'arrow' | 'sync' | 'spark'

const navItems: { id: View; label: string }[] = [
  { id: 'projects', label: 'Projects' },
  { id: 'sources', label: 'Sources' },
]

function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    projects: <><path d="M3.5 5.5h5l1.4 1.7h6.6v8.3h-13z" /><path d="M3.5 7.2h13" /></>,
    review: <><path d="M5 3.5h10v13H5z" /><path d="m7.5 10 1.7 1.7 3.6-4" /></>,
    sources: <><ellipse cx="10" cy="5" rx="6.5" ry="2.5" /><path d="M3.5 5v5c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5V5M3.5 10v5c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5v-5" /></>,
    search: <><circle cx="8.5" cy="8.5" r="5" /><path d="m12.5 12.5 3.5 3.5" /></>,
    close: <><path d="m5 5 10 10M15 5 5 15" /></>,
    more: <><circle cx="4" cy="10" r=".7" fill="currentColor" stroke="none" /><circle cx="10" cy="10" r=".7" fill="currentColor" stroke="none" /><circle cx="16" cy="10" r=".7" fill="currentColor" stroke="none" /></>,
    chevron: <path d="m7 8 3 3 3-3" />,
    check: <path d="m4.5 10 3.5 3.5 7.5-8" />,
    minus: <path d="M5 10h10" />,
    arrow: <><path d="M4 10h11M11 6l4 4-4 4" /></>,
    sync: <><path d="M15.5 7A6 6 0 0 0 5.3 4.8L3.5 7" /><path d="M3.5 3.5V7H7M4.5 13A6 6 0 0 0 14.7 15.2l1.8-2.2" /><path d="M16.5 16.5V13H13" /></>,
    spark: <><path d="M10 2.8c.5 3.8 2.1 5.4 5.9 5.9-3.8.5-5.4 2.1-5.9 5.9-.5-3.8-2.1-5.4-5.9-5.9C7.9 8.2 9.5 6.6 10 2.8Z" /><path d="M16 13.5c.2 1.3.7 1.8 2 2-.9.2-1.5.8-1.7 2-.2-1.2-.8-1.8-2-2 .9-.2 1.5-.8 1.7-2Z" /></>,
  }

  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  )
}

function formatDate(value: string) {
  const date = new Date(value)
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  if (sameDay) return `Today, ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric' })
}

function sourceLabel(source?: Source) {
  if (!source) return 'Unknown source'
  if (source.kind === 'codex') return 'Codex'
  if (source.kind === 'browser') return 'Browser'
  if (source.kind === 'takeout') return 'Takeout'
  return 'Manual'
}

function App() {
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null)
  const [view, setView] = useState<View>('projects')
  const [selectedAttributeId, setSelectedAttributeId] = useState<string | null>(null)
  const [selectedTuple, setSelectedTuple] = useState<TupleSelection | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [projectQuery, setProjectQuery] = useState('')
  const [projectMemoryFilter, setProjectMemoryFilter] = useState<ProjectFilter>('all')
  const [notice, setNotice] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    api.getWorkspace().then(setWorkspace).catch(() => setNotice('Could not load the workspace.'))
  }, [])

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setView('projects')
        window.setTimeout(() => document.getElementById('project-attribute-search')?.focus(), 0)
      }
    }
    window.addEventListener('keydown', focusSearch)
    return () => window.removeEventListener('keydown', focusSearch)
  }, [])

  useEffect(() => {
    if (!notice) return
    const timeout = window.setTimeout(() => setNotice(null), 2200)
    return () => window.clearTimeout(timeout)
  }, [notice])

  const selectedAttribute = workspace?.attributes.find((item) => item.id === selectedAttributeId) ?? null
  const updateAttribute = async (attribute: Attribute, patch: AttributePatch, message?: string) => {
    const previous = workspace
    if (!previous) return
    setWorkspace({
      ...previous,
      attributes: previous.attributes.map((item) => item.id === attribute.id ? { ...item, ...patch } : item),
    })
    try {
      const updated = await api.updateAttribute(attribute.id, patch)
      setWorkspace((current) => current ? {
        ...current,
        attributes: current.attributes.map((item) => item.id === updated.id ? updated : item),
      } : current)
      if (message) setNotice(message)
    } catch {
      setWorkspace(previous)
      setNotice('The change could not be saved.')
    }
  }

  const deleteAttribute = async (attribute: Attribute) => {
    if (!workspace) return
    const previous = workspace
    setSelectedAttributeId(null)
    setWorkspace({
      ...workspace,
      attributes: workspace.attributes.filter((item) => item.id !== attribute.id),
      projectAttributes: workspace.projectAttributes.filter((item) => item.attributeId !== attribute.id),
    })
    try {
      await api.deleteAttribute(attribute.id)
      setNotice('Attribute deleted')
    } catch {
      setWorkspace(previous)
      setNotice('The attribute could not be deleted.')
    }
  }

  const updateProjectNode = async (projectId: string, attribute: Attribute, node: ProjectAttributeNode, status: ProjectAttributeStatus) => {
    if (!workspace) return
    const previous = workspace
    const existing = workspace.projectAttributes.find((item) => item.projectId === projectId && item.attributeId === attribute.id)
    if (!existing) return
    const statusField: Record<ProjectAttributeNode, keyof Pick<ProjectAttribute, 'status' | 'valueStatus' | 'sourceStatus' | 'confidenceStatus'>> = {
      attribute: 'status',
      value: 'valueStatus',
      source: 'sourceStatus',
      confidence: 'confidenceStatus',
    }
    const optimistic = workspace.projectAttributes.map((item) => item === existing ? { ...item, [statusField[node]]: status } : item)
    setWorkspace({ ...workspace, projectAttributes: optimistic })
    try {
      const updated = await api.updateProjectAttributeNode(projectId, attribute.id, node, status)
      setWorkspace((current) => current ? {
        ...current,
        projectAttributes: current.projectAttributes.map((item) => item.projectId === projectId && item.attributeId === attribute.id ? updated : item),
      } : current)
      const statusMessage: Record<ProjectAttributeStatus, string> = {
        added: 'Attribute active in project',
        suggested: 'Attribute left unselected',
        deactivated: 'Attribute deactivated',
      }
      setNotice(statusMessage[status])
    } catch {
      setWorkspace(previous)
      setNotice('The project could not be updated.')
    }
  }

  const updateProjectRoot = async (project: Project, status: ProjectAttributeStatus) => {
    if (!workspace) return
    const previous = workspace
    setWorkspace({
      ...workspace,
      projects: workspace.projects.map((item) => item.id === project.id ? { ...item, memoryStatus: status } : item),
    })
    try {
      const updated = await api.updateProject(project.id, { memoryStatus: status })
      setWorkspace((current) => current ? {
        ...current,
        projects: current.projects.map((item) => item.id === updated.id ? updated : item),
      } : current)
      setNotice(status === 'deactivated' ? 'Project tree deactivated' : 'Project tree state updated')
    } catch {
      setWorkspace(previous)
      setNotice('The project root could not be updated.')
    }
  }

  const handleSync = async () => {
    if (!workspace || syncing) return
    setSyncing(true)
    try {
      const nextSources = await api.syncSources()
      setWorkspace({ ...workspace, sources: nextSources })
      setNotice('Sources are up to date')
    } catch {
      setNotice('Source sync failed.')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className={`app-shell ${selectedAttribute || selectedTuple ? 'has-inspector' : ''}`}>
      <Sidebar view={view} onChange={(nextView) => { setView(nextView); setSelectedAttributeId(null); setSelectedTuple(null) }} />
      <main className="main-pane">
        {!workspace ? (
          <div className="loading-state"><span className="loading-mark" />Loading local memory…</div>
        ) : (
          <>
            {view === 'projects' && (
              <ProjectsView
                workspace={workspace}
                selectedProjectId={selectedProjectId}
                onProjectChange={(id) => { setSelectedProjectId(id); setSelectedAttributeId(null); setSelectedTuple(null); setProjectQuery(''); setProjectMemoryFilter('all') }}
                query={projectQuery}
                onQueryChange={setProjectQuery}
                filter={projectMemoryFilter}
                onFilterChange={setProjectMemoryFilter}
                onOpenTuple={(selection) => { setSelectedTuple(selection); setSelectedAttributeId(null) }}
                onProjectStatusChange={updateProjectNode}
                onProjectRootChange={updateProjectRoot}
              />
            )}
            {view === 'review' && (
              <ReviewView
                workspace={workspace}
                selectedId={selectedAttributeId}
                onSelect={setSelectedAttributeId}
                onUpdate={updateAttribute}
              />
            )}
            {view === 'sources' && <SourcesView sources={workspace.sources} syncing={syncing} onSync={handleSync} />}
          </>
        )}
      </main>
      {workspace && selectedAttribute && (
        <Inspector
          key={selectedAttribute.id}
          attribute={selectedAttribute}
          source={workspace.sources.find((source) => source.id === selectedAttribute.sourceId)}
          projects={workspace.projects.filter((project) => workspace.projectAttributes.some((item) => item.projectId === project.id && item.attributeId === selectedAttribute.id && item.status === 'added'))}
          allProjects={workspace.projects}
          onClose={() => setSelectedAttributeId(null)}
          onUpdate={updateAttribute}
          onProjectStatusChange={(projectId, status) => updateProjectNode(projectId, selectedAttribute, 'attribute', status)}
          onDelete={deleteAttribute}
        />
      )}
      {workspace && selectedTuple && (() => {
        const attribute = workspace.attributes.find((item) => item.id === selectedTuple.attributeId)
        const project = workspace.projects.find((item) => item.id === selectedTuple.projectId)
        const relation = workspace.projectAttributes.find((item) => item.projectId === selectedTuple.projectId && item.attributeId === selectedTuple.attributeId)
        const source = attribute ? workspace.sources.find((item) => item.id === attribute.sourceId) : undefined
        if (!attribute || !project || !relation) return null
        return (
          <TupleInspector
            key={`${attribute.id}:${selectedTuple.node}`}
            attribute={attribute}
            project={project}
            relation={relation}
            source={source}
            node={selectedTuple.node}
            onClose={() => setSelectedTuple(null)}
            onUpdate={updateAttribute}
            onNodeStatusChange={(status) => updateProjectNode(project.id, attribute, selectedTuple.node, status)}
          />
        )
      })()}
      <JellyPet />
      {notice && <div className="notice" role="status"><Icon name="check" size={15} />{notice}</div>}
    </div>
  )
}

function Sidebar({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true"><i /><b /></span>
        <span className="brand-word">Me<span className="brand-accent">S</span>ource</span>
      </div>
      <nav aria-label="Primary navigation">
        {navItems.map((item) => (
          <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} onClick={() => onChange(item.id)}>
            <Icon name={item.id} size={17} />
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-foot">
        <div className="workspace-label">Workspace</div>
        <button className="workspace-switcher">
          <span className="workspace-avatar">J</span>
          <span className="workspace-name">Personal</span>
          <Icon name="chevron" size={14} />
        </button>
        <div className="local-status"><span />Local only · Private</div>
      </div>
    </aside>
  )
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string | null; title: string; description?: string; action?: React.ReactNode }) {
  const sectionLabels: Record<string, string> = {
    Projects: '01 / Project index',
    Review: '02 / Curation queue',
    Sources: '03 / Input registry',
  }

  return (
    <header className="page-header">
      <div className="page-heading">
        {eyebrow !== null && <div className="eyebrow">{eyebrow ?? sectionLabels[title] ?? 'Local index'}</div>}
        <h1>{title}</h1>
      </div>
      <div className="page-context">
        {description && <p>{description}</p>}
        {action && <div className="header-action">{action}</div>}
      </div>
    </header>
  )
}

function AttributeList({ attributes, sources, selectedId, onSelect, onUpdate }: {
  attributes: Attribute[]
  sources: Source[]
  selectedId: string | null
  onSelect: (id: string) => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
}) {
  if (attributes.length === 0) {
    return <div className="empty-state">Nothing here yet.</div>
  }

  return (
    <div className="attribute-list">
      {attributes.map((attribute) => (
        <AttributeRow
          key={attribute.id}
          attribute={attribute}
          source={sources.find((item) => item.id === attribute.sourceId)}
          selected={attribute.id === selectedId}
          onSelect={() => onSelect(attribute.id)}
          onUpdate={onUpdate}
        />
      ))}
    </div>
  )
}

function AttributeRow({ attribute, source, selected, onSelect, onUpdate }: {
  attribute: Attribute
  source?: Source
  selected: boolean
  onSelect: () => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
}) {
  return (
    <div className={`attribute-row ${selected ? 'selected' : ''} ${attribute.status === 'ignored' ? 'is-ignored' : ''}`} onClick={onSelect}>
      <div className={`status-tick ${attribute.status}`} aria-hidden="true">{attribute.status === 'kept' && <Icon name="check" size={11} />}</div>
      <button className="attribute-title" onClick={(event) => { event.stopPropagation(); onSelect() }}>{attribute.title}</button>
      <span className="category-label">{attribute.category}</span>
      <span className="source-label">{sourceLabel(source)}</span>
      <div className="row-actions">
        {attribute.status !== 'kept' && (
          <button className="text-action" onClick={(event) => { event.stopPropagation(); onUpdate(attribute, { status: 'kept' }, 'Attribute kept') }}>Keep</button>
        )}
        {attribute.status !== 'ignored' && (
          <button className="text-action quiet" onClick={(event) => { event.stopPropagation(); onUpdate(attribute, { status: 'ignored' }, 'Attribute ignored') }}>Ignore</button>
        )}
      </div>
    </div>
  )
}

function ProjectsView({ workspace, selectedProjectId, onProjectChange, query, onQueryChange, filter, onFilterChange, onOpenTuple, onProjectStatusChange, onProjectRootChange }: {
  workspace: WorkspaceSnapshot
  selectedProjectId: string | null
  onProjectChange: (id: string | null) => void
  query: string
  onQueryChange: (value: string) => void
  filter: ProjectFilter
  onFilterChange: (value: ProjectFilter) => void
  onOpenTuple: (selection: TupleSelection) => void
  onProjectStatusChange: (projectId: string, attribute: Attribute, node: ProjectAttributeNode, status: ProjectAttributeStatus) => void
  onProjectRootChange: (project: Project, status: ProjectAttributeStatus) => void
}) {
  const project = workspace.projects.find((item) => item.id === selectedProjectId)

  if (!project) {
    return <ProjectPicker workspace={workspace} onSelect={onProjectChange} />
  }

  const projectRelations = workspace.projectAttributes.filter((item) => item.projectId === project.id)
  const relationByAttributeId = new Map(projectRelations.map((item) => [item.attributeId, item]))
  const projectAttributes = workspace.attributes.filter((attribute) => {
    const relation = relationByAttributeId.get(attribute.id)
    if (!relation) return false
    const filterStatus: Record<Exclude<ProjectFilter, 'all'>, ProjectAttributeStatus> = {
      active: 'added',
      unselected: 'suggested',
      deactivated: 'deactivated',
    }
    const matchesFilter = filter === 'all' || relation.status === filterStatus[filter]
    const haystack = `${attribute.title} ${attribute.category} ${attribute.value}`.toLowerCase()
    return matchesFilter && haystack.includes(query.toLowerCase())
  })
  const rootActive = project.memoryStatus === 'added'
  const activeCount = rootActive ? projectRelations.filter((item) => item.status === 'added').length : 0
  const unselectedCount = rootActive ? projectRelations.filter((item) => item.status === 'suggested').length : project.memoryStatus === 'suggested' ? projectRelations.length : 0
  const deactivatedCount = rootActive ? projectRelations.filter((item) => item.status === 'deactivated').length : project.memoryStatus === 'deactivated' ? projectRelations.length : 0

  return (
    <div className="page-content">
      <PageHeader
        eyebrow={null}
        title={project.name}
        action={
          <div className="project-header-actions">
            <button className="secondary-button" onClick={() => onProjectChange(null)}>← Projects</button>
            <label className="select-control">
              <span className="sr-only">Choose project</span>
              <select value={project.id} onChange={(event) => onProjectChange(event.target.value)}>
                {workspace.projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
              <Icon name="chevron" size={14} />
            </label>
          </div>
        }
      />
      <div className="project-summary">
        <span><strong>{activeCount}</strong> active</span>
        <span><strong>{unselectedCount}</strong> not selected</span>
        <span><strong>{deactivatedCount}</strong> deactivated</span>
        <span>Updated {formatDate(project.updatedAt)}</span>
      </div>
      <div className="section-intro">
        <div>
          <h2>Attribute tree</h2>
          <p>Click a project or attribute circle to change its state. Open a tuple from the right column; use ↻ to change only that tuple.</p>
        </div>
        <div className="project-tree-legend" aria-label="Project attribute state legend">
          <span><i className="is-active" />Active</span>
          <span><i className="is-unselected" />Not selected</span>
          <span><i className="is-deactivated" />Deactivated</span>
        </div>
      </div>
      <div className="toolbar project-memory-toolbar">
        <label className="search-field">
          <Icon name="search" size={15} />
          <input id="project-attribute-search" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Search project attributes" aria-label="Search project attributes" />
          <kbd>⌘K</kbd>
        </label>
        <div className="filter-tabs" aria-label="Project attribute status">
          {(['all', 'active', 'unselected', 'deactivated'] as const).map((item) => (
            <button key={item} className={filter === item ? 'active' : ''} onClick={() => onFilterChange(item)}>
              {item === 'all' ? 'All' : item === 'active' ? 'Active' : item === 'unselected' ? 'Not selected' : 'Deactivated'}
            </button>
          ))}
        </div>
      </div>
      <ProjectAttributeTree
        project={project}
        attributes={projectAttributes}
        relations={projectRelations}
        sources={workspace.sources}
        onOpenTuple={(attributeId, node) => onOpenTuple({ projectId: project.id, attributeId, node })}
        onRootStatusChange={(status) => onProjectRootChange(project, status)}
        onNodeStatusChange={(attribute, node, status) => onProjectStatusChange(project.id, attribute, node, status)}
      />
    </div>
  )
}

function ProjectPicker({ workspace, onSelect }: { workspace: WorkspaceSnapshot; onSelect: (id: string) => void }) {
  return (
    <div className="page-content">
      <PageHeader eyebrow={null} title="Projects" description="Choose a project first. Its available attributes will open as a left-rooted tree." />
      <div className="project-picker-head">
        <span>Choose a project</span>
        <span>{workspace.projects.length} active</span>
      </div>
      <div className="project-picker">
        {workspace.projects.map((project, index) => {
          const relations = workspace.projectAttributes.filter((item) => item.projectId === project.id)
          const activeCount = relations.filter((item) => item.status === 'added').length
          const unselectedCount = relations.filter((item) => item.status === 'suggested').length
          return (
            <button className="project-picker-row" key={project.id} onClick={() => onSelect(project.id)}>
              <span className="project-index">{String(index + 1).padStart(2, '0')}</span>
              <span className="project-picker-title"><strong>{project.name}</strong><small>{project.description}</small></span>
              <span className="project-picker-stat"><strong>{activeCount}</strong> active</span>
              <span className="project-picker-stat"><strong>{unselectedCount}</strong> not selected</span>
              <span className="project-picker-date">Updated {formatDate(project.updatedAt)}</span>
              <Icon name="arrow" size={17} />
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ReviewView({ workspace, selectedId, onSelect, onUpdate }: {
  workspace: WorkspaceSnapshot
  selectedId: string | null
  onSelect: (id: string) => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
}) {
  const pending = workspace.attributes.filter((attribute) => attribute.status === 'suggested')
  const keepAll = () => pending.forEach((attribute) => onUpdate(attribute, { status: 'kept' }))

  return (
    <div className="page-content">
      <PageHeader
        title="Review"
        description="New attributes wait here until you decide what belongs in memory."
        action={pending.length ? <button className="secondary-button" onClick={keepAll}>Keep all visible</button> : undefined}
      />
      <div className="review-banner">
        <div className="review-number">{pending.length}</div>
        <div><strong>Ready for review</strong><span>Each suggestion includes its original evidence and confidence.</span></div>
      </div>
      <div className="list-meta"><span>New suggestions</span><span>Newest first</span></div>
      <AttributeList
        attributes={pending}
        sources={workspace.sources}
        selectedId={selectedId}
        onSelect={onSelect}
        onUpdate={onUpdate}
      />
    </div>
  )
}

function SourcesView({ sources, syncing, onSync }: { sources: Source[]; syncing: boolean; onSync: () => void }) {
  return (
    <div className="page-content">
      <PageHeader
        eyebrow={null}
        title="Sources"
        action={<button className="primary-button" onClick={onSync} disabled={syncing}><Icon name="sync" size={15} />{syncing ? 'Syncing…' : 'Sync all'}</button>}
      />
      <div className="source-table">
        <div className="source-table-head"><span>Source</span><span>Items</span><span>Last synced</span><span>Status</span><span /></div>
        {sources.map((source) => (
          <div className="source-row" key={source.id}>
            <div className="source-identity"><SourceGlyph kind={source.kind} /><div><strong>{source.name}</strong><span>{source.description}</span></div></div>
            <span className="numeric">{source.itemCount.toLocaleString()}</span>
            <span>{formatDate(source.lastSyncedAt)}</span>
            <span className={`connection-status ${source.status}`}><i />{source.status === 'connected' ? 'Connected' : source.status}</span>
            <button className="icon-button" aria-label={`More options for ${source.name}`}><Icon name="more" size={17} /></button>
          </div>
        ))}
      </div>
    </div>
  )
}

function SourceGlyph({ kind }: { kind: Source['kind'] }) {
  const letter = kind === 'codex' ? 'C' : kind === 'browser' ? 'B' : kind === 'takeout' ? 'G' : 'M'
  return <span className={`source-glyph ${kind}`}>{letter}</span>
}

function TupleInspector({ attribute, project, relation, source, node, onClose, onUpdate, onNodeStatusChange }: {
  attribute: Attribute
  project: Project
  relation: ProjectAttribute
  source?: Source
  node: TupleNode
  onClose: () => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
  onNodeStatusChange: (status: ProjectAttributeStatus) => void
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(attribute.title)
  const [category, setCategory] = useState(attribute.category)
  const [value, setValue] = useState(attribute.value)
  const [sourceRef, setSourceRef] = useState(attribute.sourceRef)
  const [confidence, setConfidence] = useState(String(Math.round(attribute.confidence * 100)))
  const statusField: Record<TupleNode, keyof Pick<ProjectAttribute, 'valueStatus' | 'sourceStatus' | 'confidenceStatus'>> = {
    value: 'valueStatus',
    source: 'sourceStatus',
    confidence: 'confidenceStatus',
  }
  const ownStatus = relation[statusField[node]]
  const inheritedStatus = project.memoryStatus !== 'added'
    ? project.memoryStatus
    : relation.status !== 'added'
      ? relation.status
      : null
  const inherited = inheritedStatus !== null
  const effectiveStatus = inheritedStatus ?? ownStatus
  const statusLabel: Record<ProjectAttributeStatus, string> = { added: 'Active', suggested: 'Not selected', deactivated: 'Deactivated' }

  const save = () => {
    const parsedConfidence = Number(confidence)
    onUpdate(attribute, {
      title,
      category,
      value,
      sourceRef,
      confidence: Number.isFinite(parsedConfidence) ? Math.min(Math.max(parsedConfidence, 0), 100) / 100 : attribute.confidence,
    }, 'Tuple updated')
    setEditing(false)
  }

  return (
    <aside className="inspector tuple-inspector" aria-label={`${node} tuple inspector`}>
      <div className="inspector-head">
        <span>Tuple / {node}</span>
        <button className="icon-button" onClick={onClose} aria-label="Close tuple inspector"><Icon name="close" size={17} /></button>
      </div>
      <div className="inspector-body">
        <div className="tuple-title-line"><span className={`tuple-state ${effectiveStatus}`}>{statusLabel[effectiveStatus]}</span><small>{inherited ? 'Inherited from parent' : 'Own state'}</small></div>
        <h2>{attribute.title}</h2>
        <table className="tuple-table">
          <tbody>
            <tr><th>project_id</th><td>{project.id}</td></tr>
            <tr><th>attribute_id</th><td>{attribute.id}</td></tr>
            <tr><th>node</th><td>{node}</td></tr>
            <tr><th>title</th><td>{editing ? <input value={title} onChange={(event) => setTitle(event.target.value)} /> : attribute.title}</td></tr>
            <tr><th>category</th><td>{editing ? <input value={category} onChange={(event) => setCategory(event.target.value)} /> : attribute.category}</td></tr>
            <tr className={node === 'value' ? 'is-current' : ''}><th>value</th><td>{editing ? <textarea rows={4} value={value} onChange={(event) => setValue(event.target.value)} /> : attribute.value}</td></tr>
            <tr className={node === 'source' ? 'is-current' : ''}><th>source</th><td>{source?.name ?? 'Unknown source'}</td></tr>
            <tr><th>source_ref</th><td>{editing ? <textarea rows={3} value={sourceRef} onChange={(event) => setSourceRef(event.target.value)} /> : attribute.sourceRef}</td></tr>
            <tr className={node === 'confidence' ? 'is-current' : ''}><th>confidence</th><td>{editing ? <div className="confidence-input"><input type="number" min="0" max="100" value={confidence} onChange={(event) => setConfidence(event.target.value)} /><span>%</span></div> : `${Math.round(attribute.confidence * 100)}%`}</td></tr>
            <tr><th>own_state</th><td>{statusLabel[ownStatus]}</td></tr>
            <tr><th>effective_state</th><td>{statusLabel[effectiveStatus]}</td></tr>
          </tbody>
        </table>
        <div className="inspector-section">
          <div className="inspector-label">Tuple state</div>
          <div className="tuple-state-options">
            {(['added', 'suggested', 'deactivated'] as const).map((status) => (
              <button key={status} className={ownStatus === status ? 'active' : ''} disabled={inherited} onClick={() => onNodeStatusChange(status)}>{statusLabel[status]}</button>
            ))}
          </div>
          {inherited && <p className="tuple-inherited-note">Activate the project and attribute nodes before changing this tuple state.</p>}
        </div>
      </div>
      <div className="inspector-foot">
        {editing ? <><button className="secondary-button" onClick={() => setEditing(false)}>Cancel</button><button className="primary-button" onClick={save}>Save tuple</button></> : <button className="primary-button" onClick={() => setEditing(true)}>Edit tuple</button>}
      </div>
    </aside>
  )
}

function Inspector({ attribute, source, projects, allProjects, onClose, onUpdate, onProjectStatusChange, onDelete }: {
  attribute: Attribute
  source?: Source
  projects: Project[]
  allProjects: Project[]
  onClose: () => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
  onProjectStatusChange: (projectId: string, status: ProjectAttributeStatus) => void
  onDelete: (attribute: Attribute) => void
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(attribute.title)
  const [value, setValue] = useState(attribute.value)
  const [category, setCategory] = useState(attribute.category)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const save = () => {
    onUpdate(attribute, { title, value, category }, 'Attribute updated')
    setEditing(false)
  }

  return (
    <aside className="inspector" aria-label="Attribute inspector">
      <div className="inspector-head">
        <span>Attribute</span>
        <button className="icon-button" onClick={onClose} aria-label="Close inspector"><Icon name="close" size={17} /></button>
      </div>
      <div className="inspector-body">
        <div className="inspector-status-line">
          <span className={`status-pill ${attribute.status}`}>{attribute.status}</span>
          <span>Updated {formatDate(attribute.updatedAt)}</span>
        </div>
        {editing ? (
          <div className="edit-form">
            <label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
            <label>Category<input value={category} onChange={(event) => setCategory(event.target.value)} /></label>
            <label>Details<textarea rows={5} value={value} onChange={(event) => setValue(event.target.value)} /></label>
            <div className="form-actions"><button className="primary-button" onClick={save}>Save changes</button><button className="secondary-button" onClick={() => setEditing(false)}>Cancel</button></div>
          </div>
        ) : (
          <>
            <h2>{attribute.title}</h2>
            <p className="attribute-value">{attribute.value}</p>
            <button className="secondary-button edit-button" onClick={() => setEditing(true)}>Edit attribute</button>
          </>
        )}
        <div className="inspector-section">
          <div className="inspector-label">Confidence</div>
          <div className="confidence-line"><div><span style={{ width: `${attribute.confidence * 100}%` }} /></div><strong>{Math.round(attribute.confidence * 100)}%</strong></div>
        </div>
        <div className="inspector-section">
          <div className="inspector-label">Source</div>
          <div className="source-reference">
            {source && <SourceGlyph kind={source.kind} />}
            <div><strong>{source?.name ?? 'Unknown source'}</strong><span>{attribute.sourceRef}</span></div>
          </div>
          <blockquote>{attribute.excerpt}</blockquote>
          <div className="observed-date">Observed {formatDate(attribute.observedAt)}</div>
        </div>
        <div className="inspector-section">
          <div className="inspector-label">Related projects</div>
          <div className="project-options">
            {allProjects.map((project) => {
              const active = projects.some((item) => item.id === project.id)
              return <button key={project.id} className={active ? 'active' : ''} onClick={() => onProjectStatusChange(project.id, active ? 'suggested' : 'added')}><span>{active ? '✓' : '+'}</span>{project.name}</button>
            })}
          </div>
        </div>
      </div>
      <div className="inspector-foot">
        <button className={`danger-button ${confirmDelete ? 'confirming' : ''}`} onClick={() => confirmDelete ? onDelete(attribute) : setConfirmDelete(true)}>{confirmDelete ? 'Confirm delete' : 'Delete attribute'}</button>
        {attribute.status !== 'ignored' && <button className="secondary-button" onClick={() => onUpdate(attribute, { status: 'ignored' }, 'Attribute ignored')}>Ignore</button>}
        {attribute.status !== 'kept' && <button className="primary-button" onClick={() => onUpdate(attribute, { status: 'kept' }, 'Attribute kept')}>Keep</button>}
      </div>
    </aside>
  )
}

export default App
