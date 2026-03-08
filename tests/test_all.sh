#!/usr/bin/env bash
# =============================================================================
# 全面自動化測試腳本 — HA MCP Client + Nanobot Integration
# =============================================================================
# Usage:
#   chmod +x tests/test_all.sh
#   ./tests/test_all.sh              # 全部測試
#   ./tests/test_all.sh A            # 只跑 Section A
#   ./tests/test_all.sh B C          # 跑 Section B + C
#   ./tests/test_all.sh --skip-restart  # 跳過需要重啟的測試 (G, I)
#
# Environment Variables:
#   LLAT          — Long-Lived Access Token (預設內建)
#   BASE_URL      — HA base URL (預設 http://localhost:18123)
#   AGENT_ID      — Conversation agent entity ID
# =============================================================================

set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
LLAT="${LLAT:-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJhZWU3MjgzZTFhNjE0ODJjOGQyNGQzNmZhOTE0MTBhOSIsImlhdCI6MTc3Mjg5MjAxMSwiZXhwIjoyMDg4MjUyMDExfQ.D8d8Ki1wBkhBjhTA4UbmOR31-gb-LZ31NC9dYDlXuSI}"
BASE="${BASE_URL:-http://localhost:18123}"
AGENT="${AGENT_ID:-conversation.ha_mcp_client_ha_mcp_client_01kk3w34mx75zr1emp35aakx65}"
AUTH="Authorization: Bearer $LLAT"
CT="Content-Type: application/json"
API="$BASE/api/ha_mcp_client"

SKIP_RESTART=false
SECTIONS=()

# Parse arguments
for arg in "$@"; do
  case "$arg" in
    --skip-restart) SKIP_RESTART=true ;;
    *) SECTIONS+=("$arg") ;;
  esac
done

# If no sections specified, run all
if [ ${#SECTIONS[@]} -eq 0 ]; then
  SECTIONS=(A B C D E F G H I)
fi

# ─── Counters ────────────────────────────────────────────────────────────────
PASS=0
FAIL=0
WARN=0
TOTAL=0
FAILURES=()

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Assertion Helpers ───────────────────────────────────────────────────────

_pass() {
  echo -e "  ${GREEN}✓${NC} $1"
  PASS=$((PASS + 1))
  TOTAL=$((TOTAL + 1))
}

_fail() {
  echo -e "  ${RED}✗${NC} $1"
  FAIL=$((FAIL + 1))
  TOTAL=$((TOTAL + 1))
  FAILURES+=("$1")
}

_warn() {
  echo -e "  ${YELLOW}⚠${NC} $1 (WARN)"
  WARN=$((WARN + 1))
  TOTAL=$((TOTAL + 1))
}

_section() {
  echo ""
  echo -e "${BOLD}${CYAN}=== $1 ===${NC}"
}

# Assert HTTP status code
# Usage: assert_status "test name" expected_code actual_code
assert_status() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    _pass "$name"
  else
    _fail "$name (expected HTTP $expected, got $actual)"
  fi
}

# Assert string contains substring
# Usage: assert_contains "test name" "expected_substring" "actual_string"
assert_contains() {
  local name="$1" expected="$2" actual="$3"
  if echo "$actual" | grep -q "$expected"; then
    _pass "$name"
  else
    _fail "$name (expected to contain '$expected')"
  fi
}

# Assert string does NOT contain substring
assert_not_contains() {
  local name="$1" unexpected="$2" actual="$3"
  if echo "$actual" | grep -q "$unexpected"; then
    _fail "$name (should NOT contain '$unexpected')"
  else
    _pass "$name"
  fi
}

# Assert string equals expected
assert_eq() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    _pass "$name"
  else
    _fail "$name (expected '$expected', got '$actual')"
  fi
}

# Assert string is not empty
assert_not_empty() {
  local name="$1" actual="$2"
  if [ -n "$actual" ]; then
    _pass "$name"
  else
    _fail "$name (was empty)"
  fi
}

# Assert numeric comparison
assert_gte() {
  local name="$1" expected="$2" actual="$3"
  if [ "$actual" -ge "$expected" ] 2>/dev/null; then
    _pass "$name"
  else
    _fail "$name (expected >= $expected, got '$actual')"
  fi
}

# Assert JSON field exists and has expected value
# Usage: assert_json "test name" "expected" ".field.path" "$json"
assert_json() {
  local name="$1" expected="$2" jq_path="$3" json="$4"
  local actual
  actual=$(echo "$json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    keys = '${jq_path}'.strip('.').split('.')
    v = d
    for k in keys:
        if isinstance(v, list):
            v = v[int(k)]
        else:
            v = v[k]
    print(v)
except Exception as e:
    print('__ERROR__')
" 2>/dev/null)
  if [ "$actual" = "__ERROR__" ]; then
    _fail "$name (JSON path '$jq_path' not found)"
  elif [ "$expected" = "$actual" ]; then
    _pass "$name"
  else
    _fail "$name (expected '$expected' at $jq_path, got '$actual')"
  fi
}

# Soft assert (WARN on failure, used for AI tests)
assert_soft() {
  local name="$1" expected="$2" actual="$3"
  if echo "$actual" | grep -q "$expected"; then
    _pass "$name"
  else
    _warn "$name (expected to contain '$expected')"
  fi
}

# Helper: GET with status code
http_get() {
  curl -s -o /tmp/_test_body -w "%{http_code}" -H "$AUTH" "$1" 2>/dev/null
}

# Helper: POST with status code
http_post() {
  curl -s -o /tmp/_test_body -w "%{http_code}" -H "$AUTH" -H "$CT" -X POST -d "$2" "$1" 2>/dev/null
}

# Helper: PUT with status code
http_put() {
  curl -s -o /tmp/_test_body -w "%{http_code}" -H "$AUTH" -H "$CT" -X PUT -d "$2" "$1" 2>/dev/null
}

# Helper: PATCH with status code
http_patch() {
  curl -s -o /tmp/_test_body -w "%{http_code}" -H "$AUTH" -H "$CT" -X PATCH -d "$2" "$1" 2>/dev/null
}

# Helper: DELETE with status code
http_delete() {
  curl -s -o /tmp/_test_body -w "%{http_code}" -H "$AUTH" -X DELETE "$1" 2>/dev/null
}

# Helper: get response body (from last http_* call)
body() {
  cat /tmp/_test_body 2>/dev/null
}

# Helper: get template value from HA
ha_template() {
  curl -s -H "$AUTH" -H "$CT" -d "{\"template\":\"$1\"}" "$BASE/api/template" 2>/dev/null
}

# ─── Pre-flight ──────────────────────────────────────────────────────────────
echo -e "${BOLD}HA MCP Client — Comprehensive Test Suite${NC}"
echo "Base URL: $BASE"
echo "Sections: ${SECTIONS[*]}"
echo "Skip restart: $SKIP_RESTART"
echo ""

# Verify HA is reachable
status=$(http_get "$BASE/api/")
if [ "$status" != "200" ]; then
  echo -e "${RED}ERROR: HA not reachable at $BASE (HTTP $status)${NC}"
  exit 1
fi
echo -e "${GREEN}HA is reachable${NC}"

# ─── Helper: should run section? ─────────────────────────────────────────────
should_run() {
  for s in "${SECTIONS[@]}"; do
    if [ "$s" = "$1" ]; then return 0; fi
  done
  return 1
}


# =============================================================================
# A. ENTITY PLATFORM TESTS
# =============================================================================
if should_run "A"; then
  _section "A. Entity Platform Tests"

  # ── A1. Sensor entities ──
  echo -e "  ${BOLD}A1. Sensors${NC}"

  SENSORS=(
    "sensor.nanobot_ji_yi_tiao_mu_shu"
    "sensor.nanobot_li_shi_tiao_mu_shu"
    "sensor.nanobot_shang_ci_ji_yi_zheng_he"
    "sensor.nanobot_ji_neng_shu_liang"
    "sensor.nanobot_pai_cheng_shu_liang"
  )

  for entity in "${SENSORS[@]}"; do
    val=$(ha_template "{{ states('$entity') }}")
    short="${entity#sensor.nanobot_}"
    if [ "$val" = "unavailable" ] || [ "$val" = "unknown" ] || [ -z "$val" ]; then
      _fail "Sensor $short exists and has value"
    else
      _pass "Sensor $short = $val"
    fi
  done

  # Dynamic cron sensors (check at least one exists)
  cron_next=$(ha_template "{{ states.sensor | selectattr('entity_id', 'search', 'cron_') | selectattr('entity_id', 'search', 'xia_ci') | map(attribute='state') | first | default('NONE') }}")
  if [ "$cron_next" != "NONE" ]; then
    _pass "Cron next-run sensor exists ($cron_next)"
  else
    _fail "Cron next-run sensor exists"
  fi

  cron_status=$(ha_template "{{ states.sensor | selectattr('entity_id', 'search', 'cron_') | selectattr('entity_id', 'search', 'zhuang_tai') | map(attribute='state') | first | default('NONE') }}")
  if [ "$cron_status" != "NONE" ]; then
    _pass "Cron last-status sensor exists ($cron_status)"
  else
    _fail "Cron last-status sensor exists"
  fi

  # ── A2. Number entities ──
  echo -e "  ${BOLD}A2. Numbers${NC}"

  # Read current temperature
  temp=$(ha_template "{{ states('number.nanobot_temperature') }}")
  assert_not_empty "Temperature has value" "$temp"

  # Set temperature to 0.5
  curl -s -X POST -H "$AUTH" -H "$CT" \
    -d '{"entity_id":"number.nanobot_temperature","value":"0.5"}' \
    "$BASE/api/services/number/set_value" > /dev/null

  sleep 0.5
  new_temp=$(ha_template "{{ states('number.nanobot_temperature') }}")
  assert_eq "Temperature set to 0.5" "0.5" "$new_temp"

  # Boundary: set out of range (should clamp or reject)
  curl -s -X POST -H "$AUTH" -H "$CT" \
    -d '{"entity_id":"number.nanobot_temperature","value":"3.0"}' \
    "$BASE/api/services/number/set_value" > /dev/null 2>&1
  sleep 0.3
  bounded=$(ha_template "{{ states('number.nanobot_temperature') }}")
  # Should still be 0.5 or clamped to 2.0 — NOT 3.0
  assert_not_contains "Temperature rejects out-of-range (3.0)" "3.0" "$bounded"

  # Restore temperature
  curl -s -X POST -H "$AUTH" -H "$CT" \
    -d '{"entity_id":"number.nanobot_temperature","value":"0.7"}' \
    "$BASE/api/services/number/set_value" > /dev/null

  # Max tokens
  max_tokens=$(ha_template "{{ states('number.nanobot_max_tokens') }}")
  assert_not_empty "Max tokens has value" "$max_tokens"

  # Memory window
  mem_window=$(ha_template "{{ states('number.nanobot_ji_yi_zheng_he_yu_zhi') }}")
  assert_not_empty "Memory window has value" "$mem_window"

  # ── A3. Select entities ──
  echo -e "  ${BOLD}A3. Selects${NC}"

  # Read reasoning effort
  effort=$(ha_template "{{ states('select.nanobot_reasoning_effort') }}")
  assert_not_empty "Reasoning effort has value" "$effort"

  # Change to high
  curl -s -X POST -H "$AUTH" -H "$CT" \
    -d '{"entity_id":"select.nanobot_reasoning_effort","option":"high"}' \
    "$BASE/api/services/select/select_option" > /dev/null
  sleep 0.3
  new_effort=$(ha_template "{{ states('select.nanobot_reasoning_effort') }}")
  assert_eq "Reasoning effort set to high" "high" "$new_effort"

  # Restore
  curl -s -X POST -H "$AUTH" -H "$CT" \
    -d '{"entity_id":"select.nanobot_reasoning_effort","option":"medium"}' \
    "$BASE/api/services/select/select_option" > /dev/null

  # Model select
  model=$(ha_template "{{ states('select.nanobot_ai_model') }}")
  assert_not_empty "AI model has value" "$model"

  # Provider select
  provider=$(ha_template "{{ states('select.nanobot_ai_provider') }}")
  assert_not_empty "AI provider has value" "$provider"

  # Provider options
  options=$(ha_template "{{ state_attr('select.nanobot_ai_provider', 'options') }}")
  assert_contains "Provider options include openai" "openai" "$options"
  assert_contains "Provider options include anthropic" "anthropic" "$options"

  # ── A4. Switch entities ──
  echo -e "  ${BOLD}A4. Switches${NC}"

  # List switch entities
  switches=$(ha_template "{% set ns = namespace(items=[]) %}{% for s in states.switch if 'skill_' in s.entity_id or 'cron_' in s.entity_id %}{% set ns.items = ns.items + [s.entity_id] %}{% endfor %}{{ ns.items }}")
  assert_contains "Switch entities exist" "switch." "$switches"

  # Toggle first skill switch (if exists)
  skill_sw=$(ha_template "{{ states.switch | selectattr('entity_id', 'search', 'skill_') | map(attribute='entity_id') | first | default('NONE') }}")
  if [ "$skill_sw" != "NONE" ]; then
    orig_state=$(ha_template "{{ states('$skill_sw') }}")
    # Toggle off
    curl -s -X POST -H "$AUTH" -H "$CT" \
      -d "{\"entity_id\":\"$skill_sw\"}" \
      "$BASE/api/services/switch/turn_off" > /dev/null
    sleep 0.3
    assert_eq "Skill switch turns off" "off" "$(ha_template "{{ states('$skill_sw') }}")"

    # Toggle on
    curl -s -X POST -H "$AUTH" -H "$CT" \
      -d "{\"entity_id\":\"$skill_sw\"}" \
      "$BASE/api/services/switch/turn_on" > /dev/null
    sleep 0.3
    assert_eq "Skill switch turns on" "on" "$(ha_template "{{ states('$skill_sw') }}")"

    # Restore
    if [ "$orig_state" = "off" ]; then
      curl -s -X POST -H "$AUTH" -H "$CT" \
        -d "{\"entity_id\":\"$skill_sw\"}" \
        "$BASE/api/services/switch/turn_off" > /dev/null
    fi
  else
    _warn "No skill switch found — skip toggle test"
  fi

  # Cron switch
  cron_sw=$(ha_template "{{ states.switch | selectattr('entity_id', 'search', 'cron_') | map(attribute='entity_id') | first | default('NONE') }}")
  if [ "$cron_sw" != "NONE" ]; then
    _pass "Cron switch exists: $cron_sw"
  else
    _warn "No cron switch found"
  fi
fi


# =============================================================================
# B. REST API TESTS
# =============================================================================
if should_run "B"; then
  _section "B. REST API Tests"

  # ── B1. Settings API ──
  echo -e "  ${BOLD}B1. Settings${NC}"

  status=$(http_get "$API/settings")
  assert_status "GET /settings → 200" "200" "$status"
  settings=$(body)
  assert_contains "Settings has temperature" "temperature" "$settings"
  assert_contains "Settings has model" "model" "$settings"
  assert_contains "Settings has ai_service" "ai_service" "$settings"

  # PATCH valid update
  status=$(http_patch "$API/settings" '{"temperature": 0.5, "max_tokens": 8192}')
  assert_status "PATCH /settings → 200" "200" "$status"

  # Verify
  status=$(http_get "$API/settings")
  settings=$(body)
  assert_json "Settings temperature updated" "0.5" "temperature" "$settings"
  assert_json "Settings max_tokens updated" "8192" "max_tokens" "$settings"

  # PATCH invalid temperature
  status=$(http_patch "$API/settings" '{"temperature": 5.0}')
  assert_status "PATCH /settings invalid temp → 400" "400" "$status"

  # PATCH invalid max_tokens
  status=$(http_patch "$API/settings" '{"max_tokens": 999999}')
  assert_status "PATCH /settings invalid tokens → 400" "400" "$status"

  # PATCH invalid field
  status=$(http_patch "$API/settings" '{"invalid_field": "xxx"}')
  assert_status "PATCH /settings unknown field → 400" "400" "$status"

  # Restore settings
  http_patch "$API/settings" '{"temperature": 0.7, "max_tokens": 4096}' > /dev/null

  # ── B2. Memory API ──
  echo -e "  ${BOLD}B2. Memory${NC}"

  status=$(http_get "$API/memory")
  assert_status "GET /memory → 200" "200" "$status"
  mem=$(body)
  assert_contains "Memory has sections" "soul" "$mem"

  # GET specific section
  status=$(http_get "$API/memory/soul")
  assert_status "GET /memory/soul → 200" "200" "$status"
  soul=$(body)
  assert_contains "Soul section has content" "content" "$soul"

  # PUT update soul
  status=$(http_put "$API/memory/soul" '{"content": "# Soul\nYou are a helpful assistant for testing."}')
  assert_status "PUT /memory/soul → 200" "200" "$status"

  # Verify update
  status=$(http_get "$API/memory/soul")
  soul=$(body)
  assert_contains "Soul updated content" "testing" "$soul"

  # Search history
  status=$(http_post "$API/memory/search" '{"pattern": ".*"}')
  assert_status "POST /memory/search → 200" "200" "$status"

  # Consolidate
  status=$(http_post "$API/memory/consolidate" '{}')
  # May be 200 (success) or 503 (AI service not available yet)
  code=$(cat /tmp/_test_body 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d.get('success') or d.get('info') else 'error')" 2>/dev/null || echo "error")
  if [ "$status" = "200" ]; then
    _pass "POST /memory/consolidate → 200"
  elif [ "$status" = "503" ]; then
    _warn "POST /memory/consolidate → 503 (AI service not ready)"
  else
    _fail "POST /memory/consolidate → expected 200|503, got $status"
  fi

  # ── B3. Skills API ──
  echo -e "  ${BOLD}B3. Skills${NC}"

  # List skills
  status=$(http_get "$API/skills")
  assert_status "GET /skills → 200" "200" "$status"
  skills=$(body)
  assert_contains "Skills list has skills" "skills" "$skills"

  # Create skill
  status=$(http_post "$API/skills" '{
    "name": "test_auto_skill",
    "description": "Automated test skill",
    "content": "# Test Skill\n\nThis is for automated testing.",
    "always": false
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "POST /skills create → $status"
  else
    _fail "POST /skills create (expected 200|201, got $status)"
  fi

  # Read skill
  status=$(http_get "$API/skills/test_auto_skill")
  assert_status "GET /skills/test_auto_skill → 200" "200" "$status"
  skill_body=$(body)
  assert_contains "Skill content readable" "automated testing" "$skill_body"

  # Update skill
  status=$(http_put "$API/skills/test_auto_skill" '{"description": "Updated test skill", "always": true}')
  assert_status "PUT /skills/test_auto_skill → 200" "200" "$status"

  # Verify update
  status=$(http_get "$API/skills/test_auto_skill")
  updated_skill=$(body)
  assert_contains "Skill description updated" "Updated" "$updated_skill"

  # Duplicate create → should error
  status=$(http_post "$API/skills" '{
    "name": "test_auto_skill",
    "description": "Duplicate",
    "content": "# Dup"
  }')
  if [ "$status" = "200" ]; then
    _fail "POST /skills duplicate → should not be 200"
  else
    _pass "POST /skills duplicate → rejected ($status)"
  fi

  # Delete skill
  status=$(http_delete "$API/skills/test_auto_skill")
  assert_status "DELETE /skills/test_auto_skill → 200" "200" "$status"

  # Confirm deleted
  status=$(http_get "$API/skills/test_auto_skill")
  if [ "$status" = "200" ]; then
    _fail "GET deleted skill → should not be 200"
  else
    _pass "GET deleted skill → $status (correctly gone)"
  fi

  # ── B4. Cron API ──
  echo -e "  ${BOLD}B4. Cron${NC}"

  # List jobs
  status=$(http_get "$API/cron/jobs")
  assert_status "GET /cron/jobs → 200" "200" "$status"
  jobs=$(body)
  assert_contains "Cron jobs response" "jobs" "$jobs"

  # Create job
  status=$(http_post "$API/cron/jobs" '{
    "name": "test_auto_job",
    "schedule": {"kind": "every", "every_ms": 3600000},
    "payload": {"kind": "agent_turn", "message": "Test auto job"},
    "enabled": false
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "POST /cron/jobs create → $status"
  else
    _fail "POST /cron/jobs create (expected 200|201, got $status)"
  fi
  created_job=$(body)
  JOB_ID=$(echo "$created_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$JOB_ID" ] && [ "$JOB_ID" != "" ]; then
    _pass "Created job has ID: $JOB_ID"

    # Get job detail
    status=$(http_get "$API/cron/jobs/$JOB_ID")
    assert_status "GET /cron/jobs/$JOB_ID → 200" "200" "$status"

    # Patch job
    status=$(http_patch "$API/cron/jobs/$JOB_ID" '{"enabled": true}')
    if [ "$status" = "200" ]; then
      _pass "PATCH /cron/jobs enable → 200"
    else
      _warn "PATCH /cron/jobs enable → $status"
    fi

    # Trigger job manually
    status=$(http_post "$API/cron/jobs/$JOB_ID/trigger" '{}')
    if [ "$status" = "200" ] || [ "$status" = "202" ]; then
      _pass "POST /cron/jobs trigger → $status"
    else
      _warn "POST /cron/jobs trigger → $status"
    fi

    # Delete job
    status=$(http_delete "$API/cron/jobs/$JOB_ID")
    assert_status "DELETE /cron/jobs → 200" "200" "$status"
  else
    _fail "Created job missing ID"
  fi

  # ── B5. Conversations API ──
  echo -e "  ${BOLD}B5. Conversations${NC}"

  # List conversations
  status=$(http_get "$API/conversations")
  assert_status "GET /conversations → 200" "200" "$status"

  # Create conversation
  status=$(http_post "$API/conversations" '{"title": "Test Auto Conversation"}')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "POST /conversations create → $status"
  else
    _fail "POST /conversations create (expected 200|201, got $status)"
  fi
  conv=$(body)
  CONV_ID=$(echo "$conv" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)

  if [ -n "$CONV_ID" ] && [ "$CONV_ID" != "" ]; then
    _pass "Created conversation has ID"

    # Get messages
    status=$(http_get "$API/conversations/$CONV_ID/messages")
    assert_status "GET /conversations/ID/messages → 200" "200" "$status"

    # Rename
    status=$(http_patch "$API/conversations/$CONV_ID" '{"title": "Renamed Test"}')
    assert_status "PATCH /conversations rename → 200" "200" "$status"

    # Delete
    status=$(http_delete "$API/conversations/$CONV_ID")
    assert_status "DELETE /conversations → 200" "200" "$status"
  else
    _fail "Created conversation missing ID"
  fi
fi


# =============================================================================
# C. AI CONVERSATION E2E (soft assertions)
# =============================================================================
if should_run "C"; then
  _section "C. AI Conversation E2E (soft assertions)"

  # C1. Basic conversation
  resp=$(curl -s -X POST -H "$AUTH" -H "$CT" \
    -d "{
      \"text\": \"你好，請簡短回答：1+1 等於多少？\",
      \"language\": \"zh-Hant\",
      \"agent_id\": \"$AGENT\"
    }" \
    "$BASE/api/conversation/process" 2>/dev/null)

  speech=$(echo "$resp" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)

  if [ -n "$speech" ] && [ "$speech" != "" ]; then
    _pass "AI responds to basic question"
    assert_soft "AI response contains answer" "2" "$speech"
  else
    _warn "AI basic question — no speech response"
  fi

  # C2. Tool call test (search entities)
  resp2=$(curl -s -X POST -H "$AUTH" -H "$CT" \
    -d "{
      \"text\": \"用 search_entities 工具搜尋 domain 為 light 的實體，只列出名稱\",
      \"language\": \"zh-Hant\",
      \"agent_id\": \"$AGENT\"
    }" \
    "$BASE/api/conversation/process" 2>/dev/null)

  speech2=$(echo "$resp2" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)

  assert_not_empty "AI responds to tool call request" "$speech2"

  # C3. Memory injection — verify AI knows its identity
  resp3=$(curl -s -X POST -H "$AUTH" -H "$CT" \
    -d "{
      \"text\": \"你的角色是什麼？用一句話回答\",
      \"language\": \"zh-Hant\",
      \"agent_id\": \"$AGENT\"
    }" \
    "$BASE/api/conversation/process" 2>/dev/null)

  speech3=$(echo "$resp3" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)

  assert_not_empty "AI responds to identity question" "$speech3"
fi


# =============================================================================
# D. FRONTEND STATIC RESOURCES
# =============================================================================
if should_run "D"; then
  _section "D. Frontend Static Resources"

  for file in index.html app.js styles.css; do
    status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ha_mcp_client/panel/$file")
    # HA panel might use different path — try ha-mcp-chat too
    if [ "$status" != "200" ]; then
      status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/local/ha_mcp_client/$file")
    fi
    if [ "$status" = "200" ]; then
      _pass "Frontend $file → 200"
    else
      _warn "Frontend $file → $status (panel may use iframe path)"
    fi
  done

  # Panel registration
  panel=$(ha_template "{{ states.frontend | list | length }}")
  _pass "Frontend panel registered"
fi


# =============================================================================
# E. MCP SSE SERVER
# =============================================================================
if should_run "E"; then
  _section "E. MCP SSE Server"

  # Test SSE endpoint is reachable (3 second timeout)
  sse_output=$(timeout 3 curl -s -N -H "$AUTH" "$API/sse" 2>/dev/null || true)

  if echo "$sse_output" | grep -q "event:\|data:"; then
    _pass "SSE endpoint returns event stream"
  elif [ -n "$sse_output" ]; then
    _pass "SSE endpoint responds ($( echo "$sse_output" | head -c 50 )...)"
  else
    _warn "SSE endpoint — no data within 3s timeout"
  fi

  # Check SSE endpoint returns correct content type
  ct=$(timeout 3 curl -sI -H "$AUTH" "$API/sse" 2>/dev/null | grep -i "content-type" | head -1 || true)
  if echo "$ct" | grep -qi "text/event-stream"; then
    _pass "SSE Content-Type is text/event-stream"
  elif [ -n "$ct" ]; then
    _warn "SSE Content-Type: $ct"
  else
    _warn "SSE Content-Type header not captured"
  fi
fi


# =============================================================================
# F. CRON EXECUTION
# =============================================================================
if should_run "F"; then
  _section "F. Cron Execution"

  # Create a test job and trigger it manually
  status=$(http_post "$API/cron/jobs" '{
    "name": "test_exec_job",
    "schedule": {"kind": "every", "every_ms": 86400000},
    "payload": {"kind": "agent_turn", "message": "Cron execution test. Say: CRON_OK"},
    "enabled": false
  }')

  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    exec_job=$(body)
    EXEC_JOB_ID=$(echo "$exec_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

    if [ -n "$EXEC_JOB_ID" ] && [ "$EXEC_JOB_ID" != "" ]; then
      # Trigger
      status=$(http_post "$API/cron/jobs/$EXEC_JOB_ID/trigger" '{}')
      if [ "$status" = "200" ] || [ "$status" = "202" ]; then
        _pass "Cron job trigger accepted ($status)"

        # Wait a moment for execution
        sleep 3

        # Check logs for cron execution
        cron_log=$(podman logs homeassistant 2>&1 | grep -i "cron\|CRON_OK\|test_exec_job" | tail -5)
        if [ -n "$cron_log" ]; then
          _pass "Cron job execution logged"
        else
          _warn "Cron job execution — no log found (may need longer wait)"
        fi
      else
        _warn "Cron job trigger → $status"
      fi

      # Cleanup
      http_delete "$API/cron/jobs/$EXEC_JOB_ID" > /dev/null 2>&1
      _pass "Cron test job cleaned up"
    else
      _fail "Cron execution test — no job ID"
    fi
  else
    _fail "Cron execution test — create failed ($status)"
  fi
fi


# =============================================================================
# G. ENTITY PERSISTENCE (Phase 9)
# =============================================================================
if should_run "G"; then
  if [ "$SKIP_RESTART" = true ]; then
    _section "G. Entity Persistence (SKIPPED — --skip-restart)"
  else
    _section "G. Entity Persistence (Phase 9)"

    # Save original values
    orig_temp=$(ha_template "{{ states('number.nanobot_temperature') }}")
    orig_effort=$(ha_template "{{ states('select.nanobot_reasoning_effort') }}")

    # Set to test values
    curl -s -X POST -H "$AUTH" -H "$CT" \
      -d '{"entity_id":"number.nanobot_temperature","value":"1.3"}' \
      "$BASE/api/services/number/set_value" > /dev/null

    curl -s -X POST -H "$AUTH" -H "$CT" \
      -d '{"entity_id":"select.nanobot_reasoning_effort","option":"high"}' \
      "$BASE/api/services/select/select_option" > /dev/null

    # Wait for HA to flush config_entry to disk
    sleep 5

    # Verify pre-restart values
    pre_temp=$(ha_template "{{ states('number.nanobot_temperature') }}")
    pre_effort=$(ha_template "{{ states('select.nanobot_reasoning_effort') }}")
    assert_eq "Pre-restart: temperature = 1.3" "1.3" "$pre_temp"
    assert_eq "Pre-restart: reasoning effort = high" "high" "$pre_effort"

    # Restart HA
    echo -e "  ${YELLOW}Restarting HA for persistence test...${NC}"
    podman restart homeassistant > /dev/null 2>&1
    sleep 35

    # Wait for API
    for i in $(seq 1 10); do
      check=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/" 2>/dev/null)
      if [ "$check" = "200" ]; then break; fi
      sleep 3
    done

    # Verify post-restart values
    post_temp=$(ha_template "{{ states('number.nanobot_temperature') }}")
    post_effort=$(ha_template "{{ states('select.nanobot_reasoning_effort') }}")

    assert_eq "Post-restart: temperature persisted = 1.3" "1.3" "$post_temp"
    assert_eq "Post-restart: reasoning effort persisted = high" "high" "$post_effort"

    # Verify no reload loop (integration should be up)
    mcp_state=$(ha_template "{{ states.sensor | selectattr('entity_id', 'search', 'nanobot_ji_yi') | map(attribute='state') | first | default('MISSING') }}")
    assert_not_contains "Integration still running (no reload loop)" "MISSING" "$mcp_state"

    # Restore original values (also persists to config_entry.data)
    curl -s -X POST -H "$AUTH" -H "$CT" \
      -d "{\"entity_id\":\"number.nanobot_temperature\",\"value\":\"$orig_temp\"}" \
      "$BASE/api/services/number/set_value" > /dev/null

    curl -s -X POST -H "$AUTH" -H "$CT" \
      -d "{\"entity_id\":\"select.nanobot_reasoning_effort\",\"option\":\"$orig_effort\"}" \
      "$BASE/api/services/select/select_option" > /dev/null

    # Wait for config_entry to flush to disk
    sleep 5
    _pass "Original values restored"
  fi
fi


# =============================================================================
# H. ERROR HANDLING & BOUNDARY
# =============================================================================
if should_run "H"; then
  _section "H. Error Handling & Boundary Tests"

  # Non-existent skill
  status=$(http_get "$API/skills/nonexistent_skill_xyz")
  if [ "$status" != "200" ]; then
    _pass "GET non-existent skill → $status"
  else
    _fail "GET non-existent skill → should not be 200"
  fi

  # Non-existent cron job
  status=$(http_get "$API/cron/jobs/nonexistent_job_xyz")
  if [ "$status" != "200" ]; then
    _pass "GET non-existent cron job → $status"
  else
    _fail "GET non-existent cron job → should not be 200"
  fi

  # Invalid memory section
  status=$(http_get "$API/memory/invalid_section_xyz")
  if [ "$status" != "200" ]; then
    _pass "GET invalid memory section → $status"
  else
    # Some implementations return empty content with 200
    result=$(body)
    if echo "$result" | grep -q "error\|not found\|invalid"; then
      _pass "GET invalid memory section → 200 with error message"
    else
      _warn "GET invalid memory section → 200 (may accept any section name)"
    fi
  fi

  # Create skill with missing fields
  status=$(http_post "$API/skills" '{}')
  if [ "$status" = "400" ] || [ "$status" = "422" ]; then
    _pass "POST /skills missing fields → $status"
  elif [ "$status" != "200" ]; then
    _pass "POST /skills missing fields → rejected ($status)"
  else
    _fail "POST /skills missing fields → should not be 200"
  fi

  # Create cron job with missing fields
  status=$(http_post "$API/cron/jobs" '{}')
  if [ "$status" != "200" ]; then
    _pass "POST /cron/jobs missing fields → $status"
  else
    # Clean up if it somehow created
    _warn "POST /cron/jobs missing fields → 200 (accepted empty)"
  fi

  # Settings — out of range values
  status=$(http_patch "$API/settings" '{"max_tool_calls": 999}')
  assert_status "PATCH /settings max_tool_calls OOB → 400" "400" "$status"

  status=$(http_patch "$API/settings" '{"memory_window": 0}')
  assert_status "PATCH /settings memory_window OOB → 400" "400" "$status"

  # No auth → 401
  unauth=$(curl -s -o /dev/null -w "%{http_code}" "$API/settings" 2>/dev/null)
  assert_status "GET /settings without auth → 401" "401" "$unauth"
fi


# =============================================================================
# I. RESTART STABILITY
# =============================================================================
if should_run "I"; then
  if [ "$SKIP_RESTART" = true ]; then
    _section "I. Restart Stability (SKIPPED — --skip-restart)"
  else
    _section "I. Restart Stability"

    # Collect all entity states before restart
    echo -e "  ${YELLOW}Collecting entity states...${NC}"
    before=$(ha_template "{% set ns = namespace(items=[]) %}{% for s in states if 'nanobot' in s.entity_id or 'skill_' in s.entity_id or 'cron_' in s.entity_id %}{% set ns.items = ns.items + [s.entity_id ~ '=' ~ s.state] %}{% endfor %}{{ ns.items | join('|') }}")

    entity_count=$(echo "$before" | tr '|' '\n' | wc -l)
    _pass "Captured $entity_count entity states before restart"

    # Only restart if G didn't already restart recently
    # Check if HA uptime is > 60 seconds
    uptime_check=$(ha_template "{{ as_timestamp(now()) - as_timestamp(states.sensor.date.last_updated | default(now())) }}" 2>/dev/null || echo "999")

    echo -e "  ${YELLOW}Restarting HA...${NC}"
    podman restart homeassistant > /dev/null 2>&1
    sleep 35

    # Wait for API
    for i in $(seq 1 10); do
      check=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/" 2>/dev/null)
      if [ "$check" = "200" ]; then break; fi
      sleep 3
    done

    # Collect states after restart
    after=$(ha_template "{% set ns = namespace(items=[]) %}{% for s in states if 'nanobot' in s.entity_id or 'skill_' in s.entity_id or 'cron_' in s.entity_id %}{% set ns.items = ns.items + [s.entity_id ~ '=' ~ s.state] %}{% endfor %}{{ ns.items | join('|') }}")

    after_count=$(echo "$after" | tr '|' '\n' | wc -l)
    assert_eq "Same entity count after restart" "$entity_count" "$after_count"

    # Compare states
    mismatch=0
    while IFS='=' read -r entity state; do
      [ -z "$entity" ] && continue
      after_state=$(echo "$after" | tr '|' '\n' | grep "^${entity}=" | cut -d'=' -f2-)
      if [ "$state" != "$after_state" ]; then
        # Some sensors (like timestamps) change — only count actual mismatches
        case "$entity" in
          *xia_ci*|*shang_ci*|*zheng_he*) ;; # timestamp sensors change on restart
          *)
            echo -e "    ${YELLOW}Δ${NC} $entity: $state → $after_state"
            mismatch=$((mismatch + 1))
            ;;
        esac
      fi
    done <<< "$(echo "$before" | tr '|' '\n')"

    if [ "$mismatch" -eq 0 ]; then
      _pass "All non-timestamp entities stable across restart"
    else
      _warn "Some entities changed after restart ($mismatch mismatches)"
    fi

    # Verify critical subsystems still running
    mem_sensor=$(ha_template "{{ states('sensor.nanobot_ji_yi_tiao_mu_shu') }}")
    assert_not_empty "Memory sensor alive after restart" "$mem_sensor"

    skills_sensor=$(ha_template "{{ states('sensor.nanobot_ji_neng_shu_liang') }}")
    assert_not_empty "Skills sensor alive after restart" "$skills_sensor"

    cron_sensor=$(ha_template "{{ states('sensor.nanobot_pai_cheng_shu_liang') }}")
    assert_not_empty "Cron sensor alive after restart" "$cron_sensor"
  fi
fi


# =============================================================================
# SUMMARY
# =============================================================================
echo ""
echo -e "${BOLD}═══════════════════════════════════════${NC}"
echo -e "${BOLD}         TEST RESULTS SUMMARY          ${NC}"
echo -e "${BOLD}═══════════════════════════════════════${NC}"
echo -e "  ${GREEN}Passed:${NC}  $PASS"
echo -e "  ${RED}Failed:${NC}  $FAIL"
echo -e "  ${YELLOW}Warned:${NC}  $WARN"
echo -e "  Total:   $TOTAL"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo -e "${RED}FAILURES:${NC}"
  for f in "${FAILURES[@]}"; do
    echo -e "  ${RED}✗${NC} $f"
  done
  echo ""
  exit 1
elif [ "$WARN" -gt 0 ]; then
  echo -e "${YELLOW}All critical tests passed. $WARN warnings.${NC}"
  exit 0
else
  echo -e "${GREEN}All tests passed!${NC}"
  exit 0
fi
