import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { ProfileMenu } from '../components/ProfileMenu'
import { SourcePanel } from '../components/SourcePanel'
import { ThesisPanel } from '../components/ThesisPanel'
import { ChapterEditor } from '../components/ChapterEditor'
import { ChatPanel } from '../components/ChatPanel'
import api from '../api/client'
import { extractPdfPages } from '../utils/pdfExtract'
import { useMediaQuery } from '../hooks/useMediaQuery'

// Split proposal_extract output into Bab 1 (pengenalan) and Bab 3 (metodologi) parts
function splitProposalExtract(text) {
  const idx = text.indexOf('**METODOLOGI:**')
  if (idx === -1) return { bab1: text, bab3: null }
  return { bab1: text.slice(0, idx).trim(), bab3: text.slice(idx).trim() }
}

export function ProjectPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const initMode = searchParams.get('mode')  // 'discovery' | 'proposal_upload' | null
  const [project, setProject] = useState(null)
  const [messages, setMessages] = useState([])
  const [documents, setDocuments] = useState([])
  const [chapters, setChapters] = useState([])
  const [query, setQuery] = useState('')
  const [outputMode, setOutputMode] = useState(initMode === 'discovery' ? 'discovery' : 'qa')
  const [loading, setLoading] = useState(false)
  const [credits, setCredits] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)

  // Editor state
  const [activeChapterId, setActiveChapterId] = useState(null)
  const [activeChapterContent, setActiveChapterContent] = useState('')
  const [contentLoading, setContentLoading] = useState(false)
  const [pendingSuggestion, setPendingSuggestion] = useState(null) // { text: string, stageLabel?: string } | null
  const [showProposalUpload, setShowProposalUpload] = useState(initMode === 'proposal_upload')
  const [proposalUploading, setProposalUploading] = useState(false)
  // Two-stage proposal: stores Bab 3 text pending after user Terima Bab 1
  const [proposalBab3Text, setProposalBab3Text] = useState(null)

  // Layout state
  const [sourceCollapsed, setSourceCollapsed] = useState(false)
  const [thesisCollapsed, setThesisCollapsed] = useState(false)

  // Mobile state
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [mobileView, setMobileView] = useState('editor') // 'editor' | 'chat'
  const [drawerOpen, setDrawerOpen] = useState(false) // source + navigator drawer

  const fileRef = useRef()
  const bottomRef = useRef()
  const user = JSON.parse(localStorage.getItem('rhq_user') || '{}')

  useEffect(() => {
    Promise.all([
      api.get(`/projects/${id}`),
      api.get(`/projects/${id}/messages`),
      api.get('/credits'),
      api.get(`/documents?project_id=${id}`),
      api.get(`/projects/${id}/chapters`),
    ]).then(([p, m, c, docs, chaps]) => {
      setProject(p.data)
      setMessages(m.data)
      setCredits(c.data)
      setDocuments(docs.data)
      setChapters(chaps.data)
    }).catch(() => nav('/'))
  }, [id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Fetch chapter content bila active chapter bertukar
  useEffect(() => {
    if (!activeChapterId) {
      setActiveChapterContent('')
      return
    }
    setContentLoading(true)
    api.get(`/projects/${id}/chapters/${activeChapterId}`)
      .then(r => setActiveChapterContent(r.data.content || ''))
      .catch(() => setActiveChapterContent(''))
      .finally(() => setContentLoading(false))
  }, [activeChapterId, id])

  function handleSetActive(chapterId) {
    if (pendingSuggestion && chapterId !== activeChapterId) {
      if (!window.confirm('Ada cadangan AI yang belum disimpan. Tukar bab sekarang akan buang cadangan ini.')) return
      setPendingSuggestion(null)
      setProposalBab3Text(null)
    }
    setActiveChapterId(chapterId)
  }

  async function handleQuery(e) {
    e.preventDefault()
    if (!query.trim() || loading) return
    const q = query
    setQuery('')
    setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: q, id: Date.now() }])
    try {
      const { data } = await api.post(`/projects/${id}/query`, {
        query: q, output_mode: outputMode, query_type: 'normal'
      })
      setMessages(prev => [...prev, {
        role: 'assistant', content: data.answer,
        sources: data.sources, kredit_used: data.kredit_used,
        id: Date.now() + 1
      }])
      setCredits(prev => prev ? { ...prev, kredit_remaining: data.kredit_remaining } : prev)
    } catch (err) {
      const msg = err.response?.data?.detail || 'Ralat berlaku. Cuba lagi.'
      setMessages(prev => [...prev, { role: 'error', content: msg, id: Date.now() + 1 }])
    }
    setLoading(false)
  }

  async function handleFileUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    if (file.type !== 'application/pdf') {
      alert('Sila muat naik fail PDF sahaja.')
      fileRef.current.value = ''
      return
    }
    setUploading(true)
    try {
      const pages = await extractPdfPages(file)
      const { data } = await api.post('/documents/upload', {
        project_id: id, filename: file.name, category: 'artikel', pages,
      })
      setDocuments(prev => [...prev, data])
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal proses dokumen. Cuba lagi.')
    }
    setUploading(false)
    fileRef.current.value = ''
  }

  async function handleDeleteDoc(docId) {
    try {
      await api.delete(`/documents/${docId}`)
      setDocuments(prev => prev.filter(d => d.id !== docId))
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal padam dokumen. Cuba lagi.')
    }
  }

  async function handleProposalUpload(file) {
    const pages = await extractPdfPages(file)
    await api.post('/documents/upload', {
      project_id: id,
      filename: file.name,
      category: 'proposal',
      pages,
    })
    const extractRes = await api.post(`/projects/${id}/query`, {
      query: 'Sila ekstrak semua komponen utama dari proposal ini.',
      output_mode: 'proposal_extract',
    })
    if (!extractRes.data?.answer) return

    // Two-stage: set Bab 1 as first pendingSuggestion, queue Bab 3
    const { bab1, bab3 } = splitProposalExtract(extractRes.data.answer)
    setPendingSuggestion({
      text: bab1,
      stageLabel: 'Peringkat 1 / 2 — Bab 1 (Pengenalan)',
    })
    if (bab3) setProposalBab3Text(bab3)
  }

  async function handleAddChapter(title) {
    const nextOrder = chapters.length > 0 ? Math.max(...chapters.map(c => c.chapter_order)) + 1 : 1
    try {
      const { data } = await api.post(`/projects/${id}/chapters`, { title, chapter_order: nextOrder })
      setChapters(prev => [...prev, data])
      setActiveChapterId(data.id)
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal tambah bab. Cuba lagi.')
    }
  }

  async function handleDeleteChapter(chapterId) {
    try {
      await api.delete(`/projects/${id}/chapters/${chapterId}`)
      setChapters(prev => prev.filter(c => c.id !== chapterId))
      if (activeChapterId === chapterId) {
        setActiveChapterId(null)
        setPendingSuggestion(null)
      }
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal padam bab. Cuba lagi.')
    }
  }

  async function handleReorderChapter(chapterId, direction) {
    const sorted = [...chapters].sort((a, b) => a.chapter_order - b.chapter_order)
    const idx = sorted.findIndex(c => c.id === chapterId)
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1
    if (swapIdx < 0 || swapIdx >= sorted.length) return

    const curr = sorted[idx]
    const swap = sorted[swapIdx]
    const newOrderCurr = swap.chapter_order
    const newOrderSwap = curr.chapter_order

    try {
      await Promise.all([
        api.patch(`/projects/${id}/chapters/${curr.id}`, { chapter_order: newOrderCurr }),
        api.patch(`/projects/${id}/chapters/${swap.id}`, { chapter_order: newOrderSwap }),
      ])
      setChapters(prev => prev.map(c => {
        if (c.id === curr.id) return { ...c, chapter_order: newOrderCurr }
        if (c.id === swap.id) return { ...c, chapter_order: newOrderSwap }
        return c
      }))
    } catch (err) {
      alert('Gagal susun semula bab. Cuba lagi.')
    }
  }

  function handleRejectSuggestion() {
    setPendingSuggestion(null)
    setProposalBab3Text(null)
  }

  async function handleAcceptSuggestion(text) {
    if (!activeChapterId) return
    setSaving(true)
    try {
      await api.patch(`/projects/${id}/chapters/${activeChapterId}/content`, { content: text })
      setActiveChapterContent(text)
      setChapters(prev => prev.map(c =>
        c.id === activeChapterId ? { ...c, status: 'dalam_proses' } : c
      ))
      setPendingSuggestion(null)
      // Two-stage proposal: after Bab 1 accepted, auto-queue Bab 3
      if (proposalBab3Text) {
        setPendingSuggestion({
          text: proposalBab3Text,
          stageLabel: 'Peringkat 2 / 2 — Bab 3 (Metodologi & Persampelan)',
        })
        setProposalBab3Text(null)
      }
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal simpan cadangan. Cuba lagi.')
    }
    setSaving(false)
  }

  async function handleSaveContent(text) {
    if (!activeChapterId) return
    setSaving(true)
    try {
      await api.patch(`/projects/${id}/chapters/${activeChapterId}/content`, { content: text })
      setActiveChapterContent(text)
      setChapters(prev => prev.map(c =>
        c.id === activeChapterId ? { ...c, status: 'dalam_proses' } : c
      ))
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal simpan kandungan. Cuba lagi.')
    }
    setSaving(false)
  }

  async function handleExport(chapterId) {
    alert('Export .docx untuk bab ini akan tersedia tidak lama lagi.')
  }

  if (!project) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: 'var(--ink-soft)' }}>Memuatkan...</p>
    </div>
  )

  const activeChapter = chapters.find(c => c.id === activeChapterId) || null
  const sortedChapters = [...chapters].sort((a, b) => a.chapter_order - b.chapter_order)

  // ── MOBILE LAYOUT ──────────────────────────────────────────────
  if (isMobile) {
    return (
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
        {/* Header */}
        <header style={{
          borderBottom: '1px solid var(--line)', padding: '0 16px',
          height: 52, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'var(--card)', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => nav('/')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 18 }}>←</button>
            <Logo size="sm" />
            <button
              onClick={() => setDrawerOpen(true)}
              title="Buka panel Sumber & Struktur"
              style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 4, cursor: 'pointer', padding: '4px 8px', fontSize: 12, color: 'var(--ink-soft)' }}
            >☰ Sumber</button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {credits && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: credits.kredit_remaining < 10 ? '#EF4444' : 'var(--ink-soft)' }}>
                {credits.kredit_remaining} kr
              </span>
            )}
            <ProfileMenu user={user} tier={credits?.tier} />
          </div>
        </header>

        {/* Mobile toggle bar */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', background: 'var(--card)', flexShrink: 0 }}>
          {[
            { key: 'editor', label: activeChapter ? activeChapter.title.slice(0, 20) + (activeChapter.title.length > 20 ? '…' : '') : 'Editor' },
            { key: 'chat', label: 'Chat AI' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setMobileView(tab.key)}
              style={{
                flex: 1, padding: '10px 0',
                background: mobileView === tab.key ? 'var(--ink)' : 'transparent',
                color: mobileView === tab.key ? 'var(--bg)' : 'var(--ink-soft)',
                border: 'none', fontFamily: 'var(--font-body)', fontSize: 13,
                cursor: 'pointer', borderBottom: mobileView === tab.key ? '2px solid var(--accent)' : '2px solid transparent',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Mobile views */}
        <input type="file" ref={fileRef} onChange={handleFileUpload} accept=".pdf" style={{ display: 'none' }} />

        <div style={{ flex: 1, overflow: 'hidden' }}>
          {showProposalUpload && mobileView === 'editor' && (
            <div style={{
              background: 'var(--card)', border: '1px solid var(--accent)',
              borderRadius: 'var(--radius-md)', padding: 24, margin: 16,
            }}>
              <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px', fontSize: 16 }}>
                Muat Naik Proposal
              </h3>
              <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 16px' }}>
                Muat naik proposal yang telah lulus. Sistem akan mengekstrak maklumat penting — kemudian verify sebelum masuk ke bab.
              </p>
              <input
                type="file"
                accept=".pdf"
                disabled={proposalUploading}
                onChange={async (e) => {
                  const file = e.target.files?.[0]
                  if (!file) return
                  setProposalUploading(true)
                  try {
                    await handleProposalUpload(file)
                    setShowProposalUpload(false)
                  } catch (err) {
                    console.error('Upload proposal gagal:', err)
                  } finally {
                    setProposalUploading(false)
                  }
                }}
                style={{ display: 'block', marginBottom: 12 }}
              />
              {proposalUploading && (
                <p style={{ color: 'var(--ink-soft)', fontSize: 13 }}>Mengekstrak proposal... (mungkin ambil masa 30–60 saat)</p>
              )}
              <button
                type="button"
                onClick={() => setShowProposalUpload(false)}
                style={{ padding: '8px 16px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 8, cursor: 'pointer', fontSize: 13 }}
              >
                Langkau buat masa ini
              </button>
            </div>
          )}
          {mobileView === 'editor' && !showProposalUpload && (
            <ChapterEditor
              chapter={activeChapter}
              content={contentLoading ? '' : activeChapterContent}
              pendingSuggestion={pendingSuggestion}
              onAccept={handleAcceptSuggestion}
              onReject={handleRejectSuggestion}
              onSave={handleSaveContent}
              saving={saving}
            />
          )}
          {mobileView === 'chat' && (
            <ChatPanel
              messages={messages} loading={loading}
              query={query} onQueryChange={setQuery}
              onSubmit={handleQuery}
              outputMode={outputMode} onOutputModeChange={setOutputMode}
              credits={credits}
              onSendToEditor={text => { setPendingSuggestion({ text }); setMobileView('editor') }}
              hasActiveChapter={!!activeChapterId}
              bottomRef={bottomRef}
              tier={user?.tier || 'free'}
              isDiscoveryMode={outputMode === 'discovery'}
            />
          )}
        </div>

        {/* Drawer — Source + Navigator */}
        {drawerOpen && (
          <>
            <div
              onClick={() => setDrawerOpen(false)}
              style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 40 }}
            />
            <div style={{
              position: 'fixed', top: 0, left: 0, bottom: 0, width: 280,
              background: 'var(--card)', zIndex: 50, display: 'flex', flexDirection: 'column',
              overflowY: 'auto',
            }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15 }}>Sumber & Struktur</span>
                <button onClick={() => setDrawerOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: 'var(--ink-soft)' }}>×</button>
              </div>
              {/* SourcePanel inlined for drawer */}
              <SourcePanel
                documents={documents}
                onUpload={() => { fileRef.current?.click(); setDrawerOpen(false) }}
                tier={credits?.tier ?? user?.tier}
                uploading={uploading}
                collapsed={false}
                onToggleCollapse={() => {}}
                onDeleteDoc={handleDeleteDoc}
              />
              <div style={{ borderTop: '2px solid var(--line)' }} />
              <ThesisPanel
                chapters={sortedChapters}
                onExport={handleExport}
                tier={credits?.tier ?? user?.tier}
                projectId={id}
                activeChapterId={activeChapterId}
                onSetActive={ch => { handleSetActive(ch); setDrawerOpen(false); setMobileView('editor') }}
                onAddChapter={handleAddChapter}
                onDeleteChapter={handleDeleteChapter}
                onReorderChapter={handleReorderChapter}
              />
            </div>
          </>
        )}
      </div>
    )
  }

  // ── DESKTOP LAYOUT ─────────────────────────────────────────────
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <header style={{
        borderBottom: '1px solid var(--line)', padding: '0 24px',
        height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'var(--card)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={() => nav('/')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 18 }}>←</button>
          <Logo size="sm" />
          <span style={{ color: 'var(--line)' }}>|</span>
          <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16 }}>{project.title}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {credits && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: credits.kredit_remaining < 10 ? '#EF4444' : 'var(--ink-soft)' }}>
              {credits.kredit_remaining} kredit
            </span>
          )}
          <ProfileMenu user={user} tier={credits?.tier} />
        </div>
      </header>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <input type="file" ref={fileRef} onChange={handleFileUpload} accept=".pdf" style={{ display: 'none' }} />

        {/* Source sidebar — collapsible */}
        <SourcePanel
          documents={documents}
          onUpload={() => fileRef.current?.click()}
          tier={credits?.tier ?? user?.tier}
          uploading={uploading}
          collapsed={sourceCollapsed}
          onToggleCollapse={() => setSourceCollapsed(c => !c)}
          onDeleteDoc={handleDeleteDoc}
        />

        {/* Proposal Upload Panel */}
        {showProposalUpload && (
          <div style={{
            position: 'absolute', top: 60, left: 200, right: 320, zIndex: 10,
            background: 'var(--card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-md)', padding: 24, margin: 16,
          }}>
            <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px', fontSize: 16 }}>
              Muat Naik Proposal
            </h3>
            <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 16px' }}>
              Muat naik proposal yang telah lulus. Sistem akan mengekstrak maklumat penting — kemudian verify sebelum masuk ke bab.
            </p>
            <input
              type="file"
              accept=".pdf"
              disabled={proposalUploading}
              onChange={async (e) => {
                const file = e.target.files?.[0]
                if (!file) return
                setProposalUploading(true)
                try {
                  await handleProposalUpload(file)
                  setShowProposalUpload(false)
                } catch (err) {
                  console.error('Upload proposal gagal:', err)
                } finally {
                  setProposalUploading(false)
                }
              }}
              style={{ display: 'block', marginBottom: 12 }}
            />
            {proposalUploading && (
              <p style={{ color: 'var(--ink-soft)', fontSize: 13 }}>Mengekstrak proposal... (mungkin ambil masa 30–60 saat)</p>
            )}
            <button
              type="button"
              onClick={() => setShowProposalUpload(false)}
              style={{ padding: '8px 16px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 8, cursor: 'pointer', fontSize: 13 }}
            >
              Langkau buat masa ini
            </button>
          </div>
        )}

        {/* ChapterEditor — main pane */}
        <ChapterEditor
          chapter={activeChapter}
          content={contentLoading ? '' : activeChapterContent}
          pendingSuggestion={pendingSuggestion}
          onAccept={handleAcceptSuggestion}
          onReject={handleRejectSuggestion}
          onSave={handleSaveContent}
          saving={saving}
        />

        {/* Chat — right sidebar */}
        <div style={{ width: 320, flexShrink: 0, borderLeft: '1px solid var(--line)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <ChatPanel
            messages={messages} loading={loading}
            query={query} onQueryChange={setQuery}
            onSubmit={handleQuery}
            outputMode={outputMode} onOutputModeChange={setOutputMode}
            credits={credits}
            onSendToEditor={text => setPendingSuggestion({ text })}
            hasActiveChapter={!!activeChapterId}
            bottomRef={bottomRef}
            tier={user?.tier || 'free'}
            isDiscoveryMode={outputMode === 'discovery'}
          />
        </div>

        {/* Thesis navigator — far right */}
        <ThesisPanel
          chapters={sortedChapters}
          onExport={handleExport}
          tier={credits?.tier ?? user?.tier}
          projectId={id}
          activeChapterId={activeChapterId}
          onSetActive={handleSetActive}
          onAddChapter={handleAddChapter}
          onDeleteChapter={handleDeleteChapter}
          onReorderChapter={handleReorderChapter}
          collapsed={thesisCollapsed}
          onToggleCollapse={() => setThesisCollapsed(c => !c)}
        />
      </div>
    </div>
  )
}
