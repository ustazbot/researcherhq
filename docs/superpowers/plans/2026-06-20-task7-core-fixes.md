# Task 7 — Core Functionality Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire upload PDF→RAG, build Account Settings + Support pages, add password tetap login, fix terminology, and add mobile responsive layout — all before Task 6B landing page.

**Architecture:** Pure frontend work for Items 1/2/5/9; new pages + routes for Items 3/4; hybrid backend+frontend for Item 6 (password tetap — adds DB column, new auth endpoint, extends account endpoint, redesigns AuthPage).

**Tech Stack:** React 19, Vite 8, React Router 7, pdfjs-dist (new), FastAPI, SQLite, axios

## Global Constraints

- Bahasa Malaysia untuk semua teks UI (bukan Bahasa Indonesia)
- "Kredit Kajian" adalah locked term — JANGAN rename
- Anti-gharar disclosure di delete account mesti verbatim: "Dokumen dan perbualan anda akan dipadam sepenuhnya. Rekod transaksi pembayaran dikekalkan tanpa nama untuk tujuan audit kewangan."
- Minimum password panjang 8 aksara (client + server)
- Vite base path adalah `/app/` — semua routes start dari situ
- Backend tests 90/90 mesti kekal pass — jangan break existing endpoints

## Pre-task Flags (Baca Dulu)

**FLAG A — Billing cancel endpoint:** `billing.py` tiada endpoint cancel subscription. Per brief, JANGAN bina baru. Account Settings page untuk Pro user akan show: "Untuk batalkan langganan, hubungi support@researcherhq.com"

**FLAG B — `is_ocr` dalam upload response:** `documents.py` return dict tiada field `is_ocr` (out of scope untuk ubah). Free user yang upload scanned PDF akan dapat 403 error dari backend dengan mesej "Naik taraf ke Pro untuk proses PDF imbasan" — ini akan ditangkap oleh error handler dalam `handleFileUpload`. Pro user yang upload scanned PDF akan berjaya tapi tiada OCR alert (acceptable — embedding masih jalan). Brief's `data.is_ocr` check ditinggalkan.

**FLAG C — `password_is_permanent` reset:** Bila user request-password semula, `password_is_permanent` patut reset ke 0. Plan ini menyertakan perubahan pada `request_password` endpoint di Task 5. Perubahan ini additive dan tidak break existing flow.

---

## File Map

**Create:**
- `frontend/src/utils/pdfExtract.js` — browser-side PDF text extraction (pdfjs-dist)
- `frontend/src/hooks/useMediaQuery.js` — reactive window.matchMedia hook
- `frontend/src/pages/AccountSettingsPage.jsx` — Tetapan Akaun (info, tukar password, delete)
- `frontend/src/pages/SupportPage.jsx` — Laporkan Isu form

**Modify:**
- `frontend/package.json` — add pdfjs-dist dependency
- `frontend/src/pages/ProjectPage.jsx` — real handleFileUpload + mobile tab switcher
- `frontend/src/pages/AuthPage.jsx` — Opsyen B login mode (email+password default)
- `frontend/src/components/ProfileMenu.jsx` — Tetapan Akaun nav + terminology fix
- `frontend/src/App.jsx` — add /account + /support routes
- `backend/app/database.py` — migration: add password_is_permanent column
- `backend/app/routers/auth.py` — add POST /auth/set-password endpoint + reset flag in request-password
- `backend/app/routers/account.py` — include password_is_permanent in GET /account response

---

## Task 1: Install pdfjs-dist + PDF Extraction Utility

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/utils/pdfExtract.js`

**Interfaces:**
- Produces: `extractPdfPages(file: File) → Promise<Array<{ page_number: number, text: string }>>`

- [ ] **Step 1: Install pdfjs-dist**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm install pdfjs-dist
```

Expected output: `added X packages` — no errors.

- [ ] **Step 2: Create pdfExtract.js**

Create `frontend/src/utils/pdfExtract.js`:

```js
import * as pdfjsLib from 'pdfjs-dist'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url
).toString()

export async function extractPdfPages(file) {
  const arrayBuffer = await file.arrayBuffer()
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise
  const pages = []
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i)
    const content = await page.getTextContent()
    const text = content.items.map(item => item.str).join(' ')
    pages.push({ page_number: i, text })
  }
  return pages
}
```

- [ ] **Step 3: Verify build compiles**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm run build 2>&1 | tail -20
```

Expected: build success, no `pdfjs-dist` worker errors. If you see a worker loading error, check that `node_modules/pdfjs-dist/build/pdf.worker.mjs` exists:
```bash
ls node_modules/pdfjs-dist/build/pdf.worker.mjs
```

- [ ] **Step 4: Commit**

```bash
cd /home/astro/claude-project/researcherhq/frontend && git add package.json package-lock.json src/utils/pdfExtract.js
git commit -m "feat(upload): install pdfjs-dist, add extractPdfPages util"
```

---

## Task 2: Wire PDF Upload → RAG Pipeline (BLOCKER)

**Files:**
- Modify: `frontend/src/pages/ProjectPage.jsx:77-88`

**Interfaces:**
- Consumes: `extractPdfPages(file)` from `../utils/pdfExtract`
- Consumes: `api.post('/documents/upload', { project_id, filename, category, pages })` → `{ id, filename, chunk_count, status, message }`
- Consumes: `documents` state (useState) + `setDocuments` already in scope (line 22)
- Consumes: `uploading` state (useState) + `setUploading` already in scope (line 28)
- Consumes: `fileRef` (useRef) already in scope (line 29)

- [ ] **Step 1: Replace handleFileUpload in ProjectPage.jsx**

Open `frontend/src/pages/ProjectPage.jsx`. Replace lines 1-8 (imports block) to add the new import, then replace the handleFileUpload function.

Add import at the top of the file (after existing imports, around line 9):

```jsx
import { extractPdfPages } from '../utils/pdfExtract'
```

Replace the entire `handleFileUpload` function (lines 77-88 currently):

```jsx
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
      project_id: id,
      filename: file.name,
      category: 'artikel',
      pages,
    })
    setDocuments(prev => [...prev, data])
  } catch (err) {
    const msg = err.response?.data?.detail || 'Gagal proses dokumen. Cuba lagi.'
    alert(msg)
  }
  setUploading(false)
  fileRef.current.value = ''
}
```

- [ ] **Step 2: Add uploading indicator to upload button in SourcePanel**

Check `frontend/src/components/SourcePanel.jsx` — the upload button text is `'+ Muat naik'`. We need to pass `uploading` prop from `ProjectPage.jsx` to show loading state.

In `ProjectPage.jsx`, find the `<SourcePanel>` render (around line 125) and add `uploading` prop:

```jsx
<SourcePanel
  documents={documents}
  onUpload={() => fileRef.current?.click()}
  tier={credits?.tier ?? user?.tier}
  uploading={uploading}
/>
```

In `SourcePanel.jsx`, update the function signature and button text:

```jsx
export function SourcePanel({ documents, onUpload, tier, uploading }) {
```

And update the upload button (around line 76):

```jsx
{uploadDisabled ? '🔒 Had Dicapai' : uploading ? 'Memproses...' : '+ Muat naik'}
```

Also disable the button when `uploading`:

```jsx
disabled={uploadDisabled || uploading}
```

- [ ] **Step 3: Verify build**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm run build 2>&1 | tail -10
```

Expected: build success.

- [ ] **Step 4: Commit**

```bash
cd /home/astro/claude-project/researcherhq/frontend && git add src/pages/ProjectPage.jsx src/components/SourcePanel.jsx src/utils/pdfExtract.js
git commit -m "feat(upload): wire handleFileUpload to pdfjs-dist + POST /documents/upload"
```

---

## Task 3: Support Page + Route

**Files:**
- Create: `frontend/src/pages/SupportPage.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Consumes: `api.post('/support/report', { category, description })` → `{ message, report_id }`
- Consumes: `PrivateRoute` component already in `App.jsx`

- [ ] **Step 1: Create SupportPage.jsx**

Create `frontend/src/pages/SupportPage.jsx`:

```jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'

const CATEGORIES = [
  { value: 'bug', label: 'Pepijat / Masalah Teknikal' },
  { value: 'billing', label: 'Pembayaran & Langganan' },
  { value: 'kredit', label: 'Kredit Kajian' },
  { value: 'lain-lain', label: 'Lain-lain' },
]

export function SupportPage() {
  const nav = useNavigate()
  const [category, setCategory] = useState('bug')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [reportId, setReportId] = useState(null)
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (!description.trim()) return
    setLoading(true)
    setError('')
    try {
      const { data } = await api.post('/support/report', { category, description })
      setReportId(data.report_id)
    } catch (err) {
      setError(err.response?.data?.detail || 'Gagal hantar laporan. Cuba lagi.')
    }
    setLoading(false)
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', padding: '40px 24px' }}>
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <button onClick={() => nav('/')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 14, marginBottom: 24, padding: 0 }}>
          ← Kembali ke Dashboard
        </button>
        <h1 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>
          Laporkan Isu
        </h1>
        <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 32px' }}>
          Isi borang di bawah. Kami akan maklum balas secepat mungkin.
        </p>

        {reportId ? (
          <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 'var(--radius-md)', padding: '24px' }}>
            <p style={{ fontWeight: 600, color: '#15803D', margin: '0 0 8px' }}>Laporan diterima. Terima kasih.</p>
            <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 4px' }}>No. Rujukan: <code>{reportId.slice(0, 8).toUpperCase()}</code></p>
            <button onClick={() => nav('/')} style={{ marginTop: 16, padding: '8px 16px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontFamily: 'var(--font-heading)', fontWeight: 700 }}>
              Kembali ke Dashboard
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 'var(--radius-md)', padding: 32 }}>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 500, marginBottom: 8 }}>
                Kategori
              </label>
              <select
                value={category}
                onChange={e => setCategory(e.target.value)}
                style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)' }}
              >
                {CATEGORIES.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 500, marginBottom: 8 }}>
                Keterangan
              </label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Huraikan isu anda dengan jelas..."
                required
                rows={5}
                style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', resize: 'vertical', boxSizing: 'border-box' }}
              />
            </div>
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 16px' }}>{error}</p>}
            <button type="submit" disabled={loading || !description.trim()} style={{ width: '100%', padding: '12px 0', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15, cursor: 'pointer' }}>
              {loading ? 'Menghantar...' : 'Hantar Laporan'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add route in App.jsx**

In `frontend/src/App.jsx`, add the import:

```jsx
import { SupportPage } from './pages/SupportPage'
```

Add route inside `<Routes>` (before the catch-all `*` route):

```jsx
<Route path="/support" element={<PrivateRoute><SupportPage /></PrivateRoute>} />
```

- [ ] **Step 3: Verify build**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 4: Commit**

```bash
cd /home/astro/claude-project/researcherhq/frontend && git add src/pages/SupportPage.jsx src/App.jsx
git commit -m "feat(support): add /support route + SupportPage with POST /support/report"
```

---

## Task 4: Account Settings Page (Base — Info + Delete Account)

**Files:**
- Create: `frontend/src/pages/AccountSettingsPage.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/ProfileMenu.jsx`

**Interfaces:**
- Consumes: `GET /api/account` → `{ id, email, tier, kredit_remaining, kredit_total, reset_date, created_at }`
- Consumes: `DELETE /api/account` → 204
- Note: `password_is_permanent` field will be added in Task 5 — this task renders it as `undefined` (falsy), which is fine

- [ ] **Step 1: Create AccountSettingsPage.jsx**

Create `frontend/src/pages/AccountSettingsPage.jsx`:

```jsx
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'

export function AccountSettingsPage() {
  const nav = useNavigate()
  const [account, setAccount] = useState(null)
  const [deleteStep, setDeleteStep] = useState(0) // 0=idle, 1=confirm modal
  const [deleteInput, setDeleteInput] = useState('')
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/account').then(r => setAccount(r.data)).catch(() => setError('Gagal muatkan maklumat akaun.'))
  }, [])

  async function handleDeleteAccount() {
    if (deleteInput !== 'PADAM') return
    setDeleteLoading(true)
    setDeleteError('')
    try {
      await api.delete('/account')
      localStorage.removeItem('rhq_token')
      localStorage.removeItem('rhq_user')
      nav('/auth')
    } catch (err) {
      setDeleteError(err.response?.data?.detail || 'Gagal padam akaun. Cuba lagi.')
      setDeleteLoading(false)
    }
  }

  if (error) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: '#EF4444' }}>{error}</p>
    </div>
  )

  if (!account) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: 'var(--ink-soft)' }}>Memuatkan...</p>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', padding: '40px 24px' }}>
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <button onClick={() => nav('/')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 14, marginBottom: 24, padding: 0 }}>
          ← Kembali ke Dashboard
        </button>
        <h1 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 32px' }}>
          Tetapan Akaun
        </h1>

        {/* Maklumat Akaun */}
        <section style={sectionStyle}>
          <h2 style={sectionHeadingStyle}>Maklumat Akaun</h2>
          <div style={rowStyle}>
            <span style={labelStyle}>Emel</span>
            <span style={valueStyle}>{account.email}</span>
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Pelan</span>
            <span style={{
              ...valueStyle,
              background: account.tier === 'pro' ? 'var(--accent)' : 'var(--line)',
              padding: '2px 8px', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 12,
            }}>
              {account.tier === 'pro' ? 'PRO' : 'FREE'}
            </span>
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Baki Kredit Kajian</span>
            <span style={valueStyle}>{account.kredit_remaining} / {account.kredit_total} kredit</span>
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Reset Kredit</span>
            <span style={valueStyle}>{account.reset_date}</span>
          </div>
        </section>

        {/* Langganan */}
        <section style={sectionStyle}>
          <h2 style={sectionHeadingStyle}>Langganan</h2>
          {account.tier === 'pro' ? (
            <p style={{ fontSize: 14, color: 'var(--ink-soft)', margin: 0 }}>
              Untuk batalkan langganan Pro, hubungi <strong>support@researcherhq.com</strong>
            </p>
          ) : (
            <button
              onClick={() => nav('/')}
              style={{ padding: '10px 20px', background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, cursor: 'pointer' }}
            >
              Naik Taraf ke Pro — RM39/bulan
            </button>
          )}
        </section>

        {/* Tukar Kata Laluan — will be extended in Task 6 */}
        <section style={sectionStyle} id="password-section">
          {/* Placeholder — Task 6 extends this */}
        </section>

        {/* Padam Akaun */}
        <section style={{ ...sectionStyle, borderColor: '#FECACA' }}>
          <h2 style={{ ...sectionHeadingStyle, color: '#DC2626' }}>Padam Akaun</h2>
          <p style={{ fontSize: 14, color: 'var(--ink-soft)', margin: '0 0 16px', lineHeight: 1.6 }}>
            Dokumen dan perbualan anda akan dipadam sepenuhnya. Rekod transaksi pembayaran dikekalkan tanpa nama untuk tujuan audit kewangan.
          </p>
          <button
            onClick={() => setDeleteStep(1)}
            style={{ padding: '10px 20px', background: '#EF4444', color: '#fff', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, cursor: 'pointer' }}
          >
            Padam Akaun Saya
          </button>
        </section>
      </div>

      {/* Delete Confirm Modal */}
      {deleteStep === 1 && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999, padding: 24 }}>
          <div style={{ background: 'var(--card)', borderRadius: 'var(--radius-lg)', padding: 32, maxWidth: 440, width: '100%' }}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 12px', color: '#DC2626' }}>Sahkan Pemadaman Akaun</h2>
            <p style={{ fontSize: 14, color: 'var(--ink-soft)', margin: '0 0 8px', lineHeight: 1.6 }}>
              Dokumen dan perbualan anda akan dipadam sepenuhnya. Rekod transaksi pembayaran dikekalkan tanpa nama untuk tujuan audit kewangan.
            </p>
            <p style={{ fontSize: 14, margin: '0 0 16px' }}>
              Taip <strong>PADAM</strong> untuk sahkan:
            </p>
            <input
              value={deleteInput}
              onChange={e => setDeleteInput(e.target.value)}
              placeholder="PADAM"
              style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', marginBottom: 16, boxSizing: 'border-box' }}
            />
            {deleteError && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 12px' }}>{deleteError}</p>}
            <div style={{ display: 'flex', gap: 12 }}>
              <button
                onClick={() => { setDeleteStep(0); setDeleteInput(''); setDeleteError('') }}
                style={{ flex: 1, padding: '10px 0', background: 'transparent', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', cursor: 'pointer' }}
              >
                Batal
              </button>
              <button
                onClick={handleDeleteAccount}
                disabled={deleteInput !== 'PADAM' || deleteLoading}
                style={{ flex: 1, padding: '10px 0', background: deleteInput === 'PADAM' ? '#EF4444' : 'var(--line)', color: deleteInput === 'PADAM' ? '#fff' : 'var(--ink-soft)', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, cursor: deleteInput === 'PADAM' ? 'pointer' : 'not-allowed' }}
              >
                {deleteLoading ? 'Memproses...' : 'Padam Akaun'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const sectionStyle = {
  background: 'var(--card)', border: '1px solid var(--line)',
  borderRadius: 'var(--radius-md)', padding: '24px', marginBottom: 20,
}
const sectionHeadingStyle = {
  fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16,
  margin: '0 0 16px',
}
const rowStyle = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  paddingBottom: 12, marginBottom: 12, borderBottom: '1px solid var(--line)',
}
const labelStyle = { fontSize: 14, color: 'var(--ink-soft)' }
const valueStyle = { fontSize: 14, fontWeight: 500 }
```

- [ ] **Step 2: Add route in App.jsx**

Add import:

```jsx
import { AccountSettingsPage } from './pages/AccountSettingsPage'
```

Add route (before catch-all):

```jsx
<Route path="/account" element={<PrivateRoute><AccountSettingsPage /></PrivateRoute>} />
```

- [ ] **Step 3: Fix ProfileMenu navigation**

In `frontend/src/components/ProfileMenu.jsx` line 73, change:

```jsx
{ label: 'Tetapan Akaun', action: () => {} },
```

To:

```jsx
{ label: 'Tetapan Akaun', action: () => nav('/account') },
```

- [ ] **Step 4: Build check**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
cd /home/astro/claude-project/researcherhq/frontend && git add src/pages/AccountSettingsPage.jsx src/App.jsx src/components/ProfileMenu.jsx
git commit -m "feat(account): add /account route + AccountSettingsPage with delete confirm modal"
```

---

## Task 5: Backend — Password Tetap (DB Migration + Endpoint + Account Response)

**Files:**
- Modify: `backend/app/database.py` (around line 184)
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/routers/account.py`

**Interfaces:**
- Produces: `POST /auth/set-password` body: `{ new_password: string }` → `{ message: string }`
- Produces: `GET /api/account` now returns `password_is_permanent: 0 | 1` in response dict
- Modifies: `POST /auth/request-password` resets `password_is_permanent = 0` when updating existing user

- [ ] **Step 1: Add DB migration in database.py**

In `backend/app/database.py`, after the `is_suspended` migration block (around line 185), add:

```python
    # Migration: add password_is_permanent for Opsyen B login model
    if "password_is_permanent" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN password_is_permanent INTEGER DEFAULT 0")
```

- [ ] **Step 2: Add SetPassword endpoint in auth.py**

In `backend/app/routers/auth.py`, add the Pydantic model and endpoint after the existing `login` endpoint (after line 109):

```python
class SetPasswordBody(BaseModel):
    new_password: str

@router.post("/set-password")
def set_password(body: SetPasswordBody, user=Depends(get_current_user)):
    if len(body.new_password) < 8:
        raise HTTPException(400, "Kata laluan mesti sekurang-kurangnya 8 aksara.")

    hashed = hash_password(body.new_password)
    with get_db() as db:
        db.execute(
            "UPDATE users SET password_hash = ?, password_is_permanent = 1 WHERE id = ?",
            (hashed, user["user_id"])
        )
    return {"message": "Kata laluan tetap berjaya ditetapkan."}
```

- [ ] **Step 3: Reset password_is_permanent in request_password**

In `backend/app/routers/auth.py`, in the `request_password` function, inside the `if existing:` block (around line 55), add the reset:

Change:
```python
        if existing:
            db.execute(
                "UPDATE users SET password_hash = ? WHERE email = ?",
                (hashed, body.email)
            )
```

To:
```python
        if existing:
            db.execute(
                "UPDATE users SET password_hash = ?, password_is_permanent = 0 WHERE email = ?",
                (hashed, body.email)
            )
```

- [ ] **Step 4: Add password_is_permanent to account GET response**

In `backend/app/routers/account.py`, change the SELECT query (line 89):

```python
        row = db.execute(
            "SELECT id, email, tier, kredit_remaining, kredit_total, reset_date, created_at, password_is_permanent FROM users WHERE id = ?",
            (user["user_id"],)
        ).fetchone()
```

Add `password_is_permanent` to the return dict (after line 104):

```python
    return {
        "id": row["id"],
        "email": row["email"],
        "tier": row["tier"],
        "kredit_remaining": row["kredit_remaining"],
        "kredit_total": row["kredit_total"],
        "reset_date": row["reset_date"],
        "created_at": row["created_at"],
        "password_is_permanent": row["password_is_permanent"],
    }
```

- [ ] **Step 5: Run backend tests to verify no regression**

```bash
cd /home/astro/claude-project/researcherhq && python -m pytest backend/tests/ -x -q 2>&1 | tail -20
```

Expected: all 90 tests pass. If migration error occurs, check that the column already exists gracefully (the `if "password_is_permanent" not in user_cols:` guard handles this).

- [ ] **Step 6: Commit**

```bash
cd /home/astro/claude-project/researcherhq && git add backend/app/database.py backend/app/routers/auth.py backend/app/routers/account.py
git commit -m "feat(auth): add password_is_permanent column + POST /set-password endpoint"
```

---

## Task 6: Account Settings — Tukar Kata Laluan Subsection

**Files:**
- Modify: `frontend/src/pages/AccountSettingsPage.jsx` (the `#password-section` placeholder)

**Interfaces:**
- Consumes: `account.password_is_permanent` (from Task 5's `GET /api/account` response)
- Consumes: `api.post('/auth/set-password', { new_password })` → `{ message }`

- [ ] **Step 1: Add password state to AccountSettingsPage**

In `frontend/src/pages/AccountSettingsPage.jsx`, add these state variables inside the component function (after existing state declarations):

```jsx
const [newPassword, setNewPassword] = useState('')
const [confirmPassword, setConfirmPassword] = useState('')
const [pwLoading, setPwLoading] = useState(false)
const [pwSuccess, setPwSuccess] = useState('')
const [pwError, setPwError] = useState('')
```

Add this handler function (after `handleDeleteAccount`):

```jsx
async function handleSetPassword(e) {
  e.preventDefault()
  setPwError('')
  setPwSuccess('')
  if (newPassword.length < 8) {
    setPwError('Kata laluan mesti sekurang-kurangnya 8 aksara.')
    return
  }
  if (newPassword !== confirmPassword) {
    setPwError('Kata laluan tidak sepadan.')
    return
  }
  setPwLoading(true)
  try {
    const { data } = await api.post('/auth/set-password', { new_password: newPassword })
    setPwSuccess(data.message)
    setAccount(prev => ({ ...prev, password_is_permanent: 1 }))
    setNewPassword('')
    setConfirmPassword('')
  } catch (err) {
    setPwError(err.response?.data?.detail || 'Gagal tetapkan kata laluan. Cuba lagi.')
  }
  setPwLoading(false)
}
```

- [ ] **Step 2: Replace the password-section placeholder**

In `AccountSettingsPage.jsx`, replace the empty password section:

```jsx
        {/* Tukar Kata Laluan — will be extended in Task 6 */}
        <section style={sectionStyle} id="password-section">
          {/* Placeholder — Task 6 extends this */}
        </section>
```

With:

```jsx
        {/* Tukar Kata Laluan */}
        <section style={sectionStyle}>
          <h2 style={sectionHeadingStyle}>Tukar Kata Laluan</h2>
          {!account.password_is_permanent && (
            <div style={{ background: '#FFF7ED', border: '1px solid #FED7AA', borderRadius: 8, padding: '12px 16px', marginBottom: 16 }}>
              <p style={{ fontSize: 13, color: '#C2410C', margin: 0 }}>
                Anda belum tetapkan kata laluan tetap. Tetapkan sekarang supaya tak perlu emel setiap kali log masuk.
              </p>
            </div>
          )}
          <form onSubmit={handleSetPassword}>
            <input
              type="password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              placeholder="Kata Laluan Baharu (min. 8 aksara)"
              style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', marginBottom: 10, boxSizing: 'border-box' }}
            />
            <input
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              placeholder="Sahkan Kata Laluan Baharu"
              style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', marginBottom: 10, boxSizing: 'border-box' }}
            />
            {pwError && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 10px' }}>{pwError}</p>}
            {pwSuccess && <p style={{ color: '#16A34A', fontSize: 13, margin: '0 0 10px' }}>{pwSuccess}</p>}
            <button
              type="submit"
              disabled={pwLoading || !newPassword || !confirmPassword}
              style={{ padding: '10px 20px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, cursor: 'pointer' }}
            >
              {pwLoading ? 'Menyimpan...' : account.password_is_permanent ? 'Kemaskini Kata Laluan' : 'Tetapkan Kata Laluan Tetap'}
            </button>
          </form>
        </section>
```

- [ ] **Step 3: Build check**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 4: Commit**

```bash
cd /home/astro/claude-project/researcherhq/frontend && git add src/pages/AccountSettingsPage.jsx
git commit -m "feat(account): add Tukar Kata Laluan subsection with POST /auth/set-password"
```

---

## Task 7: AuthPage Redesign — Opsyen B (Password Tetap Login)

**Files:**
- Modify: `frontend/src/pages/AuthPage.jsx`

**Interface:**
- Mode `'login'` (default): Email + Password → `POST /auth/login`
- Mode `'request'` (fallback): Email + Turnstile → `POST /auth/request-password`
- Mode `'password-after-request'`: Password field only → `POST /auth/login` (same as existing step 'password')
- After successful login via `'password-after-request'`: redirect `/?setup_password=1` if user came from request flow

- [ ] **Step 1: Replace AuthPage.jsx**

Replace the entire content of `frontend/src/pages/AuthPage.jsx`:

```jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { TurnstileWidget } from '../components/TurnstileWidget'
import api from '../api/client'

export function AuthPage() {
  const nav = useNavigate()
  // 'login' = default direct login, 'request' = request OTP email, 'password-after-request' = enter emailed password
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [turnstileToken, setTurnstileToken] = useState('')

  async function handleDirectLogin(e) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const { data } = await api.post('/auth/login', { email, password })
      localStorage.setItem('rhq_token', data.access_token)
      localStorage.setItem('rhq_user', JSON.stringify(data.user))
      nav('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Emel atau kata laluan tidak sah.')
    }
    setLoading(false)
  }

  async function handleRequestPassword(e) {
    e.preventDefault()
    if (!turnstileToken) {
      setError('Sila lengkapkan verifikasi sebelum hantar.')
      return
    }
    setLoading(true); setError('')
    try {
      await api.post('/auth/request-password', { email, turnstile_token: turnstileToken })
      setInfo('Kata laluan telah dihantar ke emel anda.')
      setMode('password-after-request')
    } catch (err) {
      setError(err.response?.data?.detail || 'Ralat berlaku.')
      setTurnstileToken('')
    }
    setLoading(false)
  }

  async function handleLoginAfterRequest(e) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const { data } = await api.post('/auth/login', { email, password })
      localStorage.setItem('rhq_token', data.access_token)
      localStorage.setItem('rhq_user', JSON.stringify(data.user))
      nav('/?setup_password=1')
    } catch (err) {
      setError(err.response?.data?.detail || 'Kata laluan salah.')
    }
    setLoading(false)
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)', padding: 24,
    }}>
      <div style={{ marginBottom: 32 }}><Logo size="lg" /></div>
      <div style={{
        background: 'var(--card)', border: '1px solid var(--line)',
        borderRadius: 'var(--radius-lg)', padding: '40px 48px',
        width: '100%', maxWidth: 400,
      }}>
        {mode === 'login' && (
          <form onSubmit={handleDirectLogin}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>Log Masuk</h2>
            <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 24px' }}>
              Masukkan emel dan kata laluan anda.
            </p>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="emel@universiti.edu.my" required
              style={inputStyle}
            />
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Kata laluan" required
              style={inputStyle}
            />
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '8px 0 0' }}>{error}</p>}
            <button type="submit" disabled={loading} style={btnStyle}>
              {loading ? 'Log masuk...' : 'Log Masuk →'}
            </button>
            <button
              type="button"
              onClick={() => { setMode('request'); setError(''); setPassword('') }}
              style={{ ...btnStyle, background: 'transparent', color: 'var(--ink-soft)', border: '1px solid var(--line)', marginTop: 8 }}
            >
              Lupa kata laluan / pertama kali log masuk?
            </button>
          </form>
        )}

        {mode === 'request' && (
          <form onSubmit={handleRequestPassword}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>Hantar Kata Laluan</h2>
            <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 24px' }}>
              Kami akan hantar kata laluan ke emel anda.
            </p>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="emel@universiti.edu.my" required
              style={inputStyle}
            />
            <TurnstileWidget onVerify={setTurnstileToken} onExpire={() => setTurnstileToken('')} />
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '8px 0 0' }}>{error}</p>}
            <button type="submit" disabled={loading || !turnstileToken} style={btnStyle}>
              {loading ? 'Menghantar...' : 'Hantar Kata Laluan →'}
            </button>
            <button
              type="button"
              onClick={() => { setMode('login'); setError('') }}
              style={{ ...btnStyle, background: 'transparent', color: 'var(--ink-soft)', marginTop: 8 }}
            >
              ← Kembali
            </button>
          </form>
        )}

        {mode === 'password-after-request' && (
          <form onSubmit={handleLoginAfterRequest}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>Masukkan Kata Laluan</h2>
            {info && <p style={{ color: '#16A34A', fontSize: 13, margin: '0 0 16px', background: '#F0FDF4', padding: '8px 12px', borderRadius: 8 }}>{info}</p>}
            <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 16px' }}>
              Emel: <strong>{email}</strong>
            </p>
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Kata laluan dari emel" required
              style={inputStyle}
            />
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '8px 0 0' }}>{error}</p>}
            <button type="submit" disabled={loading} style={btnStyle}>
              {loading ? 'Log masuk...' : 'Log Masuk →'}
            </button>
            <button
              type="button"
              onClick={() => { setMode('request'); setInfo(''); setTurnstileToken(''); setPassword('') }}
              style={{ ...btnStyle, background: 'transparent', color: 'var(--ink-soft)', marginTop: 8 }}
            >
              ← Guna emel lain
            </button>
          </form>
        )}
      </div>
      <p style={{ marginTop: 24, color: 'var(--ink-soft)', fontSize: 13, textAlign: 'center' }}>
        Workspace penyelidikan untuk postgrad Malaysia
      </p>
    </div>
  )
}

const inputStyle = {
  width: '100%', padding: '12px 14px',
  border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font-body)', fontSize: 15, color: 'var(--ink)',
  background: 'var(--bg)', outline: 'none', marginBottom: 12,
  boxSizing: 'border-box',
}

const btnStyle = {
  width: '100%', padding: '12px 0',
  background: 'var(--ink)', color: 'var(--bg)',
  border: 'none', borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15,
  cursor: 'pointer', marginTop: 4, display: 'block',
}
```

- [ ] **Step 2: Build check**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 3: Run backend tests**

```bash
cd /home/astro/claude-project/researcherhq && python -m pytest backend/tests/ -x -q 2>&1 | tail -10
```

Expected: 90 tests pass.

- [ ] **Step 4: Commit**

```bash
cd /home/astro/claude-project/researcherhq/frontend && git add src/pages/AuthPage.jsx
git commit -m "feat(auth): Opsyen B login — default email+password, fallback to request-OTP flow"
```

---

## Task 8: Terminology Fix + ProfileMenu Scan

**Files:**
- Modify: `frontend/src/components/ProfileMenu.jsx:68`

- [ ] **Step 1: Fix kredit tersisa → Baki Kredit Kajian**

In `frontend/src/components/ProfileMenu.jsx`, replace line 68:

```jsx
                {credits.kredit_remaining} kredit tersisa
```

With:

```jsx
                Baki Kredit Kajian: {credits.kredit_remaining}
```

- [ ] **Step 2: Run grep scan**

```bash
grep -rn "kredit tersisa\|baki kredit\|kredit baki" /home/astro/claude-project/researcherhq/frontend/src --include="*.jsx"
```

Record output — if any results appear beyond the one already fixed, list them for Bos's review. DO NOT auto-fix.

Also check for generic "X kredit" patterns that may be intentional (narrow UI):

```bash
grep -rn "kredit" /home/astro/claude-project/researcherhq/frontend/src --include="*.jsx" | grep -v "kredit_remaining\|kredit_used\|kredit_total\|kredit_added\|kredit digunakan\|Kredit Kajian\|kredit tersisa\|Kredit\|kr)"
```

Review output and list in commit message.

- [ ] **Step 3: Build check**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 4: Commit**

```bash
cd /home/astro/claude-project/researcherhq/frontend && git add src/components/ProfileMenu.jsx
git commit -m "fix(terminology): 'kredit tersisa' → 'Baki Kredit Kajian' in ProfileMenu

Grep scan selesai — tiada inconsistency lain ditemui [atau: senarai isu lain yang ditemui untuk review Bos]"
```

---

## Task 9: Mobile Responsive — 3-Panel Tab Switcher

**Files:**
- Create: `frontend/src/hooks/useMediaQuery.js`
- Modify: `frontend/src/pages/ProjectPage.jsx`

- [ ] **Step 1: Create useMediaQuery hook**

Create `frontend/src/hooks/useMediaQuery.js`:

```js
import { useState, useEffect } from 'react'

export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mql = window.matchMedia(query)
    const handler = () => setMatches(mql.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [query])
  return matches
}
```

- [ ] **Step 2: Add mobile state + hook to ProjectPage.jsx**

In `frontend/src/pages/ProjectPage.jsx`, add import at top:

```jsx
import { useMediaQuery } from '../hooks/useMediaQuery'
```

Add inside the `ProjectPage` component function (after existing state declarations):

```jsx
const isMobile = useMediaQuery('(max-width: 768px)')
const [mobileTab, setMobileTab] = useState('chat') // 'source' | 'chat' | 'structure'
```

- [ ] **Step 3: Wrap the 3-panel layout with mobile conditional**

Find the 3-panel flex container starting with (around line 123):
```jsx
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
```

Replace the entire content from `<div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>` to the closing `</div>` of this container (which closes just before the final `</div>` of the component's return) with:

```jsx
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {isMobile && (
          <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', background: 'var(--card)', flexShrink: 0 }}>
            {[
              { key: 'source', label: 'Sumber' },
              { key: 'chat', label: 'Chat' },
              { key: 'structure', label: 'Struktur' },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setMobileTab(tab.key)}
                style={{
                  flex: 1, padding: '10px 0',
                  background: mobileTab === tab.key ? 'var(--ink)' : 'transparent',
                  color: mobileTab === tab.key ? 'var(--bg)' : 'var(--ink-soft)',
                  border: 'none', fontFamily: 'var(--font-body)', fontSize: 13,
                  cursor: 'pointer', borderBottom: mobileTab === tab.key ? '2px solid var(--accent)' : '2px solid transparent',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
        )}

        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <input type="file" ref={fileRef} onChange={handleFileUpload} accept=".pdf" style={{ display: 'none' }} />

          {(!isMobile || mobileTab === 'source') && (
            <SourcePanel
              documents={documents}
              onUpload={() => fileRef.current?.click()}
              tier={credits?.tier ?? user?.tier}
              uploading={uploading}
            />
          )}

          {(!isMobile || mobileTab === 'chat') && (
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
          )}

          {(!isMobile || mobileTab === 'structure') && (
            <ThesisPanel
              chapters={chapters}
              onExport={handleExport}
              tier={credits?.tier ?? user?.tier}
              projectId={id}
            />
          )}
        </div>
      </div>
```

Note: also remove the old `<input type="file" ...>` that was at line 124 in the original (it's now inside the new structure above), and remove the old `<SourcePanel>`, chat div, and `<ThesisPanel>` — they're replaced by the conditional renders above.

- [ ] **Step 4: Build check**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
cd /home/astro/claude-project/researcherhq/frontend && git add src/hooks/useMediaQuery.js src/pages/ProjectPage.jsx
git commit -m "feat(responsive): mobile tab switcher for 3-panel workspace (<768px)"
```

---

## Task 10: Full Regression + Acceptance Criteria Checklist

- [ ] **Step 1: Run full backend test suite**

```bash
cd /home/astro/claude-project/researcherhq && python -m pytest backend/tests/ -v 2>&1 | tail -30
```

Expected: 90/90 pass. If any fail, fix the issue before proceeding.

- [ ] **Step 2: Production build test**

```bash
cd /home/astro/claude-project/researcherhq/frontend && npm run build 2>&1 | tail -20
```

Expected: zero errors, check for any warnings about pdfjs-dist worker.

- [ ] **Step 3: Report manual test checklist for Bos**

Report the following items that need manual verification (automated tests cannot cover these):

**Item 1 — Upload PDF:**
- [ ] AC1: Upload PDF teks biasa di project sebenar → dokumen muncul Source Panel <10s
- [ ] AC2: Tanya soalan tentang isi PDF → jawapan ada citation (RAG end-to-end)
- [ ] AC3: Upload PDF scan sebagai Free user → 403 error dengan mesej upgrade Pro
- [ ] AC4: Refresh browser lepas upload → dokumen masih nampak
- [ ] AC5: `npm run build` + production serve → PDF.js worker jalan betul
- [ ] AC6: Upload fail .docx → error message jelas

**Item 2 — Mobile Responsive:**
- [ ] AC1: Chrome DevTools iPhone SE (375px) → tab switcher visible, satu panel je, tiada scroll
- [ ] AC2: Switch tab → state kekal (chat history tak hilang)
- [ ] AC3: Desktop >768px → zero visual perubahan
- [ ] AC4: Resize slow desktop→mobile → smooth transition

**Item 3 — Tetapan Akaun:**
- [ ] AC1: Klik Tetapan Akaun → data account betul dipaparkan
- [ ] AC2: Padam Akaun → confirm → redirect /auth, login semula treated as new user
- [ ] AC3: Padam akaun tapi cancel/taip salah → tiada yang terpadam
- [ ] AC4: Reset Password link → redirect ke /auth (mode 'request')

**Item 4 — Laporkan Isu:**
- [ ] AC1: Hantar laporan → 201, report_id dipaparkan
- [ ] AC2: Check Telegram → notification diterima <5s
- [ ] AC3: Check support_reports table → row baharu dengan status='open'
- [ ] AC4: Klik Laporkan Isu dari menu → page betul terbuka

**Item 5 — Terminology:**
- [ ] AC1: ProfileMenu dropdown → "Baki Kredit Kajian: [angka]"
- [ ] AC2: Grep scan result disertakan dalam commit message Task 8

**Item 6 — Password Tetap:**
- [ ] AC1: User baharu signup → terima email, login berjaya (flow sedia ada kekal)
- [ ] AC2: Lepas login, Account Settings → set password tetap → password_is_permanent = 1
- [ ] AC3: Logout, login guna email+password tetap (mode 'login') → berjaya, TIADA email dihantar
- [ ] AC4: User belum set password tetap, cuba mode 'login' → gagal, link "Lupa kata laluan" jelas
- [ ] AC5: Set password tetap, klik Lupa kata laluan → password_is_permanent reset ke 0
- [ ] AC6: Full auth test suite → masih 90 pass

**FLAGS UNTUK BOS:**
- **FLAG A**: Billing cancel endpoint tiada — Pro user nampak "Hubungi support@researcherhq.com"
- **FLAG B**: Backend `/documents/upload` response tiada `is_ocr` field — OCR alert untuk Pro user tidak diimplementasi; Free user dengan PDF imbasan masih dapat 403 error yang betul
- **FLAG C**: `request-password` sekarang reset `password_is_permanent = 0` — ini additive, semua auth tests masih pass. Tapi confirm dengan Bos bahawa ini expected behaviour sebelum deploy.
