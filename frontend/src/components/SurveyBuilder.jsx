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

function Stepper({ view, onSelect }) {
  const steps = [
    { n: 1, label: 'Build', key: 'build', enabled: true },
    { n: 2, label: 'Collect', key: 'collect', enabled: true },
    { n: 3, label: 'Analyse', key: 'analyse', enabled: true },
  ]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {steps.map((s, i) => {
        const isActive = view === s.key
        return (
          <div key={s.n} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              onClick={() => s.enabled && onSelect(s.key)}
              disabled={!s.enabled}
              title={s.enabled ? undefined : 'Coming soon'}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '5px 12px', borderRadius: 999,
                background: isActive ? 'var(--accent-soft)' : 'transparent',
                border: isActive ? '1px solid var(--accent)' : '1px solid var(--line)',
                color: isActive ? 'var(--ink)' : 'var(--ink-soft)',
                opacity: s.enabled ? 1 : 0.5,
                fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: isActive ? 600 : 400,
                cursor: s.enabled ? 'pointer' : 'not-allowed', userSelect: 'none',
              }}
            >
              {s.n}. {s.label}
              {!s.enabled && <span style={{ fontSize: 9 }}>· Coming soon</span>}
            </button>
            {i < steps.length - 1 && <IconChevronRight size={13} stroke={1.5} color="var(--ink-soft)" />}
          </div>
        )
      })}
    </div>
  )
}

const STATUS_BADGE = {
  draft: { label: 'Draft', bg: 'var(--line)', fg: 'var(--ink-soft)' },
  pilot: { label: 'Pilot — collecting', bg: 'var(--accent-soft)', fg: 'var(--ink)' },
  pilot_closed: { label: 'Pilot closed', bg: 'var(--line)', fg: 'var(--ink-soft)' },
  published: { label: 'Published — collecting', bg: 'var(--accent-soft)', fg: 'var(--ink)' },
  closed: { label: 'Closed', bg: 'var(--line)', fg: 'var(--ink-soft)' },
}

function CollectView({ survey, setSurvey, refresh }) {
  const [mode, setMode] = useState('pilot')
  const [summary, setSummary] = useState(null)
  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const status = survey.status
  const collecting = status === 'pilot' || status === 'published'
  const shareUrl = survey.share_token ? `${window.location.origin}/app/s/${survey.share_token}` : ''

  const loadSummary = useCallback(async () => {
    if (!survey.share_token && status === 'draft') { setSummary(null); return }
    try {
      const { data } = await api.get(`/surveys/${survey.id}/responses?type=all`)
      setSummary(data)
    } catch { /* ignore */ }
  }, [survey.id, survey.share_token, status])

  useEffect(() => { loadSummary() }, [loadSummary])

  const act = async (path, body, confirmMsg) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return
    setBusy(true); setErr('')
    try {
      const { data } = await api.post(`/surveys/${survey.id}/${path}`, body || {})
      setSurvey(data)
      await refresh()
      await loadSummary()
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  const publish = () => act('publish', { mode },
    'The structure will be locked while collecting responses. Continue?')
  const close = () => act('close')
  const reopen = () => act('reopen')
  const unlock = () => act('unlock',
    null, 'Editing or deleting questions will also delete their pilot answers. Continue?')
  const unpublish = () => act('unpublish', null, 'Return this survey to draft? Only allowed with zero actual responses.')

  const exportCsv = async (type) => {
    try {
      const resp = await api.get(`/surveys/${survey.id}/export/csv?type=${type}`, { responseType: 'blob' })
      const url = URL.createObjectURL(resp.data)
      const a = document.createElement('a')
      a.href = url; a.download = `${survey.title || 'survey'}-${type}.csv`; a.click()
      URL.revokeObjectURL(url)
    } catch { setErr('Export failed.') }
  }

  const deleteAll = async (type) => {
    if (!window.confirm(`Delete ALL ${type} responses? This cannot be undone.`)) return
    setBusy(true)
    try { await api.delete(`/surveys/${survey.id}/responses?type=${type}`); await loadSummary() }
    catch { setErr('Delete failed.') } finally { setBusy(false) }
  }

  const deleteOne = async (rid) => {
    if (!window.confirm('Delete this response?')) return
    try { await api.delete(`/surveys/${survey.id}/responses/${rid}`); setDetail(null); await loadSummary() }
    catch { setErr('Delete failed.') }
  }

  const viewDetail = async (rid) => {
    try { const { data } = await api.get(`/surveys/${survey.id}/responses/${rid}`); setDetail(data) }
    catch { /* ignore */ }
  }

  const badge = STATUS_BADGE[status] || STATUS_BADGE.draft
  const box = { border: '1px solid var(--line)', borderRadius: 'var(--radius-md)', background: 'var(--card)', padding: 18, marginBottom: 14 }
  const btn = (bg, fg) => ({ padding: '8px 14px', background: bg, color: fg, border: bg === 'transparent' ? '1px solid var(--line)' : 'none', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600, cursor: busy ? 'not-allowed' : 'pointer', opacity: busy ? 0.6 : 1 })

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', maxWidth: 860, width: '100%', margin: '0 auto', boxSizing: 'border-box' }}>
      {err && <p style={{ color: '#EF4444', fontSize: 13 }}>{err}</p>}

      {/* Status + actions */}
      <div style={box}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, padding: '4px 10px', borderRadius: 999, background: badge.bg, color: badge.fg }}>
            {badge.label}
          </span>
          {collecting && summary && (
            <span style={{ fontSize: 12, color: 'var(--ink-soft)' }}>
              {(status === 'pilot' ? summary.counts.pilot : summary.counts.actual)} / {survey.response_cap} responses
              {summary.last_7_days > 0 && ` · ${summary.last_7_days} in last 7 days`}
            </span>
          )}
        </div>

        {status === 'draft' && (
          <>
            <p style={{ fontSize: 13, color: 'var(--ink-soft)', margin: '0 0 10px' }}>Publish to get a shareable public link. Respondents don't need an account.</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
              <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 13, cursor: 'pointer' }}>
                <input type="radio" name="mode" checked={mode === 'pilot'} onChange={() => setMode('pilot')} />
                <span><b>Pilot</b> — trial run (max 50). Can be reopened for edits after your pilot study; pilot responses are kept for reliability analysis.</span>
              </label>
              <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 13, cursor: 'pointer' }}>
                <input type="radio" name="mode" checked={mode === 'actual'} onChange={() => setMode('actual')} />
                <span><b>Actual</b> — real data collection (up to 1,000 responses).</span>
              </label>
            </div>
            <button onClick={publish} disabled={busy} style={btn('var(--ink)', 'var(--bg)')}>Publish</button>
          </>
        )}

        {collecting && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input readOnly value={shareUrl} style={{ flex: 1, minWidth: 220, padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-mono)', fontSize: 12 }} />
            <button onClick={() => navigator.clipboard?.writeText(shareUrl)} style={btn('transparent', 'var(--ink)')}>Copy link</button>
            <button onClick={close} disabled={busy} style={btn('transparent', 'var(--ink)')}>Close</button>
            {status === 'published' && <button onClick={unpublish} disabled={busy} style={btn('transparent', 'var(--ink)')}>Unpublish</button>}
          </div>
        )}

        {(status === 'pilot_closed' || status === 'closed') && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button onClick={reopen} disabled={busy} style={btn('var(--ink)', 'var(--bg)')}>Reopen</button>
            {status === 'pilot_closed' && <button onClick={unlock} disabled={busy} style={btn('transparent', 'var(--ink)')}>Unlock &amp; edit</button>}
          </div>
        )}
      </div>

      {/* Responses */}
      {summary && (summary.counts.all > 0) && (
        <div style={box}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14 }}>
              Responses — {summary.counts.pilot} pilot · {summary.counts.actual} actual
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              {summary.counts.pilot > 0 && <button onClick={() => exportCsv('pilot')} style={btn('transparent', 'var(--ink)')}>CSV (pilot)</button>}
              {summary.counts.actual > 0 && <button onClick={() => exportCsv('actual')} style={btn('transparent', 'var(--ink)')}>CSV (actual)</button>}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {summary.responses.map(r => (
              <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: '1px solid var(--line)', fontSize: 13 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 6px', borderRadius: 4, background: r.is_pilot ? 'var(--accent-soft)' : 'var(--line)', color: 'var(--ink-soft)' }}>
                  {r.is_pilot ? 'pilot' : 'actual'}
                </span>
                <span style={{ flex: 1, color: 'var(--ink-soft)' }}>{new Date(r.submitted_at).toLocaleString()}</span>
                <button onClick={() => viewDetail(r.id)} style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 5, cursor: 'pointer', color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 7px' }}>View</button>
                <button onClick={() => deleteOne(r.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', padding: 2, display: 'flex' }}><IconTrash size={14} stroke={1.5} /></button>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            {summary.counts.pilot > 0 && <button onClick={() => deleteAll('pilot')} style={{ ...btn('transparent', 'var(--ink-soft)'), fontSize: 12 }}>Delete all pilot</button>}
            {summary.counts.actual > 0 && <button onClick={() => deleteAll('actual')} style={{ ...btn('transparent', 'var(--ink-soft)'), fontSize: 12 }}>Delete all actual</button>}
          </div>
        </div>
      )}

      {detail && (
        <div style={box}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14 }}>Response #{detail.id}</span>
            <button onClick={() => setDetail(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 18 }}>×</button>
          </div>
          {detail.answers.map((a, i) => (
            <p key={i} style={{ fontSize: 13, margin: '4px 0', color: 'var(--ink)' }}>
              <span style={{ color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>Q{a.question_id}:</span> {a.answer_value}
            </p>
          ))}
        </div>
      )}
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

function ApaTable({ t }) {
  return (
    <div style={{ marginBottom: 16, overflowX: 'auto' }}>
      <p style={{ fontFamily: 'var(--font-heading)', fontStyle: 'italic', fontWeight: 700, fontSize: 13, margin: '0 0 6px' }}>{t.title}</p>
      <table style={{ borderCollapse: 'collapse', fontSize: 12, fontFamily: 'var(--font-body)', minWidth: 320 }}>
        <thead>
          <tr>{t.columns.map((c, i) => (
            <th key={i} style={{ textAlign: 'left', borderTop: '1.5px solid var(--ink)', borderBottom: '1px solid var(--ink)', padding: '5px 12px', fontWeight: 600 }}>{c}</th>
          ))}</tr>
        </thead>
        <tbody>
          {t.rows.map((r, ri) => (
            <tr key={ri}>{r.map((v, ci) => (
              <td key={ci} style={{ padding: '4px 12px', borderBottom: ri === t.rows.length - 1 ? '1.5px solid var(--ink)' : 'none' }}>{v === null || v === undefined ? '' : String(v)}</td>
            ))}</tr>
          ))}
        </tbody>
      </table>
      {t.note && <p style={{ fontStyle: 'italic', fontSize: 11, color: 'var(--ink-soft)', margin: '5px 0 0' }}>Note. {t.note}</p>}
    </div>
  )
}

const ANALYSIS_KINDS = [
  { key: 'descriptive', label: 'Descriptive', desc: 'Mean, SD, frequencies' },
  { key: 'reliability', label: 'Reliability', desc: "Cronbach's alpha" },
  { key: 'normality', label: 'Normality', desc: 'Skewness, kurtosis, Shapiro-Wilk' },
  { key: 'ttest_independent', label: 'Independent t-test', desc: 'Compare 2 groups (parametric)' },
  { key: 'ttest_paired', label: 'Paired t-test', desc: 'Compare 2 variables, same respondents' },
  { key: 'anova_oneway', label: 'One-way ANOVA', desc: '3+ groups, with Tukey post-hoc' },
  { key: 'mann_whitney', label: 'Mann-Whitney U', desc: '2 groups, non-parametric' },
  { key: 'kruskal_wallis', label: 'Kruskal-Wallis', desc: '3+ groups, non-parametric' },
  { key: 'wilcoxon', label: 'Wilcoxon signed-rank', desc: 'Paired, non-parametric' },
  { key: 'correlation', label: 'Correlation', desc: 'Pearson + Spearman matrix' },
  { key: 'chi_square', label: 'Chi-square', desc: 'Association of 2 categorical questions' },
]

const GROUP_KINDS = ['ttest_independent', 'anova_oneway', 'mann_whitney', 'kruskal_wallis']
const PAIRED_KINDS = ['ttest_paired', 'wilcoxon']

const TEST_LABELS = {
  ttest_independent: 'Independent t-test', ttest_paired: 'Paired t-test',
  anova_oneway: 'One-way ANOVA', mann_whitney: 'Mann-Whitney U',
  kruskal_wallis: 'Kruskal-Wallis', wilcoxon: 'Wilcoxon signed-rank',
  correlation: 'Correlation', chi_square: 'Chi-square',
}

function specFrom(v) {
  return v.startsWith('c:') ? { construct_id: Number(v.slice(2)) } : { question_id: Number(v.slice(2)) }
}

function ApaSentence({ text }) {
  const [copied, setCopied] = useState(false)
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', background: 'var(--accent-soft)', borderLeft: '3px solid var(--accent)', borderRadius: 6, padding: '10px 12px', marginBottom: 12 }}>
      <p style={{ flex: 1, margin: 0, fontSize: 13, fontStyle: 'italic', lineHeight: 1.6 }}>{text}</p>
      <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
        style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 5, cursor: 'pointer', color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 7px', whiteSpace: 'nowrap' }}>
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

function AssumptionChecks({ checks }) {
  if (!checks) return null
  const norm = checks.normality_per_group || (checks.normality_of_differences ? { Differences: checks.normality_of_differences } : null)
  return (
    <details style={{ marginBottom: 12, fontSize: 12 }}>
      <summary style={{ cursor: 'pointer', color: 'var(--ink-soft)', fontWeight: 600 }}>Assumption checks</summary>
      <div style={{ padding: '8px 0 0 14px', color: 'var(--ink)' }}>
        {checks.levene && (
          <p style={{ margin: '0 0 6px' }}>
            Levene&apos;s test (equal variances): W = {checks.levene.statistic}, p = {checks.levene.p}
            {checks.levene.p !== null && checks.levene.p < 0.05 ? ' — variances differ' : ''}
          </p>
        )}
        {norm && Object.entries(norm).map(([g, v]) => (
          <p key={g} style={{ margin: '0 0 4px' }}>
            Normality — {g}: {v.looks_normal === null ? 'too few values to test'
              : `skew ${v.skewness}, kurtosis ${v.kurtosis}, Shapiro-Wilk p ${v.shapiro_p} → ${v.looks_normal ? 'looks normal' : 'may not be normal'}`}
          </p>
        ))}
      </div>
    </details>
  )
}

function InferentialExtras({ result }) {
  return (
    <div>
      {result.apa_sentence && <ApaSentence text={result.apa_sentence} />}
      {result.effect_size && (
        <p style={{ fontSize: 12, margin: '0 0 10px' }}>
          Effect size: <strong>{result.effect_size.name} = {result.effect_size.value}</strong>
          <span style={{ marginLeft: 6, padding: '1px 8px', borderRadius: 10, background: 'var(--accent-soft)', fontSize: 11 }}>{result.effect_size.band}</span>
        </p>
      )}
      {result.warning && <p style={{ fontSize: 12, color: '#B45309', margin: '0 0 10px' }}>⚠ {result.warning}</p>}
      {result.excluded_groups?.length > 0 && (
        <p style={{ fontSize: 12, color: 'var(--ink-soft)', margin: '0 0 10px' }}>
          Excluded groups (fewer than 2 responses): {result.excluded_groups.map(g => `${g.group} (n=${g.n})`).join(', ')}
        </p>
      )}
      <AssumptionChecks checks={result.assumption_checks} />
    </div>
  )
}

const INTERPRET_DISCLAIMERS = [
  'This interpretation was generated automatically. Verify with your supervisor before use.',
  'Interpretasi ini dijana secara automatik. Sahkan dengan penyelia anda sebelum digunakan.',
]

function InterpretationBlock({ detail, setDetail, projectId }) {
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const [lang, setLang] = useState('')
  const [err, setErr] = useState('')
  const [chapters, setChapters] = useState(null) // null = picker closed
  const [chapterId, setChapterId] = useState('')

  const interp = detail.interpretation

  const interpret = async () => {
    if (!window.confirm('Generate an AI interpretation for 3 credits?')) return
    setBusy(true); setErr('')
    try {
      const body = lang ? { language: lang } : {}
      const { data } = await api.post(`/analyses/${detail.id}/interpret`, body)
      setDetail({ ...detail, interpretation: { language: data.language, narrative: data.narrative, generated_at: data.generated_at } })
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Interpretation failed — please try again.')
    } finally { setBusy(false) }
  }

  const openPicker = async () => {
    setErr('')
    try {
      const { data } = await api.get(`/projects/${projectId}/chapters`)
      if (!data.length) { setErr('Create a chapter in the Editor first.'); return }
      const bab4 = data.find(ch => (ch.title || '').includes('4'))
      setChapterId(bab4 ? bab4.id : data[0].id)
      setChapters(data)
    } catch { setErr('Could not load chapters.') }
  }

  const sendToEditor = () => {
    let text = interp ? interp.narrative : ''
    INTERPRET_DISCLAIMERS.forEach(d => { text = text.replace(d, '') })
    text = text.trim()
    const apa = (detail.results || []).map(r => r.apa_sentence).filter(Boolean).join(' ')
    const parts = [text, apa, '(See the accompanying APA table.)'].filter(Boolean)
    sessionStorage.setItem('rhq_pending_suggestion', JSON.stringify({
      chapterId, text: parts.join('\n\n'), stageLabel: 'Survey Analysis',
    }))
    nav(`/project/${projectId}`)
  }

  const btn = (primary) => ({ padding: '7px 14px', background: primary ? 'var(--ink)' : 'transparent', color: primary ? 'var(--bg)' : 'var(--ink)', border: primary ? 'none' : '1px solid var(--line)', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: busy ? 'not-allowed' : 'pointer', opacity: busy ? 0.6 : 1 })

  return (
    <div style={{ borderTop: '1px solid var(--line)', paddingTop: 12, marginTop: 4 }}>
      {err && <p style={{ color: '#EF4444', fontSize: 12, margin: '0 0 8px' }}>{err}</p>}
      {interp ? (
        <div>
          <div style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 8, padding: '12px 14px', marginBottom: 10 }}>
            <p style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.7, margin: 0 }}>{interp.narrative}</p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <button onClick={() => navigator.clipboard.writeText(interp.narrative)} style={btn(false)}>Copy</button>
            <button onClick={interpret} disabled={busy} style={btn(false)}>{busy ? 'Generating…' : 'Regenerate (3 credits)'}</button>
            {chapters === null ? (
              <button onClick={openPicker} style={btn(true)}>→ Send to Editor</button>
            ) : (
              <span style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <select value={chapterId} onChange={e => setChapterId(e.target.value)}
                  style={{ padding: '6px 8px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, background: 'var(--bg)', color: 'var(--ink)' }}>
                  {chapters.map(ch => <option key={ch.id} value={ch.id}>{ch.title}</option>)}
                </select>
                <button onClick={sendToEditor} style={btn(true)}>Send</button>
                <button onClick={() => setChapters(null)} style={btn(false)}>Cancel</button>
              </span>
            )}
          </div>
          <p style={{ fontSize: 11, color: 'var(--ink-soft)', margin: '8px 0 0' }}>
            Export the APA table via .docx and paste it into your thesis document — tables are not sent to the Editor.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={interpret} disabled={busy} style={btn(true)}>
            {busy ? 'Generating…' : 'Interpret (3 credits)'}
          </button>
          <select value={lang} onChange={e => setLang(e.target.value)}
            style={{ padding: '6px 8px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, background: 'var(--bg)', color: 'var(--ink)' }}>
            <option value="">Language: project default</option>
            <option value="ms">Bahasa Melayu</option>
            <option value="en">English</option>
          </select>
          <span style={{ fontSize: 11, color: 'var(--ink-soft)' }}>All numbers come from your computed results — the AI writes the wording only.</span>
        </div>
      )}
    </div>
  )
}

function AnalyseView({ survey, refresh, projectId }) {
  const [constructs, setConstructs] = useState([])
  const [analyses, setAnalyses] = useState([])
  const [counts, setCounts] = useState({ pilot: 0, actual: 0 })
  const [detail, setDetail] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  // new-construct form
  const [showForm, setShowForm] = useState(false)
  const [cName, setCName] = useState('')
  const [cItems, setCItems] = useState([])

  // run form
  const [kind, setKind] = useState('descriptive')
  const [source, setSource] = useState('actual')
  const [selConstructs, setSelConstructs] = useState([])

  // inferential form (36C-2)
  const [outcomeA, setOutcomeA] = useState('')
  const [outcomeB, setOutcomeB] = useState('')
  const [groupingQ, setGroupingQ] = useState('')
  const [corrVars, setCorrVars] = useState([])
  const [chiA, setChiA] = useState('')
  const [chiB, setChiB] = useState('')

  // wizard (36C-2) — deterministic backend decision tree, not AI
  const [wizOpen, setWizOpen] = useState(false)
  const [wizGoal, setWizGoal] = useState('')
  const [wizOutcome, setWizOutcome] = useState('')
  const [wizGrouping, setWizGrouping] = useState('')
  const [wizPaired, setWizPaired] = useState(false)
  const [wizResult, setWizResult] = useState(null)

  const likertQuestions = survey.sections.flatMap(s => s.questions.filter(q => q.question_type === 'likert'))
  const categoricalQuestions = survey.sections.flatMap(s => s.questions.filter(q => ['mcq', 'demographic'].includes(q.question_type)))
  const outcomeOptions = [
    ...constructs.map(c => ({ value: `c:${c.id}`, label: `${c.name} (construct)` })),
    ...likertQuestions.map(q => ({ value: `q:${q.id}`, label: q.question_text.slice(0, 48) })),
  ]

  const load = useCallback(async () => {
    try {
      const [cs, an, summ] = await Promise.all([
        api.get(`/surveys/${survey.id}/constructs`),
        api.get(`/surveys/${survey.id}/analyses`),
        api.get(`/surveys/${survey.id}/responses?type=all`),
      ])
      setConstructs(cs.data)
      setAnalyses(an.data)
      setCounts(summ.data.counts)
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed to load.') }
  }, [survey.id])

  useEffect(() => { load() }, [load])

  const saveConstruct = async () => {
    if (!cName.trim() || cItems.length < 1) { setErr('Name and at least one Likert item required.'); return }
    setBusy(true); setErr('')
    try {
      await api.post(`/surveys/${survey.id}/constructs`, { name: cName, question_ids: cItems })
      setCName(''); setCItems([]); setShowForm(false); await load()
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not create construct.') } finally { setBusy(false) }
  }

  const deleteConstruct = async (id) => {
    if (!window.confirm('Delete this construct?')) return
    await api.delete(`/constructs/${id}`); await load()
  }

  const buildRunBody = () => {
    const body = { analysis_type: kind, data_source: source }
    if (GROUP_KINDS.includes(kind)) {
      if (!outcomeA || !groupingQ) { setErr('Select an outcome and a grouping question.'); return null }
      body.outcome = specFrom(outcomeA)
      body.grouping_question_id = Number(groupingQ)
    } else if (PAIRED_KINDS.includes(kind)) {
      if (!outcomeA || !outcomeB) { setErr('Select two variables to compare.'); return null }
      body.outcome = specFrom(outcomeA)
      body.outcome2 = specFrom(outcomeB)
    } else if (kind === 'correlation') {
      if (corrVars.length < 2) { setErr('Select at least 2 variables for correlation.'); return null }
      body.variables = corrVars.map(specFrom)
    } else if (kind === 'chi_square') {
      if (!chiA || !chiB || chiA === chiB) { setErr('Select two different categorical questions.'); return null }
      body.question_ids = [Number(chiA), Number(chiB)]
    } else {
      if (selConstructs.length) body.construct_ids = selConstructs
      if (kind === 'descriptive' && !selConstructs.length) body.question_ids = likertQuestions.map(q => q.id)
    }
    return body
  }

  const runAnalysis = async (explicitBody = null) => {
    const body = explicitBody || buildRunBody()
    if (!body) return
    setBusy(true); setErr('')
    try {
      const { data } = await api.post(`/surveys/${survey.id}/analyses`, body)
      setDetail(data); await load()
    } catch (e) { setErr(e?.response?.data?.detail || 'Analysis failed.') } finally { setBusy(false) }
  }

  const runWizard = async () => {
    if (!wizGoal || !wizOutcome) { setErr('Choose a goal and a variable first.'); return }
    if (wizGoal !== 'relationship' && !wizPaired && !wizGrouping) { setErr('Choose a grouping question.'); return }
    setBusy(true); setErr(''); setWizResult(null)
    try {
      const body = { goal: wizGoal, outcome: specFrom(wizOutcome), paired: wizPaired, data_source: source }
      if (wizGrouping) body.grouping_question_id = Number(wizGrouping)
      const { data } = await api.post(`/surveys/${survey.id}/wizard`, body)
      setWizResult(data)
    } catch (e) { setErr(e?.response?.data?.detail || 'The wizard could not evaluate your data.') } finally { setBusy(false) }
  }

  const runSuggested = async (test) => {
    const body = { analysis_type: test, data_source: source }
    if (test === 'chi_square') {
      body.question_ids = [Number(wizOutcome.slice(2)), Number(wizGrouping)]
    } else if (test === 'correlation') {
      setKind('correlation'); setCorrVars([wizOutcome]); setWizOpen(false)
      setErr('Pick a second variable for the correlation, then run it.'); return
    } else if (PAIRED_KINDS.includes(test)) {
      setKind(test); setOutcomeA(wizOutcome); setWizOpen(false)
      setErr('Pick the second paired variable, then run the test.'); return
    } else {
      body.outcome = specFrom(wizOutcome)
      body.grouping_question_id = Number(wizGrouping)
    }
    setKind(test)
    await runAnalysis(body)
    setWizOpen(false)
  }

  const openAnalysis = async (id) => {
    const { data } = await api.get(`/analyses/${id}`); setDetail(data)
  }
  const deleteAnalysis = async (id) => {
    if (!window.confirm('Delete this analysis?')) return
    await api.delete(`/analyses/${id}`); setDetail(null); await load()
  }
  const exportDocx = async (id) => {
    const resp = await api.get(`/analyses/${id}/export/docx`, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = `${survey.title || 'analysis'}.docx`; a.click()
    URL.revokeObjectURL(url)
  }

  const box = { border: '1px solid var(--line)', borderRadius: 'var(--radius-md)', background: 'var(--card)', padding: 18, marginBottom: 14 }
  const toggle = (arr, v, set) => set(arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v])
  const selStyle = { width: '100%', maxWidth: 380, padding: '7px 10px', border: '1px solid var(--line)', borderRadius: 7, fontSize: 13, background: 'var(--bg)', color: 'var(--ink)', fontFamily: 'var(--font-body)' }
  const fieldLabel = { fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 6px' }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', maxWidth: 900, width: '100%', margin: '0 auto', boxSizing: 'border-box' }}>
      {err && <p style={{ color: '#EF4444', fontSize: 13 }}>{err}</p>}
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 14px' }}>
        Auto-generated results — review with your supervisor before using in your thesis.
      </p>

      {/* Constructs manager */}
      <div style={box}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14 }}>Constructs</span>
          <button onClick={() => setShowForm(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '6px 12px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 7, fontSize: 12, cursor: 'pointer', color: 'var(--ink)' }}>
            <IconPlus size={13} stroke={1.5} /> Construct
          </button>
        </div>
        {constructs.length === 0 && !showForm && (
          <p style={{ fontSize: 13, color: 'var(--ink-soft)', margin: 0, lineHeight: 1.6 }}>
            A construct groups related Likert items into one variable (e.g. items B1–B5 = "Job Satisfaction"), so you can compute a composite score and reliability. Add one to begin.
          </p>
        )}
        {showForm && (
          <div style={{ borderTop: '1px solid var(--line)', paddingTop: 10, marginTop: 6 }}>
            <input value={cName} onChange={e => setCName(e.target.value)} placeholder="Construct name (e.g. Job Satisfaction)"
              style={{ width: '100%', padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 7, fontSize: 13, boxSizing: 'border-box', marginBottom: 8 }} />
            <p style={{ fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 6px' }}>Select Likert items (same scale):</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
              {likertQuestions.map(q => (
                <button key={q.id} onClick={() => toggle(cItems, q.id, setCItems)}
                  style={{ padding: '5px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                    border: cItems.includes(q.id) ? '1px solid var(--accent)' : '1px solid var(--line)',
                    background: cItems.includes(q.id) ? 'var(--accent-soft)' : 'transparent', color: 'var(--ink)' }}>
                  {q.question_text.slice(0, 28)}{q.is_reversed ? ' ↺' : ''}
                </button>
              ))}
            </div>
            <button onClick={saveConstruct} disabled={busy} style={{ padding: '7px 16px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>Save construct</button>
          </div>
        )}
        {constructs.map(c => (
          <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: '1px solid var(--line)', fontSize: 13 }}>
            <span style={{ flex: 1 }}>{c.name} <span style={{ color: 'var(--ink-soft)', fontSize: 11 }}>· {c.question_ids.length} items</span></span>
            <button onClick={() => deleteConstruct(c.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', padding: 2 }}><IconTrash size={14} stroke={1.5} /></button>
          </div>
        ))}
      </div>

      {/* Analysis Wizard */}
      <div style={box}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14 }}>Not sure which test?</span>
          <button onClick={() => { setWizOpen(v => !v); setWizResult(null) }}
            style={{ padding: '7px 14px', background: wizOpen ? 'transparent' : 'var(--accent)', color: wizOpen ? 'var(--ink)' : '#fff', border: wizOpen ? '1px solid var(--line)' : 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
            {wizOpen ? 'Close wizard' : 'Help me choose'}
          </button>
        </div>
        {wizOpen && (
          <div style={{ borderTop: '1px solid var(--line)', paddingTop: 12, marginTop: 10 }}>
            <p style={{ fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 6px' }}>1. What do you want to find out?</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
              {[['compare_groups', 'Compare groups'], ['relationship', 'Relationship between variables'], ['association_categorical', 'Association of categories']].map(([v, l]) => (
                <button key={v} onClick={() => { setWizGoal(v); setWizResult(null) }}
                  style={{ padding: '6px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer', border: wizGoal === v ? '1px solid var(--accent)' : '1px solid var(--line)', background: wizGoal === v ? 'var(--accent-soft)' : 'transparent', color: 'var(--ink)' }}>{l}</button>
              ))}
            </div>
            {wizGoal && (
              <div style={{ marginBottom: 12 }}>
                <p style={{ fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 6px' }}>
                  2. {wizGoal === 'association_categorical' ? 'First categorical question' : 'Outcome variable'}
                </p>
                <select value={wizOutcome} onChange={e => { setWizOutcome(e.target.value); setWizResult(null) }} style={selStyle}>
                  <option value="">— select —</option>
                  {(wizGoal === 'association_categorical'
                    ? categoricalQuestions.map(q => ({ value: `q:${q.id}`, label: q.question_text.slice(0, 48) }))
                    : outcomeOptions
                  ).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            )}
            {wizGoal === 'compare_groups' && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, marginBottom: 12, cursor: 'pointer' }}>
                <input type="checkbox" checked={wizPaired} onChange={e => { setWizPaired(e.target.checked); setWizResult(null) }} />
                Paired measurements (same respondents, two variables)
              </label>
            )}
            {wizGoal && wizGoal !== 'relationship' && !wizPaired && (
              <div style={{ marginBottom: 12 }}>
                <p style={{ fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 6px' }}>
                  3. {wizGoal === 'association_categorical' ? 'Second categorical question' : 'Grouping question (MCQ / demographic)'}
                </p>
                <select value={wizGrouping} onChange={e => { setWizGrouping(e.target.value); setWizResult(null) }} style={selStyle}>
                  <option value="">— select —</option>
                  {categoricalQuestions.map(q => <option key={q.id} value={q.id}>{q.question_text.slice(0, 48)}</option>)}
                </select>
              </div>
            )}
            <button onClick={runWizard} disabled={busy} style={{ padding: '7px 16px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
              {busy ? 'Checking…' : 'Suggest a test'}
            </button>
            {wizResult && (
              <div style={{ marginTop: 12, padding: '12px 14px', background: 'var(--accent-soft)', borderRadius: 8 }}>
                <p style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 700 }}>
                  Suggested: {TEST_LABELS[wizResult.suggested_test] || wizResult.suggested_test}
                </p>
                <p style={{ margin: '0 0 8px', fontSize: 12, lineHeight: 1.6 }}>{wizResult.justification}</p>
                {wizResult.alternative_test && (
                  <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--ink-soft)' }}>
                    Alternative: {TEST_LABELS[wizResult.alternative_test]}
                  </p>
                )}
                <button onClick={() => runSuggested(wizResult.suggested_test)} disabled={busy}
                  style={{ padding: '7px 14px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                  Run suggested test
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Run analysis */}
      <div style={box}>
        <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14 }}>Run analysis</span>
        <div style={{ display: 'flex', gap: 8, margin: '10px 0', flexWrap: 'wrap' }}>
          {ANALYSIS_KINDS.map(k => (
            <button key={k.key} onClick={() => setKind(k.key)}
              style={{ flex: '1 1 160px', textAlign: 'left', padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
                border: kind === k.key ? '1px solid var(--accent)' : '1px solid var(--line)',
                background: kind === k.key ? 'var(--accent-soft)' : 'transparent' }}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{k.label}</div>
              <div style={{ fontSize: 11, color: 'var(--ink-soft)' }}>{k.desc}</div>
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 16, marginBottom: 10, flexWrap: 'wrap' }}>
          {['actual', 'pilot'].map(src => (
            <label key={src} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: counts[src] ? 'pointer' : 'not-allowed', opacity: counts[src] ? 1 : 0.5 }}>
              <input type="radio" name="src" checked={source === src} disabled={!counts[src]} onChange={() => setSource(src)} />
              {src === 'actual' ? 'Actual' : 'Pilot'} ({counts[src]} responses)
            </label>
          ))}
        </div>
        {['descriptive', 'reliability', 'normality'].includes(kind) && constructs.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <p style={fieldLabel}>
              Constructs {kind === 'reliability' ? '(required)' : kind === 'descriptive' ? '(optional — composite)' : '(optional)'}:
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {constructs.map(c => (
                <button key={c.id} onClick={() => toggle(selConstructs, c.id, setSelConstructs)}
                  style={{ padding: '5px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                    border: selConstructs.includes(c.id) ? '1px solid var(--accent)' : '1px solid var(--line)',
                    background: selConstructs.includes(c.id) ? 'var(--accent-soft)' : 'transparent', color: 'var(--ink)' }}>
                  {c.name}
                </button>
              ))}
            </div>
          </div>
        )}
        {GROUP_KINDS.includes(kind) && (
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 10 }}>
            <div>
              <p style={fieldLabel}>Outcome (construct or Likert item):</p>
              <select value={outcomeA} onChange={e => setOutcomeA(e.target.value)} style={selStyle}>
                <option value="">— select —</option>
                {outcomeOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <p style={fieldLabel}>Grouping question (MCQ / demographic):</p>
              <select value={groupingQ} onChange={e => setGroupingQ(e.target.value)} style={selStyle}>
                <option value="">— select —</option>
                {categoricalQuestions.map(q => <option key={q.id} value={q.id}>{q.question_text.slice(0, 48)}</option>)}
              </select>
            </div>
          </div>
        )}
        {PAIRED_KINDS.includes(kind) && (
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 10 }}>
            <div>
              <p style={fieldLabel}>Variable 1:</p>
              <select value={outcomeA} onChange={e => setOutcomeA(e.target.value)} style={selStyle}>
                <option value="">— select —</option>
                {outcomeOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <p style={fieldLabel}>Variable 2:</p>
              <select value={outcomeB} onChange={e => setOutcomeB(e.target.value)} style={selStyle}>
                <option value="">— select —</option>
                {outcomeOptions.filter(o => o.value !== outcomeA).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>
        )}
        {kind === 'correlation' && (
          <div style={{ marginBottom: 10 }}>
            <p style={fieldLabel}>Variables (select 2 or more):</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {outcomeOptions.map(o => (
                <button key={o.value} onClick={() => toggle(corrVars, o.value, setCorrVars)}
                  style={{ padding: '5px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                    border: corrVars.includes(o.value) ? '1px solid var(--accent)' : '1px solid var(--line)',
                    background: corrVars.includes(o.value) ? 'var(--accent-soft)' : 'transparent', color: 'var(--ink)' }}>
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        )}
        {kind === 'chi_square' && (
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 10 }}>
            <div>
              <p style={fieldLabel}>First categorical question:</p>
              <select value={chiA} onChange={e => setChiA(e.target.value)} style={selStyle}>
                <option value="">— select —</option>
                {categoricalQuestions.map(q => <option key={q.id} value={q.id}>{q.question_text.slice(0, 48)}</option>)}
              </select>
            </div>
            <div>
              <p style={fieldLabel}>Second categorical question:</p>
              <select value={chiB} onChange={e => setChiB(e.target.value)} style={selStyle}>
                <option value="">— select —</option>
                {categoricalQuestions.filter(q => String(q.id) !== chiA).map(q => <option key={q.id} value={q.id}>{q.question_text.slice(0, 48)}</option>)}
              </select>
            </div>
          </div>
        )}
        <button onClick={() => runAnalysis()} disabled={busy} style={{ padding: '9px 18px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: busy ? 'not-allowed' : 'pointer', opacity: busy ? 0.6 : 1 }}>
          {busy ? 'Running…' : 'Run analysis'}
        </button>
      </div>

      {/* Saved analyses */}
      {analyses.length > 0 && (
        <div style={box}>
          <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14 }}>Saved analyses</span>
          {analyses.map(a => (
            <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: '1px solid var(--line)', fontSize: 13 }}>
              <span style={{ flex: 1, textTransform: 'capitalize' }}>{a.analysis_type} <span style={{ color: 'var(--ink-soft)', fontSize: 11 }}>· {a.data_source} · {new Date(a.created_at).toLocaleString()}</span></span>
              <button onClick={() => openAnalysis(a.id)} style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 5, cursor: 'pointer', color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 7px' }}>View</button>
              <button onClick={() => exportDocx(a.id)} style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 5, cursor: 'pointer', color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 7px' }}>.docx</button>
              <button onClick={() => deleteAnalysis(a.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', padding: 2 }}><IconTrash size={14} stroke={1.5} /></button>
            </div>
          ))}
        </div>
      )}

      {/* Result render */}
      {detail && (
        <div style={box}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, textTransform: 'capitalize' }}>{detail.analysis_type} — {detail.data_source}</span>
            <button onClick={() => setDetail(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 18 }}>×</button>
          </div>
          {(detail.results || []).filter(r => r.apa_sentence || r.effect_size || r.assumption_checks).map((r, i) => (
            <InferentialExtras key={i} result={r} />
          ))}
          {(detail.apa_tables || []).map((t, i) => <ApaTable key={i} t={t} />)}
          <InterpretationBlock detail={detail} setDetail={setDetail} projectId={projectId} />
        </div>
      )}
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
  const [view, setView] = useState('build') // 'build' | 'collect'
  const [locked, setLocked] = useState(false) // Free tier

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
      if (err?.response?.status === 403) { setLocked(true) }
      else { setError(err?.response?.data?.detail || 'Failed to load survey.') }
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
      a.download = `${survey.title || 'survey'}.docx`
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
    const title = window.prompt('Section title:', `Section ${String.fromCharCode(65 + survey.sections.length)}`)
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

  if (locked) return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)', gap: 14, padding: 24, textAlign: 'center' }}>
      <div style={{ fontSize: 40 }}>🔒</div>
      <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, fontSize: 20, margin: 0 }}>Survey Builder is a Pro feature</h2>
      <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: 0, maxWidth: 420, lineHeight: 1.6 }}>
        Generate survey instruments from your project documents, collect responses via a public link, and export data — available on the Pro plan.
      </p>
      <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
        <button onClick={() => nav('/account')} style={{ padding: '10px 22px', background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 8, fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, cursor: 'pointer' }}>
          Upgrade to Pro — RM39/month
        </button>
        <button onClick={() => nav(`/project/${projectId}`)} style={{ padding: '10px 22px', background: 'transparent', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 14, cursor: 'pointer' }}>
          Back to workspace
        </button>
      </div>
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

  const collecting = survey.status === 'pilot' || survey.status === 'published'

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
        <Stepper view={view} onSelect={setView} />
      </header>

      {view === 'analyse' ? (
        <AnalyseView survey={survey} refresh={refresh} projectId={projectId} />
      ) : view === 'collect' ? (
        <CollectView survey={survey} setSurvey={setSurvey} refresh={refresh} />
      ) : (
      <>
      {collecting && (
        <div style={{ padding: '10px 20px', background: 'var(--accent-soft)', borderBottom: '1px solid var(--line)', fontSize: 12, color: 'var(--ink)', flexShrink: 0 }}>
          Structure locked while collecting responses. Go to <b>Collect</b> to close the survey before editing.
        </div>
      )}
      {/* Toolbar */}
      <div style={{
        display: 'flex', gap: 8, padding: '12px 20px', flexWrap: 'wrap',
        borderBottom: '1px solid var(--line)', background: 'var(--card)', flexShrink: 0,
      }}>
        <button
          onClick={handleGenerate}
          disabled={generating || collecting}
          title={collecting ? 'Structure locked while collecting responses' : undefined}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px',
            background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 8,
            fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 600,
            cursor: (generating || collecting) ? 'not-allowed' : 'pointer', opacity: (generating || collecting) ? 0.5 : 1,
          }}
        >
          <IconSparkles size={15} stroke={1.5} />
          {generating ? 'Generating draft...' : `Generate with AI — ${GENERATE_COST} credits`}
        </button>
        <button
          onClick={addSection}
          disabled={collecting}
          title={collecting ? 'Structure locked while collecting responses' : undefined}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 13, cursor: collecting ? 'not-allowed' : 'pointer', color: 'var(--ink)', opacity: collecting ? 0.5 : 1 }}
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
      </>
      )}
    </div>
  )
}
