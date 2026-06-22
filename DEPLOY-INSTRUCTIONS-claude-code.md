# DEPLOY STANDARD — Arahan untuk Claude Code

**Status:** WAJIB ikut. Tujuan: hentikan masalah login berulang setiap deploy.

---

## Punca Masalah Login (Didiagnose 22 Jun 2026)

Bukan Nginx. Bukan auth logic. **Frontend di-build tanpa `.env.production`**, jadi `baseURL` jatuh ke fallback `http://localhost:8000`. Akibatnya browser user cuba sambung ke komputer user sendiri (localhost), bukan VPS — login 404 / "emel tak sah" dalam incognito.

Bukti: bundle yang ter-deploy (`/var/www/researcherhq/app/assets/index-*.js`) mengandungi:
```
baseURL:`http://localhost:8000`
/auth/login`
```

Setiap kali deploy tanpa `.env.production` betul → masalah sama berulang.

---

## TIGA Perkara Yang Claude Code WAJIB Setup (sekali sahaja)

### 1. Patch fallback dalam `frontend/src/api/client.js`

Tukar fallback supaya kalau `.env` tak load, ia guna `/api` (relative — selamat untuk dev proxy DAN prod nginx), BUKAN `localhost:8000` yang langkau routing.

**Cari:**
```javascript
baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
```

**Ganti dengan:**
```javascript
baseURL: import.meta.env.VITE_API_URL || '/api',
```

Sebab: `/api` relatif. Dalam dev, Vite proxy (`/api` → localhost:8000, rewrite buang `/api`) tangkap. Dalam prod, Nginx (`location /api/` → backend) tangkap. Tiada lagi hardcoded localhost yang boleh bocor ke production build.

### 2. Commit `deploy.sh` + `researcherhq.service` ke repo

Letak di:
```
deploy/deploy.sh                      (dari fail deploy.sh)
deploy/systemd/researcherhq.service   (dari fail researcherhq.service)
```
Commit ke repo. Ini jadi sumber kebenaran tunggal untuk deploy.

### 3. Pasang systemd service di VPS (sekali sahaja)

```bash
sudo cp /root/researcherhq/deploy/systemd/researcherhq.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable researcherhq    # auto-start bila reboot
sudo systemctl start researcherhq
sudo systemctl status researcherhq    # sahkan aktif
```

Selepas ni, backend auto-restart bila crash atau VPS reboot.

---

## Sebelum Run deploy.sh — Edit Dua Nilai

Dalam `deploy.sh`, betulkan:

1. `PROD_TURNSTILE_SITE_KEY` — gantikan placeholder dengan Turnstile **site key produksi sebenar** (bukan test key `1x00000...`).
2. `PROD_ADMIN_EMAIL` — sahkan betul.

Dan pastikan `backend/.env` di VPS ada baris:
```
FRONTEND_URL=https://researcherhq.com
```
(WAJIB — ini untuk CORS. Kalau localhost, semua API call dari browser user kena block CORS.)

---

## Cara Deploy Setiap Kali (selepas setup di atas)

Di VPS:
```bash
cd /root/researcherhq
sudo bash deploy/deploy.sh
```

Script akan:
1. Pull kod terkini (reset hard ke origin/main)
2. Install backend deps
3. **Jalankan pytest — kalau gagal, deploy DIBATALKAN**
4. Tulis `.env.production` dengan nilai prod betul
5. Build frontend
6. **Verify build TIADA `localhost:8000` — kalau ada, deploy DIBATALKAN**
7. rsync dist/ ke `/var/www/researcherhq/app/`
8. Restart backend (systemd)
9. Reload nginx
10. **Verify end-to-end**: backend health 200, API via nginx bukan 404, SPA 200

Kalau mana-mana langkah gagal, script berhenti dengan mesej jelas — bukan deploy separuh jalan yang senyap.

---

## Peraturan Untuk Claude Code

1. **JANGAN deploy manual.** Guna `deploy.sh` sahaja. Build manual tanpa `.env.production` = punca masalah asal.
2. **JANGAN edit nginx config** untuk "betulkan" login. Nginx tak pernah jadi masalah. Kalau login pecah, 99% ia build/env, bukan nginx.
3. **JANGAN tukar baseURL fallback** kembali ke `localhost:8000`.
4. **Selepas setiap deploy**, sahkan output verifikasi langkah 10 semua PASS sebelum lapor "deploy selesai".
5. Kalau login masih gagal SELEPAS semua verify PASS — barulah siasat DB:
   ```bash
   sqlite3 <db_path> "SELECT email, tier, length(password_hash), password_is_permanent FROM users;"
   ```
   Itu masalah data, bukan deploy.

---

## Checklist Verifikasi Manual (Bos buat selepas deploy)

- [ ] Buka `https://researcherhq.com/app/` dalam incognito
- [ ] Login account Pro → berjaya, tier tunjuk "Pro"
- [ ] Login account Free → berjaya, tier tunjuk "Free"
- [ ] Network tab: request pergi ke `researcherhq.com/api/...` (BUKAN localhost)
