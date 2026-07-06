import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import axios from 'axios'
import { TurnstileWidget } from './TurnstileWidget'
import { Logo } from './Logo'

// Standalone, no-auth. Use a bare axios instance (no auth interceptor) so the
// respondent stays fully anonymous — never attach an owner token if one exists.
const publicApi = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 30000,
})

const wrap = { minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '24px 16px' }
const card = { width: '100%', maxWidth: 560, background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 'var(--radius-md)', padding: 20, marginBottom: 14 }

export function PublicSurveyForm() {
  const { token } = useParams()
  const [survey, setSurvey] = useState(null)
  const [state, setState] = useState('loading') // loading | ready | closed | notfound | error | done
  const [answers, setAnswers] = useState({})
  const [turnstileToken, setTurnstileToken] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    publicApi.get(`/public/surveys/${token}`)
      .then(r => { setSurvey(r.data); setState('ready') })
      .catch(err => {
        const s = err.response?.status
        if (s === 410) setState('closed')
        else if (s === 404) setState('notfound')
        else setState('error')
      })
  }, [token])

  const setAnswer = (qid, value) => setAnswers(a => ({ ...a, [qid]: value }))

  const allQuestions = survey?.sections.flatMap(s => s.questions) || []
  const allAnswered = allQuestions.every(q => {
    const v = answers[q.id]
    return v !== undefined && String(v).trim() !== ''
  })

  async function handleSubmit() {
    if (!turnstileToken) { setErrorMsg('Please complete the verification.'); return }
    if (!allAnswered) { setErrorMsg('Please answer all questions.'); return }
    setSubmitting(true)
    setErrorMsg('')
    try {
      await publicApi.post(`/public/surveys/${token}/responses`, {
        answers: allQuestions.map(q => ({ question_id: q.id, answer_value: String(answers[q.id]) })),
        turnstile_token: turnstileToken,
      })
      setState('done')
    } catch (err) {
      const s = err.response?.status
      if (s === 409) setErrorMsg('This survey has reached its response limit.')
      else if (s === 410) setErrorMsg('This survey is no longer accepting responses.')
      else if (s === 429) setErrorMsg('You have already submitted, or too many attempts. Please wait a moment.')
      else if (s === 403) setErrorMsg('Verification failed. Please refresh and try again.')
      else setErrorMsg('Something went wrong. Please try again.')
      setSubmitting(false)
    }
  }

  const Shell = ({ children }) => (
    <div style={wrap}>
      <div style={{ marginBottom: 16, marginTop: 8 }}><Logo size="sm" /></div>
      {children}
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', marginTop: 20 }}>
        Powered by researcherHQ
      </p>
    </div>
  )

  if (state === 'loading') return <Shell><p style={{ color: 'var(--ink-soft)' }}>Loading…</p></Shell>
  if (state === 'notfound') return <Shell><div style={card}><h2 style={{ fontFamily: 'var(--font-heading)', margin: 0, fontSize: 18 }}>Survey not found</h2><p style={{ color: 'var(--ink-soft)', fontSize: 14 }}>This link is invalid or has been removed.</p></div></Shell>
  if (state === 'closed') return <Shell><div style={card}><h2 style={{ fontFamily: 'var(--font-heading)', margin: 0, fontSize: 18 }}>Survey closed</h2><p style={{ color: 'var(--ink-soft)', fontSize: 14 }}>This survey is not accepting responses right now.</p></div></Shell>
  if (state === 'error') return <Shell><div style={card}><h2 style={{ fontFamily: 'var(--font-heading)', margin: 0, fontSize: 18 }}>Something went wrong</h2><p style={{ color: 'var(--ink-soft)', fontSize: 14 }}>Please refresh the page and try again.</p></div></Shell>
  if (state === 'done') return (
    <Shell>
      <div style={{ ...card, textAlign: 'center', padding: '40px 24px' }}>
        <div style={{ fontSize: 40, marginBottom: 8 }}>✓</div>
        <h2 style={{ fontFamily: 'var(--font-heading)', margin: '0 0 6px', fontSize: 20 }}>Thank you</h2>
        <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: 0 }}>Your response has been recorded.</p>
      </div>
    </Shell>
  )

  let qNum = 0
  return (
    <Shell>
      <div style={{ ...card, marginBottom: 18 }}>
        <h1 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, fontSize: 22, margin: 0 }}>{survey.title}</h1>
      </div>

      {survey.sections.map((sec, si) => (
        <div key={si} style={card}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16, margin: '0 0 14px' }}>{sec.title}</h2>
          {sec.questions.map(q => {
            qNum += 1
            const options = q.options || []
            return (
              <div key={q.id} style={{ marginBottom: 20 }}>
                <p style={{ fontFamily: 'var(--font-body)', fontSize: 15, margin: '0 0 10px', color: 'var(--ink)' }}>
                  {qNum}. {q.question_text}
                </p>

                {q.question_type === 'likert' && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {Array.from({ length: q.likert_points || options.length || 5 }, (_, i) => i + 1).map(pt => (
                      <label key={pt} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, cursor: 'pointer', minWidth: 52 }}>
                        <input type="radio" name={`q${q.id}`} checked={String(answers[q.id]) === String(pt)} onChange={() => setAnswer(q.id, pt)} />
                        <span style={{ fontSize: 12, color: 'var(--ink-soft)', textAlign: 'center' }}>{options[pt - 1] || pt}</span>
                      </label>
                    ))}
                  </div>
                )}

                {(q.question_type === 'mcq' || q.question_type === 'demographic') && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {options.map(opt => (
                      <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 15, padding: '4px 0' }}>
                        <input type="radio" name={`q${q.id}`} checked={answers[q.id] === opt} onChange={() => setAnswer(q.id, opt)} />
                        {opt}
                      </label>
                    ))}
                  </div>
                )}

                {q.question_type === 'open' && (
                  <textarea
                    value={answers[q.id] || ''}
                    onChange={e => setAnswer(q.id, e.target.value)}
                    maxLength={2000}
                    rows={3}
                    style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, boxSizing: 'border-box', resize: 'vertical' }}
                  />
                )}
              </div>
            )
          })}
        </div>
      ))}

      <div style={{ ...card }}>
        <TurnstileWidget onVerify={setTurnstileToken} onExpire={() => setTurnstileToken('')} />
        {errorMsg && <p style={{ color: '#EF4444', fontSize: 14, margin: '4px 0 12px' }}>{errorMsg}</p>}
        <button
          onClick={handleSubmit}
          disabled={submitting}
          style={{
            width: '100%', padding: '14px', background: 'var(--ink)', color: 'var(--bg)',
            border: 'none', borderRadius: 10, fontFamily: 'var(--font-heading)', fontWeight: 700,
            fontSize: 16, cursor: submitting ? 'not-allowed' : 'pointer', opacity: submitting ? 0.6 : 1,
          }}
        >
          {submitting ? 'Submitting…' : 'Submit'}
        </button>
      </div>
    </Shell>
  )
}
