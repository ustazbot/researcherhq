import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { ProfileMenu } from '../components/ProfileMenu'
import { CitationCard } from '../components/CitationCard'
import { SourcePanel } from '../components/SourcePanel'
import { ThesisPanel } from '../components/ThesisPanel'
import api from '../api/client'

const OUTPUT_MODES = [
  { value: 'qa', label: 'Soal-Jawab', credits: 1 },
  { value: 'key_findings', label: 'Dapatan Utama', credits: 3 },
  { value: 'executive_summary', label: 'Ringkasan Eksekutif', credits: 5 },
  { value: 'literature_review', label: 'Sorotan Kajian', credits: 10 },
]

export function ProjectPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const [project, setProject] = useState(null)
  const [messages, setMessages] = useState([])
  const [documents, setDocuments] = useState([])
  const [chapters, setChapters] = useState([])
  const [query, setQuery] = useState('')
  const [outputMode, setOutputMode] = useState('qa')
  const [loading, setLoading] = useState(false)
  const [credits, setCredits] = useState(null)
  const [uploading, setUploading] = useState(false)
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
    setUploading(true)
    try {
      alert(`Dokumen "${file.name}" sedang diproses. (PDF.js extraction dalam fasa penuh)`)
    } catch {
      alert('Gagal muat naik dokumen.')
    }
    setUploading(false)
    fileRef.current.value = ''
  }

  async function handleExport(chapterId) {
    alert(`Export .docx untuk bab ini akan tersedia tidak lama lagi.`)
  }

  if (!project) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: 'var(--ink-soft)' }}>Memuatkan...</p>
    </div>
  )

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
          <ProfileMenu user={user} />
        </div>
      </header>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <input type="file" ref={fileRef} onChange={handleFileUpload} accept=".pdf" style={{ display: 'none' }} />
        <SourcePanel
          documents={documents}
          onUpload={() => fileRef.current?.click()}
          tier={user?.tier}
        />

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ flex: 1, overflow: 'auto', padding: '24px', maxWidth: 800, width: '100%', margin: '0 auto', boxSizing: 'border-box' }}>
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--ink-soft)' }}>
                <p style={{ fontSize: 18, fontWeight: 500 }}>Muat naik dokumen dan mula bertanya.</p>
                <p style={{ fontSize: 14 }}>Semua jawapan akan bersumberkan dokumen anda sahaja.</p>
              </div>
            )}
            {messages.map(msg => (
              <div key={msg.id} style={{
                marginBottom: 24, display: 'flex', flexDirection: 'column',
                alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}>
                <div style={{
                  maxWidth: '85%',
                  background: msg.role === 'user' ? 'var(--ink)' : msg.role === 'error' ? '#FEF2F2' : 'var(--card)',
                  color: msg.role === 'user' ? 'var(--bg)' : msg.role === 'error' ? '#EF4444' : 'var(--ink)',
                  border: msg.role === 'user' ? 'none' : `1px solid ${msg.role === 'error' ? '#FECACA' : 'var(--line)'}`,
                  borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
                  padding: '14px 18px', fontFamily: 'var(--font-body)', fontSize: 15,
                  lineHeight: 1.6, whiteSpace: 'pre-wrap',
                }}>
                  {msg.content}
                  {msg.kredit_used && (
                    <span style={{ display: 'block', marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 11, opacity: 0.6 }}>
                      {msg.kredit_used} kredit digunakan
                    </span>
                  )}
                </div>
                {msg.sources && msg.sources.length > 0 && (
                  <div style={{ marginTop: 8, maxWidth: '85%', width: '100%' }}>
                    <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 6px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                      Sumber ({msg.sources.length})
                    </p>
                    {msg.sources.map(s => <CitationCard key={s.chunk_id} source={s} />)}
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 24 }}>
                <div style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: '4px 16px 16px 16px', padding: '14px 18px' }}>
                  <span style={{ color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)' }}>Berfikir...</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div style={{ borderTop: '1px solid var(--line)', padding: '16px 24px', background: 'var(--card)', flexShrink: 0 }}>
            <div style={{ maxWidth: 800, margin: '0 auto' }}>
              <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
                {OUTPUT_MODES.map(m => (
                  <button key={m.value} onClick={() => setOutputMode(m.value)} style={{
                    padding: '4px 10px',
                    background: outputMode === m.value ? 'var(--ink)' : 'transparent',
                    color: outputMode === m.value ? 'var(--bg)' : 'var(--ink-soft)',
                    border: `1px solid ${outputMode === m.value ? 'var(--ink)' : 'var(--line)'}`,
                    borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer',
                  }}>
                    {m.label} ({m.credits} kr)
                  </button>
                ))}
              </div>
              <form onSubmit={handleQuery} style={{ display: 'flex', gap: 8 }}>
                <input
                  value={query} onChange={e => setQuery(e.target.value)}
                  placeholder="Tanya soalan berdasarkan dokumen anda..."
                  disabled={loading}
                  style={{
                    flex: 1, padding: '12px 16px',
                    border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
                    fontFamily: 'var(--font-body)', fontSize: 15, background: 'var(--bg)', outline: 'none',
                  }}
                />
                <button type="submit" disabled={loading || !query.trim()} style={{
                  padding: '12px 20px', background: 'var(--accent)', color: 'var(--ink)',
                  border: 'none', borderRadius: 'var(--radius-sm)',
                  fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15, cursor: 'pointer',
                }}>
                  →
                </button>
              </form>
            </div>
          </div>
        </div>

        <ThesisPanel
          chapters={chapters}
          onExport={handleExport}
          tier={user?.tier}
          projectId={id}
        />
      </div>
    </div>
  )
}
