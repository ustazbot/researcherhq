import { useState } from 'react'
import api from '../api/client'

export function SearchOverlay({ open, onClose, projectId, tier, onAccepted }) {
  const [query, setQuery] = useState('')
  const [yearFrom, setYearFrom] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const [selectedArticle, setSelectedArticle] = useState(null)
  const [accepting, setAccepting] = useState(false)
  const [acceptedIds, setAcceptedIds] = useState(new Set())
  const [mobileView, setMobileView] = useState('list')

  if (!open) return null

  const isMobile = window.innerWidth < 768

  async function handleSearch() {
    if (query.trim().length < 3) {
      setError('Kata kunci terlalu pendek (minimum 3 aksara).')
      return
    }
    setSearching(true)
    setError('')
    setResults([])
    setSelectedArticle(null)
    setMobileView('list')
    try {
      const params = new URLSearchParams({ q: query.trim(), project_id: projectId })
      if (yearFrom) params.append('year_from', yearFrom)
      const { data } = await api.get(`/search/articles?${params}`)
      setResults(data.results || [])
      if (!data.results?.length) setError('Tiada hasil ditemui. Cuba kata kunci lain.')
    } catch (err) {
      setError(err.response?.data?.detail || 'Carian gagal. Cuba semula.')
    }
    setSearching(false)
  }

  async function handleAccept(article) {
    setAccepting(true)
    setError('')
    try {
      await api.post('/search/accept', {
        project_id: projectId,
        title: article.title,
        authors: article.authors || [],
        year: article.year,
        journal: article.journal,
        doi: article.doi,
        abstract: article.abstract || '',
        url: article.url,
        source: article.source,
        is_oa: article.is_oa || false,
        oa_url: article.oa_url || null,
        openalex_id: article.openalex_id || null,
        cited_by: article.cited_by || 0,
      })
      setAcceptedIds(prev => new Set([...prev, article.doi || article.title]))
      onAccepted?.()
    } catch (err) {
      setError(err.response?.data?.detail || 'Gagal menambah artikel.')
    }
    setAccepting(false)
  }

  const articleKey = a => a.doi || a.title

  function ResultList() {
    return (
      <div style={{
        width: isMobile ? '100%' : '35%',
        minWidth: isMobile ? undefined : 260,
        maxWidth: isMobile ? undefined : 400,
        borderRight: isMobile ? 'none' : '1px solid var(--line)',
        overflowY: 'auto', flexShrink: 0,
        display: isMobile && mobileView !== 'list' ? 'none' : 'block',
      }}>
        {!searching && !error && results.length === 0 && (
          <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--ink-soft)', fontSize: 13 }}>
            Masukkan kata kunci dan tekan Cari
          </div>
        )}
        {searching && (
          <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--ink-soft)', fontSize: 13 }}>
            Mencari artikel...
          </div>
        )}
        {!searching && error && (
          <div style={{ padding: '16px 20px', color: '#EF4444', fontSize: 13 }}>{error}</div>
        )}
        {!searching && results.map((article, i) => (
          <div
            key={i}
            onClick={() => {
              setSelectedArticle(article)
              if (isMobile) setMobileView('preview')
            }}
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--line)',
              cursor: 'pointer',
              background: selectedArticle === article ? 'var(--accent-soft)' : 'transparent',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 4 }}>
              <span style={{ fontSize: 13, flexShrink: 0, marginTop: 1 }}>
                {article.is_oa ? '🔓' : '🔒'}
              </span>
              <span style={{
                fontSize: 13, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.4,
                display: '-webkit-box', WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical', overflow: 'hidden',
              }}>
                {article.title}
              </span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginLeft: 19 }}>
              {article.authors?.slice(0, 2).join(', ')}{article.authors?.length > 2 ? ' et al.' : ''}
              {article.year ? ` · ${article.year}` : ''}
            </div>
            {article.cited_by > 0 && (
              <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginLeft: 19, marginTop: 2 }}>
                Cited: {article.cited_by}
              </div>
            )}
            {acceptedIds.has(articleKey(article)) && (
              <div style={{ fontSize: 11, color: '#059669', marginLeft: 19, marginTop: 2, fontWeight: 600 }}>
                ✓ Dah ditambah
              </div>
            )}
          </div>
        ))}
      </div>
    )
  }

  function PreviewPane() {
    if (isMobile && mobileView !== 'preview') return null
    return (
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px' }}>
        {isMobile && (
          <button
            onClick={() => setMobileView('list')}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 13, padding: '0 0 16px', display: 'flex', alignItems: 'center', gap: 4 }}
          >
            ← Balik ke senarai
          </button>
        )}
        {!selectedArticle ? (
          <div style={{ color: 'var(--ink-soft)', fontSize: 13, marginTop: 40, textAlign: 'center' }}>
            Pilih artikel dari senarai untuk lihat abstract penuh
          </div>
        ) : (
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.4, marginBottom: 8, marginTop: 0 }}>
              {selectedArticle.title}
            </h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16, fontSize: 13, color: 'var(--ink-soft)' }}>
              {selectedArticle.authors?.length > 0 && <span>{selectedArticle.authors.join(', ')}</span>}
              {selectedArticle.year && <span>· {selectedArticle.year}</span>}
              {selectedArticle.journal && <span style={{ fontStyle: 'italic' }}>· {selectedArticle.journal}</span>}
              {selectedArticle.cited_by > 0 && <span>· Cited by {selectedArticle.cited_by}</span>}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20, alignItems: 'center' }}>
              {selectedArticle.doi && (
                <a
                  href={`https://doi.org/${selectedArticle.doi}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ fontSize: 12, color: 'var(--accent)', textDecoration: 'none' }}
                >
                  DOI: {selectedArticle.doi}
                </a>
              )}
              <span style={{
                fontSize: 11, padding: '2px 8px', borderRadius: 4, fontWeight: 600,
                background: selectedArticle.is_oa ? '#D1FAE5' : '#FEE2E2',
                color: selectedArticle.is_oa ? '#065F46' : '#991B1B',
              }}>
                {selectedArticle.is_oa ? '🔓 Open Access' : '🔒 Paywalled'}
              </span>
            </div>
            {selectedArticle.abstract ? (
              <div>
                <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', marginBottom: 8 }}>Abstract</h3>
                <p style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.7, margin: 0 }}>
                  {selectedArticle.abstract}
                </p>
              </div>
            ) : (
              <p style={{ fontSize: 13, color: 'var(--ink-soft)', fontStyle: 'italic' }}>
                Abstract tidak tersedia untuk artikel ini.
              </p>
            )}
            {!selectedArticle.is_oa && (
              <div style={{
                marginTop: 20, padding: '12px 16px',
                background: '#FEF3C7', borderRadius: 6, fontSize: 13, color: '#92400E',
              }}>
                Artikel ini paywalled — AI hanya akan dapat baca abstract. Untuk analisis mendalam, muat naik PDF penuh setelah ditambah ke Sources.
              </div>
            )}
            {error && (
              <div style={{ marginTop: 12, fontSize: 13, color: '#EF4444' }}>{error}</div>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 24 }}>
              {tier !== 'pro' ? (
                <div style={{
                  padding: '10px 16px', background: 'var(--accent-soft)',
                  borderRadius: 6, fontSize: 13, color: 'var(--ink)', flex: 1, textAlign: 'center',
                }}>
                  🔒 Add to Sources — Pro only
                </div>
              ) : acceptedIds.has(articleKey(selectedArticle)) ? (
                <div style={{
                  padding: '10px 16px', background: '#D1FAE5',
                  borderRadius: 6, fontSize: 13, color: '#065F46', flex: 1, textAlign: 'center', fontWeight: 600,
                }}>
                  ✓ Sudah ditambah ke Sources
                </div>
              ) : (
                <button
                  onClick={() => handleAccept(selectedArticle)}
                  disabled={accepting}
                  style={{
                    flex: 1, padding: '10px 16px',
                    background: 'var(--accent)', color: 'white',
                    border: 'none', borderRadius: 6, cursor: accepting ? 'not-allowed' : 'pointer',
                    fontSize: 14, fontWeight: 600, opacity: accepting ? 0.6 : 1,
                  }}
                >
                  {accepting ? 'Menambah...' : '+ Tambah ke Sources'}
                </button>
              )}
              {selectedArticle.url && (
                <a
                  href={selectedArticle.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    padding: '10px 16px', border: '1px solid var(--line)',
                    borderRadius: 6, fontSize: 13, color: 'var(--ink)',
                    textDecoration: 'none', whiteSpace: 'nowrap',
                  }}
                >
                  Buka →
                </a>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'var(--bg)',
        display: 'flex', flexDirection: 'column',
      }}
      onKeyDown={e => e.key === 'Escape' && onClose()}
      tabIndex={-1}
    >
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '12px 20px', borderBottom: '1px solid var(--line)',
        background: 'var(--surface)', flexShrink: 0,
      }}>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 20, lineHeight: 1, padding: 4 }}
        >←</button>
        <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--ink)' }}>Cari Artikel</span>
      </div>

      {/* Search bar */}
      <div style={{
        padding: '12px 20px', borderBottom: '1px solid var(--line)',
        background: 'var(--surface)', flexShrink: 0,
        display: 'flex', gap: 8, alignItems: 'center',
        flexWrap: isMobile ? 'wrap' : 'nowrap',
      }}>
        <input
          autoFocus
          value={query}
          onChange={e => { setQuery(e.target.value); setError('') }}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          placeholder="Kata kunci, tajuk artikel, nama pengarang..."
          style={{
            flex: 1, padding: '8px 12px',
            border: '1px solid var(--line)', borderRadius: 6,
            fontFamily: 'var(--font-body)', fontSize: 14,
            background: 'var(--bg)', color: 'var(--ink)',
            minWidth: isMobile ? '100%' : undefined,
          }}
        />
        <input
          value={yearFrom}
          onChange={e => setYearFrom(e.target.value)}
          placeholder="Dari tahun"
          type="number"
          style={{
            width: isMobile ? 120 : 110, padding: '8px 10px',
            border: '1px solid var(--line)', borderRadius: 6,
            fontFamily: 'var(--font-body)', fontSize: 13,
            background: 'var(--bg)', color: 'var(--ink)',
          }}
        />
        <button
          onClick={handleSearch}
          disabled={searching}
          style={{
            padding: '8px 20px', background: 'var(--ink)', color: 'var(--bg)',
            border: 'none', borderRadius: 6, cursor: searching ? 'not-allowed' : 'pointer',
            fontSize: 14, fontWeight: 500, opacity: searching ? 0.6 : 1, flexShrink: 0,
          }}
        >
          {searching ? 'Mencari...' : 'Cari'}
        </button>
      </div>

      {/* Split pane body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <ResultList />
        <PreviewPane />
      </div>
    </div>
  )
}
