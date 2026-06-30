import { useState, useEffect } from 'react'
import {
  IconFiles, IconSearch, IconBookmark, IconHelpCircle,
  IconChevronLeft, IconChevronRight,
  IconFileText, IconClipboard, IconNotes, IconPencil, IconChartBar, IconSchool,
  IconUpload, IconLock,
  IconClipboardCheck, IconCircleCheck, IconCircleX, IconClock,
} from '@tabler/icons-react'
import api from '../api/client'
import { SearchOverlay } from './SearchOverlay'

const CATEGORIES = [
  { value: 'artikel',        label: 'Reference Articles', icon: <IconFileText size={15} stroke={1.5} /> },
  { value: 'proposal',       label: 'Research Proposal',  icon: <IconClipboard size={15} stroke={1.5} /> },
  { value: 'catatan_sv',     label: 'SV Notes',           icon: <IconNotes size={15} stroke={1.5} /> },
  { value: 'draf',           label: 'Own Draft',          icon: <IconPencil size={15} stroke={1.5} /> },
  { value: 'data',           label: 'Data / Transcript',  icon: <IconChartBar size={15} stroke={1.5} /> },
  { value: 'panduan_format', label: 'Format Guide',       icon: <IconSchool size={15} stroke={1.5} /> },
]

const SOURCE_LABEL = {
  openalex: 'OpenAlex',
  semantic_scholar: 'Semantic Scholar',
  crossref: 'CrossRef',
}

function RailIcon({ icon, active, title, onClick, style }) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      style={{
        width: 32, height: 32,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: active ? 'var(--accent-soft)' : 'none',
        border: active ? '1px solid var(--accent)' : '1px solid transparent',
        borderRadius: 6, cursor: 'pointer',
        color: active ? 'var(--ink)' : 'var(--ink-soft)',
        transition: 'background 0.1s',
        ...style,
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--line)' }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'none' }}
    >
      {icon}
    </button>
  )
}

function SVFeedbackPanel({ projectId }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    api.get(`/projects/${projectId}/sv-feedback`)
      .then(r => { setItems(r.data); setLoading(false) })
      .catch(() => { setError('Failed to load feedback.'); setLoading(false) })
  }, [projectId])

  async function handleStatusChange(itemId, newStatus) {
    try {
      await api.patch(`/projects/${projectId}/sv-feedback/${itemId}`, { status: newStatus })
      setItems(prev => prev.map(i =>
        i.id === itemId ? { ...i, status: newStatus } : i
      ))
    } catch {
      // silent fail — item stays as is
    }
  }

  if (loading) return <div style={{ padding: 16, color: 'var(--ink-soft)', fontSize: 13 }}>Loading...</div>
  if (error) return <div style={{ padding: 16, color: '#EF4444', fontSize: 13 }}>{error}</div>
  if (items.length === 0) return (
    <div style={{ padding: 16, color: 'var(--ink-soft)', fontSize: 13, lineHeight: 1.5 }}>
      No SV feedback yet. Upload a supervisor notes document (category: SV Notes) to extract feedback items.
    </div>
  )

  const open = items.filter(i => i.status === 'open')
  const addressed = items.filter(i => i.status === 'addressed')
  const dismissed = items.filter(i => i.status === 'dismissed')

  const statusIcon = (status) => {
    if (status === 'addressed') return <IconCircleCheck size={15} stroke={1.5} style={{ color: '#16A34A', flexShrink: 0 }} />
    if (status === 'dismissed') return <IconCircleX size={15} stroke={1.5} style={{ color: 'var(--ink-soft)', flexShrink: 0 }} />
    return <IconClock size={15} stroke={1.5} style={{ color: '#F59E0B', flexShrink: 0 }} />
  }

  function FeedbackGroup({ label, groupItems }) {
    if (!groupItems.length) return null
    return (
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.05em', padding: '0 14px', marginBottom: 4 }}>
          {label} ({groupItems.length})
        </div>
        {groupItems.map(item => (
          <div key={item.id} style={{
            display: 'flex', gap: 8, alignItems: 'flex-start',
            padding: '8px 14px', borderBottom: '1px solid var(--line)',
          }}>
            <div style={{ paddingTop: 2 }}>{statusIcon(item.status)}</div>
            <div style={{ flex: 1, fontSize: 13, color: 'var(--ink)', lineHeight: 1.4 }}>
              {item.feedback_text}
            </div>
            <select
              value={item.status}
              onChange={e => handleStatusChange(item.id, e.target.value)}
              style={{
                fontSize: 11, border: '1px solid var(--line)', borderRadius: 4,
                background: 'var(--bg)', color: 'var(--ink)', padding: '2px 4px',
                cursor: 'pointer', flexShrink: 0,
              }}
            >
              <option value="open">Open</option>
              <option value="addressed">Addressed</option>
              <option value="dismissed">Dismissed</option>
            </select>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div style={{ overflowY: 'auto', flex: 1 }}>
      <FeedbackGroup label="Open" groupItems={open} />
      <FeedbackGroup label="Addressed" groupItems={addressed} />
      <FeedbackGroup label="Dismissed" groupItems={dismissed} />
    </div>
  )
}

export function SourcePanel({ documents, onUpload, tier, uploading, collapsed, onToggleCollapse, onDeleteDoc, projectId, onAcceptArticle, onShowHelp }) {
  const [activePanel, setActivePanel] = useState('docs')
  const [activeCategory, setActiveCategory] = useState('artikel')
  const [previewDocId, setPreviewDocId] = useState(null)
  const [previewText, setPreviewText] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState(false)
  const [bibData, setBibData] = useState(null)
  const [bibLoading, setBibLoading] = useState(false)

  const [searchOpen, setSearchOpen] = useState(false)

  // legacy search state — kept to avoid breaking handleSearch/handleAccept refs below
  const [searchQuery, setSearchQuery] = useState('')
  const [yearFrom, setYearFrom] = useState('')
  const [yearTo, setYearTo] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [expandedAbstract, setExpandedAbstract] = useState(null)
  const [accepting, setAccepting] = useState(null)

  async function handlePreviewDoc(docId) {
    if (previewDocId === docId) {
      setPreviewDocId(null); setPreviewText(null); return
    }
    setPreviewDocId(docId); setPreviewLoading(true); setPreviewError(false)
    try {
      const { data } = await api.get(`/documents/${docId}/preview`)
      setPreviewText(data)
    } catch {
      setPreviewError(true)
    } finally {
      setPreviewLoading(false)
    }
  }

  async function handleSearch() {
    if (searchQuery.trim().length < 3) {
      setSearchError('Search term too short (minimum 3 characters).')
      return
    }
    setSearching(true)
    setSearchError('')
    setSearchResults([])
    try {
      const params = new URLSearchParams({ q: searchQuery.trim(), project_id: projectId })
      if (yearFrom) params.append('year_from', yearFrom)
      if (yearTo) params.append('year_to', yearTo)
      const { data } = await api.get(`/search/articles?${params}`)
      setSearchResults(data.results)
      if (data.results.length === 0) setSearchError('No results found. Try a different keyword.')
    } catch (err) {
      setSearchError(err.response?.data?.detail || 'Search failed. Please try again.')
    }
    setSearching(false)
  }

  async function handleAccept(article, index) {
    setAccepting(index)
    try {
      await onAcceptArticle(article)
      setSearchResults(prev => prev.filter((_, i) => i !== index))
      if (expandedAbstract === index) setExpandedAbstract(null)
    } catch (err) {
      setSearchError(err.response?.data?.detail || 'Failed to accept article. ' + (err.response?.status === 409 ? 'Article already added.' : 'Try again.'))
    }
    setAccepting(null)
  }

  const docCount = (documents || []).length
  const maxDocs = tier === 'pro' ? 5 : 1
  const uploadDisabled = docCount >= maxDocs
  const grouped = CATEGORIES.map(cat => ({
    ...cat,
    docs: (documents || []).filter(d => d.category === cat.value)
  }))

  function handleDelete(e, docId, filename) {
    e.stopPropagation()
    if (window.confirm(`Delete "${filename}"? All document chunks and embeddings will be removed.`)) {
      onDeleteDoc(docId)
    }
  }

  if (collapsed) {
    return (
      <div style={{
        width: 40, flexShrink: 0,
        borderRight: '1px solid var(--line)',
        background: 'var(--card)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', paddingTop: 10, gap: 2,
      }}>
        <button
          onClick={onToggleCollapse}
          title="Expand panel"
          style={{
            width: 32, height: 32,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'none', border: '1px solid transparent',
            borderRadius: 6, cursor: 'pointer', color: 'var(--ink-soft)',
          }}
        >
          <IconChevronRight size={18} stroke={1.5} />
        </button>
        <div style={{ width: '80%', height: '1px', background: 'var(--line)', margin: '4px 0' }} />
        <RailIcon icon={<IconFiles size={18} stroke={1.5} />} title="Sources" onClick={() => { onToggleCollapse(); setActivePanel('docs') }} />
        <RailIcon icon={<IconSearch size={18} stroke={1.5} />} title="Cari Artikel" onClick={() => { onToggleCollapse(); setSearchOpen(true) }} />
        <RailIcon icon={<IconBookmark size={18} stroke={1.5} />} title="References" onClick={() => { onToggleCollapse(); setActivePanel('bibliography') }} />
        <RailIcon
          icon={<IconClipboardCheck size={18} stroke={1.5} />}
          title="SV Feedback"
          onClick={() => { onToggleCollapse(); setActivePanel('sv-feedback') }}
        />
        <div style={{ flex: 1 }} />
        <RailIcon icon={<IconHelpCircle size={18} stroke={1.5} />} title="Help & documentation" onClick={onShowHelp} style={{ marginBottom: 10 }} />
      </div>
    )
  }

  return (
    <div style={{
      width: 260, flexShrink: 0, borderRight: '1px solid var(--line)',
      display: 'flex', flexDirection: 'row', background: 'var(--card)',
      overflow: 'hidden',
    }}>
      <SearchOverlay
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        projectId={projectId}
        tier={tier}
        onAccepted={onAcceptArticle}
      />
      {/* ICON RAIL */}
      <div style={{
        width: 40, flexShrink: 0,
        borderRight: '1px solid var(--line)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', paddingTop: 10, gap: 2,
        background: 'var(--bg)',
      }}>
        <RailIcon icon={<IconFiles size={18} stroke={1.5} />} active={activePanel === 'docs'} title="Sources" onClick={() => setActivePanel('docs')} />
        <RailIcon icon={<IconSearch size={18} stroke={1.5} />} active={searchOpen} title="Cari Artikel" onClick={() => setSearchOpen(true)} />
        <RailIcon icon={<IconBookmark size={18} stroke={1.5} />} active={activePanel === 'bibliography'} title="References" onClick={() => setActivePanel('bibliography')} />
        <RailIcon
          icon={<IconClipboardCheck size={18} stroke={1.5} />}
          active={activePanel === 'sv-feedback'}
          title="SV Feedback"
          onClick={() => setActivePanel('sv-feedback')}
        />
        <div style={{ flex: 1 }} />
        <RailIcon icon={<IconHelpCircle size={18} stroke={1.5} />} title="Help & documentation" onClick={onShowHelp} style={{ marginBottom: 10 }} />
      </div>

      {/* PANEL CONTENT */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
            {activePanel === 'docs' ? 'Sources' : activePanel === 'search' ? 'Search' : activePanel === 'sv-feedback' ? 'SV Feedback' : 'References'}
          </span>
          <button
            onClick={onToggleCollapse}
            title="Collapse panel"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', display: 'flex', padding: 2, borderRadius: 4 }}
          >
            <IconChevronLeft size={16} stroke={1.5} />
          </button>
        </div>

        {activePanel === 'docs' ? (
          <>
            <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
              {grouped.map(cat => (
                <div key={cat.value}>
                  <button
                    onClick={() => setActiveCategory(activeCategory === cat.value ? null : cat.value)}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      width: '100%', padding: '7px 12px',
                      background: activeCategory === cat.value ? 'var(--accent-soft)' : 'transparent',
                      border: 'none', cursor: 'pointer', textAlign: 'left', gap: 8,
                    }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--ink-soft)' }}>
                      {cat.icon}
                      <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}>
                        {cat.label}
                      </span>
                    </span>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 11,
                      color: cat.docs.length > 0 ? '#185FA5' : 'var(--ink-soft)',
                      background: cat.docs.length > 0 ? '#E6F1FB' : 'var(--line)',
                      borderRadius: 10, padding: '1px 7px', minWidth: 20, textAlign: 'center',
                    }}>
                      {cat.docs.length}
                    </span>
                  </button>
                  {activeCategory === cat.value && cat.docs.length === 0 && (
                    <p style={{
                      padding: '8px 16px 8px 32px',
                      fontFamily: 'var(--font-body)', fontSize: 12,
                      color: 'var(--ink-soft)', fontStyle: 'italic',
                      margin: 0,
                    }}>
                      No documents in this category.
                    </p>
                  )}
                  {activeCategory === cat.value && cat.docs.map(doc => (
                    <div key={doc.id} style={{ padding: '6px 12px 6px 28px' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 4 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p
                            onClick={() => handlePreviewDoc(doc.id)}
                            style={{
                              margin: 0, fontFamily: 'var(--font-body)', fontSize: 12,
                              color: previewDocId === doc.id ? 'var(--accent)' : 'var(--ink-soft)',
                              wordBreak: 'break-word', cursor: 'pointer',
                              textDecoration: previewDocId === doc.id ? 'underline' : 'none',
                            }}
                          >
                            {doc.filename}
                          </p>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)' }}>
                            {doc.chunk_count} chunk
                          </span>
                        </div>
                        <button
                          onClick={e => handleDelete(e, doc.id, doc.filename)}
                          title="Delete this document"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 14, padding: '2px 4px', flexShrink: 0, lineHeight: 1 }}
                        >x</button>
                      </div>
                      {previewDocId === doc.id && (
                        <div style={{
                          marginTop: 6, background: 'var(--bg)', border: '1px solid var(--line)',
                          borderRadius: 'var(--radius-sm)', padding: '10px 12px',
                          fontSize: 12, maxHeight: 200, overflowY: 'auto', whiteSpace: 'pre-wrap',
                          fontFamily: 'var(--font-body)', color: 'var(--ink-soft)',
                        }}>
                          {previewLoading && 'Loading preview...'}
                          {previewError && 'Failed to load -- try again.'}
                          {!previewLoading && !previewError && previewText && (
                            <>
                              <p style={{ margin: '0 0 6px', whiteSpace: 'pre-wrap' }}>{previewText.preview_text}</p>
                              <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)' }}>
                                Showing {previewText.showing_chunks} of {previewText.chunk_count} sections
                              </p>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div style={{ borderTop: '1px solid var(--line)' }}>
              <button
                onClick={uploadDisabled || uploading ? undefined : onUpload}
                disabled={uploadDisabled || uploading}
                title={uploadDisabled ? 'Free tier: 1 document only. Upgrade to Pro for up to 5 documents.' : ''}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  width: 'calc(100% - 24px)', margin: '8px 12px',
                  padding: '7px 10px',
                  background: 'none',
                  border: uploadDisabled ? '1px dashed var(--line)' : '1px dashed var(--ink-soft)',
                  borderRadius: 6, cursor: uploadDisabled || uploading ? 'not-allowed' : 'pointer',
                  color: uploadDisabled ? 'var(--ink-soft)' : 'var(--ink)',
                  fontFamily: 'var(--font-body)', fontSize: 12,
                  opacity: uploadDisabled || uploading ? 0.5 : 1,
                }}
              >
                {uploadDisabled
                  ? <><IconLock size={14} stroke={1.5} />{' '}Limit reached</>
                  : uploading
                  ? 'Processing...'
                  : <><IconUpload size={14} stroke={1.5} />{' '}Upload document</>
                }
              </button>
              <p style={{ fontSize: 11, color: 'var(--ink-soft)', textAlign: 'center', margin: '0 12px 8px', fontFamily: 'var(--font-mono)' }}>
                PDF, DOCX, XLSX, PPTX{' '}max 20MB
              </p>
            </div>
          </>
        ) : activePanel === 'sv-feedback' ? (
          <SVFeedbackPanel projectId={projectId} />
        ) : (
          <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
            {!bibData && !bibLoading && (
              <button
                onClick={async () => {
                  setBibLoading(true)
                  try {
                    const { data } = await api.get(`/projects/${projectId}/bibliography`)
                    setBibData(data)
                  } catch { setBibData({ sources: [] }) }
                  finally { setBibLoading(false) }
                }}
                style={{ padding: '8px 14px', background: 'var(--accent-soft)', border: '1px solid var(--accent)', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11 }}
              >
                Load References
              </button>
            )}
            {bibLoading && <p style={{ color: 'var(--ink-soft)', fontSize: 13 }}>Loading...</p>}
            {bibData && bibData.sources.length === 0 && (
              <p style={{ color: 'var(--ink-soft)', fontSize: 13, lineHeight: 1.5 }}>
                No references yet. Ask the AI and accept output to a chapter to generate a reference list.
              </p>
            )}
            {bibData && bibData.sources.map((s, i) => (
              <div key={i} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: '1px solid var(--line)' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink)', marginBottom: 4 }}>
                  {s.filename} <span style={{ color: 'var(--ink-soft)' }}>p. {s.page_number}</span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {s.chapter_titles.map((t, j) => (
                    <span key={j} style={{ fontFamily: 'var(--font-mono)', fontSize: 10, background: 'var(--accent-soft)', borderRadius: 3, padding: '1px 6px' }}>{t}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
