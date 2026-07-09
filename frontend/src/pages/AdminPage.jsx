import { useState, useEffect } from 'react'
import { adminApi } from '../api/adminClient'

const TABS = ['Users', 'Support', 'Billing', 'Projects', 'Action Log']

const th = { padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid var(--line)', fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 12, color: 'var(--ink-soft)', whiteSpace: 'nowrap' }
const td = { padding: '8px 12px', borderBottom: '1px solid var(--line)', fontSize: 13, verticalAlign: 'middle' }
const btn = (extra = {}) => ({ padding: '5px 12px', border: 'none', borderRadius: 6, fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 12, cursor: 'pointer', ...extra })
const inputStyle = { padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 14, width: '100%', background: 'var(--bg)', color: 'var(--ink)' }

function Badge({ value }) {
  const on = value === 'pro' || value === 'open' || value === true || value === 1
  return (
    <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700, fontFamily: 'var(--font-mono)', background: on ? '#FEF3C7' : '#F3F4F6', color: on ? '#92400E' : '#6B7280' }}>
      {String(value)}
    </span>
  )
}

// ---------- STATS BAR ----------
function StatsBar() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    adminApi.getStats()
      .then(r => setStats(r.data))
      .catch(() => { /* fail silently */ })
  }, [])

  if (!stats) return null

  const cardStyle = {
    flex: 1, minWidth: 140, background: 'var(--card)', border: '1px solid var(--line)',
    borderRadius: 8, padding: '14px 18px',
  }
  const labelStyle = { fontSize: 11, fontFamily: 'var(--font-heading)', fontWeight: 700, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }
  const valueStyle = { fontSize: 22, fontFamily: 'var(--font-heading)', fontWeight: 800, color: 'var(--ink)' }

  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
      <div style={cardStyle}>
        <div style={labelStyle}>Total Users</div>
        <div style={valueStyle}>{stats.total_users}</div>
      </div>
      <div style={cardStyle}>
        <div style={labelStyle}>Free</div>
        <div style={valueStyle}>{stats.free_users}</div>
      </div>
      <div style={cardStyle}>
        <div style={labelStyle}>Pro</div>
        <div style={valueStyle}>{stats.pro_users}</div>
      </div>
      <div style={cardStyle}>
        <div style={labelStyle}>Revenue (Bulan Ini)</div>
        <div style={valueStyle}>RM {stats.revenue_this_month.toFixed(2)}</div>
      </div>
      <div style={cardStyle}>
        <div style={labelStyle}>Pro Expiring ≤7 hari</div>
        <div style={{ ...valueStyle, color: stats.pro_expiring_7d > 0 ? '#D97706' : 'var(--ink)' }}>{stats.pro_expiring_7d}</div>
      </div>
    </div>
  )
}

// ---------- USERS TAB ----------
function UsersTab() {
  const [users, setUsers] = useState([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({})
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  async function load(q = search) {
    try {
      const { data } = await adminApi.listUsers({ search: q || undefined, page_size: 100 })
      setUsers(data.users)
      setTotal(data.total)
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal memuatkan users.')
    }
  }

  useEffect(() => { load() }, [])

  async function handleExport(tier) {
    try {
      const { data } = await adminApi.exportUsersCsv(tier)
      const url = URL.createObjectURL(new Blob([data], { type: 'text/csv' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `rhq_users_${tier}_${new Date().toISOString().slice(0, 10)}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 100)
    } catch (e) {
      console.error('Export error:', e?.response?.status, e?.response?.data, e?.message)
      setError(`Export gagal: ${e?.response?.status || e?.message || 'unknown'}`)
    }
  }

  function startEdit(u) {
    setEditing(u.id)
    setForm({ tier: u.tier, kredit_remaining: u.kredit_remaining, is_suspended: !!u.is_suspended })
    setError(''); setMsg('')
  }

  async function saveEdit(uid) {
    setError(''); setMsg('')
    try {
      await adminApi.updateUser(uid, form)
      setMsg('Berjaya dikemaskini.')
      setEditing(null)
      load()
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal kemaskini.')
    }
  }

  async function grantPro(uid, email) {
    if (!window.confirm(`Naik taraf ${email} ke PRO tanpa bayaran (500 kredit)?`)) return
    setError(''); setMsg('')
    try {
      await adminApi.grantPro(uid)
      setMsg(`${email} kini PRO (500 kredit).`)
      load()
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal naik taraf.')
    }
  }

  async function deleteUser(uid, email) {
    if (!window.confirm(`Padam akaun ${email}? Tindakan tak boleh undo.`)) return
    setError(''); setMsg('')
    try {
      await adminApi.deleteUser(uid)
      setMsg('User dipadam.')
      load()
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal padam.')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <button onClick={() => handleExport('free')} style={btn({ background: '#EFF6FF', color: '#1D4ED8', border: '1px solid #BFDBFE' })}>Export Free CSV</button>
        <button onClick={() => handleExport('pro')} style={btn({ background: '#F0FDF4', color: '#15803D', border: '1px solid #BBF7D0' })}>Export Pro CSV</button>
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari emel..." style={{ ...inputStyle, width: 280 }} />
        <button onClick={() => load(search)} style={btn({ background: 'var(--ink)', color: 'var(--bg)' })}>Cari</button>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--ink-soft)', alignSelf: 'center' }}>{total} user</span>
      </div>
      {error && <p style={{ color: '#EF4444', fontSize: 13, marginBottom: 8 }}>{error}</p>}
      {msg && <p style={{ color: '#16A34A', fontSize: 13, marginBottom: 8 }}>{msg}</p>}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {['Email', 'Tier', 'Kredit', 'Suspended', 'Daftar', 'Aksi'].map(h => <th key={h} style={th}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td style={td}>{u.email}</td>
                <td style={td}><Badge value={u.tier} /></td>
                <td style={td}>{u.kredit_remaining}/{u.kredit_total}</td>
                <td style={td}><Badge value={!!u.is_suspended} /></td>
                <td style={td} title={u.created_at}>{u.created_at?.slice(0, 10)}</td>
                <td style={td}>
                  {editing === u.id ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 220 }}>
                      <select value={form.tier} onChange={e => setForm(f => ({ ...f, tier: e.target.value }))} style={{ ...inputStyle, width: '100%' }}>
                        <option value="free">free</option>
                        <option value="pro">pro</option>
                      </select>
                      <input type="number" value={form.kredit_remaining} min={0} onChange={e => setForm(f => ({ ...f, kredit_remaining: parseInt(e.target.value) || 0 }))} style={inputStyle} placeholder="Kredit" />
                      <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <input type="checkbox" checked={form.is_suspended} onChange={e => setForm(f => ({ ...f, is_suspended: e.target.checked }))} />
                        Suspend akaun
                      </label>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button onClick={() => saveEdit(u.id)} style={btn({ background: 'var(--ink)', color: 'var(--bg)' })}>Simpan</button>
                        <button onClick={() => setEditing(null)} style={btn({ background: 'transparent', border: '1px solid var(--line)' })}>Batal</button>
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => startEdit(u)} style={btn({ background: '#EFF6FF', color: '#1D4ED8' })}>Edit</button>
                      {u.tier !== 'pro' && (
                        <button onClick={() => grantPro(u.id, u.email)} style={btn({ background: '#F0FDF4', color: '#15803D' })}>Naik Pro</button>
                      )}
                      <button onClick={() => deleteUser(u.id, u.email)} style={btn({ background: '#FEF2F2', color: '#DC2626' })}>Padam</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------- SUPPORT TAB ----------
function SupportTab() {
  const [reports, setReports] = useState([])
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  async function load(f = filter) {
    try {
      const { data } = await adminApi.listSupportReports(f ? { status: f } : undefined)
      setReports(data.reports)
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal memuatkan laporan.')
    }
  }

  useEffect(() => { load() }, [])

  async function changeStatus(id, status) {
    setError(''); setMsg('')
    try {
      await adminApi.updateSupportReport(id, { status })
      setMsg(`Laporan dikemaskini ke '${status}'.`)
      load()
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal kemaskini.')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <select value={filter} onChange={e => { setFilter(e.target.value); load(e.target.value) }} style={{ ...inputStyle, width: 160 }}>
          <option value="">Semua</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
        </select>
        <span style={{ fontSize: 13, color: 'var(--ink-soft)' }}>{reports.length} laporan</span>
      </div>
      {error && <p style={{ color: '#EF4444', fontSize: 13, marginBottom: 8 }}>{error}</p>}
      {msg && <p style={{ color: '#16A34A', fontSize: 13, marginBottom: 8 }}>{msg}</p>}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Kategori', 'Penerangan', 'Status', 'Tarikh', 'Aksi'].map(h => <th key={h} style={th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {reports.map(r => (
              <tr key={r.id}>
                <td style={td}>{r.category}</td>
                <td style={{ ...td, maxWidth: 300 }}><span title={r.description}>{r.description?.slice(0, 80)}{r.description?.length > 80 ? '…' : ''}</span></td>
                <td style={td}><Badge value={r.status} /></td>
                <td style={td}>{r.created_at?.slice(0, 10)}</td>
                <td style={td}>
                  {r.status === 'open'
                    ? <button onClick={() => changeStatus(r.id, 'resolved')} style={btn({ background: '#F0FDF4', color: '#15803D' })}>Resolve</button>
                    : <button onClick={() => changeStatus(r.id, 'open')} style={btn({ background: '#FEF3C7', color: '#92400E' })}>Reopen</button>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------- BILLING TAB ----------
function BillingTab() {
  const [events, setEvents] = useState([])
  const [filterEmail, setFilterEmail] = useState('')
  const [adj, setAdj] = useState({ user_id: '', kredit_delta: '', reason: '' })
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  async function load(q = filterEmail) {
    try {
      const { data } = await adminApi.listBillingEvents(q ? { email: q } : undefined)
      setEvents(data.events)
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal memuatkan events.')
    }
  }

  useEffect(() => { load() }, [])

  async function submitAdjustment(e) {
    e.preventDefault()
    setError(''); setMsg('')
    if (!adj.reason.trim()) { setError('Reason wajib diisi.'); return }
    const delta = parseInt(adj.kredit_delta)
    if (isNaN(delta) || delta === 0) { setError('kredit_delta mestilah nombor bukan sifar.'); return }
    try {
      const { data } = await adminApi.manualAdjustment({ user_id: adj.user_id, kredit_delta: delta, reason: adj.reason })
      setMsg(`Berjaya. Baki baru: ${data.new_balance} kredit.`)
      setAdj({ user_id: '', kredit_delta: '', reason: '' })
      load()
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal adjustment.')
    }
  }

  return (
    <div>
      <div style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 8, padding: 20, marginBottom: 20 }}>
        <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 16px', fontSize: 15 }}>Manual Credit Adjustment</h3>
        <form onSubmit={submitAdjustment} style={{ display: 'grid', gap: 10, maxWidth: 400 }}>
          <input value={adj.user_id} onChange={e => setAdj(a => ({ ...a, user_id: e.target.value }))} placeholder="User ID" required style={inputStyle} />
          <input type="number" value={adj.kredit_delta} onChange={e => setAdj(a => ({ ...a, kredit_delta: e.target.value }))} placeholder="Delta kredit (cth: 50 atau -10)" required style={inputStyle} />
          <textarea value={adj.reason} onChange={e => setAdj(a => ({ ...a, reason: e.target.value }))} placeholder="Sebab adjustment (wajib)" required rows={3} style={{ ...inputStyle, resize: 'vertical' }} />
          {error && <p style={{ color: '#EF4444', fontSize: 13, margin: 0 }}>{error}</p>}
          {msg && <p style={{ color: '#16A34A', fontSize: 13, margin: 0 }}>{msg}</p>}
          <button type="submit" style={btn({ background: 'var(--ink)', color: 'var(--bg)', padding: '9px 16px' })}>Hantar Adjustment</button>
        </form>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
        <input value={filterEmail} onChange={e => setFilterEmail(e.target.value)} placeholder="Filter by email..." style={{ ...inputStyle, width: 300 }} />
        <button onClick={() => load()} style={btn({ background: 'var(--ink)', color: 'var(--bg)' })}>Filter</button>
        {filterEmail && <button onClick={() => { setFilterEmail(''); load('') }} style={btn({ background: 'transparent', border: '1px solid var(--line)' })}>Clear</button>}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Email', 'Jenis', 'Amaun (RM)', 'Kredit', 'Rujukan', 'Tarikh'].map(h => <th key={h} style={th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {events.map(ev => (
              <tr key={ev.id}>
                <td style={td} title={ev.user_id}>{ev.user_email || <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{ev.user_id?.slice(0, 12)}…</span>}</td>
                <td style={td}><Badge value={ev.event_type} /></td>
                <td style={td}>{ev.amount}</td>
                <td style={td}>{ev.kredit_added}</td>
                <td style={{ ...td, fontFamily: 'var(--font-mono)', fontSize: 11 }}>{ev.reference_no}</td>
                <td style={td}>{ev.created_at?.slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------- PROJECTS TAB ----------
function ProjectsTab() {
  const [projects, setProjects] = useState([])
  const [filterUserId, setFilterUserId] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  async function load() {
    try {
      const { data } = await adminApi.listProjects(filterUserId ? { user_id: filterUserId } : undefined)
      setProjects(data.projects)
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal memuatkan projek.')
    }
  }

  useEffect(() => { load() }, [])

  async function deleteProject(id, title) {
    if (!window.confirm(`Padam projek "${title}"? Tindakan tak boleh undo.`)) return
    setError(''); setMsg('')
    try {
      await adminApi.deleteProject(id)
      setMsg('Projek dipadam.')
      load()
    } catch (e) {
      setError(e.response?.data?.detail || 'Gagal padam.')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
        <input value={filterUserId} onChange={e => setFilterUserId(e.target.value)} placeholder="Filter by User ID..." style={{ ...inputStyle, width: 300 }} />
        <button onClick={load} style={btn({ background: 'var(--ink)', color: 'var(--bg)' })}>Filter</button>
        {filterUserId && <button onClick={() => { setFilterUserId(''); }} style={btn({ background: 'transparent', border: '1px solid var(--line)' })}>Clear</button>}
      </div>
      {error && <p style={{ color: '#EF4444', fontSize: 13, marginBottom: 8 }}>{error}</p>}
      {msg && <p style={{ color: '#16A34A', fontSize: 13, marginBottom: 8 }}>{msg}</p>}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Tajuk', 'User ID', 'Mod', 'Tarikh', 'Aksi'].map(h => <th key={h} style={th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {projects.map(p => (
              <tr key={p.id}>
                <td style={td}>{p.title}</td>
                <td style={{ ...td, fontFamily: 'var(--font-mono)', fontSize: 11 }}>{p.user_id?.slice(0, 12)}…</td>
                <td style={td}>{p.research_mode}</td>
                <td style={td}>{p.created_at?.slice(0, 10)}</td>
                <td style={td}>
                  <button onClick={() => deleteProject(p.id, p.title)} style={btn({ background: '#FEF2F2', color: '#DC2626' })}>Padam</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------- ACTION LOG TAB ----------
function ActionLogTab() {
  const [log, setLog] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    adminApi.getActionLog()
      .then(r => setLog(r.data.log))
      .catch(e => setError(e.response?.data?.detail || 'Gagal memuatkan log.'))
  }, [])

  return (
    <div>
      {error && <p style={{ color: '#EF4444', fontSize: 13, marginBottom: 8 }}>{error}</p>}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>{['Admin', 'Aksi', 'Jenis', 'Target ID', 'Details', 'Tarikh'].map(h => <th key={h} style={th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {log.map(entry => (
              <tr key={entry.id}>
                <td style={td}>{entry.admin_email}</td>
                <td style={td}><Badge value={entry.action} /></td>
                <td style={td}>{entry.target_type}</td>
                <td style={{ ...td, fontFamily: 'var(--font-mono)', fontSize: 11 }}>{entry.target_id?.slice(0, 12)}…</td>
                <td style={{ ...td, maxWidth: 280 }}>
                  <pre style={{ margin: 0, fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'var(--font-mono)' }}>
                    {entry.details ? JSON.stringify(JSON.parse(entry.details), null, 2) : '—'}
                  </pre>
                </td>
                <td style={td}>{entry.created_at?.slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------- MAIN PAGE ----------
const TAB_COMPONENTS = {
  'Users': UsersTab,
  'Support': SupportTab,
  'Billing': BillingTab,
  'Projects': ProjectsTab,
  'Action Log': ActionLogTab,
}

export function AdminPage() {
  const [activeTab, setActiveTab] = useState('Users')
  const [apiError, setApiError] = useState('')
  const TabComponent = TAB_COMPONENTS[activeTab]

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <header style={{
        borderBottom: '1px solid var(--line)', padding: '0 24px',
        height: 60, display: 'flex', alignItems: 'center', gap: 16,
        background: 'var(--card)',
      }}>
        <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, fontSize: 18 }}>Admin Panel</span>
        <a href="/" style={{ fontSize: 13, color: 'var(--ink-soft)', textDecoration: 'none', marginLeft: 'auto' }}>← Dashboard</a>
      </header>

      <div style={{ borderBottom: '1px solid var(--line)', background: 'var(--card)', paddingLeft: 24, display: 'flex', gap: 0 }}>
        {TABS.map(tab => (
          <button key={tab} onClick={() => { setActiveTab(tab); setApiError('') }}
            style={{
              padding: '14px 20px', border: 'none', background: 'transparent',
              fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 13,
              cursor: 'pointer', color: activeTab === tab ? 'var(--ink)' : 'var(--ink-soft)',
              borderBottom: activeTab === tab ? '2px solid var(--ink)' : '2px solid transparent',
            }}>
            {tab}
          </button>
        ))}
      </div>

      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px' }}>
        <StatsBar />
        {apiError && (
          <div style={{ background: '#FEF2F2', border: '1px solid #FCA5A5', borderRadius: 8, padding: '12px 16px', marginBottom: 20, color: '#DC2626', fontSize: 14 }}>
            {apiError}
          </div>
        )}
        <TabComponent />
      </main>
    </div>
  )
}
