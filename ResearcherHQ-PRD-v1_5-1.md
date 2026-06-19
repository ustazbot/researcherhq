# ResearcherHQ — Product Requirements Document

**Versi:** 1.5 (rebrand: ResearcherHQ)
**Tarikh:** 19 Jun 2026
**Status:** ICP, pricing, architecture, workspace & consistency layer muktamad — sedia untuk MVP build berfasa
**Pemilik Produk:** Bos
**Build tool:** Claude Code → FastAPI + React (web app)
**Nota:** Tambahan §6C (User Account & Support) — completion of existing scope, bukan perubahan struktur. Version kekal 1.5; v1.6 reserved untuk perubahan luar jangka.

---

## Perubahan Utama v1.4 → v1.5

| Bidang | v1.4 (Lama) | v1.5 (Baru) |
|---|---|---|
| Context strategy | RAG top-K sahaja | **+ §5C Hierarchical Context (thesis multi-bab)** |
| Consistency | Tiada | **+ §5D Determinism Layer (temp lock, query cache, versioning)** |
| UI paradigm | Chat single-panel | **+ §6B Thesis Workspace (3-panel)** |
| Build sequence | Fasa kasar | **+ KPI exit gate setiap fasa** |
| Load handling | Anggaran | **+ §14A Load Testing Protocol (50 concurrent)** |
| Embedding | Diandaikan ringan | **Worker pool + queue (CPU bottleneck mitigation)** |
| Export | Disebut sahaja | **.docx async queue (RAM-safe)** |
| Free tier | Chat sahaja | **Workspace "visible, locked"** |

---

## 1. Ringkasan Produk

**ResearcherHQ** ialah workspace penyelidikan berasaskan dokumen untuk penyelidik Malaysia — terutama pelajar postgrad yang sedang menulis tesis. Ia bukan chatbot. Ia ingat projek penyelidikan, hanya menjawab berdasarkan dokumen yang dimuat naik, menghasilkan output siap guna dengan citation yang boleh di-trace, dan menyediakan ruang kerja berstruktur untuk menulis tesis bab demi bab.

**Tagline:** *"ChatGPT menjawab soalan. ResearcherHQ siapkan tesis awak."*

**Misi:** Bantu seramai mungkin penyelidik Malaysia hasilkan kerja akademik yang tepat, bersumberkan, dan berkualiti — tanpa perlu faham AI secara teknikal.

### Masalah Yang Diselesaikan

1. ChatGPT tak ingat konteks penyelidikan antara sesi
2. ChatGPT hallucinate rujukan akademik (reka jurnal, tahun, penulis)
3. ChatGPT bagi jawapan berbeza untuk soalan sama (inconsistency)
4. ChatGPT tool umum — bukan workspace akademik berstruktur
5. Dokumen sulit tak sepatutnya dihantar ke server pihak ketiga tanpa kawalan
6. Output ChatGPT conversational — bukan format akademik siap guna
7. Tiada ruang kerja yang satukan sumber, perbincangan AI, dan struktur tesis

---

## 2. Target Pengguna (ICP)

### Fokus Utama MVP: Pelajar Postgrad (Master & PhD)

| Elemen | Detail |
|---|---|
| **Siapa** | Pelajar Master & PhD universiti Malaysia (IPTA & IPTS) |
| **Pain utama** | SV suruh revise citation, bab Literature Review stall, takut plagiat, deadline tesis, urus banyak sumber rujukan |
| **Behaviour** | Selalu guna ChatGPT tapi kecewa bila citation salah atau AI "lupa" konteks |
| **Budget** | Ketat (PTPTN/biasiswa) — RM39/bulan perlu justify value jelas |
| **Viral path** | Share dalam WhatsApp group cohort, forum postgrad, group Facebook fakulti |

**Kenapa postgrad, bukan pensyarah:**
- Pain lebih urgent (deadline viva, SV comment)
- Decision cycle lebih pendek (bayar sendiri, tak perlu kelulusan jabatan)
- Viral coefficient lebih tinggi dalam cohort
- Malaysia ada ~150,000+ pelajar postgrad aktif (MOHE) — market cukup besar untuk MVP

### Segment Sekunder (Fasa 2, bila ada traction)

| Segment | Pain | Willingness to Pay |
|---|---|---|
| Pensyarah & penyelidik | Grant proposal, laporan penyelidikan | Tinggi |
| Pegawai kerajaan | Laporan berasaskan kajian, deadline ketat | Sederhana–Tinggi |
| Konsultan swasta | Research industri sebelum pitch client | Tinggi |

---

## 3. Model Bisnes & Pricing

### Struktur Tier (Single Paid Tier)

```
FREE (Hook)
├── 50 Kredit Kajian/bulan (auto-reset)
├── Max 1 PDF per session
├── 1 active project
├── History simpan 7 hari sahaja
├── Workspace: NAMPAK penuh, tapi LOCKED (lihat §6B)
│   ├── Chat + citation: BOLEH guna
│   ├── Chapter management: 🔒 Pro
│   └── Export .docx: 🔒 Pro
└── Watermark pada export (jika ada akses)

PRO — RM39/bulan
├── 500 Kredit Kajian/bulan (auto-reset)
├── Up to 5 PDF serentak per project
├── 10 active projects
├── History kekal selamanya
├── Workspace PENUH (3-panel, chapter management, export)
├── Export .docx per-chapter tanpa watermark
├── OCR fallback untuk scanned PDF
└── Priority queue

TOPUP (tanpa tukar tier)
└── RM10 = +200 Kredit Kajian (sah hingga akhir bulan semasa)
```

### Kadar Kredit Kajian

| Task | Kredit |
|---|---|
| Soalan biasa (Q&A) | 1 kredit |
| Soalan mendalam (deep query) | 3 kredit |
| Key Findings extraction | 3 kredit |
| Executive Summary | 5 kredit |
| Literature Review draft | 10 kredit |
| Research Gap (Fasa 3) | 10 kredit |

### Unit Economics (Hybrid Routing, RM39)

| Metrik | Nilai |
|---|---|
| Kos DeepSeek per Pro user (hybrid) | ~RM2.95/bulan |
| Harga Pro | RM39/bulan |
| **Margin** | **~92%** |
| Kos VPS | RM25/bulan (shared dengan 1page.my) |

### Projeksi Revenue (Realistic, 5–10% conversion)

| Bulan | Free Users | Paying | Revenue | Net Profit |
|---|---|---|---|---|
| 3 | 200 | 10 | RM390 | ~RM330 |
| 6 | 500 | 25 | RM975 | ~RM850 |
| 12 | 1,000 | 50 | RM1,950 | ~RM1,720 |

---

## 4. Architecture — Muktamad

```
┌─────────────────────────────────────┐
│  User Browser                       │
│  React SPA (3-Panel Workspace)      │
│  ├── Source Panel (kiri)            │
│  ├── Chat/Workspace (tengah)        │
│  ├── Thesis Structure (kanan)       │
│  ├── Kredit Kajian tank             │
│  ├── Documentation (Kredit Kajian)  │
│  └── KaTeX (LaTeX rendering)        │
│                                     │
│  PDF.js — extract text browser-side │
└──────────────┬──────────────────────┘
               │ Text only (fail asal tak upload)
               ↓ HTTPS
┌──────────────────────────────────────┐
│  Contabo VPS (8GB RAM, 4 vCPU)       │
│  Shared dengan 1page.my              │
│                                      │
│  Nginx (reverse proxy)               │
│  ├── 1page.my → port 3000            │
│  └── researcherhq → port 8000        │
│                                      │
│  FastAPI Backend (port 8000)         │
│  ├── Auth (password-on-demand)       │
│  ├── Kredit Kajian tracker + enforce │
│  ├── RAG pipeline (MMR + adaptive K) │
│  ├── Embedding worker pool + queue   │
│  ├── OCR fallback (pytesseract)      │
│  ├── LLM proxy (DeepSeek, Bos key)  │
│  ├── Output mode router              │
│  ├── Query cache (versioned)         │
│  ├── Export queue (.docx async)      │
│  └── BillPlz webhook handler        │
│                                      │
│  Embedding: all-MiniLM-L6-v2 (local)│
│                                      │
│  SQLite + sqlite-vec (WAL mode)      │
│  ├── users, projects, documents      │
│  ├── chunks + chunk_vectors          │
│  ├── chapters + chapter_content      │
│  ├── messages, billing_events        │
│  ├── query_cache                     │
│  ├── user_interactions               │
│  └── app_learnings                   │
└──────────────┬───────────────────────┘
               ↓
         DeepSeek V4 API
         (Flash default / Pro escalation)
         (Bos punya key, user tak nampak)
```

### Stack Muktamad

| Komponen | Pilihan | Status |
|---|---|---|
| Deployment | Web app, Contabo VPS (shared) | Locked |
| Backend | FastAPI | Locked |
| Frontend | React SPA (3-panel workspace) | Locked |
| Database | SQLite (WAL mode) | Locked |
| Vector store | sqlite-vec | Locked |
| Embedding | all-MiniLM-L6-v2 (local) + worker pool | Locked |
| LLM | DeepSeek V4 Flash (default) + V4 Pro (escalation) | Locked |
| File processing | PDF.js (browser) + pytesseract fallback | Locked |
| Auth | Password-on-demand (Resend SMTP) | Locked |
| Billing | BillPlz | Locked |
| Export | python-docx (.docx, async queue) | Locked |
| LaTeX | KaTeX (frontend) | Locked |
| Reverse proxy | Nginx | Locked |

---

## 5. RAG Pipeline — Anti-Hallucination Core

RAG adalah **wajib**. Tanpa RAG: AI hallucinate citation, token limit terlalu rendah, atau kos terlalu tinggi.

### Flow

```
User upload PDF
  → Detect jenis PDF (PDF.js extract)
  → Jika text < 50 token/halaman → flag scanned PDF
      → OCR via pytesseract (Pro tier, server-side, async)
  → Chunk (400 token, 80 overlap)
  → Embed (worker pool — lihat §5E)
  → Simpan SQLite-vec
  → Naikkan document_set_version project (untuk cache invalidation)

User tanya soalan
  → Check query_cache (versioned) — jika hit, return cached
  → Jika miss: Embed soalan
  → Similarity search (adaptive top-K + MMR)
  → Hantar chunk + soalan ke DeepSeek (temperature 0.1)
  → Jawapan grounded + citation [fail, ms.X]
  → Simpan ke query_cache dengan version semasa
```

### Chunking Strategy

```python
CHUNK_SIZE = 400        # token
CHUNK_OVERLAP = 80      # preserve konteks antara chunk
MIN_CHUNK_SIZE = 100    # buang header/page number
```

### Adaptive Retrieval (Top-K)

```python
def get_retrieval_k(query_type: str, doc_count: int) -> int:
    if query_type == "deep":
        return 12
    elif doc_count > 10:
        return 10
    else:
        return 6

# MMR — diversify hasil, elak chunk redundant
# similarity_weight=0.7, diversity_weight=0.3
```

### System Prompt — Anti-Hallucination (Base)

```
Anda adalah research assistant untuk ResearcherHQ.

PERATURAN WAJIB:
1. Jawab HANYA berdasarkan konteks dokumen yang diberikan
2. Jika maklumat tiada dalam konteks, jawab:
   "Maklumat ini tidak terdapat dalam dokumen yang dimuat naik."
3. Setiap fakta MESTI ada sumber [nama fail, ms. X]
4. JANGAN tambah pengetahuan umum kecuali diminta
5. Bahasa Melayu melainkan dokumen dalam Bahasa Inggeris

Format:
- Ringkas dan tepat
- Citation inline: (Nama Fail, ms. 12)
- Akhiri dengan senarai sumber
```

### OCR Fallback Flow

```
PDF.js extract → text < 50 token/halaman
  → Mesej: "PDF ini nampak seperti dokumen imbasan. OCR sedang diproses..."
  → Backend: pytesseract (lang: eng+msa), async
  → Output text → masuk pipeline RAG
  → Flag DB: is_ocr=True
  → Free tier: "Naik taraf ke Pro untuk proses PDF imbasan."
```

---

## 5A. LLM Routing Strategy

### Harga Sahih DeepSeek (Official Docs, 18 Jun 2026)

| | V4 Flash | V4 Pro |
|---|---|---|
| Input (cache miss) per 1M | $0.14 | $0.435 |
| Input (cache hit) per 1M | $0.0028 | $0.003625 |
| Output per 1M | $0.28 | $0.87 |
| Context | 1M | 1M |
| Max output | 384K | 384K |
| Concurrency limit | 2,500 | 500 |

### Routing Logic

```
DEFAULT — V4 Flash (~90% queries)
├── Q&A biasa, Key Findings, Executive Summary
└── Concurrency headroom: 2,500

ESCALATE — V4 Pro (~10% queries)
├── Literature Review penuh, Methodology analysis, deep query

FASA 1 MVP: V4 Flash sahaja (margin 92%)
Tambah Pro escalation bila ada paying user yang justify kos.
```

### Cache Optimization (DeepSeek prefix cache)

System prompt konsisten = prefix cache hit pada 1/120 harga. Sasaran 50–70% cache hit → kos turun 30–40%. *Nota: Ini berbeza dari query_cache aplikasi (§5D).*

---

## 5B. Citation Accuracy — 3 Lapis

### Lapis 1 — RAG Grounding
Jawapan MESTI dipetik dari chunk yang wujud. Citation: `[nama fail, ms. X]` — bukan rekaan.

### Lapis 2 — System Prompt Enforcement
```
PERATURAN CITATION:
- JANGAN cipta citation baharu yang tiada dalam dokumen
- JANGAN tambah author/tahun/jurnal yang tidak wujud dalam dokumen
- Jika tiada citation: "Rujukan tidak ditemui dalam dokumen anda"
- Format APA/Chicago: apply pada citation yang ditemui sahaja
```

### Lapis 3 — UI Verification
Setiap citation ada butang **"Lihat Sumber"** → expand chunk asal → user verify sendiri.

---

## 5C. Hierarchical Context Strategy (Thesis Multi-Bab)

Tesis penuh = ~150,000 token. TIDAK boleh hantar sekaligus (mahal + kualiti jatuh). Penyelesaian: ringkasan berlapis.

### Konsep

```
Setiap bab → summarize → simpan sebagai chapter_summary
(disimpan dalam chapter_content, regenerate bila content bab berubah)

Bila task perlukan konteks keseluruhan tesis (cth Literature Review):
  → Hantar semua chapter_summary (pendek, ~200 token/bab)
  + chunk relevan dari bab spesifik (RAG)
  → AI dapat "nampak" struktur penuh tesis tanpa overload context
```

### Bila Digunakan

| Task | Strategi Konteks |
|---|---|
| Q&A bab tertentu | RAG top-6 (tiada summary perlu) |
| Key Findings 1 dokumen | RAG top-10 |
| Literature Review (1–3 PDF) | RAG top-12 + MMR |
| Cross-chapter synthesis | chapter_summary semua bab + RAG relevan |

### Token Budget (Anggaran)

```
Cross-chapter call:
  5 chapter_summary × 200 token = 1,000 token
  + 12 chunk relevan × 400 token = 4,800 token
  + system prompt + soalan = ~1,000 token
  ───────────────────────────────────
  ~6,800 token input — selamat, kos terkawal
```

---

## 5D. Consistency & Determinism Layer

Mengatasi masalah "soalan sama, jawapan berbeza." **Nota jujur (anti-gharar): konsistensi 100% hanya untuk exact/near-exact match. Soalan paraphrase akan konsisten dari segi FAKTA, tapi framing mungkin berbeza sedikit.**

### Mekanisme

```
1. Temperature lock
   temperature=0.1, top_p=0.1
   → Kurangkan 70-80% variance

2. Query cache (exact + near-match)
   cache_key = hash(normalized_query + project_id + document_set_version)
   - Exact match → return cached (100% sama, zero kos)
   - Near-match (embedding similarity > 0.95) → return cached
   
3. Retrieval determinism
   results.sort(key=lambda x: (x.similarity, x.chunk_id))
   → tie-breaking konsisten, urutan chunk tak berubah

4. Cache invalidation (KRITIKAL — anti-gharar)
   document_set_version naik bila user upload/buang dokumen
   → cache lama auto-invalid → user TAK DAPAT jawapan outdated
```

### Schema Cache

```sql
CREATE TABLE query_cache (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id),
  query_normalized TEXT,
  query_embedding BLOB,
  document_set_version INTEGER,
  response TEXT,
  source_chunks TEXT,
  created_at TEXT
);
```

---

## 5E. Embedding Worker Pool (Concurrency Mitigation)

**Isu CTO:** all-MiniLM-L6-v2 jalan di CPU (tiada GPU). 50 user query serentak atas 4 vCPU = embedding akan queue, boleh tambah 3-5s latency.

### Penyelesaian

```python
# Worker pool dedicated untuk embedding
# Elak setiap request spawn embedding sendiri

EMBEDDING_WORKERS = 3        # reserve 1 core untuk FastAPI + lain
BATCH_SIZE = 8               # batch embedding bila boleh
QUEUE_TIMEOUT = 10           # saat

# Upload (chunk embedding) — batch processing
# Query (single embedding) — priority queue, jangan block read
```

### Constraint Sebenar

```
50 concurrent query embedding:
  - Tanpa pool: queue tak terurus, latency tak predictable
  - Dengan pool (3 worker, batch): ~1-2s queue worst case
  - Acceptable untuk MVP < 50 concurrent

Upgrade trigger: jika concurrent > 50 konsisten,
pertimbang embedding via API atau GPU VPS.
```

---

## 6. Research Mode (Multi-Jurusan)

Tukar **system prompt + output template** ikut jurusan (bukan tukar model).

| Mode | Keperluan Khusus |
|---|---|
| Umum | Standard research assistant |
| Kuantitatif / Sains | Ujian statistik, p-value, effect size, CI, LaTeX, cadang SPSS/R/Python |
| Kualitatif / Sains Sosial | Thematic analysis, coding, grounded theory, phenomenology |
| Undang-undang | Citation kes, precedent analysis — strict RAG-only |
| Perubatan / Kesihatan | PICO framework, PRISMA, level of evidence |

User pilih sekali per project. System prompt swap automatically.

### Mode Undang-undang — Strict Anti-Hallucination

```
PERATURAN TAMBAHAN (MODE UNDANG-UNDANG):
- JANGAN sebut kes yang tiada dalam dokumen dimuat naik
- TIADA pengetahuan umum — kes mestilah dari dokumen user sahaja
- Format citation kes: [Nama Kes] [Tahun] [Rujukan MLJ/CLJ/AMR] [halaman]
- Precedent analysis: hanya dari dokumen ada
- Jika tiada kes relevan: "Tiada kes dalam dokumen yang merangkumi isu ini"

ROADMAP FASA 3: Mini-index tajuk kes Malaysia (CLJ/MLJ) untuk verify kewujudan.
```

---

## 6A. Output Modes (5 Jenis)

| # | Mode | Output | Kredit | Fasa |
|---|---|---|---|---|
| 1 | Soal-Jawab | Q&A grounded + citation inline | 1 / 3 | 1 |
| 2 | Literature Review | Pengenalan → Sorotan → Jurang → Rumusan | 10 | 1 |
| 3 | Executive Summary | 1–2 ms: key points, methodology, findings | 5 | 1 |
| 4 | Key Findings | Bullet structured + source chunk setiap dapatan | 3 | 1 |
| 5 | Research Gap | Banding kajian → kenal pasti gap (untuk proposal) | 10 | 3 |

---

## 6B. Thesis Workspace (Core Differentiator)

Pembeza utama dari semua competitor — bukan chat, tapi **meja kerja tesis**.

### Layout 3-Panel

```
┌──────────────┬─────────────────────┬──────────────────┐
│ SUMBER        │  CHAT / WORKSPACE   │  STRUKTUR THESIS  │
│ (kiri)        │  (tengah)           │  (kanan)          │
├──────────────┼─────────────────────┼──────────────────┤
│ 📄 Artikel    │  [Chat dengan AI]   │  ☑ Bab 1: Intro   │
│ 📝 Catatan SV │  Q&A + output modes │  ☑ Bab 2: Lit Rev │
│ 📑 Draf       │  Citation + sumber  │  ⬜ Bab 3: Method  │
│ 📊 Data       │                     │  ⬜ Bab 4: Dapatan │
│              │  [Assign ke bab →]   │  ⬜ Bab 5: Rumusan │
│ [+ Upload]    │                     │  [Export Bab Ini] │
└──────────────┴─────────────────────┴──────────────────┘

Setiap panel boleh expand/collapse (responsive untuk skrin kecil).
```

### Panel Sumber (Kiri) — Berkategori

```
├── Artikel Rujukan (PDF jurnal)
├── Catatan Supervisor (nota SV — text/PDF)
├── Draf Sendiri (draf sedia ada user)
└── Data/Transkrip (kajian kualitatif)

Klik fail → preview + "Berapa kali dirujuk dalam chat"
```

### Panel Struktur Thesis (Kanan) — Chapter Entity

```
├── Setiap bab = entity dalam DB (bukan hardcode)
├── Status: draft / dalam proses / siap
├── Content AI generate boleh di-assign ke bab tertentu
├── Progress visual (5/8 bab siap)
└── Export per-bab → .docx
```

### Free Tier — "Visible, Locked"

```
Free user buka project:
├── Nampak 3-panel layout PENUH ✅
├── Source panel: upload 1 PDF, nampak ✅
├── Chat: boleh guna (50 kredit) ✅
├── Struktur Thesis panel: NAMPAK (template standard) ✅
│   └── Setiap bab ada overlay "🔒 Pro"
├── Assign content ke bab: 🔒 → "Naik taraf ke Pro"
└── Export .docx: butang nampak, klik → upgrade prompt

Prinsip (anti-gharar): Tunjuk semua, lock interaksi.
User faham persis apa Pro tawarkan — bukan beli kucing dalam karung.
```

### Onboarding — Pilih Struktur Tesis

```
Step 1: Pilih bidang (Sains/Sastera/Undang-undang/dll)
   → Set Research Mode default

Step 2: Pilih struktur tesis
   ┌─────────────────────────────┐
   │ ○ Template Standard (5 Bab)  │
   │ ○ Define Struktur Sendiri    │
   └─────────────────────────────┘

Step 3 (jika custom): Input nama bab + drag-drop reorder

Step 4: Struktur jadi chapters dalam project
   → Boleh edit/tambah/buang BILA-BILA MASA (bukan locked di onboarding)
```

### Template Standard Malaysia (Baseline)

```
BAB 1 — Pengenalan (Latar Belakang, Penyataan Masalah,
        Objektif, Persoalan, Kepentingan Kajian)
BAB 2 — Sorotan Kajian (Literature Review)
BAB 3 — Metodologi
BAB 4 — Dapatan Kajian / Analisis
BAB 5 — Perbincangan & Kesimpulan
```

*Nota: Format 5-bab umum. Sains tulen kadang guna struktur berbeza (Bab 4 "Keputusan", Bab 5 "Perbincangan", Bab 6 "Kesimpulan"). Baseline ini perlu disahkan dengan garis panduan tesis universiti sasaran (UKM/UM/USM) sebelum locked sepenuhnya.*

### Export — .docx (Async Queue)

```
Klik [Export Bab Ini] →
  → Masuk export queue (BUKAN synchronous — elak RAM spike)
  → "Sedang disediakan..." → notify bila siap
  → Compile chapter_content + citation list bab tersebut
  → Generate .docx (python-docx)
  → Download / hantar email

Format: .docx sahaja (editable, zero OAuth, buka di Word/GDocs/LibreOffice)
PDF: upgrade kemudian bila matang.
```

---

## 6C. User Account & Support (Lean MVP Scope)

Profile menu dan support channel — minimum viable, bukan full-feature. Masuk dalam Fasa 1A (tiada fasa berasingan).

### Profile Menu (Top-Right, Semua Skrin)

```
Menu User
├── Email + Tier badge (Free/Pro)
├── Kredit Kajian remaining (link → documentation page §7)
├── Manage Subscription
│   ├── Pro: cancel/downgrade, billing history (BillPlz)
│   └── Free: upgrade CTA
├── Account Settings
│   └── Reset Password (reuse flow §8 — TIADA "tukar password"
│       langsung, guna regenerate-password flow sedia ada)
├── Padam Akaun (lihat PDPA Cascade di bawah)
└── Logout
```

### PDPA — Cascade Delete (Wajib, Bukan Optional)

**Isu teknikal:** SQLite tidak enforce foreign key by default. Schema asal §10 TIADA `ON DELETE CASCADE`. Tanpa fix, "padam akaun" akan tinggalkan orphan data (PDPA breach).

```sql
-- Wajib enable setiap connection
PRAGMA foreign_keys = ON;

-- Semua FK kena ON DELETE CASCADE:
-- projects, documents, chunks, chapters, chapter_content,
-- messages, query_cache, user_interactions, support_reports
-- → cascade ikut user_id / project_id chain
```

**Pengecualian — `billing_events`:** TIDAK delete. Rekod kewangan kekal untuk keperluan audit/cukai. Approach: **anonymize**, bukan hard-delete.

```python
def delete_user_account(user_id: str):
    # 1. Manual delete chunk_vectors (virtual table, FK tak applicable)
    chunk_ids = db.execute(
        "SELECT c.id FROM chunks c "
        "JOIN documents d ON c.doc_id = d.id "
        "JOIN projects p ON d.project_id = p.id "
        "WHERE p.user_id = ?", (user_id,)
    ).fetchall()
    for cid in chunk_ids:
        db.execute("DELETE FROM chunk_vectors WHERE chunk_id = ?", (cid,))

    # 2. Anonymize billing_events SEBELUM delete user (kekal rekod kewangan)
    db.execute(
        "UPDATE billing_events SET user_id = 'deleted_user' WHERE user_id = ?",
        (user_id,)
    )

    # 3. Delete user → cascade automatik padam projects, documents,
    #    chunks, chapters, messages, query_cache, user_interactions
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
```

**Prinsip (anti-gharar):** Data peribadi & kandungan penyelidikan (dokumen, chat, draf) → padam betul-betul. Rekod transaksi kewangan → anonymize, kekalkan untuk pematuhan audit. User diberitahu jelas di UI: *"Dokumen dan perbualan anda akan dipadam sepenuhnya. Rekod transaksi pembayaran dikekalkan tanpa nama untuk tujuan audit kewangan."*

### Lean Report Issue (Helpdesk Fasa 1)

Bukan ticketing system penuh — direct-to-Telegram, single channel.

```
POST /support/report
{
  "category": "bug" | "billing" | "kredit" | "lain-lain",
  "description": str,
  "project_id": optional
}
→ Simpan dalam support_reports (status: open)
→ Hantar notification ke Telegram Bos (Bot API, instant, free)
→ Auto-reply ke user: "Laporan diterima."
```

**Setup required (manual, bukan code):**
1. Buat bot via @BotFather → `TELEGRAM_BOT_TOKEN`
2. Start chat dengan bot → dapatkan `chat_id` Bos
3. Simpan dalam `.env`

**Nota:** Email (Resend) kekal khas untuk auth password sahaja — jangan double-purpose untuk support, elak kerumitan tak perlu pada volume MVP (10–50 paying user).

---

## 7. Kredit Kajian — Display & Quota System

### Konsep
**Kredit Kajian** = unit yang gambarkan "kedalaman" kerja AI. Task yang perlukan AI baca lebih banyak dokumen = lebih banyak kredit.

### UI Display (Visual Tank B+C)

```
┌─────────────────────────────────────────┐
│  Kredit Kajian                          │
│  [████████████░░░░░░░░] 380 / 500       │
│  Reset: 1 Julai 2026                    │
│  [Topup +200 kredit — RM10]             │
└─────────────────────────────────────────┘

Tooltip ("?"):
  "Kredit Kajian habis bila AI perlu baca lebih banyak
   dokumen untuk jawab soalan awak. Ini pastikan kualiti
   jawapan kekal tinggi untuk semua pengguna."
```

### Internal Token Tracking (Backend, hidden)

```python
response = deepseek.chat(messages, temperature=0.1)
tokens_used = response.usage.total_tokens
db.log_token_usage(user_id, tokens_used, task_type)
db.deduct_kredit(user_id, kredit_cost[task_type])

if user.kredit_remaining <= 0:
    return {"error": "Kredit Kajian habis.", "action": "topup_atau_reset"}
```

### Admin Dashboard (Bos sahaja)

```
Total token used bulan ini: 4,250,000
Estimated cost: ~RM2.30
Per paying user avg: ~RM0.046
Cache hit rate: 62%
```

### Documentation Page — "Apa itu Kredit Kajian?"

Dedicated page (bukan popup) yang explain konsep, jadual kadar, cara topup, dan FAQ.

---

## 8. Auth Flow — Password-on-Demand

```
1. User masukkan email
2. Backend generate password rawak 8 char (alphanumeric)
3. Hantar via Resend SMTP (3,000 email/bulan free)
4. User login email + password
5. JWT session — expires 30 hari
6. "Lupa password?" → generate & hantar semula

Nota: Ini bukan "magic link" — password sementara on-demand.
```

---

## 9. Anti-Abuse (Multi-Account Prevention)

| Fasa | Lapisan | Berkesan Terhadap |
|---|---|---|
| 1 (Launch) | Email verification + sekat disposable domain | Abuser malas |
| 1 (Launch) | Email pattern detection | Multi-email mudah |
| 2 (Bulan 2–3) | Device fingerprint (fingerprintjs) | Multi-account device sama |
| 3 (Bila ada abuse) | IP tracking + behavioral flag | Abuser tegar |

**Prinsip:** Jangan over-engineer awal.

---

## 10. SQLite Schema

```sql
PRAGMA journal_mode=WAL;   -- WAJIB untuk concurrent access

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  tier TEXT DEFAULT 'free',
  kredit_remaining INTEGER DEFAULT 50,
  kredit_total INTEGER DEFAULT 50,
  tokens_used_internal INTEGER DEFAULT 0,
  reset_date TEXT,
  fingerprint TEXT,
  created_at TEXT
);

CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  title TEXT,
  research_mode TEXT DEFAULT 'general',
  field TEXT,
  document_set_version INTEGER DEFAULT 1,
  created_at TEXT
);

CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  filename TEXT,
  category TEXT,            -- 'artikel'|'catatan_sv'|'draf'|'data'
  page_count INTEGER,
  chunk_count INTEGER,
  is_ocr INTEGER DEFAULT 0,
  uploaded_at TEXT
);

CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  doc_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
  page_number INTEGER,
  chunk_index INTEGER,
  text TEXT,
  created_at TEXT
);

-- NOTA (§6C): chunk_vectors ialah virtual table (vec0) — TIDAK
-- support FK constraint/cascade. Kena delete manual dalam application
-- code (lihat delete_user_account() di §6C) sebelum delete chunks induk.
CREATE VIRTUAL TABLE chunk_vectors USING vec0(
  chunk_id TEXT,
  embedding FLOAT[384]
);

CREATE TABLE chapters (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT,
  chapter_order INTEGER,
  status TEXT DEFAULT 'draft',   -- 'draft'|'dalam_proses'|'siap'
  created_at TEXT
);

CREATE TABLE chapter_content (
  id TEXT PRIMARY KEY,
  chapter_id TEXT REFERENCES chapters(id) ON DELETE CASCADE,
  content TEXT,                  -- working content (markdown)
  summary TEXT,                  -- chapter_summary untuk hierarchical context
  source_citations TEXT,         -- JSON: citation list untuk export
  updated_at TEXT
);

CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  role TEXT,
  content TEXT,
  output_mode TEXT,
  source_chunks TEXT,
  kredit_used INTEGER,
  tokens_used_internal INTEGER,
  created_at TEXT
);

CREATE TABLE query_cache (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  query_normalized TEXT,
  query_embedding BLOB,
  document_set_version INTEGER,
  response TEXT,
  source_chunks TEXT,
  created_at TEXT
);

-- NOTA (§6C): TIDAK cascade delete. Rekod kewangan kekal untuk audit/
-- cukai — user_id di-anonymize ('deleted_user') semasa padam akaun,
-- bukan dipadam. Sengaja TIADA ON DELETE CASCADE di sini.
CREATE TABLE billing_events (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id),
  event_type TEXT,
  amount REAL,
  kredit_added INTEGER,
  created_at TEXT
);

CREATE TABLE user_interactions (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  event_type TEXT,
  research_mode TEXT,
  output_mode TEXT,
  response_rating INTEGER,
  query_length INTEGER,
  kredit_used INTEGER,
  session_id TEXT,
  created_at TEXT
);

CREATE TABLE app_learnings (
  id TEXT PRIMARY KEY,
  pattern TEXT,
  confidence REAL,
  action_suggested TEXT,
  created_at TEXT
);

-- Tambahan §6C — Lean Report Issue (Helpdesk Fasa 1)
CREATE TABLE support_reports (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  category TEXT,             -- 'bug'|'billing'|'kredit'|'lain-lain'
  description TEXT,
  project_id TEXT,
  status TEXT DEFAULT 'open',  -- 'open'|'resolved'
  created_at TEXT
);
```

**Wajib aktifkan setiap koneksi:** `PRAGMA foreign_keys = ON;` — tanpa ni, semua `ON DELETE CASCADE` di atas tidak akan jalan (SQLite default OFF). Rujuk §6C untuk flow padam akaun penuh.

---

## 11. App Intelligence Layer (Learning Curve)

Setiap interaksi dilog untuk improve produk berdasarkan data sebenar.

| Event | Insight |
|---|---|
| Output mode paling kerap | Feature mana di-prioritize |
| Research mode popular | Jurusan mana perlu improvement |
| Drop-off (upload tapi tak query) | Friction onboarding |
| Rating rendah pada mode | RAG/prompt perlu tune |
| Kredit habis hari ke-berapa | Free tier cukup atau terlalu rendah |

### Weekly Summary (Auto, untuk Bos)

```
Minggu 18–24 Jun:
  Mode paling popular: Literature Review (34%)
  Avg rating: 3.8/5
  Drop-off: 22% upload PDF tapi tak hantar soalan pertama
  → Cadangan: Tambah onboarding nudge selepas upload
```

---

## 12. LLM Abstraction Layer (Contingency)

```python
llm_client = LLMProvider(config.LLM_PROVIDER)
# "deepseek-v4-flash" | "deepseek-v4-pro" | "gemini-flash" | "openai"
```

| Risiko | Mitigasi |
|---|---|
| DeepSeek naik harga/tutup | Swap ke Gemini Flash |
| V4 Pro concurrency limit (500) | Flash default (2,500) |
| Viral cost spike | Hard cap free tier → waitlist |
| Exchange rate USD/MYR | Review harga 6 bulan |
| `deepseek-chat`/`deepseek-reasoner` deprecate 24 Jul 2026 | Explicit model ID dari awal |

---

## 13. VPS Resource Plan

VPS: **Cloud VPS 10 — 8GB RAM, 4 vCPU, 75GB NVMe** (shared dengan 1page.my).

| Service | RAM Estimate |
|---|---|
| OS + Nginx | ~450MB |
| 1page.my (existing) | ~200–400MB |
| FastAPI + React static | ~350MB |
| SQLite + sqlite-vec | ~150MB |
| Embedding model + worker pool | ~250MB |
| pytesseract (on-demand) | ~100MB |
| Export queue (.docx, on-demand) | ~100–200MB |
| LLM proxy (concurrent) | ~200–400MB |
| **Total** | **~2.0–2.3GB / 8GB** |

**Upgrade trigger:** RAM > 6GB konsisten, response > 3s peak, ATAU paying users > 100.

---

## 14. MVP Build Sequence + KPI Exit Gate

**Prinsip:** Plan struktur penuh awal, build & debug per-fasa. Setiap fasa ada KPI exit gate — tak proceed sebelum lulus.

### FASA 1A — RAG Core (3–4 minggu)
```
├── Auth (password-on-demand, Resend)
├── Project + PDF upload (PDF.js + OCR flag)
├── RAG pipeline (chunk + embed + sqlite-vec + MMR + adaptive K)
├── Embedding worker pool (§5E)
├── Q&A + citation + "Lihat Sumber"
├── Kredit counter + free tier limit
├── Profile menu + Reset Password + Padam Akaun (§6C)
└── Lean Report Issue → Telegram (§6C)
```

| KPI | Target | Cara Ukur |
|---|---|---|
| Retrieval relevance | ≥80% chunk relevan | Manual review 20 soalan |
| Citation accuracy | 100% traceable, zero fabrication | Verify via "Lihat Sumber" |
| Response time | <5s (Flash, non-deep) | Log latency |
| Hallucination rate | 0% fakta luar dokumen | Soalan "trap" |
| Cascade delete integrity | 100% — zero orphan rows selepas padam akaun | Test: padam test user, query semua table |
| billing_events anonymize | 100% — user_id jadi 'deleted_user', amount/date kekal | Test: padam user dengan rekod billing, verify |
| Report issue delivery | 100% — Telegram notification diterima <5s | Test: hantar 5 report, log latency |

**→ LOAD TEST di sini (§14A) sebelum proceed ke 1B.**

### FASA 1B — Consistency Layer (1 minggu)
```
├── Temperature lock (0.1)
├── Query cache (versioned) + invalidation
└── Retrieval tie-breaking deterministic
```

| KPI | Target | Cara Ukur |
|---|---|---|
| Exact-match consistency | 100% sama | 10 soalan × ulang 3x |
| Cache hit rate | ≥40% | Log hit vs miss |
| Fact consistency (paraphrase) | ≥90% fakta sama | 10 paraphrase pairs |
| Cache invalidation | 100% — upload baru clear cache | Test upload mid-session |

### FASA 1C — Output Modes + Hierarchical Context (2 minggu)
```
├── Lit Review, Exec Summary, Key Findings
├── Chapter summarization (§5C)
└── Output → assign ke chapter_content
```

| KPI | Target | Cara Ukur |
|---|---|---|
| Output koheren (Lit Review) | Tiada kontradiksi | Manual review 5 sample |
| Chapter summary accuracy | Tiada fakta hilang/reka | Banding summary vs bab |
| Kredit deduction | 100% ikut kadar | Audit log per mode |

### FASA 2 — Kredit Kajian + Monetization (2 minggu)
```
├── BillPlz, topup, kredit display (visual tank)
├── Documentation page "Kredit Kajian"
└── OCR fallback aktif (Pro tier)
```

| KPI | Target | Cara Ukur |
|---|---|---|
| Kredit deduct accuracy | 100%, zero discrepancy | Automated test 10 transaksi |
| BillPlz webhook | 100% → kredit <30s | 5 transaksi sebenar (kecil) |
| Topup flow | Zero error end-to-end | Manual test |

### FASA 3 — Thesis Workspace (4–5 minggu)
```
├── 3-panel layout (responsive)
├── Source panel berkategori
├── Chapter entity + status + onboarding (standard/custom)
├── Export .docx per-chapter (async queue)
├── Research Gap (output mode ke-5)
└── Free tier "visible locked"
```

| KPI | Target | Cara Ukur |
|---|---|---|
| End-to-end flow | Upload → chat → assign → export tanpa error | Full walkthrough |
| Export integrity | .docx tak corrupt, format kekal, citation included | Buka di Word + GDocs + LibreOffice |
| Onboarding completion | Faham pilih template <2 minit | Time signup → first chapter |
| Free tier lock | 100% interaksi Pro betul-betul locked | Test sebagai free user |

---

## 14A. Load Testing Protocol (50 Concurrent Users)

Dijalankan **selepas Fasa 1A**, sebelum 1B. Elak bina di atas foundation lemah.

### Bottleneck Yang Diuji

```
1. DeepSeek API concurrency — 50 << 2,500 limit ✅ (selamat)
2. Embedding (CPU) — worker pool (§5E) handle queue
3. SQLite concurrent write — WAL mode WAJIB enable
4. RAM peak — 50 user × embedding serentak
```

### Setup Test

```
Tool: locust.io atau k6

Simulate 50 concurrent user, mixed bidang:
  10 user × Undang-undang
  10 user × Kuantitatif
  10 user × Kualitatif
  10 user × Perubatan
  10 user × Umum

Verify: tiada cross-contamination (context bocor antara project).
```

### KPI Load Test

| KPI | Target |
|---|---|
| Response time @ 50 concurrent | <8s (naik dari 5s baseline, tapi tak lebih) |
| Error rate (DB locked, timeout) | <1% |
| RAM usage peak | <6GB (threshold upgrade) |
| Cross-project data leak | 0% — project A context TAK muncul dalam project B |
| Concurrent write success | 100% — kredit tak gagal/double-deduct |
| Embedding queue latency | <2s worst case |

### Mitigasi Wajib Sebelum Load Test

```
├── PRAGMA journal_mode=WAL;
├── Connection pooling (FastAPI)
├── Async write queue untuk non-critical (user_interactions)
└── Embedding worker pool (3 worker, batch 8)
```

---

## 15. Differentiation vs ChatGPT

| # | Pembeza | Positioning |
|---|---|---|
| 1 | Ingat konteks projek | "ChatGPT lupa awak setiap kali. ResearcherHQ ingat projek awak." |
| 2 | Grounded, tiada hallucination | "ChatGPT boleh reka fakta. ResearcherHQ hanya jawab dari dokumen awak." |
| 3 | Consistency | "Soalan sama, jawapan sama. ChatGPT berubah-ubah." |
| 4 | Workspace tesis | "Bukan chat — meja kerja tesis lengkap dengan sumber & struktur bab." |
| 5 | Privacy dokumen | "Dokumen sensitif awak tak sepatutnya kat server orang lain." |
| 6 | Export siap guna | "Export bab terus ke .docx untuk bawa jumpa SV." |
| 7 | Verify citation | "Setiap citation ada butang 'Lihat Sumber'." |

### Kelemahan (Acknowledge Jujur)
- Web only (tiada mobile app)
- Brand ChatGPT lebih kuat — trust barrier
- User kena upload dokumen sendiri — friction
- Tiada internet search (dokumen sahaja)

**Strategi:** Own the niche — *workspace tesis berasaskan dokumen untuk postgrad Malaysia.*

---

## 16. Prinsip Anti-Gharar (Compliance)

- Tiada testimoni rekaan
- Tiada false urgency / FOMO
- Tiada claim tak berasas ("100% accurate", "gantikan supervisor")
- **Consistency dinyatakan jujur:** 100% untuk exact match, fakta konsisten untuk paraphrase — BUKAN janji "selalu sama perkataan demi perkataan"
- Watermark free tier = jujur
- Free tier "visible locked" = telus, user nampak apa Pro tawarkan
- Cache invalidation = user tak dapat jawapan outdated
- AI output grounded — tidak menipu dengan fakta rekaan

---

## 17. Isu Tertangguh (Pending)

| Isu | Status |
|---|---|
| Domain rasmi | **researcherhq.com — dah dibeli ✅** |
| Test kualiti V4 Flash output akademik BM/BI | Pending — guna 5M token percuma |
| Format chapter standard universiti (UKM/UM/USM) | Perlu sahkan baseline sebenar |
| Landing page + demo video 60s | Belum mula |
| Citation export format testing (APA/Chicago) | Selepas Fasa 1C |
| Nama unit "Kredit Kajian" | Locked ✅ |

---

*Tamat PRD v1.5 — 19 Jun 2026*
