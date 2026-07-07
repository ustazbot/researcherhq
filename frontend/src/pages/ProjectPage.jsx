import { useState, useEffect, useRef } from 'react'
import { IconUser, IconFile, IconLayout, IconArrowLeft, IconFiles, IconListTree, IconHelpCircle, IconPencil, IconMessageCircle, IconUpload } from '@tabler/icons-react'
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
import { OnboardingTour } from '../components/OnboardingTour'

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
  const [liveContent, setLiveContent] = useState(null) // §6J: unsaved editor HTML for live word count
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
  const [voiceSampleFile, setVoiceSampleFile] = useState(null)
  const [voiceSampleAnalysis, setVoiceSampleAnalysis] = useState('')
  const [voiceAnalysing, setVoiceAnalysing] = useState(false)
  const [voiceAnalysisError, setVoiceAnalysisError] = useState('')
  const [voiceSampleMode, setVoiceSampleMode] = useState('paste')
  const [showHelp, setShowHelp] = useState(false)
  const [useWebSearch, setUseWebSearch] = useState(false)
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [exportingChapterId, setExportingChapterId] = useState(null)
  const [compiling, setCompiling] = useState(false)
  const [compileError, setCompileError] = useState(null)
  const [compileWarning, setCompileWarning] = useState(null)

  // Upload category picker state
  const [pendingFile, setPendingFile] = useState(null)
  const [pendingFileType, setPendingFileType] = useState('pdf')
  const [showCategoryPicker, setShowCategoryPicker] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState('artikel')

  // Layout state
  const [sourceCollapsed, setSourceCollapsed] = useState(false)
  const [thesisCollapsed, setThesisCollapsed] = useState(false)
  const [openMenu, setOpenMenu] = useState(null) // 'fail' | 'paparan' | null

  // Mobile state
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [mobileView, setMobileView] = useState('editor') // 'sources' | 'chapters' | 'editor' | 'chat'

  const fileRef = useRef()
  const bottomRef = useRef()
  const user = JSON.parse(localStorage.getItem('rhq_user') || '{}')

  useEffect(() => {
    Promise.all([
      api.get(`/projects/${id}`),
      api.get(`/projects/${id}/sessions`),
      api.get('/credits'),
      api.get(`/documents?project_id=${id}`),
      api.get(`/projects/${id}/chapters`),
      api.get(`/voice-profile/${id}`),
    ]).then(([p, sess, c, docs, chaps, vp]) => {
      setProject(p.data)
      const sessList = sess.data || []
      setSessions(sessList)
      const latestSession = sessList[0]
      if (latestSession) {
        setActiveSessionId(latestSession.id)
        api.get(`/projects/${id}/messages?session_id=${latestSession.id}`).then(m => setMessages(m.data))
      }
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

  // Incoming suggestion from the Survey module (36C-3 Send to Editor) —
  // rides the same pendingSuggestion Accept/Reject flow as chat answers.
  useEffect(() => {
    const raw = sessionStorage.getItem('rhq_pending_suggestion')
    if (!raw) return
    sessionStorage.removeItem('rhq_pending_suggestion')
    try {
      const { chapterId, text, stageLabel } = JSON.parse(raw)
      if (!text) return
      if (chapterId) setActiveChapterId(chapterId)
      setPendingSuggestion({ text, stageLabel })
      if (isMobile) setMobileView('editor')
    } catch { /* malformed payload — ignore */ }
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
    setLiveContent(null) // §6J: stale override must not leak into the next chapter
    api.get(`/projects/${id}/chapters/${activeChapterId}`)
      .then(r => setActiveChapterContent(r.data.content || ''))
      .catch(() => setActiveChapterContent(''))
      .finally(() => setContentLoading(false))
  }, [activeChapterId, id])

  function handleSetActive(chapterId) {
    if (pendingSuggestion && chapterId !== activeChapterId) {
      if (!window.confirm('You have an unsaved AI suggestion. Switching chapters now will discard it.')) return
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
      const wsFlag = useWebSearch
      setUseWebSearch(false)
      const { data } = await api.post(`/projects/${id}/query`, {
        query: q, output_mode: outputMode, query_type: 'normal', use_web_search: wsFlag,
        session_id: activeSessionId,
      })
      // Refresh session list to pick up auto-title + updated_at
      api.get(`/projects/${id}/sessions`).then(r => {
        setSessions(r.data || [])
        if (!activeSessionId && r.data?.[0]) setActiveSessionId(r.data[0].id)
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
      const msg = err.response?.data?.detail || 'An error occurred. Please try again.'
      setMessages(prev => [...prev, { role: 'error', content: msg, id: Date.now() + 1 }])
    }
    setLoading(false)
  }

  async function handleNewSession() {
    const { data } = await api.post(`/projects/${id}/sessions`)
    setSessions(prev => [data, ...prev])
    setActiveSessionId(data.id)
    setMessages([])
  }

  async function handleSelectSession(sessionId) {
    setActiveSessionId(sessionId)
    const { data } = await api.get(`/projects/${id}/messages?session_id=${sessionId}`)
    setMessages(data)
  }

  async function handleRenameSession(sessionId, title) {
    await api.patch(`/projects/${id}/sessions/${sessionId}`, { title })
    setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, title } : s))
  }

  async function handleDeleteSession(sessionId) {
    try {
      await api.delete(`/projects/${id}/sessions/${sessionId}`)
      const updated = sessions.filter(s => s.id !== sessionId)
      setSessions(updated)
      if (activeSessionId === sessionId) {
        const next = updated[0]
        if (next) { setActiveSessionId(next.id); handleSelectSession(next.id) }
      }
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to delete session.')
    }
  }

  const OFFICE_TYPES = {
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
  }

  function handleFileSelect(e) {
    const file = e.target.files[0]
    if (!file) return

    const isPdf = file.type === 'application/pdf'
    const isOffice = file.type in OFFICE_TYPES

    if (!isPdf && !isOffice) {
      alert('Supported formats: PDF, DOCX, XLSX, PPTX')
      fileRef.current.value = ''
      return
    }

    setPendingFile(file)
    setPendingFileType(isPdf ? 'pdf' : 'office')
    setSelectedCategory('artikel')
    setShowCategoryPicker(true)
  }

  async function handleUploadConfirm() {
    if (!pendingFile) return
    setShowCategoryPicker(false)
    setUploading(true)
    try {
      let docData
      if (pendingFileType === 'pdf') {
        const pages = await extractPdfPages(pendingFile)
        const { data } = await api.post('/documents/upload', {
          project_id: id, filename: pendingFile.name, category: selectedCategory, pages,
        })
        docData = data
      } else {
        const { uploadOfficeFile } = await import('../utils/officeUpload')
        docData = await uploadOfficeFile(pendingFile, id, selectedCategory)
      }
      setDocuments(prev => [...prev, docData])
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to process document. Please try again.')
    }
    setUploading(false)
    setPendingFile(null)
    setPendingFileType('pdf')
    fileRef.current.value = ''
  }

  async function handleDeleteDoc(docId) {
    try {
      await api.delete(`/documents/${docId}`)
      setDocuments(prev => prev.filter(d => d.id !== docId))
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to delete document. Please try again.')
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
      if (data.exists && data.sample_analysis) {
        setVoiceSampleAnalysis(data.sample_analysis)
        setVoiceSampleMode('upload')
      }
    } catch {}
    setVoiceError('')
    setVoiceQ1('')
    setVoiceQ2('')
    setVoiceQ3('')
    setVoiceSampleFile(null)
    setVoiceAnalysisError('')
    setShowVoiceProfile('edit')
  }

  async function handleAnalyseSample() {
    if (!voiceSampleFile) return
    setVoiceAnalysing(true)
    setVoiceAnalysisError('')
    try {
      const formData = new FormData()
      formData.append('file', voiceSampleFile)
      const { data } = await api.post(
        `/voice-profile/${id}/analyse-sample`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      setVoiceSampleAnalysis(data.style_description)
    } catch (err) {
      setVoiceAnalysisError(
        err.response?.data?.detail || 'Analysis failed. Please try again.'
      )
    }
    setVoiceAnalysing(false)
  }

  async function handleSaveVoiceProfile() {
    setVoiceSaving(true)
    setVoiceError('')
    try {
      await api.post(`/voice-profile/${id}`, {
        answers: { q1: voiceQ1, q2: voiceQ2, q3: voiceQ3 },
        sample_excerpt: voiceSampleMode === 'paste' ? (voiceSample || null) : null,
        sample_analysis: voiceSampleMode === 'upload' ? (voiceSampleAnalysis || null) : null,
      })
      setVoiceSaved(true)
      setShowVoiceProfile(false)
    } catch (err) {
      if (err.response?.status === 403) {
        setVoiceError(err.response.data.detail || 'This feature is for Pro users only.')
      } else {
        setVoiceError('Failed to save. Please try again.')
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
      stageLabel: 'Stage 1 / 2 — Chapter 1 (Introduction)',
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
      alert(err.response?.data?.detail || 'Failed to add chapter. Please try again.')
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
      alert(err.response?.data?.detail || 'Failed to delete chapter. Please try again.')
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
      alert('Failed to reorder chapters. Please try again.')
    }
  }

  async function handleRenameChapter(chapterId, newTitle) {
    try {
      await api.patch(`/projects/${id}/chapters/${chapterId}`, { title: newTitle })
      setChapters(prev => prev.map(c => c.id === chapterId ? { ...c, title: newTitle } : c))
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to rename chapter.')
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
          stageLabel: 'Stage 2 / 2 — Chapter 3 (Methodology & Sampling)',
        })
        setProposalBab3Text(null)
      }
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to save suggestion. Please try again.')
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
        c.id === activeChapterId ? { ...c, status: 'dalam_proses', content: text } : c
      ))
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to save content. Please try again.')
    }
    setSaving(false)
  }

  // §6J — set/clear a chapter's word count target (0 = clear, backend sentinel)
  async function handleSetWordTarget(chapterId, target) {
    try {
      const { data } = await api.patch(`/projects/${id}/chapters/${chapterId}`, { word_count_target: target })
      setChapters(prev => prev.map(c =>
        c.id === chapterId ? { ...c, word_count_target: data.word_count_target } : c
      ))
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to save the word target.')
    }
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
          a.download = `${chap?.title ?? 'chapter'}.docx`
          a.click()
          URL.revokeObjectURL(url)
          return
        }
        // Parse JSON status from arraybuffer
        const text = new TextDecoder().decode(poll.data)
        try {
          const json = JSON.parse(text)
          if (json.status === 'error') { alert('Export failed. Please try again.'); return }
        } catch { /* not JSON, keep polling */ }
      }
      alert('Export is taking too long. Please try again.')
    } catch {
      alert('Export failed. Please try again.')
    } finally {
      setExportingChapterId(null)
    }
  }

  async function handleCompile() {
    setCompileError(null)
    setCompileWarning(null)

    // Pre-flight: ada bab?
    if (chapters.length === 0) {
      setCompileError('No chapters yet. Add at least one chapter before compiling.')
      return
    }
    // Pre-flight: ada bab yang ada content?
    const hasContent = chapters.some(c => c.has_content)
    if (!hasContent) {
      setCompileError('All chapters are still empty. Add content to a chapter first.')
      return
    }

    setCompiling(true)
    try {
      const { data: init } = await api.post(`/projects/${id}/compile`)
      if (init.skipped_chapters?.length > 0) {
        setCompileWarning(`${init.skipped_chapters.length} empty chapter(s) will be skipped: ${init.skipped_chapters.join(', ')}`)
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
            setCompileError(`Compile failed: ${json.message ?? 'Unknown error.'}`)
            return
          }
        } catch { /* keep polling */ }
      }
      setCompileError('Compile is taking too long. Please try again.')
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'object' && detail?.code === 'all_chapters_empty') {
        setCompileError(detail.message)
      } else if (typeof detail === 'string') {
        setCompileError(`Compile failed: ${detail}`)
      } else {
        setCompileError('Compile failed. Please try again or contact support.')
      }
    } finally {
      setCompiling(false)
    }
  }

  if (!project) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: 'var(--ink-soft)' }}>Loading...</p>
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
        <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, margin: '0 0 6px', fontSize: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
          <IconUser size={20} stroke={1.5} /> Writing Style Profile
        </h2>
        <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 20px' }}>
          Help the AI understand your writing style for more natural output.{' '}
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
              style={{ padding: '10px 20px', border: '1px solid var(--line)', borderRadius: 8, background: 'transparent', cursor: 'pointer', color: 'var(--ink)', fontSize: 14, display: 'block', width: '100%' }}
            >
              Skip for now
            </button>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: 16 }}>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px' }}>
                1. You prefer sentences that...
              </p>
              {[
                'Short & concise (≤20 words)',
                'Long & detailed (>20 words)',
                'Mixed as needed',
              ].map(opt => (
                <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, cursor: 'pointer', fontSize: 14 }}>
                  <input type="radio" name="vq1" value={opt} checked={voiceQ1 === opt} onChange={() => setVoiceQ1(opt)} />
                  {opt}
                </label>
              ))}
            </div>

            <div style={{ marginBottom: 16 }}>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px' }}>
                2. Your academic writing style...
              </p>
              {[
                'Traditional formal (passive, distant)',
                'Modern & direct (active, clear)',
                "I'm not sure — follow my field's standard",
              ].map(opt => (
                <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, cursor: 'pointer', fontSize: 14 }}>
                  <input type="radio" name="vq2" value={opt} checked={voiceQ2 === opt} onChange={() => setVoiceQ2(opt)} />
                  {opt}
                </label>
              ))}
            </div>

            <div style={{ marginBottom: 16 }}>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px' }}>
                3. Any other preferences? (optional)
              </p>
              <input
                value={voiceQ3}
                onChange={e => setVoiceQ3(e.target.value)}
                placeholder="e.g. avoid first-person pronouns"
                style={{ width: '100%', padding: '8px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 14, boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ marginBottom: 20 }}>
              <p style={{
                fontFamily: 'var(--font-mono)', fontSize: 11,
                textTransform: 'uppercase', letterSpacing: '0.08em',
                color: 'var(--ink-soft)', margin: '0 0 8px',
              }}>
                4. Writing sample (optional)
              </p>

              {/* Tab toggle */}
              <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
                {[
                  { key: 'paste',  label: 'Paste text' },
                  { key: 'upload', label: 'Upload file' },
                ].map(t => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setVoiceSampleMode(t.key)}
                    style={{
                      padding: '5px 12px',
                      background: voiceSampleMode === t.key ? 'var(--ink)' : 'transparent',
                      color: voiceSampleMode === t.key ? 'var(--bg)' : 'var(--ink-soft)',
                      border: voiceSampleMode === t.key ? '1px solid var(--ink)' : '1px solid var(--line)',
                      borderRadius: 5, cursor: 'pointer',
                      fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500,
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {voiceSampleMode === 'paste' ? (
                <textarea
                  value={voiceSample}
                  onChange={e => setVoiceSample(e.target.value)}
                  placeholder="Paste 1–2 paragraphs from your own writing as a style example..."
                  rows={3}
                  style={{
                    width: '100%', padding: '8px 12px',
                    border: '1px solid var(--line)', borderRadius: 8,
                    fontFamily: 'var(--font-body)', fontSize: 14,
                    boxSizing: 'border-box', resize: 'vertical',
                  }}
                />
              ) : (
                <div>
                  <p style={{
                    fontFamily: 'var(--font-body)', fontSize: 12,
                    color: 'var(--ink-soft)', margin: '0 0 8px', lineHeight: 1.5,
                  }}>
                    Upload a document written entirely in your own words — not AI-generated or copied from others.
                    The AI will analyse your writing style from the file.
                  </p>

                  <label style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '8px 12px',
                    border: '1px dashed var(--line)', borderRadius: 8,
                    cursor: 'pointer', fontSize: 13, color: 'var(--ink-soft)',
                    marginBottom: 8,
                  }}>
                    <IconUpload size={15} stroke={1.5} />
                    {voiceSampleFile ? voiceSampleFile.name : 'Choose .docx or .txt file'}
                    <input
                      type="file"
                      accept=".docx,.txt"
                      style={{ display: 'none' }}
                      onChange={e => {
                        setVoiceSampleFile(e.target.files?.[0] || null)
                        setVoiceSampleAnalysis('')
                        setVoiceAnalysisError('')
                      }}
                    />
                  </label>

                  {voiceSampleFile && !voiceSampleAnalysis && (
                    <button
                      type="button"
                      onClick={handleAnalyseSample}
                      disabled={voiceAnalysing}
                      style={{
                        width: '100%', padding: '8px',
                        background: 'var(--accent-soft)',
                        border: '1px solid var(--accent)',
                        borderRadius: 8, cursor: voiceAnalysing ? 'not-allowed' : 'pointer',
                        fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600,
                        color: 'var(--ink)', marginBottom: 8,
                      }}
                    >
                      {voiceAnalysing ? 'Analysing writing style...' : 'Analyse my writing style →'}
                    </button>
                  )}

                  {voiceAnalysisError && (
                    <p style={{ color: '#EF4444', fontSize: 12, margin: '0 0 8px' }}>
                      {voiceAnalysisError}
                    </p>
                  )}

                  {voiceSampleAnalysis && (
                    <div style={{
                      background: 'var(--bg)', border: '1px solid var(--line)',
                      borderRadius: 8, padding: '10px 12px', marginBottom: 4,
                    }}>
                      <p style={{
                        fontFamily: 'var(--font-mono)', fontSize: 10,
                        textTransform: 'uppercase', letterSpacing: '0.05em',
                        color: 'var(--ink-soft)', margin: '0 0 6px',
                      }}>
                        Style analysis result
                      </p>
                      <p style={{
                        fontFamily: 'var(--font-body)', fontSize: 13,
                        color: 'var(--ink)', margin: 0, lineHeight: 1.6,
                      }}>
                        {voiceSampleAnalysis}
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          setVoiceSampleAnalysis('')
                          setVoiceSampleFile(null)
                          setVoiceAnalysisError('')
                        }}
                        style={{
                          marginTop: 8, background: 'none', border: 'none',
                          cursor: 'pointer', color: 'var(--ink-soft)',
                          fontSize: 12, textDecoration: 'underline', padding: 0,
                        }}
                      >
                        Remove and re-upload
                      </button>
                    </div>
                  )}
                </div>
              )}
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

  const helpModal = showHelp ? (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 300,
      }}
      onClick={() => setShowHelp(false)}
    >
      <div
        style={{
          background: 'var(--card)', borderRadius: 'var(--radius-md)',
          padding: 28, width: '100%', maxWidth: 460,
          border: '1px solid var(--line)', maxHeight: '85vh', overflowY: 'auto',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 18, margin: 0 }}>
            Platform Guide
          </h2>
          <button onClick={() => setShowHelp(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 20 }}>×</button>
        </div>

        {[
          {
            q: 'How do I change the project title?',
            a: 'Go to Dashboard (← arrow in header) and click the ⋯ menu on your project card → Rename. Inline title editing on the project page is coming soon.'
          },
          {
            q: 'How do I upload a document?',
            a: 'Click the "Upload document" button in the Sources panel (left side). Supported formats: PDF, DOCX, XLSX, PPTX. Max 20MB per file.'
          },
          {
            q: 'What are Research Credits?',
            a: 'Credits are deducted each time the AI generates a response. Free tier: 50 credits/month. Pro tier: 500 credits/month + option to top up.'
          },
          {
            q: 'How do I export a chapter?',
            a: 'Open the Thesis Structure panel (right side) and click ".docx" next to the chapter you want to export.'
          },
          {
            q: 'What is Style Profile?',
            a: 'Style Profile (Pro only) lets you describe your writing style so the AI output sounds more like you. Access it from the menu bar: Style profile.'
          },
          {
            q: 'How do I search for journal articles?',
            a: 'Click the Search icon (magnifying glass) in the source panel rail to open the Search Articles panel. Enter keywords and filter by year.'
          },
          {
            q: 'What is the Format Guide category?',
            a: "Upload your faculty's thesis formatting guidelines here. Full AI integration for this category is coming in an upcoming update."
          },
        ].map((item, i) => (
          <div key={i} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: i < 6 ? '1px solid var(--line)' : 'none' }}>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600, margin: '0 0 4px', color: 'var(--ink)' }}>
              {item.q}
            </p>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, margin: 0, color: 'var(--ink-soft)', lineHeight: 1.6 }}>
              {item.a}
            </p>
          </div>
        ))}
      </div>
    </div>
  ) : null

  // ── MOBILE LAYOUT ──────────────────────────────────────────────
  if (isMobile) {
    return (
      <div className="mobile-shell" style={{ display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
        {voiceProfileModal}
        {helpModal}
        {/* Header */}
        <header style={{
          borderBottom: '0.5px solid var(--line)',
          padding: '0 14px',
          height: 50,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--card)',
          flexShrink: 0,
          gap: 10,
        }}>
          {/* Left: back + logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <button
              onClick={() => nav('/')}
              aria-label="Back to dashboard"
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--ink-soft)', padding: 4, display: 'flex', alignItems: 'center',
              }}
            >
              <IconArrowLeft size={18} stroke={1.5} />
            </button>
            <Logo size="sm" />
          </div>

          {/* Centre: project title — truncates cleanly */}
          <span style={{
            flex: 1, minWidth: 0,
            fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
            color: 'var(--ink)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            textAlign: 'center',
          }}>
            {project?.title || ''}
          </span>

          {/* Right: credits + avatar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {credits && (
              /* ponytail: compact pill — the full CreditTank card (minWidth 240) blows past a 390px header */
              <span
                title={`Research Credits — resets ${credits.reset_date || ''}`}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
                  padding: '4px 8px', borderRadius: 999,
                  border: '1px solid var(--line)', background: 'var(--bg)',
                  color: (credits.kredit_remaining / credits.kredit_total) < 0.2 ? '#EF4444' : 'var(--ink)',
                  whiteSpace: 'nowrap',
                }}
              >
                {credits.kredit_remaining}/{credits.kredit_total}
              </span>
            )}
            <button
              onClick={() => setShowHelp(true)}
              aria-label="Help"
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--ink-soft)', padding: 4, display: 'flex', alignItems: 'center',
              }}
            >
              <IconHelpCircle size={20} stroke={1.5} />
            </button>
            <ProfileMenu user={user} tier={credits?.tier} />
          </div>
        </header>

        {/* Mobile views */}
        <input type="file" ref={fileRef} onChange={handleFileSelect} accept=".pdf,.docx,.xlsx,.pptx" style={{ display: 'none' }} />

        <div style={{ flex: 1, overflow: 'hidden' }}>
          {showProposalUpload && mobileView === 'editor' && (
            <div style={{
              background: 'var(--card)', border: '1px solid var(--accent)',
              borderRadius: 'var(--radius-md)', padding: 24, margin: 16,
            }}>
              <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px', fontSize: 16 }}>
                Upload Proposal
              </h3>
              <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 16px' }}>
                Upload your approved proposal. The system will extract key information — verify before inserting into a chapter.
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
                <p style={{ color: 'var(--ink-soft)', fontSize: 13 }}>Extracting proposal... (may take 30–60 seconds)</p>
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
            activeChapterId ? (
              <ChapterEditor
                chapter={activeChapter}
                content={contentLoading ? '' : activeChapterContent}
                pendingSuggestion={pendingSuggestion}
                onAccept={handleAcceptSuggestion}
                onReject={handleRejectSuggestion}
                onSave={handleSaveContent}
                onContentChange={setLiveContent}
                saving={saving}
                projectId={id}
                chapterId={activeChapterId}
              />
            ) : (
              <div style={{
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                height: '100%', padding: '0 32px',
                textAlign: 'center', gap: 10,
              }}>
                <IconListTree size={36} stroke={1} color="var(--ink-soft)" />
                <p style={{
                  fontFamily: 'var(--font-heading)', fontSize: 15, fontWeight: 600,
                  color: 'var(--ink)', margin: 0,
                }}>
                  No chapter selected
                </p>
                <p style={{
                  fontFamily: 'var(--font-body)', fontSize: 13,
                  color: 'var(--ink-soft)', margin: 0, lineHeight: 1.6,
                }}>
                  Open the Chapters panel to select or create a chapter.
                </p>
                <button
                  onClick={() => setMobileView('chapters')}
                  style={{
                    marginTop: 6,
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '9px 18px',
                    background: 'var(--ink)', color: 'var(--bg)',
                    border: 'none', borderRadius: 8,
                    fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  <IconListTree size={15} stroke={2} />
                  Open Chapters
                </button>
              </div>
            )
          )}
          {mobileView === 'sources' && (
            <div className="mobile-tab-panel">
              <SourcePanel
                documents={documents}
                onUpload={() => { fileRef.current?.click() }}
                tier={credits?.tier ?? user?.tier}
                uploading={uploading}
                collapsed={false}
                onToggleCollapse={() => {}}
                onDeleteDoc={handleDeleteDoc}
                projectId={id}
                onAcceptArticle={handleAcceptArticle}
                onShowHelp={() => setShowHelp(true)}
              />
            </div>
          )}
          {mobileView === 'chapters' && (
            <div className="mobile-tab-panel">
              <ThesisPanel
                chapters={sortedChapters}
                onExport={handleExport}
                exportingChapterId={exportingChapterId}
                tier={credits?.tier ?? user?.tier}
                projectId={id}
                activeChapterId={activeChapterId}
                onSetActive={ch => { handleSetActive(ch); setMobileView('editor') }}
                onAddChapter={handleAddChapter}
                onDeleteChapter={handleDeleteChapter}
                onReorderChapter={handleReorderChapter}
                onRenameChapter={handleRenameChapter}
                onSetWordTarget={handleSetWordTarget}
                activeContentOverride={liveContent}
                onCompile={handleCompile}
                compiling={compiling}
                compileError={compileError}
                compileWarning={compileWarning}
                onDismissError={() => setCompileError(null)}
              />
            </div>
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
              useWebSearch={useWebSearch}
              onWebSearchToggle={setUseWebSearch}
              isPro={isPro}
              sessions={sessions}
              activeSessionId={activeSessionId}
              onNewSession={handleNewSession}
              onSelectSession={handleSelectSession}
              onRenameSession={handleRenameSession}
              onDeleteSession={handleDeleteSession}
            />
          )}
        </div>

        {/* Bottom navigation */}
        <div style={{
          height: 54,
          background: 'var(--card)',
          borderTop: '0.5px solid var(--line)',
          display: 'flex',
          alignItems: 'center',
          flexShrink: 0,
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}>
          {[
            { key: 'sources',  label: 'Sources',  icon: <IconFiles size={22} stroke={1.5} /> },
            { key: 'chapters', label: 'Chapters', icon: <IconListTree size={22} stroke={1.5} /> },
            { key: 'editor',   label: 'Editor',   icon: <IconPencil size={22} stroke={1.5} /> },
            { key: 'chat',     label: 'Chat',     icon: <IconMessageCircle size={22} stroke={1.5} /> },
          ].map(item => (
            <button
              key={item.key}
              aria-label={item.label}
              onClick={() => setMobileView(item.key)}
              style={{
                flex: 1, height: '100%',
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                gap: 3,
                background: mobileView === item.key ? 'var(--card)' : 'none',
                border: 'none', cursor: 'pointer', position: 'relative',
                color: mobileView === item.key ? 'var(--ink)' : 'var(--ink-soft)',
                borderTop: mobileView === item.key ? '2px solid var(--accent)' : '2px solid transparent',
                transition: 'color 0.1s, border-color 0.1s',
              }}
            >
              {item.icon}
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: mobileView === item.key ? 600 : 500, letterSpacing: '0.02em' }}>
                {item.label}
              </span>
              {item.key === 'editor' && pendingSuggestion && mobileView !== 'editor' && (
                <span style={{
                  position: 'absolute', top: 8, right: 'calc(50% - 18px)',
                  width: 6, height: 6,
                  background: 'var(--accent)', borderRadius: '50%',
                }} />
              )}
            </button>
          ))}
        </div>

      </div>
    )
  }

  // ── DESKTOP LAYOUT ─────────────────────────────────────────────
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <OnboardingTour active={initMode === 'discovery'} isPro={isPro} />
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
                } catch { alert('Failed to initiate top-up. Please try again.') }
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
          ><IconFile size={15} stroke={1.5} /> File <span style={{ fontSize: 10, opacity: 0.7 }}>▾</span></button>
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
                  Compile Full Thesis <span style={{ fontSize: 10, background: 'var(--line)', padding: '1px 5px', borderRadius: 3, marginLeft: 4 }}>Pro</span>
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
            <IconUser size={15} stroke={1.5} /> Style profile{voiceSaved ? ' ✓' : ''}
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
          ><IconLayout size={15} stroke={1.5} /> View <span style={{ fontSize: 10, opacity: 0.7 }}>▾</span></button>
          {openMenu === 'paparan' && (
            <div onClick={e => e.stopPropagation()} style={{
              position: 'absolute', top: '100%', left: 0, zIndex: 100,
              background: 'var(--card)', border: '1px solid var(--line)',
              borderRadius: 'var(--radius-sm)', boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              minWidth: 200,
            }}>
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
        <input type="file" ref={fileRef} onChange={handleFileSelect} accept=".pdf,.docx,.xlsx,.pptx" style={{ display: 'none' }} />

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
          onShowHelp={() => setShowHelp(true)}
        />

        {/* Proposal Upload Panel */}
        {showProposalUpload && (
          <div style={{
            position: 'absolute', top: 60, left: 200, right: 320, zIndex: 10,
            background: 'var(--card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-md)', padding: 24, margin: 16,
          }}>
            <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px', fontSize: 16 }}>
              Upload Proposal
            </h3>
            <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 16px' }}>
              Upload your approved proposal. The system will extract key information — verify before inserting into a chapter.
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
              <p style={{ color: 'var(--ink-soft)', fontSize: 13 }}>Extracting proposal... (may take 30–60 seconds)</p>
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
          onContentChange={setLiveContent}
          saving={saving}
          projectId={id}
          chapterId={activeChapterId}
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
            useWebSearch={useWebSearch}
            onWebSearchToggle={setUseWebSearch}
            isPro={isPro}
            sessions={sessions}
            activeSessionId={activeSessionId}
            onNewSession={handleNewSession}
            onSelectSession={handleSelectSession}
            onRenameSession={handleRenameSession}
            onDeleteSession={handleDeleteSession}
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
          onSetWordTarget={handleSetWordTarget}
          activeContentOverride={liveContent}
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
              Select Category
            </p>
            <p style={{ margin: '0 0 16px', fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-soft)', wordBreak: 'break-all' }}>
              {pendingFile.name}
            </p>
            {pendingFileType === 'office' && (
              <p style={{
                margin: '0 0 12px',
                fontSize: 11,
                color: 'var(--ink-soft)',
                fontFamily: 'var(--font-body)',
                lineHeight: 1.5,
              }}>
                Office files are processed on our server and immediately deleted after text extraction.
              </p>
            )}
            {[
              { value: 'artikel', label: 'Reference Articles', icon: '📄' },
              { value: 'proposal', label: 'Research Proposal', icon: '📋' },
              { value: 'catatan_sv', label: 'SV Notes', icon: '📝' },
              { value: 'draf', label: 'Own Draft', icon: '📑' },
              { value: 'data', label: 'Data / Transcript', icon: '📊' },
              { value: 'panduan_format', label: 'Faculty Format Guide', icon: '🏫' },
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
              >Upload</button>
              <button
                onClick={() => { setShowCategoryPicker(false); setPendingFile(null); fileRef.current.value = '' }}
                style={{
                  padding: '9px 16px', background: 'transparent',
                  border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
                  fontFamily: 'var(--font-body)', fontSize: 13, cursor: 'pointer',
                }}
              >Cancel</button>
            </div>
          </div>
        </div>
      )}

      {helpModal}
    </div>
  )
}

