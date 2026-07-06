# ResearcherHQ — Pindaan PRD §6R (v1.9.1)

**Tarikh:** 7 Julai 2026
**Status:** Merekod keputusan sebenar selepas 36A & 36B shipped. Menggantikan bahagian bertanda dalam v1.9 §6R.
**Rujukan asas:** PRD v1.9 addendum §6R. Dokumen ini pindaan, bukan ganti penuh.

---

## 1. §6R.E (Kadar Kredit) — DIGANTIKAN

Jadual kredit v1.9 batal. Keputusan sebenar:

| Item | Keputusan |
|---|---|
| Akses modul (Bina + Kumpul + Analisis) | **Pro sahaja** — Free nampak rail icon + locked page dengan CTA upgrade (teaser pattern) |
| Jana instrumen AI (penuh) | 10 Kredit Kajian |
| Jana semula / tambah section (AI) | 3 Kredit Kajian |
| Edit manual, export, publish, kutipan respons | 0 kredit |
| Analisis statistik (descriptive/reliability/normality — 36C-1) | 0 kredit (kos compute sifar) |
| Interpretasi AI hasil analisis (36C-2) | Kadar ditentukan dalam brief 36C-2 (cadangan awal: 3 kredit/analisis) |

**Rasional gating:** monetization pada AI usage (kos sebenar) + tier gate pada modul; kutipan respons percuma menggalakkan data masuk → keperluan analisis → retention Pro.

**Status implementasi (36A/36B shipped):** Pro-gating aktif pada `create_survey` (403 untuk Free); kadar 10/3 kredit pada endpoint `generate`; publish + kutipan respons sifar kredit. Padan dengan jadual di atas.

## 2. §6R Fasa B — REKOD IMPLEMENTASI SEBENAR (36B shipped)

- **Dua mod publish:** `pilot` (cap max 50) dan `actual` (cap max 100 default, max 1,000)
- **State machine:** struktur soalan dikunci sepanjang kutipan aktif (409). Pilot yang ditutup boleh **unlock** semula ke draft walaupun ada respons (respons kekal, `is_pilot=1`); actual frozen kekal, unpublish hanya bila 0 respons
- **Tier limit:** Pro max 5 survey kutipan aktif serentak
- **Public form:** `/s/{token}`, mobile-first, chrome English, kandungan soalan ikut `output_language`, Turnstile wajib, footer "Powered by researcherHQ"
- **Privacy:** zero raw IP — `ip_hash` = SHA256(ip + APP_SALT). **APP_SALT wajib diset dalam .env prod** (default dev salt adalah public dalam repo → hash boleh brute-force)
- **Rate limiting:** dua lapis — Nginx `limit_req` (`deploy/nginx-researcherhq.conf`, apply manual sekali di VPS) + app-level `enforce_rate_limit`. **Tiada kebergantungan Cloudflare.** Susunan dalam submit: payload cap → rate limit → Turnstile → status/validation
- **Deploy nota:** `deploy.sh` tidak sentuh nginx; prosedur salin conf + reload didokumen dalam DEPLOY-INSTRUCTIONS

**Status prod (7 Julai 2026):** 36A + 36B deployed. APP_SALT prod diset (bukan default). Nginx `limit_req` diapply di VPS (`nginx -t` lulus, reloaded) — disahkan aktif (429 selepas burst).

## 3. §6R.C — PECAHAN FASA C (dikemaskini)

| Task | Skop | Status |
|---|---|---|
| **36C-1** Stats Foundation | pandas+scipy sahaja; dataset dari respons (pilot/actual); construct mapping + reverse-coding; descriptive, Cronbach's alpha, normality; APA table + docx export; step 3 enabled | **Brief ditulis** |
| **36C-2** Inferential + Intelligence | t-test/ANOVA/correlation/chi-square (+fallback non-parametrik); analysis wizard; interpretasi LLM (angka injected sahaja, guard anti-hallucination ikut spec §8); Send to Editor → Bab 4; CSV upload data luaran | Belum brief — selepas 36C-1 closed |

**Prinsip kekal:** satu task = satu cycle audit penuh. 36C-2 tidak dibrief sebelum 36C-1 closed.

## 4. Baseline test rasmi

246 (36 mobile) → 269 (36A) → 297 (36B + fix) → target ≥312 (36C-1)
