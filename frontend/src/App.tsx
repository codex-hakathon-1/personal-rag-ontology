import { useEffect, useMemo, useState } from 'react'
import { api } from './api/client'
import type { Attribute, AttributePatch, Project, Source, WorkspaceSnapshot } from './domain'

type View = 'memory' | 'projects' | 'review' | 'sources'
type IconName = View | 'search' | 'close' | 'more' | 'chevron' | 'check' | 'minus' | 'arrow' | 'sync' | 'spark'

const navItems: { id: View; label: string }[] = [
  { id: 'memory', label: 'Memory' },
  { id: 'projects', label: 'Projects' },
  { id: 'review', label: 'Review' },
  { id: 'sources', label: 'Sources' },
]

function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    memory: <><path d="M4 5.5h12M4 10h12M4 14.5h8" /></>,
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
  const [view, setView] = useState<View>('memory')
  const [selectedAttributeId, setSelectedAttributeId] = useState<string | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState('project-rag')
  const [query, setQuery] = useState('')
  const [memoryFilter, setMemoryFilter] = useState<'all' | 'kept' | 'suggested' | 'ignored'>('all')
  const [notice, setNotice] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    api.getWorkspace().then(setWorkspace).catch(() => setNotice('Could not load the workspace.'))
  }, [])

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setView('memory')
        window.setTimeout(() => document.getElementById('memory-search')?.focus(), 0)
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
  const pendingCount = workspace?.attributes.filter((attribute) => attribute.status === 'suggested').length ?? 0

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
    setWorkspace({ ...workspace, attributes: workspace.attributes.filter((item) => item.id !== attribute.id) })
    try {
      await api.deleteAttribute(attribute.id)
      setNotice('Attribute deleted')
    } catch {
      setWorkspace(previous)
      setNotice('The attribute could not be deleted.')
    }
  }

  const addAttributeToProject = async (projectId: string, attribute: Attribute) => {
    if (!workspace) return
    const previous = workspace
    const existing = workspace.projectAttributes.find((item) => item.projectId === projectId && item.attributeId === attribute.id)
    const optimistic = existing
      ? workspace.projectAttributes.map((item) => item === existing ? { ...item, status: 'added' as const } : item)
      : [...workspace.projectAttributes, { projectId, attributeId: attribute.id, status: 'added' as const, suggestedAt: new Date().toISOString() }]
    setWorkspace({ ...workspace, projectAttributes: optimistic })
    try {
      const updated = await api.updateProjectAttribute(projectId, attribute.id, 'added')
      setWorkspace((current) => current ? {
        ...current,
        projectAttributes: current.projectAttributes.map((item) => item.projectId === projectId && item.attributeId === attribute.id ? updated : item),
      } : current)
      setNotice('Added to project')
    } catch {
      setWorkspace(previous)
      setNotice('The project could not be updated.')
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
    <div className={`app-shell ${selectedAttribute ? 'has-inspector' : ''}`}>
      <Sidebar view={view} pendingCount={pendingCount} onChange={(nextView) => { setView(nextView); setSelectedAttributeId(null) }} />
      <main className="main-pane">
        {!workspace ? (
          <div className="loading-state"><span className="loading-mark" />Loading local memory…</div>
        ) : (
          <>
            {view === 'memory' && (
              <MemoryView
                workspace={workspace}
                query={query}
                onQueryChange={setQuery}
                filter={memoryFilter}
                onFilterChange={setMemoryFilter}
                selectedId={selectedAttributeId}
                onSelect={setSelectedAttributeId}
                onUpdate={updateAttribute}
              />
            )}
            {view === 'projects' && (
              <ProjectsView
                workspace={workspace}
                selectedProjectId={selectedProjectId}
                onProjectChange={setSelectedProjectId}
                selectedId={selectedAttributeId}
                onSelect={setSelectedAttributeId}
                onUpdate={updateAttribute}
                onAddToProject={addAttributeToProject}
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
          projects={workspace.projects.filter((project) => selectedAttribute.projectIds.includes(project.id))}
          allProjects={workspace.projects}
          onClose={() => setSelectedAttributeId(null)}
          onUpdate={updateAttribute}
          onDelete={deleteAttribute}
        />
      )}
      {notice && <div className="notice" role="status"><Icon name="check" size={15} />{notice}</div>}
    </div>
  )
}

function Sidebar({ view, pendingCount, onChange }: { view: View; pendingCount: number; onChange: (view: View) => void }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true"><i /><b /></span>
        <span className="brand-word">Index</span>
        <span className="brand-edition">Local</span>
      </div>
      <nav aria-label="Primary navigation">
        {navItems.map((item) => (
          <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} onClick={() => onChange(item.id)}>
            <Icon name={item.id} size={17} />
            <span>{item.label}</span>
            {item.id === 'review' && pendingCount > 0 && <span className="nav-count">{pendingCount}</span>}
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

function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description: string; action?: React.ReactNode }) {
  const sectionLabels: Record<string, string> = {
    Memory: '01 / Local archive',
    Review: '03 / Curation queue',
    Sources: '04 / Input registry',
  }

  return (
    <header className="page-header">
      <div className="page-heading">
        <div className="eyebrow">{eyebrow ?? sectionLabels[title] ?? 'Local index'}</div>
        <h1>{title}</h1>
      </div>
      <div className="page-context">
        <p>{description}</p>
        {action && <div className="header-action">{action}</div>}
      </div>
    </header>
  )
}

function MemoryView({ workspace, query, onQueryChange, filter, onFilterChange, selectedId, onSelect, onUpdate }: {
  workspace: WorkspaceSnapshot
  query: string
  onQueryChange: (value: string) => void
  filter: 'all' | 'kept' | 'suggested' | 'ignored'
  onFilterChange: (value: 'all' | 'kept' | 'suggested' | 'ignored') => void
  selectedId: string | null
  onSelect: (id: string) => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
}) {
  const filtered = workspace.attributes.filter((attribute) => {
    const matchesFilter = filter === 'all' || attribute.status === filter
    const haystack = `${attribute.title} ${attribute.category} ${attribute.value}`.toLowerCase()
    return matchesFilter && haystack.includes(query.toLowerCase())
  })

  return (
    <div className="page-content">
      <PageHeader title="Memory" description="The facts, decisions, and preferences that can inform your work." />
      <div className="toolbar">
        <label className="search-field">
          <Icon name="search" size={15} />
          <input id="memory-search" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Search memory" aria-label="Search memory" />
          <kbd>⌘K</kbd>
        </label>
        <div className="filter-tabs" aria-label="Memory status">
          {(['all', 'kept', 'suggested', 'ignored'] as const).map((item) => (
            <button key={item} className={filter === item ? 'active' : ''} onClick={() => onFilterChange(item)}>
              {item[0].toUpperCase() + item.slice(1)}
            </button>
          ))}
        </div>
      </div>
      <div className="list-meta">
        <span>{filtered.length} attributes</span>
        <span>Sorted by newest</span>
      </div>
      <AttributeList
        attributes={filtered}
        sources={workspace.sources}
        selectedId={selectedId}
        onSelect={onSelect}
        onUpdate={onUpdate}
      />
    </div>
  )
}

function AttributeList({ attributes, sources, selectedId, onSelect, onUpdate, projectMode = false, addedAttributeIds, onAddToProject }: {
  attributes: Attribute[]
  sources: Source[]
  selectedId: string | null
  onSelect: (id: string) => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
  projectMode?: boolean
  addedAttributeIds?: Set<string>
  onAddToProject?: (attribute: Attribute) => void
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
          projectMode={projectMode}
          isAddedToProject={addedAttributeIds?.has(attribute.id) ?? false}
          onAddToProject={onAddToProject}
        />
      ))}
    </div>
  )
}

function AttributeRow({ attribute, source, selected, onSelect, onUpdate, projectMode, isAddedToProject, onAddToProject }: {
  attribute: Attribute
  source?: Source
  selected: boolean
  onSelect: () => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
  projectMode: boolean
  isAddedToProject: boolean
  onAddToProject?: (attribute: Attribute) => void
}) {
  return (
    <div className={`attribute-row ${selected ? 'selected' : ''} ${attribute.status === 'ignored' ? 'is-ignored' : ''}`} role="button" tabIndex={0} onClick={onSelect} onKeyDown={(event) => { if (event.key === 'Enter') onSelect() }}>
      <div className={`status-tick ${attribute.status}`} aria-hidden="true">{attribute.status === 'kept' && <Icon name="check" size={11} />}</div>
      <div className="attribute-title">{attribute.title}</div>
      <span className="category-label">{attribute.category}</span>
      <span className="source-label">{sourceLabel(source)}</span>
      <div className="row-actions">
        {projectMode && !isAddedToProject && (
          <button className="text-action add-action" onClick={(event) => { event.stopPropagation(); onAddToProject?.(attribute) }}>Add to project</button>
        )}
        {attribute.status !== 'kept' && (
          <button className="text-action" onClick={(event) => { event.stopPropagation(); onUpdate(attribute, { status: 'kept' }, 'Attribute kept') }}>Keep</button>
        )}
        {attribute.status !== 'ignored' && (
          <button className="text-action quiet" onClick={(event) => { event.stopPropagation(); onUpdate(attribute, { status: 'ignored' }, 'Attribute ignored') }}>Ignore</button>
        )}
        {projectMode && <button className="text-action quiet" aria-label={`Edit ${attribute.title}`} onClick={(event) => { event.stopPropagation(); onSelect() }}>Edit</button>}
      </div>
    </div>
  )
}

function ProjectsView({ workspace, selectedProjectId, onProjectChange, selectedId, onSelect, onUpdate, onAddToProject }: {
  workspace: WorkspaceSnapshot
  selectedProjectId: string
  onProjectChange: (id: string) => void
  selectedId: string | null
  onSelect: (id: string) => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
  onAddToProject: (projectId: string, attribute: Attribute) => void
}) {
  const project = workspace.projects.find((item) => item.id === selectedProjectId) ?? workspace.projects[0]
  const projectAttributes = workspace.attributes.filter((attribute) => attribute.projectIds.includes(project.id) && attribute.status !== 'ignored')
  const groups = useMemo(() => {
    return projectAttributes.reduce<Record<string, Attribute[]>>((result, attribute) => {
      result[attribute.category] = [...(result[attribute.category] ?? []), attribute]
      return result
    }, {})
  }, [projectAttributes])
  const projectRelations = workspace.projectAttributes.filter((item) => item.projectId === project.id)
  const addedAttributeIds = new Set(projectRelations.filter((item) => item.status === 'added').map((item) => item.attributeId))
  const addedCount = addedAttributeIds.size
  const suggestedCount = projectRelations.filter((item) => item.status === 'suggested').length

  return (
    <div className="page-content">
      <PageHeader
        eyebrow="02 / Active project"
        title={project.name}
        description={project.description}
        action={
          <label className="select-control">
            <span className="sr-only">Choose project</span>
            <select value={project.id} onChange={(event) => onProjectChange(event.target.value)}>
              {workspace.projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            <Icon name="chevron" size={14} />
          </label>
        }
      />
      <div className="project-summary">
        <span><strong>{addedCount}</strong> in project</span>
        <span><strong>{suggestedCount}</strong> suggested</span>
        <span>Updated {formatDate(project.updatedAt)}</span>
      </div>
      <div className="section-intro">
        <div>
          <h2>Project attributes</h2>
          <p>Review suggestions and keep only what should shape this project.</p>
        </div>
        <span className="suggestion-label"><Icon name="spark" size={14} />Suggested from your sources</span>
      </div>
      <div className="category-groups">
        {Object.entries(groups).map(([category, attributes]) => (
          <section className="category-group" key={category}>
            <div className="category-heading"><h3>{category}</h3><span>{attributes.length}</span></div>
            <AttributeList
              attributes={attributes}
              sources={workspace.sources}
              selectedId={selectedId}
              onSelect={onSelect}
              onUpdate={onUpdate}
              projectMode
              addedAttributeIds={addedAttributeIds}
              onAddToProject={(attribute) => onAddToProject(project.id, attribute)}
            />
          </section>
        ))}
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
        title="Sources"
        description="Local inputs that contribute evidence to your memory."
        action={<button className="primary-button" onClick={onSync} disabled={syncing}><Icon name="sync" size={15} />{syncing ? 'Syncing…' : 'Sync all'}</button>}
      />
      <div className="sources-note"><span className="shield-mark">✓</span><div><strong>Source data stays local</strong><p>Index reads from local exports and databases. Nothing is uploaded by this interface.</p></div></div>
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

function Inspector({ attribute, source, projects, allProjects, onClose, onUpdate, onDelete }: {
  attribute: Attribute
  source?: Source
  projects: Project[]
  allProjects: Project[]
  onClose: () => void
  onUpdate: (attribute: Attribute, patch: AttributePatch, message?: string) => void
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

  const toggleProject = (projectId: string) => {
    const next = attribute.projectIds.includes(projectId)
      ? attribute.projectIds.filter((id) => id !== projectId)
      : [...attribute.projectIds, projectId]
    onUpdate(attribute, { projectIds: next }, 'Projects updated')
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
              return <button key={project.id} className={active ? 'active' : ''} onClick={() => toggleProject(project.id)}><span>{active ? '✓' : '+'}</span>{project.name}</button>
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
