import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  IconArrowLeft, IconPlus, IconTrash, IconChevronUp, IconChevronDown,
  IconSparkles, IconDownload, IconChevronRight, IconClipboardList,
} from '@tabler/icons-react'
import api from '../api/client'
import { Logo } from './Logo'

const QUESTION_TYPES = [
  { value: 'likert', label: 'Likert' },
  { value: 'mcq', label: 'MCQ' },
  { value: 'open', label: 'Open-ended' },
  { value: 'demographic', label: 'Demographic' },
]

const GENERATE_COST = 10

function Stepper() {
  const steps = [
    { n: 1, label: 'Build', active: true },
    { n: 2, label: 'Collect', active: false },
    { n: 3, label: 'Analyse', active: false },
  ]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {steps.map((s, i) => (
        <div key={s.n} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div
            title={s.active ? undefined : 'Coming soon'}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '5px 12px', borderRadius: 999,
              background: s.active ? 'var(--accent-soft)' : 'transparent',
              border: s.active ? '1px solid var(--accent)' : '1px solid var(--line)',
              color: s.active ? 'var(--ink)' : 'var(--ink-soft)',
              opacity: s.active ? 1 : 0.55,
              fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: s.active ? 600 : 400,
              cursor: 'default', userSelect: 'none',
            }}
          >
            {s.n}. {s.label}
            {!s.active && <span style={{ fontSize: 9 }}>· Coming soon</span>}
          </div>
          {i < steps.length - 1 && <IconChevronRight size={13} stroke={1.5} color="var(--ink-soft)" />}
        </div>
      ))}
    </div>
  )
}

function QuestionRow({ q, index, total, onChange, onDelete, onMove }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(q.question_text)
  const [qtype, setQtype] = useState(q.question_type)
  const [optionsStr, setOptionsStr] = useState((q.options || []).join(', '))
  const [points, setPoints] = useState(q.likert_points || 5)

  const save = () => {
    const payload = { question_text: text, question_type: qtype }
    if (qtype === 'open') {
      payload.options = []
      payload.likert_points = null
    } else {
      payload.options = optionsStr.split(',').map(s => s.trim()).filter(Boolean)
      payload.likert_points = qtype === 'likert' ? Number(points) : null
    }
    onChange(payload)
    setEditing(false)
  }

  if (!editing) {
    return (
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 10px',
        borderBottom: '1px solid var(--line)',
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, margin: 0, color: 'var(--ink)' }}>
            {index + 1}. {q.question_text}
          </p>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, margin: '3px 0 0', color: 'var(--ink-soft)' }}>
            {q.question_type}
            {q.question_type === 'likert' && ` · ${q.likert_points || 5}-point`}
            {q.options?.length ? ` · ${q.options.join(' / ')}` : ''}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
          <button onClick={() => onMove(-1)} disabled={index === 0} title="Move up"
            style={{ background: 'none', border: 'none', cursor: index === 0 ? 'default' : 'pointer', color: 'var(--ink-soft)', opacity: index === 0 ? 0.3 : 1, padding: 2 }}>
            <IconChevronUp size={15} stroke={1.5} />
          </button>
          <button onClick={() => onMove(1)} disabled={index === total - 1} title="Move down"
            style={{ background: 'none', border: 'none', cursor: index === total - 1 ? 'default' : 'pointer', color: 'var(--ink-soft)', opacity: index === total - 1 ? 0.3 : 1, padding: 2 }}>
            <IconChevronDown size={15} stroke={1.5} />
          </button>
          <button onClick={() => setEditing(true)} title="Edit question"
            style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 5, cursor: 'pointer', color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 7px' }}>
            Edit
          </button>
          <button onClick={onDelete} title="Delete question"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', padding: 2 }}>
            <IconTrash size={14} stroke={1.5} />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: '10px', borderBottom: '1px solid var(--line)', background: 'var(--bg)' }}>
      <textarea
        value={text} onChange={e => setText(e.target.value)} rows={2}
        style={{ width: '100%', padding: '7px 10px', border: '1px solid var(--line)', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 13, boxSizing: 'border-box', resize: 'vertical', marginBottom: 6 }}
      />
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 6 }}>
        <select value={qtype} onChange={e => setQtype(e.target.value)}
          style={{ padding: '5px 8px', border: '1px solid var(--line)', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 12 }}>
          {QUESTION_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        {qtype === 'likert' && (
          <select value={points} onChange={e => setPoints(e.target.value)}
            style={{ padding: '5px 8px', border: '1px solid var(--line)', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 12 }}>
            {[4, 5, 7].map(p => <option key={p} value={p}>{p}-point</option>)}
          </select>
        )}
      </div>
      {qtype !== 'open' && (
        <input
          value={optionsStr} onChange={e => setOptionsStr(e.target.value)}
          placeholder="Options, separated by commas"
          style={{ width: '100%', padding: '7px 10px', border: '1px solid var(--line)', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 12, boxSizing: 'border-box', marginBottom: 6 }}
        />
      )}
      <div style={{ display: 'flex', gap: 6 }}>
        <button onClick={save}
          style={{ padding: '6px 14px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
          Save
        </button>
        <button onClick={() => setEditing(false)}
          style={{ padding: '6px 14px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 12, cursor: 'pointer', color: 'var(--ink-soft)' }}>
          Cancel
        </button>
      </div>
    </div>
  )
}

export function SurveyBuilder() {
  const { id: projectId } = useParams()
  const nav = useNavigate()
  const [survey, setSurvey] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [collapsed, setCollapsed] = useState({}) // sectionId -> bool

  const loadSurvey = useCallback(async () => {
    try {
      const { data: list } = await api.get(`/projects/${projectId}/surveys`)
      let sid = list[0]?.id
      if (!sid) {
        const { data: created } = await api.post(`/projects/${projectId}/surveys`, {})
        sid = created.id
      }
      const { data: full } = await api.get(`/surveys/${sid}`)
      setSurvey(full)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to load survey.')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { loadSurvey() }, [loadSurvey])

  const refresh = async () => {
    const { data: full } = await api.get(`/surveys/${survey.id}`)
    setSurvey(full)
  }

  const handleGenerate = async () => {
    const hasContent = survey.sections.length > 0
    const msg = hasContent
      ? `Generate with AI uses ${GENERATE_COST} credits and will REPLACE all existing sections & questions. Continue?`
      : `Generate with AI uses ${GENERATE_COST} credits. Continue?`
    if (!window.confirm(msg)) return
    setGenerating(true)
    setError('')
    try {
      const { data } = await api.post(`/surveys/${survey.id}/generate`, { scope: 'full' })
      setSurvey(data)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Generation failed. Please try again.')
    } finally {
      setGenerating(false)
    }
  }

  const handleExport = async () => {
    try {
      const resp = await api.get(`/surveys/${survey.id}/export/docx`, { responseType: 'blob' })
      const url = URL.createObjectURL(resp.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `${survey.title || 'soal-selidik'}.docx`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('Export failed. Please try again.')
    }
  }

  const handleRename = async () => {
    const title = window.prompt('Survey title:', survey.title)
    if (!title || title === survey.title) return
    await api.patch(`/surveys/${survey.id}`, { title })
    setSurvey(s => ({ ...s, title }))
  }

  const addSection = async () => {
    const title = window.prompt('Section title:', `Bahagian ${String.fromCharCode(65 + survey.sections.length)}`)
    if (!title) return
    await api.post(`/surveys/${survey.id}/sections`, { title })
    refresh()
  }

  const renameSection = async (sec) => {
    const title = window.prompt('Section title:', sec.title)
    if (!title || title === sec.title) return
    await api.patch(`/sections/${sec.id}`, { title })
    refresh()
  }

  const deleteSection = async (sec) => {
    if (!window.confirm(`Delete "${sec.title}" and all its questions?`)) return
    await api.delete(`/sections/${sec.id}`)
    refresh()
  }

  const moveSection = async (sec, dir) => {
    const sorted = survey.sections
    const idx = sorted.findIndex(s => s.id === sec.id)
    const swap = sorted[idx + dir]
    if (!swap) return
    await api.patch(`/sections/${sec.id}`, { position: swap.position })
    await api.patch(`/sections/${swap.id}`, { position: sec.position })
    refresh()
  }

  const addQuestion = async (sec) => {
    await api.post(`/sections/${sec.id}/questions`, {
      question_text: 'New question',
      question_type: 'likert',
      options: ['Sangat Tidak Setuju', 'Tidak Setuju', 'Tidak Pasti', 'Setuju', 'Sangat Setuju'],
      likert_points: 5,
    })
    refresh()
  }

  const updateQuestion = async (q, payload) => {
    await api.patch(`/questions/${q.id}`, payload)
    refresh()
  }

  const deleteQuestion = async (q) => {
    await api.delete(`/questions/${q.id}`)
    refresh()
  }

  const moveQuestion = async (sec, q, dir) => {
    const idx = sec.questions.findIndex(x => x.id === q.id)
    const swap = sec.questions[idx + dir]
    if (!swap) return
    await api.patch(`/questions/${q.id}`, { position: swap.position })
    await api.patch(`/questions/${swap.id}`, { position: q.position })
    refresh()
  }

  if (loading) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: 'var(--ink-soft)' }}>Loading...</p>
    </div>
  )

  if (!survey) return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)', gap: 12, padding: 24, textAlign: 'center' }}>
      <p style={{ color: 'var(--ink)', fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15, margin: 0 }}>
        Failed to load survey
      </p>
      <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: 0 }}>{error || 'Please try again.'}</p>
      <button
        onClick={() => nav(`/project/${projectId}`)}
        style={{ padding: '8px 18px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
      >
        Back to workspace
      </button>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{
        borderBottom: '1px solid var(--line)', padding: '0 20px', height: 56,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'var(--card)', flexShrink: 0, gap: 12, flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <button
            onClick={() => nav(`/project/${projectId}`)}
            aria-label="Back to workspace"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', padding: 4, display: 'flex' }}
          >
            <IconArrowLeft size={18} stroke={1.5} />
          </button>
          <Logo size="sm" />
          <IconClipboardList size={16} stroke={1.5} color="var(--ink-soft)" />
          <button
            onClick={handleRename}
            title="Rename survey"
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15, color: 'var(--ink)',
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 260, padding: 0,
            }}
          >
            {survey?.title}
          </button>
        </div>
        <Stepper />
      </header>

      {/* Toolbar */}
      <div style={{
        display: 'flex', gap: 8, padding: '12px 20px', flexWrap: 'wrap',
        borderBottom: '1px solid var(--line)', background: 'var(--card)', flexShrink: 0,
      }}>
        <button
          onClick={handleGenerate}
          disabled={generating}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px',
            background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 8,
            fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600,
            cursor: generating ? 'not-allowed' : 'pointer', opacity: generating ? 0.6 : 1,
          }}
        >
          <IconSparkles size={15} stroke={1.5} />
          {generating ? 'Generating draft...' : `Generate with AI — ${GENERATE_COST} credits`}
        </button>
        <button
          onClick={addSection}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, cursor: 'pointer', color: 'var(--ink)' }}
        >
          <IconPlus size={14} stroke={1.5} /> Section
        </button>
        <button
          onClick={handleExport}
          disabled={!survey?.sections?.length}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, cursor: survey?.sections?.length ? 'pointer' : 'not-allowed', color: 'var(--ink)', opacity: survey?.sections?.length ? 1 : 0.5 }}
        >
          <IconDownload size={14} stroke={1.5} /> Export .docx
        </button>
      </div>

      {error && (
        <p style={{ color: '#EF4444', fontSize: 13, margin: 0, padding: '10px 20px' }}>{error}</p>
      )}

      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', maxWidth: 860, width: '100%', margin: '0 auto', boxSizing: 'border-box' }}>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 14px' }}>
          AI draft — review with your supervisor. This instrument requires expert review & a pilot study before use.
        </p>

        {survey.sections.length === 0 ? (
          <div style={{
            border: '1px dashed var(--line)', borderRadius: 'var(--radius-md)',
            padding: '48px 24px', textAlign: 'center', background: 'var(--card)',
          }}>
            <IconClipboardList size={32} stroke={1} color="var(--ink-soft)" />
            <p style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15, margin: '10px 0 6px', color: 'var(--ink)' }}>
              No sections yet
            </p>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)', margin: 0, lineHeight: 1.6 }}>
              Generate an instrument draft from your project documents with "Generate with AI",
              or build manually with "+ Section".
            </p>
          </div>
        ) : (
          survey.sections.map((sec, si) => (
            <div key={sec.id} style={{
              border: '1px solid var(--line)', borderRadius: 'var(--radius-md)',
              background: 'var(--card)', marginBottom: 12, overflow: 'hidden',
            }}>
              {/* Section header */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 12px', borderBottom: collapsed[sec.id] ? 'none' : '1px solid var(--line)' }}>
                <button
                  onClick={() => setCollapsed(c => ({ ...c, [sec.id]: !c[sec.id] }))}
                  aria-label={collapsed[sec.id] ? 'Expand section' : 'Collapse section'}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', padding: 2, display: 'flex' }}
                >
                  {collapsed[sec.id] ? <IconChevronRight size={15} stroke={1.5} /> : <IconChevronDown size={15} stroke={1.5} />}
                </button>
                <button
                  onClick={() => renameSection(sec)}
                  title="Rename section"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, color: 'var(--ink)', padding: 0, flex: 1, textAlign: 'left', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {sec.title}
                </button>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)', flexShrink: 0 }}>
                  {sec.questions.length} question{sec.questions.length === 1 ? '' : 's'}
                </span>
                <button onClick={() => moveSection(sec, -1)} disabled={si === 0} title="Move section up"
                  style={{ background: 'none', border: 'none', cursor: si === 0 ? 'default' : 'pointer', color: 'var(--ink-soft)', opacity: si === 0 ? 0.3 : 1, padding: 2 }}>
                  <IconChevronUp size={15} stroke={1.5} />
                </button>
                <button onClick={() => moveSection(sec, 1)} disabled={si === survey.sections.length - 1} title="Move section down"
                  style={{ background: 'none', border: 'none', cursor: si === survey.sections.length - 1 ? 'default' : 'pointer', color: 'var(--ink-soft)', opacity: si === survey.sections.length - 1 ? 0.3 : 1, padding: 2 }}>
                  <IconChevronDown size={15} stroke={1.5} />
                </button>
                <button onClick={() => deleteSection(sec)} title="Delete section"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', padding: 2 }}>
                  <IconTrash size={15} stroke={1.5} />
                </button>
              </div>

              {/* Questions */}
              {!collapsed[sec.id] && (
                <>
                  {sec.questions.map((q, qi) => (
                    <QuestionRow
                      key={q.id}
                      q={q}
                      index={qi}
                      total={sec.questions.length}
                      onChange={payload => updateQuestion(q, payload)}
                      onDelete={() => deleteQuestion(q)}
                      onMove={dir => moveQuestion(sec, q, dir)}
                    />
                  ))}
                  <button
                    onClick={() => addQuestion(sec)}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '8px 10px', padding: '6px 12px', background: 'transparent', border: '1px dashed var(--line)', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 12, cursor: 'pointer', color: 'var(--ink-soft)' }}
                  >
                    <IconPlus size={13} stroke={1.5} /> Question
                  </button>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
