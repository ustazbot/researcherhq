#!/usr/bin/env bash
# Task 14A Load Test Runner
# Usage: bash load_tests/run_load_test.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
LOAD_TESTS_DIR="$REPO_ROOT/load_tests"
REPORT_DIR="$LOAD_TESTS_DIR/reports"
DB_PATH="/tmp/rhq_loadtest.db"
PORT=18999  # avoid clashing with prod port 8000
BASE_URL="http://localhost:$PORT"

# KPI thresholds
MAX_P95_MS=5000
MAX_ERR_RATE=1  # percent

echo "=== Task 14A Load Test ==="
echo "DB: $DB_PATH | Port: $PORT"

# Cleanup previous run
rm -f "$DB_PATH"
mkdir -p "$REPORT_DIR"

# Start backend with mock mode
echo "[1/5] Starting backend (mock mode)..."
cd "$BACKEND_DIR"
DATABASE_URL="$DB_PATH" \
LLM_PROVIDER=mock \
LOAD_TEST_MODE=1 \
JWT_SECRET=loadtest-secret-key-not-for-prod \
  python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --workers 1 \
  > /tmp/rhq_loadtest_server.log 2>&1 &
SERVER_PID=$!
echo "  Server PID: $SERVER_PID"

# Wait for backend to be ready (up to 30s)
echo "[2/5] Waiting for backend..."
for i in $(seq 1 30); do
  if curl -sf "$BASE_URL/health" > /dev/null 2>&1; then
    echo "  Ready after ${i}s"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "ERROR: Backend did not start in 30s"
    cat /tmp/rhq_loadtest_server.log
    kill "$SERVER_PID" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

# Seed test data
echo "[3/5] Seeding test data..."
cd "$REPO_ROOT"
DATABASE_URL="$DB_PATH" python "$LOAD_TESTS_DIR/seed_data.py"

# Run Locust headless
REPORT_FILE="$REPORT_DIR/report_$(date +%Y%m%d_%H%M%S).html"
STATS_CSV="/tmp/rhq_locust_stats.csv"
echo "[4/5] Running Locust (50 users, 2 min)..."
locust \
  -f "$LOAD_TESTS_DIR/locustfile.py" \
  --headless \
  --host "$BASE_URL" \
  -u 50 -r 5 -t 2m \
  --html "$REPORT_FILE" \
  --csv /tmp/rhq_locust \
  2>&1 | tee /tmp/rhq_locust_output.log

# Kill backend
echo "[5/5] Stopping backend..."
kill "$SERVER_PID" 2>/dev/null || true

# Parse results and PASS/FAIL
echo ""
echo "=== RESULTS ==="

# Check CSV for stats — locust writes _stats.csv
STATS_FILE="/tmp/rhq_locust_stats.csv"
if [ ! -f "$STATS_FILE" ]; then
  echo "FAIL: No stats CSV found — locust may have crashed"
  exit 1
fi

# Extract P95 and failure rate for RAG endpoint
RAG_P95=$(awk -F',' 'NR>1 && /projects.*query/ {print $14}' "$STATS_FILE" | head -1)
TOTAL_FAILURES=$(awk -F',' 'NR>1 {fail+=$7} END {print fail+0}' "$STATS_FILE")
TOTAL_REQUESTS=$(awk -F',' 'NR>1 {req+=$3} END {print req+0}' "$STATS_FILE")

# Check for database locked error in server log
DB_LOCK_ERRORS=$(grep -c "database is locked" /tmp/rhq_loadtest_server.log 2>/dev/null || echo 0)

echo "RAG P95 (ms):       ${RAG_P95:-N/A}"
echo "Total requests:     $TOTAL_REQUESTS"
echo "Total failures:     $TOTAL_FAILURES"
echo "DB locked errors:   $DB_LOCK_ERRORS"
echo "HTML report:        $REPORT_FILE"

PASS=true

if [ -n "$RAG_P95" ] && [ "$(echo "$RAG_P95 > $MAX_P95_MS" | bc -l 2>/dev/null || echo 0)" = "1" ]; then
  echo "FAIL: RAG P95 ${RAG_P95}ms >= ${MAX_P95_MS}ms threshold"
  PASS=false
fi

if [ "$TOTAL_REQUESTS" -gt 0 ]; then
  ERR_RATE=$(echo "scale=2; $TOTAL_FAILURES * 100 / $TOTAL_REQUESTS" | bc -l)
  if [ "$(echo "$ERR_RATE >= $MAX_ERR_RATE" | bc -l)" = "1" ]; then
    echo "FAIL: Error rate ${ERR_RATE}% >= ${MAX_ERR_RATE}% threshold"
    PASS=false
  fi
fi

if [ "$DB_LOCK_ERRORS" -gt 0 ]; then
  echo "FAIL: $DB_LOCK_ERRORS 'database is locked' errors found"
  PASS=false
fi

if [ "$PASS" = true ]; then
  echo ""
  echo "✓ PASS — all KPIs met"
  exit 0
else
  echo ""
  echo "✗ FAIL — see above"
  exit 1
fi
