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

  // Voice Profile state
  const [showVoiceProfile, setShowVoiceProfile] = useState(false)  // 'onboarding' | 'edit' | false
  const [voiceQ1, setVoiceQ1] = useState('')
  const [voiceQ2, setVoiceQ2] = useState('')
  const [voiceQ3, setVoiceQ3] = useState('')
  const [voiceSample, setVoiceSample] = useState('')
  const [voiceSaving, setVoiceSaving] = useState(false)
  const [voiceError, setVoiceError] = useState('')
  const [voiceSaved, setVoiceSaved] = useState(false)

  // Layout state
  const [sourceCollapsed, setSourceCollapsed] = useState(false)
  const [thesisCollapsed, setThesisCollapsed] = useState(false)
  const [openMenu, setOpenMenu] = useState(null) // 'fail' | 'paparan' | null

  // Mobile state
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [mobileView, setMobileView] = useState('editor') // 'editor' | 'chat'
  const [drawerOpen, setDrawerOpen] = useState(false) // source + navigator drawer
  const [drawerTab, setDrawerTab] = useState('sumber') // 'sumber' | 'struktur'

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
      api.get(`/voice-profile/${id}`),
    ]).then(([p, m, c, docs, chaps, vp]) => {
      setProject(p.data)
      setMessages(m.data)
      setCredits(c.data)
      setDocuments(docs.data)
      setChapters(chaps.data)
      if (vp.data.exists) {
        setVoiceQ1('')  // pre-fill not needed for onboarding; edit modal re-fetches
        setVoiceSaved(true)
      } else if (initMode) {
        // New project (came from Step 1) — show Step 3
        setShowVoiceProfile('onboarding')
      }
    }).catch(() => nav('/'))
  }, [id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    function handleClickOutside() { setOpenMenu(null) }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [])

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

  async function openVoiceProfileEdit() {
    try {
      const { data } = await api.get(`/voice-profile/${id}`)
      if (data.exists && data.sample_excerpt) setVoiceSample(data.sample_excerpt)
    } catch {}
    setVoiceError('')
    setVoiceQ1('')
    setVoiceQ2('')
    setVoiceQ3('')
    setShowVoiceProfile('edit')
  }

  async function handleSaveVoiceProfile() {
    setVoiceSaving(true)
    setVoiceError('')
    try {
      await api.post(`/voice-profile/${id}`, {
        answers: { q1: voiceQ1, q2: voiceQ2, q3: voiceQ3 },
        sample_excerpt: voiceSample || null,
      })
      setVoiceSaved(true)
      setShowVoiceProfile(false)
    } catch (err) {
      if (err.response?.status === 403) {
        setVoiceError(err.response.data.detail || 'Ciri ini hanya untuk pengguna Pro.')
      } else {
        setVoiceError('Gagal simpan. Cuba semula.')
      }
    } finally {
      setVoiceSaving(false)
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
  const isPro = (credits?.tier ?? user?.tier) === 'pro'

  const voiceProfileModal = showVoiceProfile ? (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 200, padding: 16,
    }}>
      <div style={{
        background: 'var(--card)', borderRadius: 'var(--radius-md)',
        padding: 28, width: '100%', maxWidth: 480,
        border: '1px solid var(--line)', maxHeight: '90vh', overflowY: 'auto',
      }}>
        {showVoiceProfile === 'onboarding' && (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-soft)', margin: '0 0 8px', letterSpacing: '0.04em' }}>
            Langkah 3 daripada 3 — Gaya Penulisan Anda
          </p>
        )}
        <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, margin: '0 0 6px', fontSize: 20 }}>
          🎙 Profil Gaya Penulisan
        </h2>
        <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 20px' }}>
          Bantu AI faham cara anda menulis untuk output yang lebih semula jadi.{' '}
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, background: 'var(--line)', padding: '1px 5px', borderRadius: 3 }}>Pro</span>
        </p>

        {!isPro ? (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <p style={{ fontSize: 24, margin: '0 0 8px' }}>🔒</p>
            <p style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15, margin: '0 0 6px' }}>
              Profil Gaya Penulisan — Eksklusif Pro
            </p>
            <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 20px' }}>
              Naik taraf untuk peribadikan output AI mengikut gaya penulisan anda.
            </p>
            <button
              onClick={() => nav('/account')}
              style={{ padding: '10px 20px', background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 8, fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, cursor: 'pointer', marginBottom: 10, display: 'block', width: '100%' }}
            >
              Naik Taraf ke Pro — RM39/bulan
            </button>
            <button
              onClick={() => setShowVoiceProfile(false)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 13, textDecoration: 'underline' }}
            >
              Langkau buat masa ini
            </button>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: 16 }}>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px' }}>
                1. Anda lebih suka ayat yang...
              </p>
              {[
                'Pendek & padat (≤20 patah perkataan)',
                'Panjang & terperinci (>20 patah perkataan)',
                'Campuran ikut keperluan',
              ].map(opt => (
                <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, cursor: 'pointer', fontSize: 14 }}>
                  <input type="radio" name="vq1" value={opt} checked={voiceQ1 === opt} onChange={() => setVoiceQ1(opt)} />
                  {opt}
                </label>
              ))}
            </div>

            <div style={{ marginBottom: 16 }}>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px' }}>
                2. Gaya penulisan akademik anda...
              </p>
              {[
                'Formal tradisional (pasif, jarak jauh)',
                'Moden & langsung (aktif, jelas)',
                'Saya tak pasti — ikut standard bidang saya',
              ].map(opt => (
                <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, cursor: 'pointer', fontSize: 14 }}>
                  <input type="radio" name="vq2" value={opt} checked={voiceQ2 === opt} onChange={() => setVoiceQ2(opt)} />
                  {opt}
                </label>
              ))}
            </div>

            <div style={{ marginBottom: 16 }}>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px' }}>
                3. Ada keutamaan lain? (optional)
              </p>
              <input
                value={voiceQ3}
                onChange={e => setVoiceQ3(e.target.value)}
                placeholder="Contoh: elak penggunaan kata ganti 'saya'"
                style={{ width: '100%', padding: '8px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 14, boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ marginBottom: 20 }}>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px' }}>
                Sampel tulisan anda (optional)
              </p>
              <textarea
                value={voiceSample}
                onChange={e => setVoiceSample(e.target.value)}
                placeholder="Paste 1-2 ayat dari karya anda sendiri sebagai contoh gaya..."
                rows={3}
                style={{ width: '100%', padding: '8px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 14, boxSizing: 'border-box', resize: 'vertical' }}
              />
            </div>

            {voiceError && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 12px' }}>{voiceError}</p>}

            <button
              onClick={handleSaveVoiceProfile}
              disabled={voiceSaving || (!voiceQ1 && !voiceQ2)}
              style={{
                width: '100%', padding: '11px', background: 'var(--ink)', color: 'var(--bg)',
                border: 'none', borderRadius: 8, fontFamily: 'var(--font-heading)',
                fontWeight: 700, fontSize: 14, cursor: (!voiceQ1 && !voiceQ2) ? 'not-allowed' : 'pointer',
                opacity: (!voiceQ1 && !voiceQ2) ? 0.5 : 1, marginBottom: 10,
              }}
            >
              {voiceSaving ? 'Menyimpan...' : 'Simpan Profil Gaya →'}
            </button>
            <p style={{ textAlign: 'center' }}>
              <button
                onClick={() => setShowVoiceProfile(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 13, textDecoration: 'underline' }}
              >
                Langkau buat masa ini
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  ) : null

  // ── MOBILE LAYOUT ──────────────────────────────────────────────
  if (isMobile) {
    return (
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
        {voiceProfileModal}
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
              style={{
                background: 'var(--accent-soft)',
                border: '1.5px solid var(--accent)',
                borderRadius: 6, cursor: 'pointer',
                padding: '6px 12px', fontSize: 12,
                color: 'var(--ink)', fontFamily: 'var(--font-body)',
                fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6,
              }}
            >
              <span>☰</span>
              <span>Sumber & Struktur Tesis</span>
            </button>
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

        {/* Segmented toggle */}
        <div style={{
          display: 'flex', borderBottom: '1px solid var(--line)',
          background: 'var(--bg)', flexShrink: 0, padding: '6px 12px', gap: 4,
        }}>
          {[
            { key: 'editor', label: 'Editor' },
            { key: 'chat', label: 'Chat AI' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setMobileView(tab.key)}
              style={{
                flex: 1, padding: '7px 0',
                background: mobileView === tab.key ? 'var(--card)' : 'transparent',
                color: mobileView === tab.key ? 'var(--ink)' : 'var(--ink-soft)',
                border: 'none',
                borderRadius: 6,
                boxShadow: mobileView === tab.key ? '0 1px 4px rgba(0,0,0,0.12)' : 'none',
                fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: mobileView === tab.key ? 600 : 400,
                cursor: 'pointer', position: 'relative',
                transition: 'background 0.15s, box-shadow 0.15s',
              }}
            >
              {tab.label}
              {/* Dot indicator for pending suggestion on Editor tab */}
              {tab.key === 'editor' && pendingSuggestion && mobileView !== 'editor' && (
                <span style={{
                  position: 'absolute', top: 6, right: 'calc(50% - 24px)',
                  width: 7, height: 7,
                  background: 'var(--accent)', borderRadius: '50%',
                  display: 'inline-block',
                }} />
              )}
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
                <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15 }}>Panel</span>
                <button onClick={() => setDrawerOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: 'var(--ink-soft)' }}>×</button>
              </div>
              {/* Tab row inside drawer */}
              <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', padding: '4px 12px', gap: 4 }}>
                {[
                  { key: 'sumber', label: 'Sumber' },
                  { key: 'struktur', label: 'Struktur Tesis' },
                ].map(t => (
                  <button
                    key={t.key}
                    onClick={() => setDrawerTab(t.key)}
                    style={{
                      padding: '5px 12px',
                      background: drawerTab === t.key ? 'var(--accent-soft)' : 'none',
                      border: drawerTab === t.key ? '1px solid var(--accent)' : '1px solid transparent',
                      borderRadius: 5, cursor: 'pointer',
                      fontFamily: 'var(--font-mono)', fontSize: 11,
                      color: drawerTab === t.key ? 'var(--ink)' : 'var(--ink-soft)',
                    }}
                  >{t.label}</button>
                ))}
              </div>
              {drawerTab === 'sumber' && (
                <SourcePanel
                  documents={documents}
                  onUpload={() => { fileRef.current?.click(); setDrawerOpen(false) }}
                  tier={credits?.tier ?? user?.tier}
                  uploading={uploading}
                  collapsed={false}
                  onToggleCollapse={() => {}}
                  onDeleteDoc={handleDeleteDoc}
                />
              )}
              {drawerTab === 'struktur' && (
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
              )}
            </div>
          </>
        )}
      </div>
    )
  }

  // ── DESKTOP LAYOUT ─────────────────────────────────────────────
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      {voiceProfileModal}
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

      {/* Menu bar — desktop only */}
      <div style={{
        height: 36, display: 'flex', alignItems: 'center', gap: 0,
        borderBottom: '1px solid var(--line)', background: 'var(--bg)',
        flexShrink: 0, padding: '0 8px', position: 'relative',
      }}>
        {/* Menu Fail */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={e => { e.stopPropagation(); setOpenMenu(openMenu === 'fail' ? null : 'fail') }}
            style={{
              background: openMenu === 'fail' ? 'var(--accent-soft)' : 'none',
              border: openMenu === 'fail' ? '1px solid var(--accent)' : '1px solid transparent',
              cursor: 'pointer', padding: '3px 10px',
              fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)',
              borderRadius: 4, display: 'flex', alignItems: 'center', gap: 4,
              transition: 'background 0.1s',
            }}
            onMouseEnter={e => { if (openMenu !== 'fail') e.currentTarget.style.background = 'var(--line)' }}
            onMouseLeave={e => { if (openMenu !== 'fail') e.currentTarget.style.background = 'none' }}
          >Fail <span style={{ fontSize: 10, opacity: 0.7 }}>▾</span></button>
          {openMenu === 'fail' && (
            <div onClick={e => e.stopPropagation()} style={{
              position: 'absolute', top: '100%', left: 0, zIndex: 100,
              background: 'var(--card)', border: '1px solid var(--line)',
              borderRadius: 'var(--radius-sm)', boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              minWidth: 180,
            }}>
              <button
                onClick={() => { handleExport(activeChapterId); setOpenMenu(null) }}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}
              >Export Bab Aktif</button>
              <button
                onClick={() => { fileRef.current?.click(); setOpenMenu(null) }}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}
              >Muat Naik Dokumen</button>
              {/* Fasa 3 items — disabled, labelled */}
              <button disabled style={{
                display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px',
                background: 'none', border: 'none', cursor: 'not-allowed',
                fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)',
                opacity: 0.5,
              }}>
                Export Tesis Penuh <span style={{ fontSize: 10, background: 'var(--line)', padding: '1px 5px', borderRadius: 3, marginLeft: 4 }}>Fasa 3</span>
              </button>
            </div>
          )}
        </div>

        {/* Menu Profil Gaya */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={e => { e.stopPropagation(); openVoiceProfileEdit(); setOpenMenu(null) }}
            style={{
              background: 'none', border: '1px solid transparent',
              cursor: 'pointer', padding: '3px 10px',
              fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)',
              borderRadius: 4, display: 'flex', alignItems: 'center', gap: 4,
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--line)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
          >
            🎙 Profil Gaya{voiceSaved ? ' ✓' : ''}
          </button>
        </div>

        {/* Menu Paparan */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={e => { e.stopPropagation(); setOpenMenu(openMenu === 'paparan' ? null : 'paparan') }}
            style={{
              background: openMenu === 'paparan' ? 'var(--accent-soft)' : 'none',
              border: openMenu === 'paparan' ? '1px solid var(--accent)' : '1px solid transparent',
              cursor: 'pointer', padding: '3px 10px',
              fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)',
              borderRadius: 4, display: 'flex', alignItems: 'center', gap: 4,
              transition: 'background 0.1s',
            }}
            onMouseEnter={e => { if (openMenu !== 'paparan') e.currentTarget.style.background = 'var(--line)' }}
            onMouseLeave={e => { if (openMenu !== 'paparan') e.currentTarget.style.background = 'none' }}
          >Paparan <span style={{ fontSize: 10, opacity: 0.7 }}>▾</span></button>
          {openMenu === 'paparan' && (
            <div onClick={e => e.stopPropagation()} style={{
              position: 'absolute', top: '100%', left: 0, zIndex: 100,
              background: 'var(--card)', border: '1px solid var(--line)',
              borderRadius: 'var(--radius-sm)', boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              minWidth: 200,
            }}>
              <button
                onClick={() => { setSourceCollapsed(c => !c); setOpenMenu(null) }}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}
              >{sourceCollapsed ? '› ' : '‹ '}Togol Panel Sumber</button>
              <button
                onClick={() => { setThesisCollapsed(c => !c); setOpenMenu(null) }}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}
              >{thesisCollapsed ? '› ' : '‹ '}Togol Struktur Tesis</button>
              <button disabled style={{
                display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px',
                background: 'none', border: 'none', cursor: 'not-allowed',
                fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)',
                opacity: 0.5,
              }}>
                Eksport Google Docs <span style={{ fontSize: 10, background: 'var(--line)', padding: '1px 5px', borderRadius: 3, marginLeft: 4 }}>Fasa 3</span>
              </button>
              <button disabled style={{
                display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px',
                background: 'none', border: 'none', cursor: 'not-allowed',
                fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)',
                opacity: 0.5,
              }}>
                Bibliografi Manager <span style={{ fontSize: 10, background: 'var(--line)', padding: '1px 5px', borderRadius: 3, marginLeft: 4 }}>Fasa 3</span>
              </button>
            </div>
          )}
        </div>
      </div>

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
