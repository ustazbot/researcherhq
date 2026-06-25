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
import { CreditTank } from '../components/CreditTank'

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
  const [exportingChapterId, setExportingChapterId] = useState(null)
  const [compiling, setCompiling] = useState(false)
  const [compileError, setCompileError] = useState(null)
  const [compileWarning, setCompileWarning] = useState(null)

  // Upload category picker state
  const [pendingFile, setPendingFile] = useState(null)
  const [showCategoryPicker, setShowCategoryPicker] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState('artikel')

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
        web_citations: data.web_citations,
        source_type: data.source_type,
        id: Date.now() + 1
      }])
      setCredits(prev => prev ? { ...prev, kredit_remaining: data.kredit_remaining } : prev)
    } catch (err) {
      const msg = err.response?.data?.detail || 'Ralat berlaku. Cuba lagi.'
      setMessages(prev => [...prev, { role: 'error', content: msg, id: Date.now() + 1 }])
    }
    setLoading(false)
  }

  function handleFileSelect(e) {
    const file = e.target.files[0]
    if (!file) return
    if (file.type !== 'application/pdf') {
      alert('Sila muat naik fail PDF sahaja.')
      fileRef.current.value = ''
      return
    }
    setPendingFile(file)
    setSelectedCategory('artikel')
    setShowCategoryPicker(true)
  }

  async function handleUploadConfirm() {
    if (!pendingFile) return
    setShowCategoryPicker(false)
    setUploading(true)
    try {
      const pages = await extractPdfPages(pendingFile)
      const { data } = await api.post('/documents/upload', {
        project_id: id, filename: pendingFile.name, category: selectedCategory, pages,
      })
      setDocuments(prev => [...prev, data])
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal proses dokumen. Cuba lagi.')
    }
    setUploading(false)
    setPendingFile(null)
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

  async function handleAcceptArticle(article) {
    await api.post('/search/accept', {
      project_id: id,
      title: article.title,
      authors: article.authors,
      year: article.year,
      journal: article.journal,
      doi: article.doi,
      abstract: article.abstract,
      url: article.url,
      source: article.source,
    })
    const { data } = await api.get(`/projects/${id}/documents`)
    setDocuments(data)
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

  async function handleRenameChapter(chapterId, newTitle) {
    try {
      await api.patch(`/projects/${id}/chapters/${chapterId}`, { title: newTitle })
      setChapters(prev => prev.map(c => c.id === chapterId ? { ...c, title: newTitle } : c))
    } catch (err) {
      alert(err.response?.data?.detail || 'Gagal ubah nama bab.')
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
    setExportingChapterId(chapterId)
    try {
      const { data: initData } = await api.post(`/projects/${id}/chapters/${chapterId}/export`)
      const jobId = initData.job_id
      const chap = chapters.find(c => c.id === chapterId)

      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 1500))
        const poll = await api.get(
          `/projects/${id}/chapters/${chapterId}/export/${jobId}`,
          { responseType: 'arraybuffer' }
        )
        const ct = poll.headers['content-type'] ?? ''
        if (ct.includes('wordprocessingml') || ct.includes('octet-stream')) {
          const blob = new Blob([poll.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `${chap?.title ?? 'bab'}.docx`
          a.click()
          URL.revokeObjectURL(url)
          return
        }
        // Parse JSON status from arraybuffer
        const text = new TextDecoder().decode(poll.data)
        try {
          const json = JSON.parse(text)
          if (json.status === 'error') { alert('Export gagal. Sila cuba lagi.'); return }
        } catch { /* not JSON, keep polling */ }
      }
      alert('Export mengambil masa terlalu lama. Sila cuba lagi.')
    } catch {
      alert('Export gagal. Sila cuba lagi.')
    } finally {
      setExportingChapterId(null)
    }
  }

  async function handleCompile() {
    setCompileError(null)
    setCompileWarning(null)

    // Pre-flight: ada bab?
    if (chapters.length === 0) {
      setCompileError('Projek belum ada bab. Tambah sekurang-kurangnya satu bab dahulu.')
      return
    }
    // Pre-flight: ada bab yang ada content?
    const hasContent = chapters.some(c => c.has_content)
    if (!hasContent) {
      setCompileError('Semua bab masih kosong. Tambah kandungan ke bab dahulu.')
      return
    }

    setCompiling(true)
    try {
      const { data: init } = await api.post(`/projects/${id}/compile`)
      if (init.skipped_chapters?.length > 0) {
        setCompileWarning(`${init.skipped_chapters.length} bab kosong akan diskip: ${init.skipped_chapters.join(', ')}`)
      }
      const jobId = init.job_id
      for (let i = 0; i < 40; i++) {
        await new Promise(r => setTimeout(r, 1500))
        const poll = await api.get(
          `/projects/${id}/compile/${jobId}`,
          { responseType: 'arraybuffer' }
        )
        const ct = poll.headers['content-type'] ?? ''
        if (ct.includes('wordprocessingml') || ct.includes('octet-stream')) {
          const blob = new Blob([poll.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `${project?.title ?? 'thesis'}.docx`
          a.click()
          URL.revokeObjectURL(url)
          return
        }
        const text = new TextDecoder().decode(poll.data)
        try {
          const json = JSON.parse(text)
          if (json.status === 'error') {
            setCompileError(`Compile gagal: ${json.message ?? 'Ralat tidak diketahui.'}`)
            return
          }
        } catch { /* keep polling */ }
      }
      setCompileError('Compile mengambil masa terlalu lama. Sila cuba lagi.')
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'object' && detail?.code === 'all_chapters_empty') {
        setCompileError(detail.message)
      } else if (typeof detail === 'string') {
        setCompileError(`Compile gagal: ${detail}`)
      } else {
        setCompileError('Compile gagal. Sila cuba lagi atau hubungi sokongan.')
      }
    } finally {
      setCompiling(false)
    }
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
            Step 3 of 3 — Your Writing Style
          </p>
        )}
        <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, margin: '0 0 6px', fontSize: 20 }}>
          🎙 Writing Style Profile
        </h2>
        <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 20px' }}>
          Bantu AI faham cara anda menulis untuk output yang lebih semula jadi.{' '}
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, background: 'var(--line)', padding: '1px 5px', borderRadius: 3 }}>Pro</span>
        </p>

        {!isPro ? (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <p style={{ fontSize: 24, margin: '0 0 8px' }}>🔒</p>
            <p style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15, margin: '0 0 6px' }}>
              Writing Style Profile — Pro Exclusive
            </p>
            <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 20px' }}>
              Upgrade to personalize AI output to match your writing style.
            </p>
            <button
              onClick={() => nav('/account')}
              style={{ padding: '10px 20px', background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 8, fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, cursor: 'pointer', marginBottom: 10, display: 'block', width: '100%' }}
            >
              Upgrade to Pro — RM39/month
            </button>
            <button
              onClick={() => setShowVoiceProfile(false)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 13, textDecoration: 'underline' }}
            >
              Skip for now
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
              {voiceSaving ? 'Saving...' : 'Save Style Profile →'}
            </button>
            <p style={{ textAlign: 'center' }}>
              <button
                onClick={() => setShowVoiceProfile(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 13, textDecoration: 'underline' }}
              >
                Skip for now
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
              <CreditTank
                remaining={credits.kredit_remaining}
                total={credits.kredit_total}
                resetDate={credits.reset_date}
                onTopup={isPro ? async () => {
                  try {
                    const { data } = await api.post('/billing/topup/initiate')
                    window.location.href = data.payment_url
                  } catch { alert('Gagal memulakan topup. Sila cuba lagi.') }
                } : undefined}
              />
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
        <input type="file" ref={fileRef} onChange={handleFileSelect} accept=".pdf" style={{ display: 'none' }} />

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
                Skip for now
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
                  projectId={id}
                  onAcceptArticle={handleAcceptArticle}
                />
              )}
              {drawerTab === 'struktur' && (
                <ThesisPanel
                  chapters={sortedChapters}
                  onExport={handleExport}
                  exportingChapterId={exportingChapterId}
                  tier={credits?.tier ?? user?.tier}
                  projectId={id}
                  activeChapterId={activeChapterId}
                  onSetActive={ch => { handleSetActive(ch); setDrawerOpen(false); setMobileView('editor') }}
                  onAddChapter={handleAddChapter}
                  onDeleteChapter={handleDeleteChapter}
                  onReorderChapter={handleReorderChapter}
                  onRenameChapter={handleRenameChapter}
                  onCompile={handleCompile}
                  compiling={compiling}
                  compileError={compileError}
                  compileWarning={compileWarning}
                  onDismissError={() => setCompileError(null)}
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
            <CreditTank
              remaining={credits.kredit_remaining}
              total={credits.kredit_total}
              resetDate={credits.reset_date}
              onTopup={isPro ? async () => {
                try {
                  const { data } = await api.post('/billing/topup/initiate')
                  window.location.href = data.payment_url
                } catch { alert('Gagal memulakan topup. Sila cuba lagi.') }
              } : undefined}
            />
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
          >File <span style={{ fontSize: 10, opacity: 0.7 }}>▾</span></button>
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
              >Export Active Chapter</button>
              <button
                onClick={() => { fileRef.current?.click(); setOpenMenu(null) }}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}
              >Upload Document</button>
              {(credits?.tier ?? user?.tier) === 'pro' ? (
                <button
                  onClick={() => { handleCompile(); setOpenMenu(null) }}
                  disabled={compiling}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px',
                    background: 'none', border: 'none', cursor: compiling ? 'wait' : 'pointer',
                    fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)',
                  }}
                >
                  {compiling ? 'Generating thesis...' : 'Compile Full Thesis (.docx)'}
                </button>
              ) : (
                <button disabled style={{
                  display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px',
                  background: 'none', border: 'none', cursor: 'not-allowed',
                  fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)',
                  opacity: 0.5,
                }}>
                  Compile Tesis Penuh <span style={{ fontSize: 10, background: 'var(--line)', padding: '1px 5px', borderRadius: 3, marginLeft: 4 }}>Pro</span>
                </button>
              )}
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
            🎙 Style Profile{voiceSaved ? ' ✓' : ''}
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
          >View <span style={{ fontSize: 10, opacity: 0.7 }}>▾</span></button>
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
              >{sourceCollapsed ? '› ' : '‹ '}Toggle Sources Panel</button>
              <button
                onClick={() => { setThesisCollapsed(c => !c); setOpenMenu(null) }}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}
              >{thesisCollapsed ? '› ' : '‹ '}Toggle Thesis Structure</button>
              <button disabled style={{
                display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px',
                background: 'none', border: 'none', cursor: 'not-allowed',
                fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)',
                opacity: 0.5,
              }}>
                Export Google Docs <span style={{ fontSize: 10, background: 'var(--line)', padding: '1px 5px', borderRadius: 3, marginLeft: 4 }}>Phase 3</span>
              </button>
              <button disabled style={{
                display: 'block', width: '100%', textAlign: 'left', padding: '8px 14px',
                background: 'none', border: 'none', cursor: 'not-allowed',
                fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)',
                opacity: 0.5,
              }}>
                Bibliography Manager <span style={{ fontSize: 10, background: 'var(--line)', padding: '1px 5px', borderRadius: 3, marginLeft: 4 }}>Phase 3</span>
              </button>
            </div>
          )}
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <input type="file" ref={fileRef} onChange={handleFileSelect} accept=".pdf" style={{ display: 'none' }} />

        {/* Source sidebar — collapsible */}
        <SourcePanel
          documents={documents}
          onUpload={() => fileRef.current?.click()}
          tier={credits?.tier ?? user?.tier}
          uploading={uploading}
          collapsed={sourceCollapsed}
          onToggleCollapse={() => setSourceCollapsed(c => !c)}
          onDeleteDoc={handleDeleteDoc}
          projectId={id}
          onAcceptArticle={handleAcceptArticle}
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
              Skip for now
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
          exportingChapterId={exportingChapterId}
          tier={credits?.tier ?? user?.tier}
          projectId={id}
          activeChapterId={activeChapterId}
          onSetActive={handleSetActive}
          onAddChapter={handleAddChapter}
          onDeleteChapter={handleDeleteChapter}
          onReorderChapter={handleReorderChapter}
          onRenameChapter={handleRenameChapter}
          collapsed={thesisCollapsed}
          onToggleCollapse={() => setThesisCollapsed(c => !c)}
          onCompile={handleCompile}
          compiling={compiling}
          compileError={compileError}
          compileWarning={compileWarning}
          onDismissError={() => setCompileError(null)}
        />
      </div>

      {showCategoryPicker && pendingFile && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
        }}>
          <div style={{
            background: 'var(--card)', borderRadius: 'var(--radius-sm)',
            padding: 24, maxWidth: 320, width: '90%', boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
          }}>
            <p style={{ margin: '0 0 4px', fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15 }}>
              Pilih Kategori
            </p>
            <p style={{ margin: '0 0 16px', fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-soft)', wordBreak: 'break-all' }}>
              {pendingFile.name}
            </p>
            {[
              { value: 'artikel', label: 'Artikel Rujukan', icon: '📄' },
              { value: 'proposal', label: 'Proposal Kajian', icon: '📋' },
              { value: 'catatan_sv', label: 'Catatan SV', icon: '📝' },
              { value: 'draf', label: 'Draf Sendiri', icon: '📑' },
              { value: 'data', label: 'Data / Transkrip', icon: '📊' },
            ].map(cat => (
              <label key={cat.value} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
                cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13,
              }}>
                <input
                  type="radio"
                  name="upload_category"
                  value={cat.value}
                  checked={selectedCategory === cat.value}
                  onChange={() => setSelectedCategory(cat.value)}
                />
                {cat.icon} {cat.label}
              </label>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button
                onClick={handleUploadConfirm}
                style={{
                  flex: 1, padding: '9px 0', background: 'var(--accent)',
                  border: 'none', borderRadius: 'var(--radius-sm)',
                  fontFamily: 'var(--font-body)', fontSize: 13, cursor: 'pointer', fontWeight: 600,
                }}
              >Muat Naik</button>
              <button
                onClick={() => { setShowCategoryPicker(false); setPendingFile(null); fileRef.current.value = '' }}
                style={{
                  padding: '9px 16px', background: 'transparent',
                  border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
                  fontFamily: 'var(--font-body)', fontSize: 13, cursor: 'pointer',
                }}
              >Batal</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
