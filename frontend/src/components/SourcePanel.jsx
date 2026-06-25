import { useState } from 'react'
import api from '../api/client'

const CATEGORIES = [
  { value: 'artikel', label: 'Reference Articles', icon: '📄' },
  { value: 'proposal', label: 'Research Proposal', icon: '📋' },
  { value: 'catatan_sv', label: 'SV Notes', icon: '📝' },
  { value: 'draf', label: 'Own Draft', icon: '📑' },
  { value: 'data', label: 'Data / Transcript', icon: '📊' },
]

const SOURCE_LABEL = {
  openalex: 'OpenAlex',
  semantic_scholar: 'Semantic Scholar',
  crossref: 'CrossRef',
}

export function SourcePanel({ documents, onUpload, tier, uploading, collapsed, onToggleCollapse, onDeleteDoc, projectId, onAcceptArticle }) {
  const [activeTab, setActiveTab] = useState('docs')
  const [activeCategory, setActiveCategory] = useState('artikel')
  const [previewDocId, setPreviewDocId] = useState(null)
  const [previewText, setPreviewText] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState(false)
  const [bibData, setBibData] = useState(null)
  const [bibLoading, setBibLoading] = useState(false)

  // Search state
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
        width: 36, flexShrink: 0, borderRight: '1px solid var(--line)',
        background: 'var(--card)', display: 'flex', flexDirection: 'column', alignItems: 'center',
        paddingTop: 12,
      }}>
        <button
          onClick={onToggleCollapse}
          title="Open Sources panel"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 16, padding: 4 }}
        >›</button>
      </div>
    )
  }

  return (
    <div style={{
      width: 260, flexShrink: 0, borderRight: '1px solid var(--line)',
      display: 'flex', flexDirection: 'column', background: 'var(--card)',
      overflow: 'hidden',
    }}>
      {/* Header + collapse */}
      <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
          Sources
        </span>
        <button
          onClick={onToggleCollapse}
          title="Close Sources panel"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 16, padding: 0 }}
        >‹</button>
      </div>

      {/* Tab toggle */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', padding: '4px 8px', gap: 4 }}>
        {[
          { key: 'docs', label: 'Sources' },
          { key: 'search', label: 'Search Articles' },
          { key: 'bibliography', label: 'References' },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              flex: 1, padding: '5px 0',
              background: activeTab === t.key ? 'var(--accent-soft)' : 'none',
              border: activeTab === t.key ? '1px solid var(--accent)' : '1px solid transparent',
              borderRadius: 5, cursor: 'pointer',
              fontFamily: 'var(--font-mono)', fontSize: 10,
              color: activeTab === t.key ? 'var(--ink)' : 'var(--ink-soft)',
              letterSpacing: '0.04em',
            }}
          >{t.label}</button>
        ))}
      </div>

      {activeTab === 'docs' ? (
        <>
          <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
            {grouped.map(cat => (
              <div key={cat.value}>
                <button
                  onClick={() => setActiveCategory(activeCategory === cat.value ? null : cat.value)}
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    width: '100%', padding: '8px 16px', background: 'transparent', border: 'none',
                    fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)',
                    cursor: 'pointer', textAlign: 'left',
                  }}
                >
                  <span>{cat.icon} {cat.label}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)' }}>
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
                  <div key={doc.id} style={{ padding: '6px 16px 6px 32px' }}>
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
                      >×</button>
                    </div>
                    {previewDocId === doc.id && (
                      <div style={{
                        marginTop: 6, background: 'var(--bg)', border: '1px solid var(--line)',
                        borderRadius: 'var(--radius-sm)', padding: '10px 12px',
                        fontSize: 12, maxHeight: 200, overflowY: 'auto', whiteSpace: 'pre-wrap',
                        fontFamily: 'var(--font-body)', color: 'var(--ink-soft)',
                      }}>
                        {previewLoading && 'Loading preview...'}
                        {previewError && 'Failed to load — try again.'}
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
          <div style={{ padding: 12, borderTop: '1px solid var(--line)' }}>
            <button
              onClick={uploadDisabled || uploading ? undefined : onUpload}
              disabled={uploadDisabled || uploading}
              title={uploadDisabled ? 'Free tier: 1 PDF only. Upgrade to Pro for up to 5 PDFs.' : ''}
              style={{
                width: '100%', padding: '8px 0',
                background: uploadDisabled ? 'var(--line)' : 'var(--accent-soft)',
                border: `1px solid ${uploadDisabled ? 'var(--line)' : 'var(--accent)'}`,
                borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 13,
                cursor: uploadDisabled || uploading ? 'not-allowed' : 'pointer',
                color: uploadDisabled ? 'var(--ink-soft)' : 'var(--ink)',
                opacity: uploadDisabled || uploading ? 0.6 : 1,
              }}
            >
              {uploadDisabled ? '🔒 Limit Reached' : uploading ? 'Processing...' : '+ Upload'}
            </button>
            <p style={{
              margin: '6px 0 0',
              fontFamily: 'var(--font-mono)', fontSize: 10,
              color: uploadDisabled ? '#EF4444' : 'var(--ink-soft)',
              textAlign: 'center',
            }}>
              {docCount}/{maxDocs} documents
              {!uploadDisabled && tier !== 'pro' && (
                <span style={{ color: 'var(--ink-soft)' }}> · Pro: up to 5</span>
              )}
            </p>
          </div>
        </>
      ) : (
        /* Search tab */
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--line)' }}>
            <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
              <input
                value={searchQuery}
                onChange={e => { setSearchQuery(e.target.value); setSearchError('') }}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="Search keywords..."
                style={{
                  flex: 1, padding: '7px 10px', border: '1px solid var(--line)',
                  borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 13,
                  background: 'var(--bg)', color: 'var(--ink)',
                }}
              />
              <button
                onClick={handleSearch}
                disabled={searching}
                style={{
                  padding: '7px 10px', background: 'var(--ink)', color: 'var(--bg)',
                  border: 'none', borderRadius: 6, fontFamily: 'var(--font-mono)',
                  fontSize: 11, cursor: searching ? 'not-allowed' : 'pointer',
                  opacity: searching ? 0.6 : 1, flexShrink: 0,
                }}
              >
                {searching ? '...' : 'Search'}
              </button>
            </div>
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)' }}>Year:</span>
              <input
                value={yearFrom}
                onChange={e => setYearFrom(e.target.value)}
                placeholder="dari"
                type="number"
                style={{ flex: 1, padding: '4px 6px', border: '1px solid var(--line)', borderRadius: 5, fontFamily: 'var(--font-mono)', fontSize: 11, background: 'var(--bg)', color: 'var(--ink)' }}
              />
              <span style={{ color: 'var(--ink-soft)', fontSize: 11 }}>–</span>
              <input
                value={yearTo}
                onChange={e => setYearTo(e.target.value)}
                placeholder="ke"
                type="number"
                style={{ flex: 1, padding: '4px 6px', border: '1px solid var(--line)', borderRadius: 5, fontFamily: 'var(--font-mono)', fontSize: 11, background: 'var(--bg)', color: 'var(--ink)' }}
              />
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
            {searching && (
              <p style={{ color: 'var(--ink-soft)', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>Searching...</p>
            )}
            {!searching && searchError && (
              <p style={{ color: '#EF4444', fontSize: 12, padding: '8px 12px' }}>{searchError}</p>
            )}
            {tier !== 'pro' && searchResults.length > 0 && (
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)', padding: '4px 12px', background: 'var(--accent-soft)', margin: '0 0 4px' }}>
                Free: 5 results only · <span style={{ textDecoration: 'underline', cursor: 'pointer' }}>Upgrade to Pro</span>
              </p>
            )}
            {searchResults.map((article, i) => (
              <div key={i} style={{
                padding: '10px 12px', borderBottom: '1px solid var(--line)',
              }}>
                <p style={{ margin: '0 0 2px', fontSize: 12, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.4 }}>
                  {article.title}
                </p>
                <p style={{ margin: '0 0 2px', fontSize: 11, color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)' }}>
                  {article.authors?.join(', ')}{article.year ? ` (${article.year})` : ''}
                </p>
                {article.journal && (
                  <p style={{ margin: '0 0 4px', fontSize: 11, color: 'var(--ink-soft)', fontStyle: 'italic' }}>
                    {article.journal}
                  </p>
                )}
                <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap', marginBottom: 6 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, background: 'var(--line)', padding: '1px 5px', borderRadius: 3 }}>
                    {SOURCE_LABEL[article.source] || article.source}
                  </span>
                  {article.cited_by > 0 && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--ink-soft)' }}>
                      Cited: {article.cited_by}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  {article.abstract && (
                    <button
                      onClick={() => setExpandedAbstract(expandedAbstract === i ? null : i)}
                      style={{
                        flex: 1, padding: '5px 0', background: 'transparent',
                        border: '1px solid var(--line)', borderRadius: 5,
                        fontFamily: 'var(--font-mono)', fontSize: 10, cursor: 'pointer',
                        color: 'var(--ink-soft)',
                      }}
                    >
                      Abstract {expandedAbstract === i ? '▲' : '▼'}
                    </button>
                  )}
                  <button
                    onClick={() => handleAccept(article, i)}
                    disabled={accepting === i}
                    style={{
                      flex: 1, padding: '5px 0', background: 'var(--accent-soft)',
                      border: '1px solid var(--accent)', borderRadius: 5,
                      fontFamily: 'var(--font-mono)', fontSize: 10, cursor: accepting === i ? 'not-allowed' : 'pointer',
                      color: 'var(--ink)', fontWeight: 600,
                      opacity: accepting === i ? 0.6 : 1,
                    }}
                  >
                    {accepting === i ? '...' : 'Accept'}
                  </button>
                </div>
                {expandedAbstract === i && article.abstract && (
                  <div style={{
                    marginTop: 6, background: 'var(--bg)', border: '1px solid var(--line)',
                    borderRadius: 5, padding: '8px 10px', fontSize: 11,
                    color: 'var(--ink-soft)', lineHeight: 1.5, maxHeight: 150, overflowY: 'auto',
                  }}>
                    {article.abstract}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'bibliography' && (
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
  )
}
