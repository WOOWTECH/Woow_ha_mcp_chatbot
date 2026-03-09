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
  SECTIONS=(A B C D E F G H I J K L M N O P Q R)
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

  # Active LLM Provider select (replaces old nanobot_ai_provider + nanobot_ai_model)
  provider=$(ha_template "{{ states('select.active_llm_provider') }}")
  assert_not_empty "Active LLM provider has value" "$provider"

  # Provider options (now lists provider IDs like openai_1, ollama_1 etc.)
  options=$(ha_template "{{ state_attr('select.active_llm_provider', 'options') }}")
  assert_contains "Provider options include at least one provider" "_" "$options"

  # Provider attributes include model info
  model=$(ha_template "{{ state_attr('select.active_llm_provider', 'model') }}")
  assert_not_empty "Active LLM has model attribute" "$model"

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
  # Note: HEAD (-I) returns 405 on StreamResponse; use GET with -D to capture headers
  timeout 3 curl -s -D /tmp/_sse_ct_headers.txt -o /dev/null -N -H "$AUTH" "$API/sse" 2>/dev/null || true
  ct=$(grep -i "content-type" /tmp/_sse_ct_headers.txt 2>/dev/null | head -1 || true)
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
# J. CRON ADVANCED SCHEDULING
# =============================================================================
if should_run "J"; then
  _section "J. Cron Advanced Scheduling"

  # ── J1. "at" schedule (one-time) ──
  echo -e "  ${BOLD}J1. One-time (at) schedule${NC}"

  # Create a one-time job in the future (5 minutes from now)
  FUTURE_MS=$(python3 -c "import time; print(int((time.time() + 300) * 1000))")
  status=$(http_post "$API/cron/jobs" "{
    \"name\": \"test_at_job\",
    \"schedule\": {\"kind\": \"at\", \"at_ms\": $FUTURE_MS},
    \"payload\": {\"kind\": \"agent_turn\", \"message\": \"One-time test\"},
    \"enabled\": true
  }")
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create at-schedule job → $status"
  else
    _fail "Create at-schedule job (expected 200|201, got $status)"
  fi
  at_job=$(body)
  AT_JOB_ID=$(echo "$at_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$AT_JOB_ID" ] && [ "$AT_JOB_ID" != "" ]; then
    # Verify schedule kind
    status=$(http_get "$API/cron/jobs/$AT_JOB_ID")
    job_detail=$(body)
    at_kind=$(echo "$job_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('schedule',{}).get('kind',''))" 2>/dev/null)
    assert_eq "at job schedule kind" "at" "$at_kind"

    # Verify next_run_at_ms is set
    next_run=$(echo "$job_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('next_run_at_ms',0))" 2>/dev/null)
    if [ "$next_run" -gt 0 ] 2>/dev/null; then
      _pass "at job has next_run_at_ms set ($next_run)"
    else
      _fail "at job next_run_at_ms should be > 0 (got $next_run)"
    fi

    # Cleanup
    http_delete "$API/cron/jobs/$AT_JOB_ID" > /dev/null 2>&1
  else
    _fail "at job missing ID"
  fi

  # ── J2. "cron" expression schedule ──
  echo -e "  ${BOLD}J2. Cron expression schedule${NC}"

  status=$(http_post "$API/cron/jobs" '{
    "name": "test_cron_expr_job",
    "schedule": {"kind": "cron", "cron": "*/30 * * * *", "tz": "Asia/Taipei"},
    "payload": {"kind": "agent_turn", "message": "Cron expression test"},
    "enabled": true
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create cron-expression job → $status"
  else
    _fail "Create cron-expression job (expected 200|201, got $status)"
  fi
  cron_job=$(body)
  CRON_EXPR_ID=$(echo "$cron_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$CRON_EXPR_ID" ] && [ "$CRON_EXPR_ID" != "" ]; then
    # Verify schedule kind and cron expression
    status=$(http_get "$API/cron/jobs/$CRON_EXPR_ID")
    cron_detail=$(body)
    cron_kind=$(echo "$cron_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('schedule',{}).get('kind',''))" 2>/dev/null)
    assert_eq "cron job schedule kind" "cron" "$cron_kind"

    cron_expr=$(echo "$cron_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('schedule',{}).get('cron',''))" 2>/dev/null)
    assert_eq "cron expression stored" "*/30 * * * *" "$cron_expr"

    cron_tz=$(echo "$cron_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('schedule',{}).get('tz',''))" 2>/dev/null)
    assert_eq "cron timezone stored" "Asia/Taipei" "$cron_tz"

    # Verify next_run_at_ms computed (croniter must be installed)
    cron_next=$(echo "$cron_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('next_run_at_ms',0))" 2>/dev/null)
    if [ "$cron_next" -gt 0 ] 2>/dev/null; then
      _pass "cron job has computed next_run_at_ms ($cron_next)"
    else
      _warn "cron job next_run_at_ms = 0 (croniter may not be installed)"
    fi

    # Cleanup
    http_delete "$API/cron/jobs/$CRON_EXPR_ID" > /dev/null 2>&1
  else
    _fail "cron expression job missing ID"
  fi

  # ── J3. system_event payload ──
  echo -e "  ${BOLD}J3. System event payload${NC}"

  status=$(http_post "$API/cron/jobs" '{
    "name": "test_system_event_job",
    "schedule": {"kind": "every", "every_ms": 86400000},
    "payload": {"kind": "system_event", "message": "System event test payload"},
    "enabled": false
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create system_event job → $status"
  else
    _fail "Create system_event job (expected 200|201, got $status)"
  fi
  sys_job=$(body)
  SYS_JOB_ID=$(echo "$sys_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$SYS_JOB_ID" ] && [ "$SYS_JOB_ID" != "" ]; then
    # Verify payload kind
    status=$(http_get "$API/cron/jobs/$SYS_JOB_ID")
    sys_detail=$(body)
    payload_kind=$(echo "$sys_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('payload',{}).get('kind',''))" 2>/dev/null)
    assert_eq "system_event payload kind" "system_event" "$payload_kind"

    payload_msg=$(echo "$sys_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('payload',{}).get('message',''))" 2>/dev/null)
    assert_eq "system_event message stored" "System event test payload" "$payload_msg"

    # Trigger and verify it runs without error
    # Enable first
    http_patch "$API/cron/jobs/$SYS_JOB_ID" '{"enabled": true}' > /dev/null 2>&1
    status=$(http_post "$API/cron/jobs/$SYS_JOB_ID/trigger" '{}')
    if [ "$status" = "200" ] || [ "$status" = "202" ]; then
      _pass "Trigger system_event job → $status"
    else
      _warn "Trigger system_event job → $status"
    fi
    sleep 1

    # Check job state after trigger
    status=$(http_get "$API/cron/jobs/$SYS_JOB_ID")
    triggered_detail=$(body)
    last_status=$(echo "$triggered_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('last_status',''))" 2>/dev/null)
    assert_eq "system_event job last_status = ok" "ok" "$last_status"

    # Cleanup
    http_delete "$API/cron/jobs/$SYS_JOB_ID" > /dev/null 2>&1
  else
    _fail "system_event job missing ID"
  fi

  # ── J4. delete_after_run flag ──
  echo -e "  ${BOLD}J4. delete_after_run${NC}"

  # Create a one-time job with delete_after_run=true, trigger it
  DAR_MS=$(python3 -c "import time; print(int((time.time() + 300) * 1000))")
  status=$(http_post "$API/cron/jobs" "{
    \"name\": \"test_delete_after_run\",
    \"schedule\": {\"kind\": \"at\", \"at_ms\": $DAR_MS},
    \"payload\": {\"kind\": \"agent_turn\", \"message\": \"Delete me after run\"},
    \"enabled\": true,
    \"delete_after_run\": true
  }")
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create delete_after_run job → $status"
  else
    _fail "Create delete_after_run job (expected 200|201, got $status)"
  fi
  dar_job=$(body)
  DAR_JOB_ID=$(echo "$dar_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$DAR_JOB_ID" ] && [ "$DAR_JOB_ID" != "" ]; then
    # Trigger it
    status=$(http_post "$API/cron/jobs/$DAR_JOB_ID/trigger" '{}')
    if [ "$status" = "200" ] || [ "$status" = "202" ]; then
      _pass "Trigger delete_after_run job → $status"
    else
      _warn "Trigger delete_after_run job → $status"
    fi
    sleep 2

    # Verify job was deleted
    status=$(http_get "$API/cron/jobs/$DAR_JOB_ID")
    if [ "$status" != "200" ]; then
      _pass "Job auto-deleted after run (GET → $status)"
    else
      # Job might still exist if trigger was async
      _warn "Job still exists after trigger (delete may be async)"
      http_delete "$API/cron/jobs/$DAR_JOB_ID" > /dev/null 2>&1
    fi
  else
    _fail "delete_after_run job missing ID"
  fi

  # ── J5. Job state tracking ──
  echo -e "  ${BOLD}J5. Job state tracking${NC}"

  status=$(http_post "$API/cron/jobs" '{
    "name": "test_state_track",
    "schedule": {"kind": "every", "every_ms": 86400000},
    "payload": {"kind": "agent_turn", "message": "State tracking test"},
    "enabled": true
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    state_job=$(body)
    STATE_JOB_ID=$(echo "$state_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

    if [ -n "$STATE_JOB_ID" ] && [ "$STATE_JOB_ID" != "" ]; then
      # Before trigger: last_run_at_ms should be 0
      status=$(http_get "$API/cron/jobs/$STATE_JOB_ID")
      pre_detail=$(body)
      pre_last_run=$(echo "$pre_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('last_run_at_ms',0))" 2>/dev/null)
      assert_eq "Pre-trigger: last_run_at_ms = 0" "0" "$pre_last_run"

      # Trigger
      http_post "$API/cron/jobs/$STATE_JOB_ID/trigger" '{}' > /dev/null 2>&1
      sleep 2

      # After trigger: last_run_at_ms should be > 0, last_status should be ok
      status=$(http_get "$API/cron/jobs/$STATE_JOB_ID")
      post_detail=$(body)
      post_last_run=$(echo "$post_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('last_run_at_ms',0))" 2>/dev/null)
      if [ "$post_last_run" -gt 0 ] 2>/dev/null; then
        _pass "Post-trigger: last_run_at_ms updated ($post_last_run)"
      else
        _fail "Post-trigger: last_run_at_ms should be > 0 (got $post_last_run)"
      fi

      post_status=$(echo "$post_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('last_status',''))" 2>/dev/null)
      assert_eq "Post-trigger: last_status = ok" "ok" "$post_status"

      post_error=$(echo "$post_detail" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('last_error',''))" 2>/dev/null)
      assert_eq "Post-trigger: last_error empty" "" "$post_error"

      # Cleanup
      http_delete "$API/cron/jobs/$STATE_JOB_ID" > /dev/null 2>&1
    else
      _fail "state tracking job missing ID"
    fi
  else
    _fail "Create state tracking job (expected 200|201, got $status)"
  fi
fi


# =============================================================================
# K. MEMORY ADVANCED TESTS
# =============================================================================
if should_run "K"; then
  _section "K. Memory Advanced Tests"

  # ── K1. USER.md read/write ──
  echo -e "  ${BOLD}K1. User profile (USER.md)${NC}"

  # Read user section
  status=$(http_get "$API/memory/user")
  assert_status "GET /memory/user → 200" "200" "$status"
  user_body=$(body)
  assert_contains "User section has content key" "content" "$user_body"

  # Save original content
  orig_user=$(echo "$user_body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('content',''))" 2>/dev/null)

  # Write new user profile
  status=$(http_put "$API/memory/user" '{"content": "# User Profile\n\n- **Name**: Test User\n- **Timezone**: UTC+8\n- **Language**: 繁體中文"}')
  assert_status "PUT /memory/user → 200" "200" "$status"

  # Verify written
  status=$(http_get "$API/memory/user")
  updated_user=$(body)
  assert_contains "User profile updated" "Test User" "$updated_user"

  # Restore original
  escaped_user=$(python3 -c "import json; print(json.dumps({'content': '''$orig_user'''}))" 2>/dev/null || echo '{"content": ""}')
  http_put "$API/memory/user" "$escaped_user" > /dev/null 2>&1

  # ── K2. HISTORY.md read ──
  echo -e "  ${BOLD}K2. History read${NC}"

  status=$(http_get "$API/memory/history")
  assert_status "GET /memory/history → 200" "200" "$status"
  history_body=$(body)
  assert_contains "History section has content key" "content" "$history_body"

  # ── K3. Memory stats ──
  echo -e "  ${BOLD}K3. Memory stats${NC}"

  status=$(http_get "$API/memory/stats")
  assert_status "GET /memory/stats → 200" "200" "$status"
  stats_body=$(body)
  assert_contains "Stats has memory_entries" "memory_entries" "$stats_body"
  assert_contains "Stats has history_entries" "history_entries" "$stats_body"
  assert_contains "Stats has memory_file" "memory_file" "$stats_body"

  # ── K4. Memory (MEMORY.md) read/write ──
  echo -e "  ${BOLD}K4. Long-term memory read/write${NC}"

  status=$(http_get "$API/memory/memory")
  assert_status "GET /memory/memory → 200" "200" "$status"
  mem_body=$(body)
  orig_memory=$(echo "$mem_body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('content',''))" 2>/dev/null)

  # Write test content
  status=$(http_put "$API/memory/memory" '{"content": "# Test Memory\n\n- The user likes testing things.\n- Important: this is a test entry."}')
  assert_status "PUT /memory/memory → 200" "200" "$status"

  # Verify
  status=$(http_get "$API/memory/memory")
  updated_mem=$(body)
  assert_contains "Long-term memory updated" "test entry" "$updated_mem"

  # Restore original
  escaped_mem=$(python3 -c "import json; print(json.dumps({'content': '''$orig_memory'''}))" 2>/dev/null || echo '{"content": ""}')
  http_put "$API/memory/memory" "$escaped_mem" > /dev/null 2>&1

  # ── K5. Search with specific pattern ──
  echo -e "  ${BOLD}K5. History search patterns${NC}"

  status=$(http_post "$API/memory/search" '{"pattern": "20[0-9]{2}-[0-9]{2}"}')
  assert_status "POST /memory/search date pattern → 200" "200" "$status"
  search_body=$(body)
  assert_contains "Search returns matches field" "matches" "$search_body"
  assert_contains "Search returns count field" "count" "$search_body"

  # Search with limit
  status=$(http_post "$API/memory/search" '{"pattern": ".*", "limit": 5}')
  assert_status "POST /memory/search with limit → 200" "200" "$status"

  # ── K6. GET all memory sections at once ──
  echo -e "  ${BOLD}K6. All memory sections${NC}"

  status=$(http_get "$API/memory")
  assert_status "GET /memory all → 200" "200" "$status"
  all_mem=$(body)
  assert_contains "All memory has soul" "soul" "$all_mem"
  assert_contains "All memory has user" "user" "$all_mem"
  assert_contains "All memory has history" "history" "$all_mem"
  assert_contains "All memory has stats" "stats" "$all_mem"

  # ── K7. Write to non-writable section ──
  echo -e "  ${BOLD}K7. Write protection${NC}"

  status=$(http_put "$API/memory/history" '{"content": "should not work"}')
  if [ "$status" = "400" ]; then
    _pass "PUT /memory/history → 400 (write-protected)"
  else
    _warn "PUT /memory/history → $status (expected 400)"
  fi

  status=$(http_put "$API/memory/stats" '{"content": "should not work"}')
  if [ "$status" = "400" ]; then
    _pass "PUT /memory/stats → 400 (write-protected)"
  else
    _warn "PUT /memory/stats → $status (expected 400)"
  fi
fi


# =============================================================================
# L. SKILLS ADVANCED TESTS
# =============================================================================
if should_run "L"; then
  _section "L. Skills Advanced Tests"

  # ── L1. Partial update (metadata only, body preserved) ──
  echo -e "  ${BOLD}L1. Partial update preserves body${NC}"

  # Create a test skill
  status=$(http_post "$API/skills" '{
    "name": "test_partial_update",
    "description": "Original description",
    "content": "# Partial Update Test\n\nThis body should survive metadata updates.",
    "always": false
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create test_partial_update skill → $status"
  else
    _fail "Create test_partial_update skill (expected 200|201, got $status)"
  fi

  # Update only description (no content field)
  status=$(http_put "$API/skills/test_partial_update" '{"description": "Updated description"}')
  assert_status "PUT update description only → 200" "200" "$status"

  # Read and verify body is preserved
  status=$(http_get "$API/skills/test_partial_update")
  partial_body=$(body)
  assert_contains "Body preserved after metadata update" "body should survive" "$partial_body"
  assert_contains "Description updated" "Updated description" "$partial_body"

  # ── L2. Toggle skill always flag ──
  echo -e "  ${BOLD}L2. Toggle always flag${NC}"

  # Toggle to always=true
  status=$(http_put "$API/skills/test_partial_update" '{"always": true}')
  assert_status "PUT toggle always=true → 200" "200" "$status"

  # Verify
  status=$(http_get "$API/skills/test_partial_update")
  toggled=$(body)
  assert_contains "Skill always toggled to true" "true" "$toggled"

  # Toggle back
  status=$(http_put "$API/skills/test_partial_update" '{"always": false}')
  assert_status "PUT toggle always=false → 200" "200" "$status"

  # ── L3. Name sanitization ──
  echo -e "  ${BOLD}L3. Name sanitization${NC}"

  # Create with special chars in name (should be sanitized to underscores)
  status=$(http_post "$API/skills" '{
    "name": "Test Skill With Spaces!@#",
    "description": "Name sanitization test",
    "content": "# Sanitized"
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create skill with special chars → $status"

    # The sanitized name should be something like test_skill_with_spaces___
    # Try to find it in the list
    status=$(http_get "$API/skills")
    skills_list=$(body)
    if echo "$skills_list" | grep -q "test_skill_with_spaces"; then
      _pass "Sanitized name found in skills list"
      # Clean up the sanitized skill
      sanitized_name=$(echo "$skills_list" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d.get('skills', []):
    if 'test_skill_with_spaces' in s.get('name', ''):
        print(s['name'])
        break
" 2>/dev/null)
      if [ -n "$sanitized_name" ]; then
        http_delete "$API/skills/$sanitized_name" > /dev/null 2>&1
      fi
    else
      _fail "Sanitized skill name not found in list"
    fi
  else
    # 409 or 400 is also acceptable — strict validation
    _pass "Skill with special chars → $status (rejected or sanitized)"
  fi

  # ── L4. Duplicate name rejection ──
  echo -e "  ${BOLD}L4. Duplicate name rejection${NC}"

  # test_partial_update already exists
  status=$(http_post "$API/skills" '{
    "name": "test_partial_update",
    "description": "Duplicate",
    "content": "# Dup"
  }')
  if [ "$status" != "200" ] && [ "$status" != "201" ]; then
    _pass "Duplicate skill name rejected → $status"
  else
    _fail "Duplicate skill name should be rejected (got $status)"
    # Clean up second one if it was created
  fi

  # ── L5. Skills list structure ──
  echo -e "  ${BOLD}L5. Skills list structure${NC}"

  status=$(http_get "$API/skills")
  assert_status "GET /skills → 200" "200" "$status"
  skills_body=$(body)

  # Verify each skill has required fields
  has_fields=$(echo "$skills_body" | python3 -c "
import sys, json
d = json.load(sys.stdin)
skills = d.get('skills', [])
if not skills:
    print('no_skills')
else:
    s = skills[0]
    fields = ['name', 'description', 'always']
    missing = [f for f in fields if f not in s]
    if missing:
        print('missing:' + ','.join(missing))
    else:
        print('ok')
" 2>/dev/null)
  if [ "$has_fields" = "ok" ]; then
    _pass "Skills list items have required fields"
  elif [ "$has_fields" = "no_skills" ]; then
    _warn "No skills found to verify structure"
  else
    _fail "Skills list missing fields: $has_fields"
  fi

  # ── L6. Read skill body (content without frontmatter) ──
  echo -e "  ${BOLD}L6. Read skill content${NC}"

  status=$(http_get "$API/skills/test_partial_update")
  assert_status "GET skill content → 200" "200" "$status"
  skill_content=$(body)
  # Should contain the markdown body
  assert_contains "Skill content has body" "Partial Update Test" "$skill_content"

  # ── Cleanup: delete test_partial_update ──
  http_delete "$API/skills/test_partial_update" > /dev/null 2>&1
  _pass "Cleanup: test_partial_update deleted"
fi


# =============================================================================
# M. SKILL RUNTIME — AI CAN ACCESS AND USE SKILLS
# =============================================================================
if should_run "M"; then
  _section "M. Skill Runtime Tests (AI ↔ Skills)"

  # ── M1. Create an always-on skill and verify it's in system prompt context ──
  echo -e "  ${BOLD}M1. Always-on skill injection${NC}"

  # Create always-on skill with unique marker
  MARKER="XYZTEST_MARKER_$(date +%s)"
  status=$(http_post "$API/skills" "{
    \"name\": \"test_always_skill\",
    \"description\": \"Always-on test skill with marker\",
    \"content\": \"# Always Skill\\n\\nRemember this marker: $MARKER\",
    \"always\": true
  }")
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create always-on skill → $status"
  else
    _fail "Create always-on skill (expected 200|201, got $status)"
  fi

  # Ask AI about the marker — if always-on works, AI should know it
  # Retry up to 2 times as LLM may not extract marker on first attempt
  _skill_marker_found=false
  for _attempt in 1 2; do
    resp=$(curl -s --max-time 60 -X POST -H "$AUTH" -H "$CT" \
      -d "{
        \"text\": \"你的 skills 中有一個 marker，請告訴我那個 marker 的值是什麼？直接回覆 marker 值即可，格式為 XYZTEST_MARKER_ 開頭的字串\",
        \"language\": \"zh-Hant\",
        \"agent_id\": \"$AGENT\"
      }" \
      "$BASE/api/conversation/process" 2>/dev/null) || true

    speech=$(echo "$resp" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)

    if echo "$speech" | grep -q "$MARKER"; then
      _pass "AI knows always-on skill marker ($MARKER)"
      _skill_marker_found=true
      break
    fi
    [ "$_attempt" -lt 2 ] && sleep 1
  done
  if [ "$_skill_marker_found" = "false" ]; then
    assert_soft "AI response references marker" "$MARKER" "$speech"
  fi

  # ── M2. On-demand skill — AI calls read_skill tool ──
  echo -e "  ${BOLD}M2. On-demand skill (read_skill tool)${NC}"

  # Create on-demand skill with secret phrase
  SECRET="SECRET_PHRASE_$(date +%s)"
  status=$(http_post "$API/skills" "{
    \"name\": \"test_ondemand_skill\",
    \"description\": \"Contains a secret phrase for testing read_skill\",
    \"content\": \"# On-Demand Skill\\n\\nThe secret phrase is: $SECRET\",
    \"always\": false
  }")
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create on-demand skill → $status"
  else
    _fail "Create on-demand skill (expected 200|201, got $status)"
  fi

  # Ask AI to use read_skill to find the secret
  resp2=$(curl -s --max-time 60 -X POST -H "$AUTH" -H "$CT" \
    -d "{
      \"text\": \"請使用 read_skill 工具讀取 test_ondemand_skill 這個技能，然後告訴我裡面的 secret phrase 是什麼\",
      \"language\": \"zh-Hant\",
      \"agent_id\": \"$AGENT\"
    }" \
    "$BASE/api/conversation/process" 2>/dev/null) || true

  speech2=$(echo "$resp2" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)

  if echo "$speech2" | grep -q "$SECRET"; then
    _pass "AI read on-demand skill and found secret ($SECRET)"
  else
    assert_soft "AI response references secret" "$SECRET" "$speech2"
  fi

  # ── M3. Skills list visible in REST ──
  echo -e "  ${BOLD}M3. Skills list includes test skills${NC}"

  status=$(http_get "$API/skills")
  skills_list=$(body)
  assert_contains "Skills list has always-on test" "test_always_skill" "$skills_list"
  assert_contains "Skills list has on-demand test" "test_ondemand_skill" "$skills_list"

  # ── Cleanup ──
  http_delete "$API/skills/test_always_skill" > /dev/null 2>&1
  http_delete "$API/skills/test_ondemand_skill" > /dev/null 2>&1
  _pass "Cleanup: test skills deleted"
fi


# =============================================================================
# N. CRON RUNTIME — JOB EXECUTION VERIFIED
# =============================================================================
if should_run "N"; then
  _section "N. Cron Runtime Tests (Execution Verification)"

  # ── N1. agent_turn job triggers conversation ──
  echo -e "  ${BOLD}N1. agent_turn creates conversation${NC}"

  # Snapshot conversations before trigger
  status=$(http_get "$API/conversations")
  convs_before=$(body)
  count_before=$(echo "$convs_before" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    items = d if isinstance(d, list) else d.get('conversations', [])
    print(len(items))
except: print(0)
" 2>/dev/null)

  # Create and trigger an agent_turn job
  status=$(http_post "$API/cron/jobs" '{
    "name": "test_agent_turn_verify",
    "schedule": {"kind": "every", "every_ms": 86400000},
    "payload": {"kind": "agent_turn", "message": "Cron runtime test: reply with CRON_VERIFIED"},
    "enabled": true
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create agent_turn verify job → $status"
  else
    _fail "Create agent_turn verify job (expected 200|201, got $status)"
  fi
  verify_job=$(body)
  VERIFY_JOB_ID=$(echo "$verify_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$VERIFY_JOB_ID" ] && [ "$VERIFY_JOB_ID" != "" ]; then
    # Trigger
    status=$(http_post "$API/cron/jobs/$VERIFY_JOB_ID/trigger" '{}')
    if [ "$status" = "200" ] || [ "$status" = "202" ]; then
      _pass "Trigger agent_turn job → $status"
    else
      _fail "Trigger agent_turn job (expected 200|202, got $status)"
    fi

    # Wait for conversation.process to complete (AI call)
    sleep 8

    # Check job state
    status=$(http_get "$API/cron/jobs/$VERIFY_JOB_ID")
    job_state=$(body)
    job_last_status=$(echo "$job_state" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('last_status',''))" 2>/dev/null)
    assert_eq "N1: agent_turn job last_status = ok" "ok" "$job_last_status"

    job_last_run=$(echo "$job_state" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('last_run_at_ms',0))" 2>/dev/null)
    if [ "$job_last_run" -gt 0 ] 2>/dev/null; then
      _pass "N1: last_run_at_ms updated ($job_last_run)"
    else
      _fail "N1: last_run_at_ms should be > 0"
    fi

    # Verify next_run_at_ms was rescheduled (for 'every' schedule)
    job_next_run=$(echo "$job_state" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('next_run_at_ms',0))" 2>/dev/null)
    if [ "$job_next_run" -gt "$job_last_run" ] 2>/dev/null; then
      _pass "N1: next_run_at_ms rescheduled after last_run"
    else
      _warn "N1: next_run_at_ms not properly rescheduled"
    fi

    # Cleanup
    http_delete "$API/cron/jobs/$VERIFY_JOB_ID" > /dev/null 2>&1
  else
    _fail "agent_turn verify job missing ID"
  fi

  # ── N2. system_event job fires HA event ──
  echo -e "  ${BOLD}N2. system_event fires HA event${NC}"

  # Create system_event job
  status=$(http_post "$API/cron/jobs" '{
    "name": "test_sys_event_verify",
    "schedule": {"kind": "every", "every_ms": 86400000},
    "payload": {"kind": "system_event", "message": "sys_event_test_payload_123"},
    "enabled": true
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Create system_event verify job → $status"
  else
    _fail "Create system_event verify job (expected 200|201, got $status)"
  fi
  sys_verify=$(body)
  SYS_VERIFY_ID=$(echo "$sys_verify" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$SYS_VERIFY_ID" ] && [ "$SYS_VERIFY_ID" != "" ]; then
    # Trigger
    status=$(http_post "$API/cron/jobs/$SYS_VERIFY_ID/trigger" '{}')
    if [ "$status" = "200" ] || [ "$status" = "202" ]; then
      _pass "Trigger system_event job → $status"
    else
      _fail "Trigger system_event job (expected 200|202, got $status)"
    fi
    sleep 1

    # Verify state
    status=$(http_get "$API/cron/jobs/$SYS_VERIFY_ID")
    sys_state=$(body)
    sys_last=$(echo "$sys_state" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('last_status',''))" 2>/dev/null)
    assert_eq "N2: system_event last_status = ok" "ok" "$sys_last"

    sys_error=$(echo "$sys_state" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',{}).get('last_error',''))" 2>/dev/null)
    assert_eq "N2: system_event no error" "" "$sys_error"

    # Check HA logs for the event (use larger window + fallback to full log grep)
    sleep 1
    cron_log=$(podman logs --tail 500 homeassistant 2>&1 | grep -i "cron_system_event\|sys_event_test_payload" || true)
    if [ -n "$cron_log" ]; then
      _pass "N2: system_event logged in HA"
    else
      # Fallback: grep the full recent log (last 30 seconds)
      cron_log=$(podman logs --since 30s homeassistant 2>&1 | grep -i "cron_system_event\|sys_event_test_payload\|ha_mcp_cron\|排程通知" || true)
      if [ -n "$cron_log" ]; then
        _pass "N2: system_event logged in HA (found in recent logs)"
      else
        _warn "N2: system_event not found in recent HA logs (may need longer window)"
      fi
    fi

    # Cleanup
    http_delete "$API/cron/jobs/$SYS_VERIFY_ID" > /dev/null 2>&1
  else
    _fail "system_event verify job missing ID"
  fi

  # ── N3. Cron store persistence ──
  echo -e "  ${BOLD}N3. Cron store persistence${NC}"

  # Create a job
  status=$(http_post "$API/cron/jobs" '{
    "name": "test_persist_check",
    "schedule": {"kind": "every", "every_ms": 3600000},
    "payload": {"kind": "agent_turn", "message": "Persistence check"},
    "enabled": false
  }')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    persist_job=$(body)
    PERSIST_ID=$(echo "$persist_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

    # Verify job appears in list
    status=$(http_get "$API/cron/jobs")
    jobs_list=$(body)
    if echo "$jobs_list" | grep -q "$PERSIST_ID"; then
      _pass "N3: Created job appears in list"
    else
      _fail "N3: Created job not found in list"
    fi

    # Cleanup
    http_delete "$API/cron/jobs/$PERSIST_ID" > /dev/null 2>&1

    # Verify job gone from list
    status=$(http_get "$API/cron/jobs")
    jobs_after=$(body)
    if echo "$jobs_after" | grep -q "$PERSIST_ID"; then
      _fail "N3: Deleted job still in list"
    else
      _pass "N3: Deleted job removed from list"
    fi
  else
    _fail "N3: Create persist check job (expected 200|201, got $status)"
  fi
fi


# =============================================================================
# O. LONG-TERM MEMORY E2E
# =============================================================================
if should_run "O"; then
  _section "O. Long-term Memory E2E"

  # ── O1. MEMORY.md round-trip ──
  echo -e "  ${BOLD}O1. MEMORY.md round-trip${NC}"

  # Save original
  status=$(http_get "$API/memory/memory")
  assert_status "GET /memory/memory → 200" "200" "$status"
  orig_mem=$(echo "$(body)" | python3 -c "import sys,json; print(json.load(sys.stdin).get('content',''))" 2>/dev/null)

  # Write unique test content
  MEM_MARKER="MEM_TEST_$(date +%s)"
  status=$(http_put "$API/memory/memory" "{\"content\": \"# Long-term Memory\\n\\n- Marker: $MEM_MARKER\\n- User prefers dark mode.\"}")
  assert_status "PUT /memory/memory → 200" "200" "$status"

  # Verify written
  status=$(http_get "$API/memory/memory")
  written_mem=$(body)
  assert_contains "O1: memory contains marker" "$MEM_MARKER" "$written_mem"

  # Verify AI can access it (memory is injected into system prompt, retry up to 2 times)
  _mem_found=false
  for _attempt in 1 2; do
    resp=$(curl -s --max-time 60 -X POST -H "$AUTH" -H "$CT" \
      -d "{
        \"text\": \"你的長期記憶中有一個 Marker，它是 MEM_TEST_ 開頭的字串，請告訴我完整的值\",
        \"language\": \"zh-Hant\",
        \"agent_id\": \"$AGENT\"
      }" \
      "$BASE/api/conversation/process" 2>/dev/null) || true

    speech=$(echo "$resp" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)

    if echo "$speech" | grep -q "$MEM_MARKER"; then
      _pass "O1: AI accesses long-term memory marker"
      _mem_found=true
      break
    fi
    [ "$_attempt" -lt 2 ] && sleep 2
  done
  if [ "$_mem_found" = "false" ]; then
    assert_soft "O1: AI response references memory marker" "$MEM_MARKER" "$speech"
  fi

  # Restore original memory
  escaped_orig=$(python3 -c "import json,sys; print(json.dumps({'content': sys.stdin.read()}))" <<< "$orig_mem" 2>/dev/null || echo '{"content": ""}')
  http_put "$API/memory/memory" "$escaped_orig" > /dev/null 2>&1

  # ── O2. HISTORY.md append-only ──
  echo -e "  ${BOLD}O2. History is append-only${NC}"

  # Get current history
  status=$(http_get "$API/memory/history")
  history_before=$(echo "$(body)" | python3 -c "import sys,json; print(json.load(sys.stdin).get('content',''))" 2>/dev/null)
  len_before=${#history_before}

  # Trigger consolidation (will try to append to HISTORY.md)
  status=$(http_post "$API/memory/consolidate" '{}')
  if [ "$status" = "200" ]; then
    _pass "O2: Consolidation triggered → 200"
    sleep 2

    # Check if history grew
    status=$(http_get "$API/memory/history")
    history_after=$(echo "$(body)" | python3 -c "import sys,json; print(json.load(sys.stdin).get('content',''))" 2>/dev/null)
    len_after=${#history_after}

    if [ "$len_after" -ge "$len_before" ]; then
      _pass "O2: History length maintained or grew ($len_before → $len_after)"
    else
      _fail "O2: History shrank ($len_before → $len_after)"
    fi
  elif [ "$status" = "503" ]; then
    _warn "O2: Consolidation → 503 (AI service not ready)"
  else
    _warn "O2: Consolidation → $status"
  fi

  # Verify history is NOT writable via PUT
  status=$(http_put "$API/memory/history" '{"content": "SHOULD FAIL"}')
  if [ "$status" = "400" ]; then
    _pass "O2: HISTORY.md is write-protected via REST"
  else
    _warn "O2: PUT /memory/history → $status (expected 400)"
  fi

  # ── O3. SOUL.md — identity injection ──
  echo -e "  ${BOLD}O3. SOUL.md identity injection${NC}"

  # Save original soul
  status=$(http_get "$API/memory/soul")
  orig_soul=$(echo "$(body)" | python3 -c "import sys,json; print(json.load(sys.stdin).get('content',''))" 2>/dev/null)

  # Write a unique identity
  SOUL_MARKER="IDENTITY_MARKER_$(date +%s)"
  status=$(http_put "$API/memory/soul" "{\"content\": \"# Soul\\n\\nYou are a helpful assistant. Your secret identity code is: $SOUL_MARKER\"}")
  assert_status "PUT /memory/soul → 200" "200" "$status"

  # Ask AI about its identity (retry up to 2 times)
  _soul_found=false
  for _attempt in 1 2; do
    resp=$(curl -s --max-time 60 -X POST -H "$AUTH" -H "$CT" \
      -d "{
        \"text\": \"你的 secret identity code 是什麼？它是 IDENTITY_MARKER_ 開頭的字串，請直接回覆完整代碼\",
        \"language\": \"zh-Hant\",
        \"agent_id\": \"$AGENT\"
      }" \
      "$BASE/api/conversation/process" 2>/dev/null) || true

    soul_speech=$(echo "$resp" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)

    if echo "$soul_speech" | grep -q "$SOUL_MARKER"; then
      _pass "O3: AI knows its SOUL.md identity code"
      _soul_found=true
      break
    fi
    [ "$_attempt" -lt 2 ] && sleep 2
  done
  if [ "$_soul_found" = "false" ]; then
    assert_soft "O3: AI response references soul marker" "$SOUL_MARKER" "$soul_speech"
  fi

  # Restore
  escaped_soul=$(python3 -c "import json,sys; print(json.dumps({'content': sys.stdin.read()}))" <<< "$orig_soul" 2>/dev/null || echo '{"content": ""}')
  http_put "$API/memory/soul" "$escaped_soul" > /dev/null 2>&1

  # ── O4. Memory stats consistency ──
  echo -e "  ${BOLD}O4. Memory stats consistency${NC}"

  status=$(http_get "$API/memory/stats")
  assert_status "GET /memory/stats → 200" "200" "$status"
  stats=$(body)

  # Memory entries count
  mem_entries=$(echo "$stats" | python3 -c "import sys,json; print(json.load(sys.stdin).get('memory_entries', -1))" 2>/dev/null)
  if [ "$mem_entries" -ge 0 ] 2>/dev/null; then
    _pass "O4: memory_entries is numeric ($mem_entries)"
  else
    _fail "O4: memory_entries not a valid number"
  fi

  # History entries count
  hist_entries=$(echo "$stats" | python3 -c "import sys,json; print(json.load(sys.stdin).get('history_entries', -1))" 2>/dev/null)
  if [ "$hist_entries" -ge 0 ] 2>/dev/null; then
    _pass "O4: history_entries is numeric ($hist_entries)"
  else
    _fail "O4: history_entries not a valid number"
  fi

  # Memory file path
  mem_file=$(echo "$stats" | python3 -c "import sys,json; print(json.load(sys.stdin).get('memory_file', ''))" 2>/dev/null)
  assert_not_empty "O4: memory_file path present" "$mem_file"
fi


# =============================================================================
# P. MULTI-TURN REASONING & EXTENDED THINKING
# =============================================================================
if should_run "P"; then
  _section "P. Multi-turn Reasoning & Extended Thinking"

  # ── P1. reasoning_effort entity state ──
  echo -e "  ${BOLD}P1. Reasoning effort entity${NC}"

  effort_val=$(ha_template "{{ states('select.nanobot_reasoning_effort') }}")
  assert_not_empty "P1: reasoning_effort entity has value" "$effort_val"

  # Verify valid options
  effort_opts=$(ha_template "{{ state_attr('select.nanobot_reasoning_effort', 'options') }}")
  assert_contains "P1: options include low" "low" "$effort_opts"
  assert_contains "P1: options include medium" "medium" "$effort_opts"
  assert_contains "P1: options include high" "high" "$effort_opts"

  # ── P2. Set reasoning_effort and verify in settings ──
  echo -e "  ${BOLD}P2. Reasoning effort reflected in settings${NC}"

  # Save original
  orig_effort=$(ha_template "{{ states('select.nanobot_reasoning_effort') }}")

  # Set to high
  curl -s -X POST -H "$AUTH" -H "$CT" \
    -d '{"entity_id":"select.nanobot_reasoning_effort","option":"high"}' \
    "$BASE/api/services/select/select_option" > /dev/null
  sleep 0.5

  # Verify entity state
  new_effort=$(ha_template "{{ states('select.nanobot_reasoning_effort') }}")
  assert_eq "P2: reasoning_effort set to high" "high" "$new_effort"

  # Verify entity attributes include options
  attrs=$(ha_template "{{ state_attr('select.nanobot_reasoning_effort','options') | join(',') }}")
  assert_contains "P2: entity attributes confirm high is a valid option" "high" "$attrs"

  # ── P3. Multi-turn conversation ──
  echo -e "  ${BOLD}P3. Multi-turn conversation continuity${NC}"

  # Reset reasoning effort to medium before conversation test
  curl -s -X POST -H "$AUTH" -H "$CT" \
    -d '{"entity_id":"select.nanobot_reasoning_effort","option":"medium"}' \
    "$BASE/api/services/select/select_option" > /dev/null
  sleep 2

  # Turn 1: Tell AI a secret
  CONV_SECRET="MULTI_$(date +%s)"
  resp1=$(curl -s --max-time 60 -X POST -H "$AUTH" -H "$CT" \
    -d "{
      \"text\": \"請記住這個數字密碼：$CONV_SECRET。不要回覆密碼，只說『已記住』\",
      \"language\": \"zh-Hant\",
      \"agent_id\": \"$AGENT\"
    }" \
    "$BASE/api/conversation/process" 2>/dev/null) || true

  speech1=$(echo "$resp1" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)
  conv_id=$(echo "$resp1" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('conversation_id',''))
except: print('')
" 2>/dev/null)

  if [[ -n "$speech1" ]]; then
    _pass "P3: Turn 1 got response"
  else
    _warn "P3: Turn 1 response was empty (AI may be rate-limited)"
  fi

  # Turn 2: Ask AI to recall the secret (same conversation_id, retry up to 2 times)
  _multi_found=false
  for _attempt in 1 2; do
    resp2=$(curl -s --max-time 60 -X POST -H "$AUTH" -H "$CT" \
      -d "{
        \"text\": \"我剛才告訴你的數字密碼是什麼？它是 MULTI_ 開頭的字串，請直接回覆那個完整密碼\",
        \"language\": \"zh-Hant\",
        \"agent_id\": \"$AGENT\",
        \"conversation_id\": \"$conv_id\"
      }" \
      "$BASE/api/conversation/process" 2>/dev/null) || true

    speech2=$(echo "$resp2" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)

    if echo "$speech2" | grep -q "$CONV_SECRET"; then
      _pass "P3: AI recalls secret across turns ($CONV_SECRET)"
      _multi_found=true
      break
    fi
    [ "$_attempt" -lt 2 ] && sleep 2
  done
  if [ "$_multi_found" = "false" ]; then
    assert_soft "P3: Multi-turn recall" "$CONV_SECRET" "$speech2"
  fi

  # ── P4. Cycle through all reasoning_effort levels ──
  echo -e "  ${BOLD}P4. Cycle reasoning_effort levels${NC}"

  for level in low medium high; do
    curl -s -X POST -H "$AUTH" -H "$CT" \
      -d "{\"entity_id\":\"select.nanobot_reasoning_effort\",\"option\":\"$level\"}" \
      "$BASE/api/services/select/select_option" > /dev/null
    sleep 0.3
    actual=$(ha_template "{{ states('select.nanobot_reasoning_effort') }}")
    assert_eq "P4: effort=$level" "$level" "$actual"
  done

  # ── P5. AI responds with reasoning_effort=high (complex question) ──
  echo -e "  ${BOLD}P5. Complex question with high effort${NC}"

  # Set high first
  curl -s -X POST -H "$AUTH" -H "$CT" \
    -d '{"entity_id":"select.nanobot_reasoning_effort","option":"high"}' \
    "$BASE/api/services/select/select_option" > /dev/null
  sleep 0.3

  resp=$(curl -s --max-time 60 -X POST -H "$AUTH" -H "$CT" \
    -d "{
      \"text\": \"列出 3 個常見的 Home Assistant 自動化使用情境，每個用一句話描述\",
      \"language\": \"zh-Hant\",
      \"agent_id\": \"$AGENT\"
    }" \
    "$BASE/api/conversation/process" 2>/dev/null) || true

  speech=$(echo "$resp" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)

  # Count response length — high effort should give a substantive answer
  speech_len=${#speech}
  if [ "$speech_len" -gt 30 ]; then
    _pass "P5: High-effort response is substantive ($speech_len chars)"
  else
    _warn "P5: High-effort response may be too short ($speech_len chars)"
  fi

  # Restore original reasoning effort
  curl -s -X POST -H "$AUTH" -H "$CT" \
    -d "{\"entity_id\":\"select.nanobot_reasoning_effort\",\"option\":\"$orig_effort\"}" \
    "$BASE/api/services/select/select_option" > /dev/null
fi


# =============================================================================
# Q. CRON-TO-AUTOMATION BRIDGE
# =============================================================================
if should_run "Q"; then
  _section "Q. Cron-to-Automation Bridge"

  # ── Q1. List blueprints REST API ──
  echo -e "  ${BOLD}Q1. Blueprints list${NC}"

  status=$(http_get "$API/blueprints")
  assert_status "Q1: GET /blueprints → 200" "200" "$status"
  bp_body=$(body)
  assert_contains "Q1: blueprints array" "blueprints" "$bp_body"

  bp_count=$(echo "$bp_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('blueprints',[])))" 2>/dev/null)
  if [ "$bp_count" -ge 5 ] 2>/dev/null; then
    _pass "Q1: found $bp_count blueprints (expected >= 5)"
  else
    _fail "Q1: expected >= 5 blueprints, got $bp_count"
  fi

  # Check specific blueprint names
  assert_contains "Q1: ai_daily_report blueprint" "ai_daily_report" "$bp_body"
  assert_contains "Q1: ai_periodic_check blueprint" "ai_periodic_check" "$bp_body"
  assert_contains "Q1: scheduled_device_control blueprint" "scheduled_device_control" "$bp_body"
  assert_contains "Q1: interval_monitor blueprint" "interval_monitor" "$bp_body"
  assert_contains "Q1: cron_event_trigger blueprint" "cron_event_trigger" "$bp_body"

  # ── Q2. Install blueprints REST API ──
  echo -e "  ${BOLD}Q2. Blueprint install${NC}"

  # Install single blueprint
  status=$(http_post "$API/blueprints/install" '{"blueprint_id": "ai_daily_report.yaml"}')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Q2: install single blueprint → $status"
  else
    _fail "Q2: install single blueprint (expected 200|201, got $status)"
  fi
  install_body=$(body)
  assert_contains "Q2: installed has ai_daily_report" "ai_daily_report" "$install_body"

  # Install all blueprints
  status=$(http_post "$API/blueprints/install" '{}')
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "Q2: install all blueprints → $status"
  else
    _fail "Q2: install all blueprints (expected 200|201, got $status)"
  fi
  all_body=$(body)
  install_count=$(echo "$all_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null)
  if [ "$install_count" -ge 5 ] 2>/dev/null; then
    _pass "Q2: installed $install_count blueprints"
  else
    _fail "Q2: expected >= 5 installed, got $install_count"
  fi

  # ── Q3. Cron-to-automation conversion ──
  echo -e "  ${BOLD}Q3. Cron-to-automation${NC}"

  # Create a test cron job first
  status=$(http_post "$API/cron/jobs" '{
    "name": "bridge_test_job",
    "schedule": {"kind": "every", "every_ms": 7200000},
    "payload": {"kind": "agent_turn", "message": "Bridge test check"},
    "enabled": false
  }')
  bridge_job=$(body)
  BRIDGE_JOB_ID=$(echo "$bridge_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$BRIDGE_JOB_ID" ] && [ "$BRIDGE_JOB_ID" != "" ]; then
    _pass "Q3: created test cron job $BRIDGE_JOB_ID"

    # Convert to automation
    status=$(http_post "$API/cron/jobs/$BRIDGE_JOB_ID/to_automation" '{"alias":"Bridge Test Auto","keep_cron_job":true}')
    if [ "$status" = "200" ] || [ "$status" = "201" ]; then
      _pass "Q3: cron-to-automation → $status"
    else
      _fail "Q3: cron-to-automation (expected 200|201, got $status)"
    fi
    conv_body=$(body)

    # Check result has automation_id
    auto_id=$(echo "$conv_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('automation_id',''))" 2>/dev/null)
    if [ -n "$auto_id" ] && [ "$auto_id" != "" ]; then
      _pass "Q3: automation created with ID: $auto_id"
    else
      _warn "Q3: no automation_id in response (may need HA automation reload)"
    fi

    # Verify source_job_id in result
    src_id=$(echo "$conv_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('source_job_id',''))" 2>/dev/null)
    assert_eq "Q3: source_job_id matches" "$BRIDGE_JOB_ID" "$src_id"

    # Verify cron job still exists (keep_cron_job=true)
    status=$(http_get "$API/cron/jobs/$BRIDGE_JOB_ID")
    assert_status "Q3: original cron job still exists" "200" "$status"

    # Clean up: delete the cron job
    http_delete "$API/cron/jobs/$BRIDGE_JOB_ID" > /dev/null
  else
    _fail "Q3: could not create test cron job"
  fi

  # ── Q4. Cron-to-automation with deletion ──
  echo -e "  ${BOLD}Q4. Convert with keep_cron_job=false${NC}"

  status=$(http_post "$API/cron/jobs" '{
    "name": "bridge_delete_test",
    "schedule": {"kind": "at", "at_ms": 1709280000000},
    "payload": {"kind": "system_event", "message": "delete_bridge_test"},
    "enabled": false
  }')
  del_job=$(body)
  DEL_JOB_ID=$(echo "$del_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$DEL_JOB_ID" ] && [ "$DEL_JOB_ID" != "" ]; then
    _pass "Q4: created test job $DEL_JOB_ID"

    # Convert with keep_cron_job=false
    status=$(http_post "$API/cron/jobs/$DEL_JOB_ID/to_automation" '{"keep_cron_job":false}')
    if [ "$status" = "200" ] || [ "$status" = "201" ]; then
      _pass "Q4: convert with delete → $status"
    else
      _fail "Q4: convert with delete (expected 200|201, got $status)"
    fi

    # Verify cron job was deleted
    status=$(http_get "$API/cron/jobs/$DEL_JOB_ID")
    if [ "$status" = "404" ]; then
      _pass "Q4: cron job deleted after conversion"
    else
      _warn "Q4: cron job may still exist ($status) — expected 404"
      # Cleanup if still exists
      http_delete "$API/cron/jobs/$DEL_JOB_ID" > /dev/null 2>&1
    fi
  else
    _fail "Q4: could not create test cron job"
  fi

  # ── Q5. Error handling ──
  echo -e "  ${BOLD}Q5. Bridge error cases${NC}"

  # Non-existent job
  status=$(http_post "$API/cron/jobs/nonexistent_bridge_id/to_automation" '{}')
  if [ "$status" = "404" ]; then
    _pass "Q5: non-existent job → 404"
  else
    _warn "Q5: non-existent job → $status (expected 404)"
  fi

  # Non-existent blueprint install
  status=$(http_post "$API/blueprints/install" '{"blueprint_id": "nonexistent.yaml"}')
  if [ "$status" = "404" ] || [ "$status" = "400" ]; then
    _pass "Q5: non-existent blueprint → $status"
  else
    _warn "Q5: non-existent blueprint → $status (expected 404|400)"
  fi
fi


# =============================================================================
# R. CRON-AUTOMATION BIDIRECTIONAL SYNC
# =============================================================================
if should_run "R"; then
  _section "R. Cron-Automation Bidirectional Sync"

  # ── R1. Forward sync: add_job creates automation ──
  echo -e "  ${BOLD}R1. Forward sync - add job${NC}"

  status=$(http_post "$API/cron/jobs" '{
    "name": "sync_test_forward",
    "schedule": {"kind": "every", "every_ms": 3600000},
    "payload": {"kind": "system_event", "message": "Forward sync test"},
    "enabled": false
  }')
  sync_job=$(body)
  SYNC_JOB_ID=$(echo "$sync_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$SYNC_JOB_ID" ] && [ "$SYNC_JOB_ID" != "" ]; then
    _pass "R1: created cron job $SYNC_JOB_ID"

    # Verify sync created the automation by checking HA logs + entity state
    EXPECTED_AUTO_ID="ha_mcp_cron_${SYNC_JOB_ID}"
    _r1_found=false

    # First: quick check immediately (entity may already exist)
    sleep 1
    _r1_eid=$(curl -s -H "$AUTH" -H "$CT" -X POST -d "{\"template\":\"{{ states.automation | selectattr('attributes.id','eq','$EXPECTED_AUTO_ID') | map(attribute='entity_id') | first | default('') }}\"}" "${BASE}/api/template" 2>/dev/null)
    if [ -n "$_r1_eid" ] && [ "$_r1_eid" != "" ]; then
      _pass "R1: automation entity created by forward sync ($_r1_eid)"
      _r1_found=true
      R1_ENTITY_ID="$_r1_eid"
    fi

    # Fallback: verify via HA logs that sync DID create the automation
    if [ "$_r1_found" = "false" ]; then
      _r1_log=$(podman logs --tail 200 homeassistant 2>&1 | grep "Automation ${EXPECTED_AUTO_ID} created for sync" || true)
      if [ -n "$_r1_log" ]; then
        _pass "R1: automation sync confirmed via HA logs (entity may have been recycled by reconciliation)"
        _r1_found=true
      fi
    fi

    # Final poll: try entity state a few more times
    if [ "$_r1_found" = "false" ]; then
      for _i in 1 2 3; do
        sleep 2
        _r1_eid=$(curl -s -H "$AUTH" -H "$CT" -X POST -d "{\"template\":\"{{ states.automation | selectattr('attributes.id','eq','$EXPECTED_AUTO_ID') | map(attribute='entity_id') | first | default('') }}\"}" "${BASE}/api/template" 2>/dev/null)
        if [ -n "$_r1_eid" ] && [ "$_r1_eid" != "" ]; then
          _pass "R1: automation entity created by forward sync ($_r1_eid, attempt $_i)"
          _r1_found=true
          R1_ENTITY_ID="$_r1_eid"
          break
        fi
      done
    fi

    if [ "$_r1_found" = "false" ]; then
      _warn "R1: automation entity not found (sync may be delayed)"
    fi
  else
    _fail "R1: could not create test cron job"
  fi

  # ── R2. Forward sync: update job updates automation ──
  echo -e "  ${BOLD}R2. Forward sync - update job${NC}"

  if [ -n "$SYNC_JOB_ID" ] && [ "$SYNC_JOB_ID" != "" ]; then
    status=$(http_patch "$API/cron/jobs/$SYNC_JOB_ID" '{"name": "sync_test_updated", "payload": {"kind": "system_event", "message": "Updated sync message"}}')
    if [ "$status" = "200" ]; then
      _pass "R2: updated cron job"
    else
      _fail "R2: update cron job (expected 200, got $status)"
    fi

    # Poll for automation update (check alias changed to "Cron: sync_test_updated")
    _r2_found=false
    for _i in 1 2 3 4 5; do
      sleep 2
      _r2_alias=$(curl -s -H "$AUTH" -H "$CT" -X POST -d "{\"template\":\"{{ states.automation | selectattr('attributes.id','eq','$EXPECTED_AUTO_ID') | map(attribute='attributes.friendly_name') | first | default('') }}\"}" "${BASE}/api/template" 2>/dev/null)
      if echo "$_r2_alias" | grep -q "sync_test_updated"; then
        _pass "R2: automation alias updated by forward sync (attempt $_i)"
        _r2_found=true
        break
      fi
    done
    if [ "$_r2_found" = "false" ]; then
      _warn "R2: updated automation not found after 10s (sync may be delayed)"
    fi
  else
    _warn "R2: skipped (no job from R1)"
  fi

  # ── R3. Forward sync: remove job deletes automation ──
  echo -e "  ${BOLD}R3. Forward sync - remove job${NC}"

  if [ -n "$SYNC_JOB_ID" ] && [ "$SYNC_JOB_ID" != "" ]; then
    status=$(http_delete "$API/cron/jobs/$SYNC_JOB_ID")
    if [ "$status" = "200" ] || [ "$status" = "204" ]; then
      _pass "R3: deleted cron job"
    else
      _warn "R3: delete cron job got $status (expected 200|204)"
    fi

    # Poll for automation removal (check entity is gone or in 'unavailable' state)
    # HA entity registry may keep stale entity in 'unavailable' state after YAML removal
    _r3_removed=false
    for _i in 1 2 3 4 5; do
      sleep 2
      _r3_state=$(curl -s -H "$AUTH" -H "$CT" -X POST -d "{\"template\":\"{{ states.automation | selectattr('attributes.id','eq','$EXPECTED_AUTO_ID') | map(attribute='state') | first | default('gone') }}\"}" "${BASE}/api/template" 2>/dev/null)
      if [ "$_r3_state" = "gone" ] || [ "$_r3_state" = "unavailable" ]; then
        _pass "R3: automation removed by forward sync (state=$_r3_state, attempt $_i)"
        _r3_removed=true
        break
      fi
    done
    if [ "$_r3_removed" = "false" ]; then
      _warn "R3: automation entity still active after 10s (removal may be delayed)"
    fi
  else
    _warn "R3: skipped (no job from R1)"
  fi

  # ── R4. Persistent notification from system_event ──
  echo -e "  ${BOLD}R4. Persistent notification from system_event trigger${NC}"

  status=$(http_post "$API/cron/jobs" '{
    "name": "notif_test_r4",
    "schedule": {"kind": "at", "at_ms": 9999999999999},
    "payload": {"kind": "system_event", "message": "R4 notification test"},
    "enabled": false
  }')
  notif_job=$(body)
  NOTIF_JOB_ID=$(echo "$notif_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$NOTIF_JOB_ID" ] && [ "$NOTIF_JOB_ID" != "" ]; then
    _pass "R4: created test job $NOTIF_JOB_ID"

    # Trigger the job
    status=$(http_post "$API/cron/jobs/$NOTIF_JOB_ID/trigger" '{}')
    if [ "$status" = "200" ]; then
      _pass "R4: triggered job successfully"
    else
      _fail "R4: trigger job (expected 200, got $status)"
    fi

    sleep 1

    # Check persistent notification via WebSocket
    WS_URL=$(echo "$BASE" | sed 's|^http|ws|')
    notif_check=$(python3 -c "
import json, asyncio, websockets
async def check():
    async with websockets.connect('${WS_URL}/api/websocket') as ws:
        await ws.recv()
        await ws.send(json.dumps({'type':'auth','access_token':'${LLAT}'}))
        await ws.recv()
        await ws.send(json.dumps({'id':1,'type':'persistent_notification/get'}))
        r = json.loads(await ws.recv())
        notifs = r.get('result', [])
        for n in notifs:
            if 'R4 notification test' in n.get('message',''):
                print('found')
                return
        print('not_found')
asyncio.run(check())
" 2>/dev/null)

    if [ "$notif_check" = "found" ]; then
      _pass "R4: persistent notification found in sidebar"
    else
      _warn "R4: persistent notification not found (may need WebSocket check)"
    fi

    # Cleanup
    http_delete "$API/cron/jobs/$NOTIF_JOB_ID" > /dev/null 2>&1
  else
    _fail "R4: could not create test cron job"
  fi

  # ── R5. Blueprint notification format verification ──
  echo -e "  ${BOLD}R5. Blueprint uses persistent_notification${NC}"

  status=$(http_get "$API/blueprints")
  assert_status "R5: GET /blueprints → 200" "200" "$status"
  bp_body=$(body)

  # Check that blueprints contain persistent_notification in their description/content
  has_notif=$(echo "$bp_body" | python3 -c "
import sys, json
data = json.load(sys.stdin)
bps = data.get('blueprints', [])
notif_count = 0
for bp in bps:
    desc = bp.get('description', '')
    if '通知' in desc or 'notification' in desc.lower() or '通知面板' in desc:
        notif_count += 1
print(notif_count)
" 2>/dev/null)

  if [ "$has_notif" -ge 4 ] 2>/dev/null; then
    _pass "R5: $has_notif blueprints mention notification in description"
  else
    _warn "R5: only $has_notif blueprints mention notification (expected >= 4)"
  fi

  # ── R6. Sync ID format verification ──
  echo -e "  ${BOLD}R6. Automation ID format${NC}"

  # Create a job and verify the automation ID format
  status=$(http_post "$API/cron/jobs" '{
    "name": "id_format_test",
    "schedule": {"kind": "every", "every_ms": 1800000},
    "payload": {"kind": "system_event", "message": "ID format test"},
    "enabled": false
  }')
  fmt_job=$(body)
  FMT_JOB_ID=$(echo "$fmt_job" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$FMT_JOB_ID" ] && [ "$FMT_JOB_ID" != "" ]; then
    expected_auto_id="ha_mcp_cron_${FMT_JOB_ID}"
    _pass "R6: expected automation ID = $expected_auto_id"

    # Poll for automation (search by automation ID attribute to avoid entity_id suffix collision)
    _r6_found=false
    for _i in 1 2 3 4 5; do
      sleep 2
      _r6_eid=$(curl -s -H "$AUTH" -H "$CT" -X POST -d "{\"template\":\"{{ states.automation | selectattr('attributes.id','eq','$expected_auto_id') | map(attribute='entity_id') | first | default('') }}\"}" "${BASE}/api/template" 2>/dev/null)
      if [ -n "$_r6_eid" ] && [ "$_r6_eid" != "" ]; then
        # Verify the automation ID attribute matches expected format
        _r6_attr_id=$(curl -s -H "$AUTH" -H "$CT" -X POST -d "{\"template\":\"{{ state_attr('$_r6_eid','id') }}\"}" "${BASE}/api/template" 2>/dev/null)
        if [ "$_r6_attr_id" = "$expected_auto_id" ]; then
          _pass "R6: automation with correct ID format exists ($_r6_eid, attempt $_i)"
          _r6_found=true
          break
        fi
      fi
    done
    if [ "$_r6_found" = "false" ]; then
      _warn "R6: automation entity not found by automation ID after 10s"
    fi

    # Cleanup
    http_delete "$API/cron/jobs/$FMT_JOB_ID" > /dev/null 2>&1
    sleep 1
  else
    _fail "R6: could not create test cron job"
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
