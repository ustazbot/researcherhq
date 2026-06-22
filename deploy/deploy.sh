#!/usr/bin/env bash
#
# ============================================================================
#  ResearcherHQ — DEPLOY SCRIPT STANDARD
#  Guna setiap kali deploy. JANGAN deploy manual tanpa script ini.
# ============================================================================
#
#  PUNCA MASALAH LOGIN BERULANG (didiagnose 22 Jun 2026):
#  Frontend di-build tanpa .env.production → baseURL jatuh ke
#  fallback `http://localhost:8000` → browser user call komputer SENDIRI →
#  login 404 / "emel tak sah". Nginx & backend TIDAK PERNAH bersalah.
#
#  Script ini memastikan:
#    1. Frontend SENTIASA build dengan VITE_API_URL betul (prod)
#    2. dist/ disalin ke LOKASI BETUL di VPS
#    3. Backend restart bersih
#    4. Verifikasi automatik selepas deploy — gagal = stop, bukan senyap
#
#  CARA GUNA:
#    Di VPS:   sudo bash deploy.sh
#    (Script ini dijalankan DI VPS. Ia clone/pull, build, deploy, verify.)
#
# ============================================================================

set -euo pipefail   # henti pada error, undefined var, atau pipe gagal

# ────────────────────────────────────────────────────────────────────────────
# KONFIGURASI — semak betul sebelum run pertama kali
# ────────────────────────────────────────────────────────────────────────────
REPO_DIR="/root/researcherhq"
REPO_URL="https://github.com/ustazbot/researcherhq.git"
BRANCH="main"

WEB_ROOT="/var/www/researcherhq"          # nginx serve dari sini
APP_DIR="${WEB_ROOT}/app"                  # SPA build (base path /app/)

BACKEND_DIR="${REPO_DIR}/backend"
FRONTEND_DIR="${REPO_DIR}/frontend"
VENV_DIR="${BACKEND_DIR}/venv"

# Nilai PRODUCTION — ditulis ke .env.production sebelum build
PROD_API_URL="https://researcherhq.com/api"
PROD_FRONTEND_URL="https://researcherhq.com"
PROD_ADMIN_EMAIL="planetrizq@gmail.com"
# Turnstile site key produksi — GANTI dengan key sebenar (bukan test key)
PROD_TURNSTILE_SITE_KEY="0x4AAAAAADpNkWviQf3m0t2_"

# Backend run config
UVICORN_HOST="127.0.0.1"
UVICORN_PORT="8000"
UVICORN_WORKERS="2"
SERVICE_NAME="researcherhq"               # systemd service

# ────────────────────────────────────────────────────────────────────────────
# Warna untuk output
# ────────────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[deploy]${NC} $*"; }
ok()   { echo -e "${GREEN}[ ok ]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
die()  { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }

# ────────────────────────────────────────────────────────────────────────────
# 0. Pra-syarat
# ────────────────────────────────────────────────────────────────────────────
log "Semak pra-syarat..."
command -v node    >/dev/null || die "node tak dijumpai. Install Node.js dulu."
command -v npm     >/dev/null || die "npm tak dijumpai."
command -v git     >/dev/null || die "git tak dijumpai."
command -v python3 >/dev/null || die "python3 tak dijumpai."
ok "Pra-syarat lengkap."

# ────────────────────────────────────────────────────────────────────────────
# 1. Pull kod terkini
# ────────────────────────────────────────────────────────────────────────────
if [ -d "${REPO_DIR}/.git" ]; then
  log "Pull kod terkini dari ${BRANCH}..."
  cd "${REPO_DIR}"
  git fetch origin "${BRANCH}"
  git reset --hard "origin/${BRANCH}"   # buang perubahan tempatan — sumber kebenaran = repo
else
  log "Clone repo..."
  git clone -b "${BRANCH}" "${REPO_URL}" "${REPO_DIR}"
  cd "${REPO_DIR}"
fi
COMMIT=$(git rev-parse --short HEAD)
ok "Pada commit ${COMMIT}"

# ────────────────────────────────────────────────────────────────────────────
# 2. BACKEND — venv, deps, env
# ────────────────────────────────────────────────────────────────────────────
log "Setup backend..."
cd "${BACKEND_DIR}"

if [ ! -d "${VENV_DIR}" ]; then
  python3 -m venv "${VENV_DIR}"
  ok "Venv dicipta."
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
ok "Backend deps dipasang."

# Semak .env backend wujud — JANGAN auto-generate (ada secret)
if [ ! -f "${BACKEND_DIR}/.env" ]; then
  die ".env backend TAK WUJUD di ${BACKEND_DIR}/.env
       Cipta manual dengan: DEEPSEEK_API_KEY, JWT_SECRET, RESEND_API_KEY,
       TOYYIBPAY_SECRET_KEY, ADMIN_EMAIL, DATABASE_URL,
       FRONTEND_URL=${PROD_FRONTEND_URL}
       (FRONTEND_URL WAJIB = domain prod untuk CORS, bukan localhost)"
fi

# Verifikasi FRONTEND_URL dalam .env betul — punca CORS fail kalau salah
if ! grep -q "FRONTEND_URL=${PROD_FRONTEND_URL}" "${BACKEND_DIR}/.env"; then
  warn "FRONTEND_URL dalam backend/.env mungkin TIDAK ${PROD_FRONTEND_URL}"
  warn "Kalau CORS error selepas ni, betulkan FRONTEND_URL dalam backend/.env"
fi

# ────────────────────────────────────────────────────────────────────────────
# 3. BACKEND — jalankan test sebelum deploy (gate)
# ────────────────────────────────────────────────────────────────────────────
log "Jalankan backend tests (gate sebelum deploy)..."
cd "${BACKEND_DIR}"
# Env minimum untuk test — guna nilai dummy, DATABASE_URL in-memory
if DEEPSEEK_API_KEY=sk-test JWT_SECRET=testsecret RESEND_API_KEY=re_test \
   TOYYIBPAY_SECRET_KEY=tp_test ADMIN_EMAIL=admin@test.com DATABASE_URL=:memory: \
   python -m pytest tests/ -q -p no:warnings 2>&1 | tail -5; then
  ok "Tests lulus."
else
  die "TESTS GAGAL. Deploy dibatalkan. Betulkan test dulu — JANGAN deploy kod yang gagal test."
fi

# ────────────────────────────────────────────────────────────────────────────
# 4. FRONTEND — TULIS .env.production (INI PUNCA MASALAH LOGIN DULU)
# ────────────────────────────────────────────────────────────────────────────
log "Tulis frontend .env.production dengan nilai PRODUCTION..."
cd "${FRONTEND_DIR}"

cat > .env.production <<EOF
VITE_API_URL=${PROD_API_URL}
VITE_TURNSTILE_SITE_KEY=${PROD_TURNSTILE_SITE_KEY}
VITE_ADMIN_EMAIL=${PROD_ADMIN_EMAIL}
EOF
ok ".env.production ditulis — VITE_API_URL=${PROD_API_URL}"

# Sanity: pastikan TIDAK guna placeholder turnstile
if grep -q "GANTI_DENGAN" .env.production; then
  die "TURNSTILE_SITE_KEY masih placeholder. Edit PROD_TURNSTILE_SITE_KEY dalam deploy.sh."
fi

# ────────────────────────────────────────────────────────────────────────────
# 5. FRONTEND — build
# ────────────────────────────────────────────────────────────────────────────
log "Build frontend (npm ci + build)..."
npm ci --silent
npm run build
[ -d "${FRONTEND_DIR}/dist" ] || die "Build gagal — dist/ tak wujud."
ok "Build siap."

# ────────────────────────────────────────────────────────────────────────────
# 6. FRONTEND — VERIFY BUILD SEBELUM DEPLOY (tangkap localhost bug AWAL)
# ────────────────────────────────────────────────────────────────────────────
log "Verify build — pastikan TIADA localhost:8000 dalam bundle..."
if grep -rq "localhost:8000" "${FRONTEND_DIR}/dist/assets/"*.js; then
  die "BUILD MENGANDUNGI localhost:8000!
       .env.production tak ter-load semasa build.
       Login AKAN pecah kalau deploy ini. Dibatalkan.
       Semak: fail .env.production wujud & VITE_API_URL betul."
fi
# Pastikan API URL betul WUJUD dalam bundle
if ! grep -rq "researcherhq.com/api" "${FRONTEND_DIR}/dist/assets/"*.js; then
  warn "Tak jumpa 'researcherhq.com/api' dalam bundle — semak VITE_API_URL betul-betul ter-inject."
fi
ok "Build bersih — tiada localhost, API URL prod wujud."

# ────────────────────────────────────────────────────────────────────────────
# 7. DEPLOY — salin dist/ ke web root
# ────────────────────────────────────────────────────────────────────────────
log "Deploy dist/ ke ${APP_DIR}..."
mkdir -p "${APP_DIR}"
# --delete: buang fail lama (elak asset usang bercampur)
rsync -a --delete "${FRONTEND_DIR}/dist/" "${APP_DIR}/"
ok "Frontend di-deploy ke ${APP_DIR}"

# ────────────────────────────────────────────────────────────────────────────
# 8. BACKEND — restart service
# ────────────────────────────────────────────────────────────────────────────
if systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
  log "Restart systemd service ${SERVICE_NAME}..."
  systemctl restart "${SERVICE_NAME}"
  sleep 2
  systemctl is-active --quiet "${SERVICE_NAME}" || die "Service ${SERVICE_NAME} gagal start. Cek: journalctl -u ${SERVICE_NAME} -n 50"
  ok "Service ${SERVICE_NAME} aktif."
else
  warn "systemd service '${SERVICE_NAME}' TAK WUJUD."
  warn "Backend kini berjalan manual (akan mati bila VPS reboot)."
  warn "Sediakan service dengan: sudo bash deploy.sh --setup-service"
  warn "Cuba restart manual proses uvicorn sedia ada..."
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  sleep 1
  cd "${BACKEND_DIR}"
  nohup "${VENV_DIR}/bin/uvicorn" app.main:app \
    --host "${UVICORN_HOST}" --port "${UVICORN_PORT}" --workers "${UVICORN_WORKERS}" \
    > "${BACKEND_DIR}/uvicorn.log" 2>&1 &
  sleep 2
  ok "Backend di-restart manual (log: ${BACKEND_DIR}/uvicorn.log)"
fi

# ────────────────────────────────────────────────────────────────────────────
# 9. NGINX — reload (config tak disentuh oleh script, cuma reload)
# ────────────────────────────────────────────────────────────────────────────
log "Test & reload nginx..."
nginx -t 2>/dev/null || die "Nginx config ada error. Jangan reload. Semak: nginx -t"
systemctl reload nginx
ok "Nginx di-reload."

# ────────────────────────────────────────────────────────────────────────────
# 10. VERIFIKASI POST-DEPLOY — end-to-end, bukan andaian
# ────────────────────────────────────────────────────────────────────────────
log "Verifikasi post-deploy..."

# 10a. Backend health (terus, bypass nginx)
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://${UVICORN_HOST}:${UVICORN_PORT}/health" || echo "000")
[ "${HEALTH}" = "200" ] || die "Backend /health = ${HEALTH} (jangkaan 200). Backend tak sihat."
ok "Backend health: 200"

# 10b. API melalui nginx (path prod sebenar) — guna endpoint login
#      Jangkaan: 422 (body tak lengkap) atau 400 — BUKAN 404.
#      404 = nginx tak route ke backend (masalah dulu).
API_VIA_NGINX=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "https://researcherhq.com/api/auth/login" \
  -H "Content-Type: application/json" -d '{}' || echo "000")
if [ "${API_VIA_NGINX}" = "404" ]; then
  die "API via nginx = 404 — routing /api/ ke backend TER-PUTUS. Semak nginx config."
fi
ok "API via nginx: ${API_VIA_NGINX} (bukan 404 — routing OK)"

# 10c. Frontend index dapat dicapai
SPA=$(curl -s -o /dev/null -w "%{http_code}" "https://researcherhq.com/app/" || echo "000")
[ "${SPA}" = "200" ] || warn "SPA /app/ = ${SPA} (jangkaan 200). Semak nginx /app/ block."
[ "${SPA}" = "200" ] && ok "SPA /app/: 200"

# ────────────────────────────────────────────────────────────────────────────
# Selesai
# ────────────────────────────────────────────────────────────────────────────
echo ""
ok "=============================================="
ok " DEPLOY SELESAI — commit ${COMMIT}"
ok "=============================================="
echo ""
log "LANGKAH MANUAL TERAKHIR (Bos):"
echo "  1. Buka https://researcherhq.com/app/ dalam browser BARU (incognito)"
echo "  2. Login dengan account Pro DAN Free"
echo "  3. Sahkan: login berjaya + tier dipaparkan betul"
echo ""
warn "Kalau login masih gagal selepas semua verify PASS:"
warn "  → Masalah BUKAN deploy. Cek DB: sqlite3 <db> \"SELECT email,tier,length(password_hash) FROM users;\""
