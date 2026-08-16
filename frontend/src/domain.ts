export type SourceKind = 'codex' | 'browser' | 'takeout' | 'manual'
export type SourceStatus = 'connected' | 'syncing' | 'attention'
export type AttributeStatus = 'suggested' | 'kept' | 'ignored'
export type ProjectAttributeStatus = 'suggested' | 'added' | 'deactivated'
export type ProjectAttributeNode = 'attribute' | 'value' | 'source' | 'confidence'

export interface Source {
  id: string
  name: string
  kind: SourceKind
  description: string
  itemCount: number
  lastSyncedAt: string
  status: SourceStatus
}

export interface Attribute {
  id: string
  title: string
  value: string
  category: string
  sourceId: string
  confidence: number
  status: AttributeStatus
  excerpt: string
  sourceRef: string
  observedAt: string
  updatedAt: string
}

export interface Project {
  id: string
  name: string
  description: string
  status: 'active' | 'archived'
  memoryStatus: ProjectAttributeStatus
  updatedAt: string
}

export interface ProjectAttribute {
  projectId: string
  attributeId: string
  status: ProjectAttributeStatus
  valueStatus: ProjectAttributeStatus
  sourceStatus: ProjectAttributeStatus
  confidenceStatus: ProjectAttributeStatus
  suggestedAt: string
}

export interface WorkspaceSnapshot {
  sources: Source[]
  attributes: Attribute[]
  projects: Project[]
  projectAttributes: ProjectAttribute[]
}

export interface AttributePatch {
  title?: string
  value?: string
  category?: string
  confidence?: number
  sourceRef?: string
  status?: AttributeStatus
}

export interface ProjectPatch {
  memoryStatus?: ProjectAttributeStatus
}
