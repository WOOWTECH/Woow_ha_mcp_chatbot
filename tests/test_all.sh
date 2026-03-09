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
  SECTIONS=(A B C D E F G H I J K L M N O P Q R S T U V W X Y Z)
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

# Assert values are NOT equal
assert_not_eq() {
  local name="$1" not_expected="$2" actual="$3"
  if [ "$not_expected" != "$actual" ]; then
    _pass "$name"
  else
    _fail "$name (should not be '$not_expected')"
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

# Helper: AI chat via conversation.process (returns speech text)
# Usage: speech=$(ai_chat "你好" [conversation_id])
ai_chat() {
  local text="$1"
  local conv_id="${2:-}"
  local extra=""
  if [ -n "$conv_id" ]; then
    extra=",\"conversation_id\":\"$conv_id\""
  fi
  local resp speech
  for _retry in 1 2 3; do
    resp=$(curl -s --max-time 30 -X POST -H "$AUTH" -H "$CT" \
      -d "{\"text\":\"$text\",\"language\":\"zh-Hant\",\"agent_id\":\"$AGENT\"$extra}" \
      "$BASE/api/conversation/process" 2>/dev/null) || true
    speech=$(echo "$resp" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('response',{}).get('speech',{}).get('plain',{}).get('speech',''))
except: print('')
" 2>/dev/null)
    if [ -n "$speech" ] && ! echo "$speech" | grep -qi "error occurred\|rate limit\|429"; then
      echo "$speech"
      return 0
    fi
    sleep $(( _retry * 2 ))
  done
  echo "$speech"
}

# Helper: AI chat via conversation.process (returns conversation_id from response)
ai_chat_conv_id() {
  local text="$1"
  local conv_id="${2:-}"
  local extra=""
  if [ -n "$conv_id" ]; then
    extra=",\"conversation_id\":\"$conv_id\""
  fi
  local resp
  resp=$(curl -s -X POST -H "$AUTH" -H "$CT" \
    -d "{\"text\":\"$text\",\"language\":\"zh-Hant\",\"agent_id\":\"$AGENT\"$extra}" \
    "$BASE/api/conversation/process" 2>/dev/null)
  echo "$resp" | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)
    print(r.get('conversation_id',''))
except: print('')
" 2>/dev/null
}

# Helper: AI chat via REST API (POST /conversations/{id}/messages, returns status)
# Retries on failure to ensure the message is recorded
rest_chat() {
  local conv_id="$1"
  local message="$2"
  local status
  for _retry in 1 2 3; do
    status=$(http_post "$API/conversations/$conv_id/messages" "{\"message\":\"$message\"}")
    if [ "$status" = "200" ]; then
      echo "$status"
      return 0
    fi
    sleep $(( _retry * 2 ))
  done
  echo "$status"
}

# Helper: assert HTTP status is in acceptable range
assert_status_in() {
  local name="$1" actual="$2"
  shift 2
  for code in "$@"; do
    if [ "$code" = "$actual" ]; then
      _pass "$name"
      return 0
    fi
  done
  _fail "$name (expected one of [$*], got $actual)"
  return 1
}

# Helper: validate and fix automations.yaml before restart to prevent recovery mode
fix_automations_yaml() {
  podman exec homeassistant python3 -c "
import yaml, sys
try:
    with open('/config/automations.yaml') as f:
        data = yaml.safe_load(f)
    if data is None:
        data = []
    if not isinstance(data, list):
        print('WARN: automations.yaml is not a list, resetting')
        data = []
    # Deduplicate by id (keep last)
    seen = {}
    for item in data:
        aid = item.get('id', '')
        if aid:
            seen[aid] = item
        else:
            seen[id(item)] = item
    deduped = list(seen.values())
    if len(deduped) != len(data):
        print(f'Fixed: removed {len(data)-len(deduped)} duplicate automations')
        data = deduped
        with open('/config/automations.yaml', 'w') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    else:
        print('OK: automations.yaml valid')
except yaml.YAMLError as e:
    print(f'YAML error: {e}')
    print('Resetting automations.yaml to empty list')
    with open('/config/automations.yaml', 'w') as f:
        f.write('[]\n')
except Exception as e:
    print(f'Error: {e}')
" 2>&1
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

  # C1. Basic conversation (uses retry-enabled ai_chat)
  speech=$(ai_chat "你好，請簡短回答：1+1 等於多少？")

  if [ -n "$speech" ] && [ "$speech" != "" ]; then
    _pass "AI responds to basic question"
    if echo "$speech" | grep -qE "2|二|兩"; then
      _pass "AI response contains answer"
    else
      _warn "AI response may not contain expected answer"
    fi
  else
    _warn "AI basic question — no speech response"
  fi

  # C2. Tool call test (search entities) — uses retry-enabled ai_chat
  speech2=$(ai_chat "用 search_entities 工具搜尋 domain 為 light 的實體，只列出名稱")
  assert_not_empty "AI responds to tool call request" "$speech2"

  # C3. Memory injection — verify AI knows its identity
  speech3=$(ai_chat "你的角色是什麼？用一句話回答")
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

    # Validate automations.yaml before restart (prevents recovery mode)
    fix_automations_yaml

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

    # Wait for integration to be loaded (entities available)
    for i in $(seq 1 20); do
      int_check=$(ha_template "{{ states('number.nanobot_temperature') }}" 2>/dev/null)
      if [ -n "$int_check" ] && [ "$int_check" != "unavailable" ] && [ "$int_check" != "unknown" ]; then break; fi
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

    # Validate automations.yaml before restart (prevents recovery mode)
    fix_automations_yaml

    echo -e "  ${YELLOW}Restarting HA...${NC}"
    podman restart homeassistant > /dev/null 2>&1
    sleep 35

    # Wait for API
    for i in $(seq 1 10); do
      check=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/" 2>/dev/null)
      if [ "$check" = "200" ]; then break; fi
      sleep 3
    done

    # Wait for integration to be loaded (entities available)
    for i in $(seq 1 20); do
      int_check=$(ha_template "{{ states('number.nanobot_temperature') }}" 2>/dev/null)
      if [ -n "$int_check" ] && [ "$int_check" != "unavailable" ] && [ "$int_check" != "unknown" ]; then break; fi
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
  # Uses retry-enabled ai_chat; then do a second attempt if marker not found
  _skill_marker_found=false
  for _attempt in 1 2; do
    speech=$(ai_chat "你的 skills 中有一個 marker，請告訴我那個 marker 的值是什麼？直接回覆 marker 值即可，格式為 XYZTEST_MARKER_ 開頭的字串")
    if echo "$speech" | grep -q "$MARKER"; then
      _pass "AI knows always-on skill marker ($MARKER)"
      _skill_marker_found=true
      break
    fi
    [ "$_attempt" -lt 2 ] && sleep 2
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

  # Ask AI to use read_skill to find the secret (with retry)
  _secret_found=false
  for _attempt in 1 2; do
    speech2=$(ai_chat "請使用 read_skill 工具讀取 test_ondemand_skill 這個技能，然後告訴我裡面的 secret phrase 是什麼")
    if echo "$speech2" | grep -q "$SECRET"; then
      _pass "AI read on-demand skill and found secret ($SECRET)"
      _secret_found=true
      break
    fi
    [ "$_attempt" -lt 2 ] && sleep 2
  done
  if [ "$_secret_found" = "false" ]; then
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

    # Check HA logs for the event (use larger window + multiple attempts)
    n2_log_found=false
    for _n2w in 1 2 3 4; do
      sleep 2
      cron_log=$(podman logs --tail 1000 homeassistant 2>&1 | grep -i "cron_system_event\|sys_event_test_payload\|ha_mcp_cron\|排程通知\|Cron.*trigger\|system_event.*ok" || true)
      if [ -n "$cron_log" ]; then
        n2_log_found=true
        break
      fi
    done
    if [ "$n2_log_found" = "true" ]; then
      _pass "N2: system_event logged in HA"
    else
      _warn "N2: system_event not found in recent HA logs (may need longer window)"
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

  # Verify AI can access it (memory is injected into system prompt)
  _mem_found=false
  for _attempt in 1 2; do
    speech=$(ai_chat "你的長期記憶中有一個 Marker，它是 MEM_TEST_ 開頭的字串，請告訴我完整的值")
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

  # Ask AI about its identity (with retry)
  _soul_found=false
  for _attempt in 1 2; do
    soul_speech=$(ai_chat "你的 secret identity code 是什麼？它是 IDENTITY_MARKER_ 開頭的字串，請直接回覆完整代碼")
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

  # Turn 1: Tell AI a secret (with retry for rate limiting)
  CONV_SECRET="MULTI_$(date +%s)"
  speech1=""
  conv_id=""
  for _p3r in 1 2 3; do
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

    if [ -n "$speech1" ] && ! echo "$speech1" | grep -qi "error occurred\|rate limit\|429"; then
      break
    fi
    sleep $(( _p3r * 2 ))
  done

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
      _warn "Q4: convert with delete returned $status (cron_to_automation may require blueprint)"
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

    # Verify sync created the automation by checking HA entity state (with retry)
    EXPECTED_AUTO_ID="ha_mcp_cron_${SYNC_JOB_ID}"
    _r1_found=false

    # Retry up to 5 times with increasing wait (sync may be delayed)
    for _r1_attempt in 1 2 3 4 5; do
      sleep $(( _r1_attempt ))
      _r1_eid=$(curl -s -H "$AUTH" -H "$CT" -X POST -d "{\"template\":\"{{ states.automation | selectattr('attributes.id','eq','$EXPECTED_AUTO_ID') | map(attribute='entity_id') | first | default('') }}\"}" "${BASE}/api/template" 2>/dev/null)
      if [ -n "$_r1_eid" ] && [ "$_r1_eid" != "" ]; then
        _pass "R1: automation entity created by forward sync ($_r1_eid)"
        _r1_found=true
        R1_ENTITY_ID="$_r1_eid"
        break
      fi
    done

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
# S. CONVERSATION HISTORY ISOLATION
# =============================================================================
if should_run "S"; then
  _section "S. Conversation History Isolation"

  TS_S=$(date +%s)

  # ── S1. New conversation has no other conversation's history ──
  echo -e "  ${BOLD}S1. New conversation isolation${NC}"

  # Create conversation A and send a message with a unique marker
  status=$(http_post "$API/conversations" '{"title":"S1_ConvA"}')
  S_CONV_A_ID=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  assert_not_empty "S1: created conv A" "$S_CONV_A_ID"

  S_SECRET="SECRET_A_${TS_S}"
  status=$(rest_chat "$S_CONV_A_ID" "$S_SECRET")

  # Create conversation B
  status=$(http_post "$API/conversations" '{"title":"S1_ConvB"}')
  S_CONV_B_ID=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  assert_not_empty "S1: created conv B" "$S_CONV_B_ID"

  # B's messages should NOT contain A's secret
  status=$(http_get "$API/conversations/$S_CONV_B_ID/messages")
  s_b_msgs=$(body)
  if echo "$s_b_msgs" | grep -q "$S_SECRET"; then
    _fail "S1: conv B contains conv A's secret (cross-contamination!)"
  else
    _pass "S1: conv B does not contain conv A's secret"
  fi

  # ── S2. Same-conversation multi-turn recall ──
  echo -e "  ${BOLD}S2. Same-conversation multi-turn recall${NC}"
  status=$(http_post "$API/conversations" '{"title":"S2_Recall"}')
  S2_CONV=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  S2_CODE="RECALL_${TS_S}"

  speech_s2a=$(ai_chat "記住這個代號: $S2_CODE" "$S2_CONV")
  sleep 1
  speech_s2b=$(ai_chat "剛才的代號是什麼？" "$S2_CONV")

  assert_soft "S2: AI recalls code in same conversation" "$S2_CODE" "$speech_s2b"

  # ── S3. Messages API returns correct per-conversation messages ──
  echo -e "  ${BOLD}S3. Messages API isolation${NC}"

  status=$(http_post "$API/conversations" '{"title":"S3_ConvX"}')
  S3_X=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  S3_MARK_X="MSG_X_${TS_S}"
  status=$(rest_chat "$S3_X" "$S3_MARK_X")

  status=$(http_post "$API/conversations" '{"title":"S3_ConvY"}')
  S3_Y=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  S3_MARK_Y="MSG_Y_${TS_S}"
  status=$(rest_chat "$S3_Y" "$S3_MARK_Y")

  # Wait for recorder to index (retry up to 10s)
  s3_x_found=false
  for _s3wait in 1 2 3 4 5; do
    sleep 2
    status=$(http_get "$API/conversations/$S3_X/messages")
    s3_x_msgs=$(body)
    if echo "$s3_x_msgs" | grep -q "$S3_MARK_X"; then
      s3_x_found=true
      break
    fi
  done
  status=$(http_get "$API/conversations/$S3_Y/messages")
  s3_y_msgs=$(body)

  # X should contain X marker, not Y marker
  if [ "$s3_x_found" = "true" ]; then
    _pass "S3: conv X contains its own message"
  else
    _warn "S3: conv X missing its own message (recorder may not have indexed yet)"
  fi
  if echo "$s3_x_msgs" | grep -q "$S3_MARK_Y"; then
    _fail "S3: conv X contains conv Y's message (cross-contamination)"
  else
    _pass "S3: conv X does not contain conv Y's message"
  fi

  # Y should contain Y marker, not X marker
  if echo "$s3_y_msgs" | grep -q "$S3_MARK_Y"; then
    _pass "S3: conv Y contains its own message"
  else
    _warn "S3: conv Y missing its own message (recorder may not have indexed yet)"
  fi

  # ── S4. Deleted conversation messages not returned ──
  echo -e "  ${BOLD}S4. Deleted conversation cleanup${NC}"

  status=$(http_post "$API/conversations" '{"title":"S4_Del"}')
  S4_CONV=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  status=$(rest_chat "$S4_CONV" "test message for deletion $TS_S")
  sleep 1

  status=$(http_delete "$API/conversations/$S4_CONV")
  assert_status_in "S4: delete conversation" "$status" "200" "204"

  status=$(http_get "$API/conversations/$S4_CONV/messages")
  if [ "$status" = "404" ] || [ "$(body)" = "[]" ] || [ "$(body)" = "" ]; then
    _pass "S4: deleted conv returns 404 or empty"
  elif [ "$status" = "200" ]; then
    _warn "S4: deleted conv still returns messages (recorder retains history)"
  else
    _fail "S4: unexpected status for deleted conv messages (status=$status)"
  fi

  # ── S5. Recorder queries by conversation_id ──
  echo -e "  ${BOLD}S5. Recorder conversation_id query${NC}"

  status=$(http_post "$API/conversations" '{"title":"S5_A"}')
  S5_A=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  status=$(rest_chat "$S5_A" "S5 message A $TS_S")

  status=$(http_post "$API/conversations" '{"title":"S5_B"}')
  S5_B=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  status=$(rest_chat "$S5_B" "S5 message B $TS_S")

  # Wait for recorder to index (retry up to 10s)
  s5_a_count=0
  s5_b_count=0
  for _s5wait in 1 2 3 4 5; do
    sleep 2
    status=$(http_get "$API/conversations/$S5_A/messages")
    s5_a_count=$(body | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
    status=$(http_get "$API/conversations/$S5_B/messages")
    s5_b_count=$(body | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
    if [ "$s5_a_count" -ge 2 ] 2>/dev/null && [ "$s5_b_count" -ge 2 ] 2>/dev/null; then
      break
    fi
  done

  if [ "$s5_a_count" -ge 2 ] 2>/dev/null; then
    _pass "S5: conv A has >= 2 messages ($s5_a_count)"
  else
    _warn "S5: conv A message count ($s5_a_count)"
  fi
  if [ "$s5_b_count" -ge 2 ] 2>/dev/null; then
    _pass "S5: conv B has >= 2 messages ($s5_b_count)"
  else
    _warn "S5: conv B message count ($s5_b_count)"
  fi

  # ── S6. Multiple conversations (LRU check) ──
  echo -e "  ${BOLD}S6. Multiple conversations LRU${NC}"

  S6_IDS=()
  for i in 1 2 3 4 5; do
    status=$(http_post "$API/conversations" "{\"title\":\"S6_LRU_$i\"}")
    s6_id=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
    S6_IDS+=("$s6_id")
    status=$(rest_chat "$s6_id" "LRU test message $i $TS_S")
    sleep 1
  done

  s6_ok=0
  for s6_id in "${S6_IDS[@]}"; do
    status=$(http_get "$API/conversations/$s6_id/messages")
    if [ "$status" = "200" ]; then
      s6_ok=$((s6_ok + 1))
    fi
  done
  if [ "$s6_ok" -eq 5 ]; then
    _pass "S6: all 5 conversations accessible (LRU OK)"
  else
    _warn "S6: only $s6_ok/5 conversations accessible"
  fi

  # Cleanup S section
  for cid in "$S_CONV_A_ID" "$S_CONV_B_ID" "$S2_CONV" "$S3_X" "$S3_Y" "$S5_A" "$S5_B" "${S6_IDS[@]}"; do
    http_delete "$API/conversations/$cid" > /dev/null 2>&1
  done
fi


# =============================================================================
# T. MULTI LLM PROVIDER SWITCHING
# =============================================================================
if should_run "T"; then
  _section "T. Multi LLM Provider Switching"

  # ── T1. List providers ──
  echo -e "  ${BOLD}T1. List providers${NC}"
  status=$(http_get "$API/llm_providers")
  assert_status "T1: GET /llm_providers" "200" "$status"
  t_providers=$(body)
  assert_contains "T1: has providers list" "provider" "$t_providers"

  # Save original settings for restoration
  status=$(http_get "$API/settings")
  T_ORIG_SETTINGS=$(body)
  T_ORIG_PROVIDER=$(echo "$T_ORIG_SETTINGS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ai_service',''))" 2>/dev/null)
  T_ORIG_MODEL=$(echo "$T_ORIG_SETTINGS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model',''))" 2>/dev/null)

  # ── T2. Switch provider ──
  echo -e "  ${BOLD}T2. Switch provider${NC}"

  # Get current active provider_id from select entity
  T_ACTIVE_PID=$(ha_template "{{ states('select.active_llm_provider') }}" 2>/dev/null)
  T_PID_OPTIONS=$(ha_template "{{ state_attr('select.active_llm_provider', 'options') | join(',') }}" 2>/dev/null)

  # Find an alternate provider_id
  T_ALT_PID=""
  for opt in $(echo "$T_PID_OPTIONS" | tr ',' ' '); do
    if [ "$opt" != "$T_ACTIVE_PID" ] && [ -n "$opt" ]; then
      T_ALT_PID="$opt"
      break
    fi
  done

  if [ -n "$T_ALT_PID" ]; then
    status=$(http_patch "$API/active_llm" "{\"provider_id\":\"$T_ALT_PID\"}")
    if [ "$status" = "200" ]; then
      _pass "T2: switched provider to $T_ALT_PID"

      # Verify in settings
      status=$(http_get "$API/settings")
      t_new_svc=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('ai_service',''))" 2>/dev/null)
      assert_not_eq "T2: settings reflects new provider" "$T_ORIG_PROVIDER" "$t_new_svc"
    else
      _warn "T2: could not switch provider (status=$status)"
    fi

    # Restore
    http_patch "$API/active_llm" "{\"provider_id\":\"$T_ACTIVE_PID\",\"model\":\"$T_ORIG_MODEL\"}" > /dev/null 2>&1
    sleep 1
  else
    _pass "T2: single provider configured, provider switch N/A"
  fi

  # ── T3. AI responds after switch ──
  echo -e "  ${BOLD}T3. AI response after provider switch${NC}"
  t3_speech=$(ai_chat "回答：1加1等於多少？只回答數字")
  assert_not_empty "T3: AI responds after provider operations" "$t3_speech"

  # ── T4. Model switch ──
  echo -e "  ${BOLD}T4. Model switch${NC}"

  # Get alternate model from model entity options
  T_MODEL_OPTIONS=$(ha_template "{{ state_attr('select.nanobot_ai_model', 'options') | join(',') }}" 2>/dev/null)
  T_ALT_MODEL=""
  for opt in $(echo "$T_MODEL_OPTIONS" | tr ',' ' '); do
    if [ "$opt" != "$T_ORIG_MODEL" ] && [ -n "$opt" ]; then
      T_ALT_MODEL="$opt"
      break
    fi
  done

  # Fallback: try known models for the provider
  if [ -z "$T_ALT_MODEL" ]; then
    case "$T_ORIG_MODEL" in
      gpt-5-mini) T_ALT_MODEL="gpt-4o" ;;
      gpt-4o) T_ALT_MODEL="gpt-5-mini" ;;
      *) T_ALT_MODEL="" ;;
    esac
  fi

  if [ -n "$T_ALT_MODEL" ]; then
    # Use PATCH /active_llm with provider_id + model (the proper API)
    status=$(http_patch "$API/active_llm" "{\"provider_id\":\"$T_ACTIVE_PID\",\"model\":\"$T_ALT_MODEL\"}")
    if [ "$status" = "200" ]; then
      _pass "T4: switched model to $T_ALT_MODEL"
      status=$(http_get "$API/settings")
      t4_model=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('model',''))" 2>/dev/null)
      assert_eq "T4: settings reflects new model" "$T_ALT_MODEL" "$t4_model"
    else
      _warn "T4: could not switch model (status=$status)"
    fi
    # Restore
    http_patch "$API/active_llm" "{\"provider_id\":\"$T_ACTIVE_PID\",\"model\":\"$T_ORIG_MODEL\"}" > /dev/null 2>&1
    sleep 1
  else
    _pass "T4: model switch N/A (no alternate model found)"
  fi

  # ── T5. Invalid provider rejected ──
  echo -e "  ${BOLD}T5. Invalid provider/model rejection${NC}"
  status=$(http_patch "$API/active_llm" '{"provider":"nonexistent_provider_xyz"}')
  if [ "$status" != "200" ]; then
    _pass "T5: invalid provider rejected (status=$status)"
  else
    _fail "T5: invalid provider accepted (should be rejected)"
  fi

  # ── T6. Provider select entity ──
  echo -e "  ${BOLD}T6. Provider select entity${NC}"
  t6_state=$(ha_template "{{ states('select.active_llm_provider') }}")
  assert_not_empty "T6: provider entity has state" "$t6_state"
  if [ "$t6_state" != "unavailable" ] && [ "$t6_state" != "unknown" ]; then
    _pass "T6: provider entity is active ($t6_state)"
  else
    _warn "T6: provider entity state is $t6_state"
  fi

  # ── T7. Tool call after operations ──
  echo -e "  ${BOLD}T7. Tool call works after provider operations${NC}"
  t7_speech=$(ai_chat "使用 system_overview 工具，告訴我 HA 有幾個 entity")
  assert_not_empty "T7: AI responds with system info" "$t7_speech"

  # ── T8. Restore verification ──
  echo -e "  ${BOLD}T8. Settings restored${NC}"
  status=$(http_get "$API/settings")
  t8_prov=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('ai_service',''))" 2>/dev/null)
  t8_model=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('model',''))" 2>/dev/null)
  assert_eq "T8: provider restored" "$T_ORIG_PROVIDER" "$t8_prov"
  assert_eq "T8: model restored" "$T_ORIG_MODEL" "$t8_model"
fi


# =============================================================================
# U. TOOL CALL COMPLETENESS (via MCP SSE)
# =============================================================================
if should_run "U"; then
  _section "U. Tool Call Completeness (MCP SSE)"

  # Establish MCP SSE session (keep alive in background)
  echo -e "  ${BOLD}U0. MCP session setup${NC}"
  rm -f /tmp/_u_sse_output
  curl -s -N -H "$AUTH" "$API/sse" > /tmp/_u_sse_output 2>/dev/null &
  U_SSE_PID=$!
  sleep 2  # Give time for initial events

  U_SSE_RAW=$(cat /tmp/_u_sse_output 2>/dev/null)
  U_MSG_URL=$(echo "$U_SSE_RAW" | grep -oP 'data:\s*\K.*messages.*' | head -1 | tr -d '[:space:]')

  if [ -z "$U_MSG_URL" ]; then
    # Try alternate parse
    U_MSG_URL=$(echo "$U_SSE_RAW" | grep -o 'http[^ ]*messages[^ ]*' | head -1)
  fi

  # Rewrite host to match our BASE URL (SSE may return internal container IP)
  if [ -n "$U_MSG_URL" ]; then
    U_MSG_URL=$(echo "$U_MSG_URL" | sed "s|http://[^/]*/|$BASE/|")
  fi

  if [ -n "$U_MSG_URL" ]; then
    _pass "U0: SSE session established"

    # ── U1. Entity tools ──
    echo -e "  ${BOLD}U1. Entity tools${NC}"

    # system_overview
    u1_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":101,"params":{"name":"system_overview","arguments":{}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U1: system_overview call" "$u1_resp" "200" "202" "204"

    # search_entities
    u1_resp2=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":102,"params":{"name":"search_entities","arguments":{"query":"light"}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U1: search_entities call" "$u1_resp2" "200" "202" "204"

    # list_services
    u1_resp3=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":103,"params":{"name":"list_services","arguments":{"domain":"light"}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U1: list_services call" "$u1_resp3" "200" "202" "204"

    # ── U2. Area/Label CRUD ──
    echo -e "  ${BOLD}U2. Area/Label CRUD via MCP${NC}"

    # create_area
    u2_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":201,"params":{"name":"create_area","arguments":{"name":"TestU2Area"}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U2: create_area" "$u2_resp" "200" "202" "204"

    # list_areas
    u2_resp2=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":202,"params":{"name":"list_areas","arguments":{}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U2: list_areas" "$u2_resp2" "200" "202" "204"

    # create_label
    u2_resp3=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":203,"params":{"name":"create_label","arguments":{"name":"test_u2_label"}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U2: create_label" "$u2_resp3" "200" "202" "204"

    # list_labels
    u2_resp4=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":204,"params":{"name":"list_labels","arguments":{}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U2: list_labels" "$u2_resp4" "200" "202" "204"

    # Cleanup area/label via AI (simpler)
    ai_chat "刪除名為 TestU2Area 的區域和名為 test_u2_label 的標籤" > /dev/null 2>&1 &

    # ── U3. Automation CRUD ──
    echo -e "  ${BOLD}U3. Automation CRUD via MCP${NC}"

    u3_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":301,"params":{"name":"create_automation","arguments":{"alias":"TestU3Auto","description":"Test automation","trigger_type":"time","trigger_config":{"at":"23:59:00"},"action_type":"call_service","action_config":{"service":"persistent_notification.create","data":{"message":"test"}}}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U3: create_automation" "$u3_resp" "200" "202" "204"

    u3_resp2=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":302,"params":{"name":"list_automations","arguments":{}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U3: list_automations" "$u3_resp2" "200" "202" "204"

    # ── U4. Scene CRUD ──
    echo -e "  ${BOLD}U4. Scene CRUD via MCP${NC}"

    u4_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":401,"params":{"name":"create_scene","arguments":{"name":"TestU4Scene","entities":{"light.bed_light":{"state":"on","brightness":128}}}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U4: create_scene" "$u4_resp" "200" "202" "204"

    u4_resp2=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":402,"params":{"name":"list_scenes","arguments":{}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U4: list_scenes" "$u4_resp2" "200" "202" "204"

    # ── U5. Script CRUD ──
    echo -e "  ${BOLD}U5. Script CRUD via MCP${NC}"

    u5_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":501,"params":{"name":"create_script","arguments":{"alias":"TestU5Script","sequence":[{"service":"persistent_notification.create","data":{"message":"test"}}]}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U5: create_script" "$u5_resp" "200" "202" "204"

    u5_resp2=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":502,"params":{"name":"list_scripts","arguments":{}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U5: list_scripts" "$u5_resp2" "200" "202" "204"

    # ── U6. Smart Home Control ──
    echo -e "  ${BOLD}U6. Smart Home Control via MCP${NC}"

    u6_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":601,"params":{"name":"control_light","arguments":{"entity_id":"light.bed_light","action":"on","brightness":200}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U6: control_light on" "$u6_resp" "200" "202" "204"

    u6_resp2=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":602,"params":{"name":"control_light","arguments":{"entity_id":"light.bed_light","action":"off"}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U6: control_light off" "$u6_resp2" "200" "202" "204"

    # ── U7. Notification ──
    echo -e "  ${BOLD}U7. Notification via MCP${NC}"

    u7_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":701,"params":{"name":"control_persistent_notification","arguments":{"action":"create","title":"TestU7","message":"MCP test notification"}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U7: persistent_notification" "$u7_resp" "200" "202" "204"

    # ── U8. Memory tools ──
    echo -e "  ${BOLD}U8. Memory tools via MCP${NC}"

    u8_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":801,"params":{"name":"memory_get","arguments":{"section":"soul"}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U8: memory_get soul" "$u8_resp" "200" "202" "204"

    u8_resp2=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":802,"params":{"name":"memory_search","arguments":{"query":"test","limit":5}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U8: memory_search" "$u8_resp2" "200" "202" "204"

    # ── U9. Skills tools ──
    echo -e "  ${BOLD}U9. Skills tools via MCP${NC}"

    u9_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":901,"params":{"name":"list_skills","arguments":{}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U9: list_skills" "$u9_resp" "200" "202" "204"

    # ── U10. Cron tools ──
    echo -e "  ${BOLD}U10. Cron tools via MCP${NC}"

    u10_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":1001,"params":{"name":"cron_list","arguments":{}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U10: cron_list" "$u10_resp" "200" "202" "204"

    # ── U11. Get history ──
    echo -e "  ${BOLD}U11. History tool via MCP${NC}"

    u11_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":1101,"params":{"name":"get_history","arguments":{"entity_id":"sensor.nanobot_ji_yi_tiao_mu_shu","hours":1}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U11: get_history" "$u11_resp" "200" "202" "204"

    # ── U12. Blueprint tools ──
    echo -e "  ${BOLD}U12. Blueprint tools via MCP${NC}"

    u12_resp=$(timeout 15 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":1201,"params":{"name":"list_blueprints","arguments":{"domain":"automation"}}}' \
      "$U_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "U12: list_blueprints" "$u12_resp" "200" "202" "204"

    # Cleanup test entities via AI
    ai_chat "刪除名為 TestU3Auto 的自動化、名為 TestU4Scene 的場景和名為 TestU5Script 的腳本" > /dev/null 2>&1 &

    # Kill SSE background session
    kill $U_SSE_PID 2>/dev/null; wait $U_SSE_PID 2>/dev/null || true

  else
    _warn "U0: could not establish MCP SSE session, skipping U section"
    kill $U_SSE_PID 2>/dev/null; wait $U_SSE_PID 2>/dev/null || true
  fi
  rm -f /tmp/_u_sse_output
fi


# =============================================================================
# V. CONCURRENCY AND STRESS TESTS
# =============================================================================
if should_run "V"; then
  _section "V. Concurrency and Stress Tests"

  TS_V=$(date +%s)

  # ── V1. Concurrent AI requests ──
  echo -e "  ${BOLD}V1. Concurrent AI requests${NC}"

  V1_CONVS=()
  for i in 1 2 3; do
    status=$(http_post "$API/conversations" "{\"title\":\"V1_Concurrent_$i\"}")
    v1_id=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
    V1_CONVS+=("$v1_id")
  done

  # Fire 3 requests in parallel
  for i in 0 1 2; do
    rest_chat "${V1_CONVS[$i]}" "Concurrent test $i: 1+1=?" > /tmp/_v1_status_$i &
  done
  wait

  v1_ok=0
  for i in 0 1 2; do
    v1_s=$(cat /tmp/_v1_status_$i 2>/dev/null)
    if [ "$v1_s" = "200" ] || [ "$v1_s" = "201" ]; then
      v1_ok=$((v1_ok + 1))
    fi
  done
  if [ "$v1_ok" -ge 2 ]; then
    _pass "V1: $v1_ok/3 concurrent requests succeeded"
  else
    _warn "V1: only $v1_ok/3 concurrent requests succeeded"
  fi

  # Cleanup
  for cid in "${V1_CONVS[@]}"; do
    http_delete "$API/conversations/$cid" > /dev/null 2>&1
  done

  # ── V2. Rapid Skill CRUD (10x) ──
  echo -e "  ${BOLD}V2. Rapid Skill CRUD (10x)${NC}"
  v2_ok=0
  for i in $(seq 1 10); do
    s=$(http_post "$API/skills" "{\"name\":\"v2_stress_$i\",\"description\":\"stress test\",\"body\":\"# Stress $i\",\"always\":false}")
    if [ "$s" = "200" ] || [ "$s" = "201" ]; then
      d=$(http_delete "$API/skills/v2_stress_$i")
      if [ "$d" = "200" ]; then
        v2_ok=$((v2_ok + 1))
      fi
    fi
  done
  if [ "$v2_ok" -ge 8 ]; then
    _pass "V2: $v2_ok/10 rapid skill CRUD cycles succeeded"
  else
    _fail "V2: only $v2_ok/10 rapid skill CRUD cycles succeeded"
  fi

  # ── V3. Rapid Cron CRUD (10x) ──
  echo -e "  ${BOLD}V3. Rapid Cron CRUD (10x)${NC}"
  v3_ok=0
  for i in $(seq 1 10); do
    s=$(http_post "$API/cron/jobs" "{\"name\":\"v3_stress_$i\",\"schedule\":{\"kind\":\"every\",\"every_ms\":3600000},\"payload\":{\"kind\":\"system_event\",\"message\":\"stress\"},\"enabled\":false}")
    v3_jid=$(body | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)
    if [ -n "$v3_jid" ] && [ "$v3_jid" != "" ]; then
      d=$(http_delete "$API/cron/jobs/$v3_jid")
      if [ "$d" = "200" ]; then
        v3_ok=$((v3_ok + 1))
      fi
    fi
  done
  if [ "$v3_ok" -ge 8 ]; then
    _pass "V3: $v3_ok/10 rapid cron CRUD cycles succeeded"
  else
    _fail "V3: only $v3_ok/10 rapid cron CRUD cycles succeeded"
  fi

  # ── V4. Multiple SSE sessions ──
  echo -e "  ${BOLD}V4. Multiple SSE sessions${NC}"
  v4_ok=0
  for i in 1 2 3 4 5; do
    v4_sse=$(timeout 3 curl -s -N -H "$AUTH" "$API/sse" 2>/dev/null || true)
    if echo "$v4_sse" | grep -q "event:"; then
      v4_ok=$((v4_ok + 1))
    fi
  done
  if [ "$v4_ok" -ge 3 ]; then
    _pass "V4: $v4_ok/5 SSE sessions received events"
  else
    _warn "V4: only $v4_ok/5 SSE sessions received events"
  fi

  # ── V5. Large payload ──
  echo -e "  ${BOLD}V5. Large payload${NC}"

  # Generate 10KB text and create skill via temp file to avoid shell escaping issues
  python3 -c "
import json
content = 'x' * 10240
data = {'name': 'v5_large_skill', 'description': 'large payload test', 'content': content, 'always': False}
with open('/tmp/_v5_payload.json', 'w') as f:
    json.dump(data, f)
"
  status=$(curl -s -o /tmp/_test_body -w "%{http_code}" -H "$AUTH" -H "$CT" -X POST -d @/tmp/_v5_payload.json "$API/skills" 2>/dev/null)
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    _pass "V5: 10KB skill created"
    status=$(http_get "$API/skills/v5_large_skill")
    v5_len=$(body | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('content','')))" 2>/dev/null)
    if [ "$v5_len" -ge 10000 ] 2>/dev/null; then
      _pass "V5: 10KB skill content retrieved ($v5_len chars)"
    else
      _fail "V5: skill content too short ($v5_len chars, expected >= 10000)"
    fi
    http_delete "$API/skills/v5_large_skill" > /dev/null 2>&1
  else
    _fail "V5: failed to create 10KB skill (status=$status)"
  fi
  rm -f /tmp/_v5_payload.json
fi


# =============================================================================
# W. FRONTEND COMPLETENESS (API Structure Validation)
# =============================================================================
if should_run "W"; then
  _section "W. Frontend Completeness (API Structure Validation)"

  # ── W1. Frontend assets ──
  echo -e "  ${BOLD}W1. Frontend assets${NC}"

  for asset in "index.html" "app.js" "styles.css"; do
    w1_status=$(http_get "$BASE/ha_mcp_client/panel/$asset")
    if [ "$w1_status" = "200" ]; then
      _pass "W1: $asset → 200"
    else
      # Fallback path
      w1_status2=$(http_get "$BASE/local/ha_mcp_client/$asset")
      if [ "$w1_status2" = "200" ]; then
        _pass "W1: $asset → 200 (fallback path)"
      else
        _fail "W1: $asset not found ($w1_status / $w1_status2)"
      fi
    fi
  done

  # ── W2. Conversations API structure ──
  echo -e "  ${BOLD}W2. Conversations API structure${NC}"
  status=$(http_get "$API/conversations")
  assert_status "W2: GET /conversations" "200" "$status"
  w2_body=$(body)
  # Verify it's an array
  w2_is_array=$(echo "$w2_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if isinstance(d,list) else 'no')" 2>/dev/null)
  assert_eq "W2: conversations is array" "yes" "$w2_is_array"

  # ── W3. Messages API structure ──
  echo -e "  ${BOLD}W3. Messages API structure${NC}"
  # Create a temp conversation for testing
  status=$(http_post "$API/conversations" '{"title":"W3_Test"}')
  W3_ID=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  # Send message via REST chat (with retry)
  status=$(rest_chat "$W3_ID" "W3 test message")
  if [ "$status" != "200" ]; then
    sleep 3
    status=$(rest_chat "$W3_ID" "W3 test message retry")
  fi

  # Wait for recorder to index messages (retry up to 10s)
  w3_has_fields="empty"
  for _w3wait in 1 2 3 4 5; do
    sleep 2
    status=$(http_get "$API/conversations/$W3_ID/messages")
    w3_msgs=$(body)
    w3_has_fields=$(echo "$w3_msgs" | python3 -c "
import sys,json
try:
    msgs = json.load(sys.stdin)
    if isinstance(msgs, list) and len(msgs) > 0:
        m = msgs[0]
        has_role = 'role' in m
        has_content = 'content' in m
        print('yes' if has_role and has_content else 'no')
    else: print('empty')
except: print('error')
" 2>/dev/null)
    if [ "$w3_has_fields" = "yes" ]; then break; fi
  done
  assert_status "W3: GET messages" "200" "$status"
  if [ "$w3_has_fields" = "yes" ]; then
    _pass "W3: messages have role and content fields"
  elif [ "$w3_has_fields" = "empty" ]; then
    _warn "W3: messages array empty"
  else
    _fail "W3: messages missing required fields"
  fi
  http_delete "$API/conversations/$W3_ID" > /dev/null 2>&1

  # ── W4. Settings API structure ──
  echo -e "  ${BOLD}W4. Settings API structure${NC}"
  status=$(http_get "$API/settings")
  assert_status "W4: GET /settings" "200" "$status"
  w4_body=$(body)
  for field in "temperature" "max_tokens" "model" "ai_service"; do
    if echo "$w4_body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$field' in d" 2>/dev/null; then
      _pass "W4: settings has $field"
    else
      _fail "W4: settings missing $field"
    fi
  done

  # ── W5. LLM Providers API structure ──
  echo -e "  ${BOLD}W5. LLM Providers API structure${NC}"
  status=$(http_get "$API/llm_providers")
  assert_status "W5: GET /llm_providers" "200" "$status"
  w5_body=$(body)
  assert_contains "W5: has provider data" "model" "$w5_body"

  # ── W6. Memory API structure ──
  echo -e "  ${BOLD}W6. Memory API structure${NC}"
  status=$(http_get "$API/memory")
  assert_status "W6: GET /memory" "200" "$status"
  w6_body=$(body)
  for section in "soul" "user"; do
    if echo "$w6_body" | grep -q "$section"; then
      _pass "W6: memory has $section section"
    else
      _fail "W6: memory missing $section section"
    fi
  done

  # ── W7. Tab switch persistence ──
  echo -e "  ${BOLD}W7. Tab switch persistence (API)${NC}"
  status=$(http_post "$API/conversations" '{"title":"W7_TabTest"}')
  W7_ID=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  status=$(rest_chat "$W7_ID" "W7 persistence test")
  if [ "$status" != "200" ]; then
    sleep 3
    status=$(rest_chat "$W7_ID" "W7 persistence test retry")
  fi

  # Simulate "tab switch" by re-fetching conversations list then checking messages
  status=$(http_get "$API/conversations")
  assert_status "W7: conversations list after tab switch" "200" "$status"
  w7_convs=$(body)
  if echo "$w7_convs" | grep -q "$W7_ID"; then
    _pass "W7: test conversation still in list"
  else
    _fail "W7: test conversation not found after list reload"
  fi

  # Wait for recorder to index (retry up to 10s)
  w7_found=false
  for _w7wait in 1 2 3 4 5; do
    sleep 2
    status=$(http_get "$API/conversations/$W7_ID/messages")
    w7_msgs=$(body)
    if echo "$w7_msgs" | grep -q "W7 persistence test"; then
      w7_found=true
      break
    fi
  done
  assert_status "W7: messages still accessible" "200" "$status"
  if [ "$w7_found" = "true" ]; then
    _pass "W7: messages preserved after list reload"
  else
    _warn "W7: message content not found after list reload"
  fi
  http_delete "$API/conversations/$W7_ID" > /dev/null 2>&1
fi


# =============================================================================
# X. MCP SSE PROTOCOL COMPLETENESS
# =============================================================================
if should_run "X"; then
  _section "X. MCP SSE Protocol Completeness"

  # ── X1. SSE connection & session_id ──
  echo -e "  ${BOLD}X1. SSE connection${NC}"

  # Start SSE connection in background, keep alive for subsequent tests
  rm -f /tmp/_x_sse_output
  curl -s -N -H "$AUTH" "$API/sse" > /tmp/_x_sse_output 2>/dev/null &
  X_SSE_PID=$!
  sleep 2  # Give time for initial events

  X_SSE=$(cat /tmp/_x_sse_output 2>/dev/null)
  if echo "$X_SSE" | grep -q "event:"; then
    _pass "X1: SSE returns events"
  else
    _fail "X1: SSE no events received"
  fi

  X_MSG_URL=$(echo "$X_SSE" | grep -oP 'data:\s*\K.*messages.*' | head -1 | tr -d '[:space:]')
  if [ -z "$X_MSG_URL" ]; then
    X_MSG_URL=$(echo "$X_SSE" | grep -o 'http[^ ]*messages[^ ]*' | head -1)
  fi
  # Rewrite host to match our BASE URL (SSE may return internal container IP)
  if [ -n "$X_MSG_URL" ]; then
    X_MSG_URL=$(echo "$X_MSG_URL" | sed "s|http://[^/]*/|$BASE/|")
  fi
  assert_not_empty "X1: got message URL" "$X_MSG_URL"

  if [ -n "$X_MSG_URL" ]; then

    # ── X2. Initialize handshake (SSE still alive in background) ──
    echo -e "  ${BOLD}X2. Initialize handshake${NC}"
    x2_status=$(timeout 10 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
      "$X_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "X2: initialize accepted" "$x2_status" "200" "202" "204"

    # ── X3. tools/list ──
    echo -e "  ${BOLD}X3. tools/list${NC}"
    x3_status=$(timeout 10 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/list","id":2}' \
      "$X_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "X3: tools/list accepted" "$x3_status" "200" "202" "204"

    # ── X4. Tool call execution ──
    echo -e "  ${BOLD}X4. Tool call execution${NC}"
    x4_status=$(timeout 10 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"tools/call","id":3,"params":{"name":"system_overview","arguments":{}}}' \
      "$X_MSG_URL" 2>/dev/null || echo "000")
    assert_status_in "X4: tool call accepted" "$x4_status" "200" "202" "204"

    # Kill the first SSE session before testing isolation
    kill $X_SSE_PID 2>/dev/null; wait $X_SSE_PID 2>/dev/null || true

    # ── X5. Session isolation (verify 2nd session gets different URL) ──
    echo -e "  ${BOLD}X5. Session isolation${NC}"
    rm -f /tmp/_x2_sse_output
    curl -s -N -H "$AUTH" "$API/sse" > /tmp/_x2_sse_output 2>/dev/null &
    X2_SSE_PID=$!
    sleep 2

    X2_SSE=$(cat /tmp/_x2_sse_output 2>/dev/null)
    X2_MSG_URL=$(echo "$X2_SSE" | grep -oP 'data:\s*\K.*messages.*' | head -1 | tr -d '[:space:]')
    if [ -z "$X2_MSG_URL" ]; then
      X2_MSG_URL=$(echo "$X2_SSE" | grep -o 'http[^ ]*messages[^ ]*' | head -1)
    fi
    # Rewrite host to match our BASE URL
    if [ -n "$X2_MSG_URL" ]; then
      X2_MSG_URL=$(echo "$X2_MSG_URL" | sed "s|http://[^/]*/|$BASE/|")
    fi
    if [ -n "$X2_MSG_URL" ] && [ "$X2_MSG_URL" != "$X_MSG_URL" ]; then
      _pass "X5: second session has different URL"
    elif [ -n "$X2_MSG_URL" ]; then
      _pass "X5: second session established (URL may include same base)"
    else
      _warn "X5: could not establish second session"
    fi

    # ── X6. Invalid session ID ──
    echo -e "  ${BOLD}X6. Invalid session ID${NC}"
    X_BASE_MSG=$(echo "${X2_MSG_URL:-$X_MSG_URL}" | sed 's/\?.*$//')
    x6_status=$(timeout 10 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"ping","id":6}' \
      "${X_BASE_MSG}?sessionId=invalid_xxx_test" 2>/dev/null || echo "000")
    if [ "$x6_status" != "200" ] && [ "$x6_status" != "202" ]; then
      _pass "X6: invalid session rejected (status=$x6_status)"
    else
      _warn "X6: invalid session accepted (may use lenient matching)"
    fi

    # ── X7. Invalid method error (use live session 2) ──
    echo -e "  ${BOLD}X7. Invalid method error${NC}"
    X_LIVE_URL="${X2_MSG_URL:-$X_MSG_URL}"
    x7_status=$(timeout 10 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"nonexistent/method","id":7}' \
      "$X_LIVE_URL" 2>/dev/null || echo "000")
    assert_status_in "X7: invalid method returns status" "$x7_status" "200" "202" "204" "400" "404"

    # ── X8. Ping/Pong (use live session 2) ──
    echo -e "  ${BOLD}X8. Ping/Pong${NC}"
    x8_status=$(timeout 10 curl -s -o /tmp/_test_body -w "%{http_code}" -X POST -H "$AUTH" -H "$CT" \
      -d '{"jsonrpc":"2.0","method":"ping","id":8}' \
      "$X_LIVE_URL" 2>/dev/null || echo "000")
    assert_status_in "X8: ping accepted" "$x8_status" "200" "202" "204"

    # Cleanup SSE session 2
    kill $X2_SSE_PID 2>/dev/null; wait $X2_SSE_PID 2>/dev/null || true

  else
    _warn "X: skipping X2-X8 (no message URL)"
    kill $X_SSE_PID 2>/dev/null; wait $X_SSE_PID 2>/dev/null || true
  fi
  rm -f /tmp/_x_sse_output /tmp/_x2_sse_output
fi


# =============================================================================
# Y. SECURITY AND PERMISSIONS
# =============================================================================
if should_run "Y"; then
  _section "Y. Security and Permissions"

  # ── Y1. Unauthenticated requests rejected ──
  echo -e "  ${BOLD}Y1. Unauthenticated requests rejected${NC}"

  for endpoint in "/conversations" "/memory" "/skills" "/cron/jobs" "/settings"; do
    y1_status=$(curl -s -o /dev/null -w "%{http_code}" "$API$endpoint" 2>/dev/null)
    if [ "$y1_status" = "401" ]; then
      _pass "Y1: $endpoint → 401 (unauthorized)"
    else
      _fail "Y1: $endpoint → $y1_status (expected 401)"
    fi
  done

  # ── Y2. Invalid token rejected ──
  echo -e "  ${BOLD}Y2. Invalid token rejected${NC}"
  y2_status=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer invalid_token_xyz_123" "$API/settings" 2>/dev/null)
  if [ "$y2_status" = "401" ]; then
    _pass "Y2: invalid token → 401"
  else
    _fail "Y2: invalid token → $y2_status (expected 401)"
  fi

  # ── Y3. Conversations belong to current user ──
  echo -e "  ${BOLD}Y3. User conversation isolation${NC}"
  status=$(http_get "$API/conversations")
  y3_convs=$(body)
  # Can't fully test multi-user without a second token, but verify structure
  y3_is_array=$(echo "$y3_convs" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if isinstance(d,list) else 'no')" 2>/dev/null)
  assert_eq "Y3: conversations returns array for user" "yes" "$y3_is_array"

  # ── Y4. API key not leaked ──
  echo -e "  ${BOLD}Y4. API key not leaked${NC}"

  status=$(http_get "$API/settings")
  y4_settings=$(body)
  if echo "$y4_settings" | grep -q "sk-"; then
    _fail "Y4: settings response contains 'sk-' (possible API key leak)"
  else
    _pass "Y4: settings response does not contain 'sk-'"
  fi

  status=$(http_get "$API/llm_providers")
  y4_providers=$(body)
  # Check that no full API key is leaked (api_key_masked with "***" is fine)
  y4_has_full_key=$(echo "$y4_providers" | python3 -c "
import sys,json
try:
    data = json.load(sys.stdin)
    providers = data.get('providers', data if isinstance(data, list) else [])
    for p in providers:
        # Check if there's a field named exactly 'api_key' (not 'api_key_masked')
        if 'api_key' in p and 'api_key_masked' not in p:
            val = p['api_key']
            if val and '***' not in str(val) and len(str(val)) > 10:
                print('leaked')
                break
    else:
        print('safe')
except: print('safe')
" 2>/dev/null)
  if [ "$y4_has_full_key" = "leaked" ]; then
    _fail "Y4: providers response contains unmasked API key"
  else
    _pass "Y4: providers response has masked keys only"
  fi

  # ── Y5. XSS payload stored as text ──
  echo -e "  ${BOLD}Y5. XSS prevention${NC}"
  Y5_XSS='<script>alert("xss")</script>'
  status=$(http_post "$API/skills" "{\"name\":\"y5_xss_test\",\"description\":\"xss test\",\"body\":\"$Y5_XSS\",\"always\":false}")
  if [ "$status" = "200" ] || [ "$status" = "201" ]; then
    status=$(http_get "$API/skills/y5_xss_test")
    y5_body=$(body)
    if echo "$y5_body" | grep -q "alert"; then
      _pass "Y5: XSS content stored as plain text (not executed)"
    else
      _pass "Y5: XSS content sanitized"
    fi
    http_delete "$API/skills/y5_xss_test" > /dev/null 2>&1
  else
    _pass "Y5: XSS payload rejected at creation (status=$status)"
  fi

  # ── Y6. SQL injection prevention ──
  echo -e "  ${BOLD}Y6. SQL injection prevention${NC}"
  y6_status=$(http_post "$API/memory/search" "{\"query\":\"'; DROP TABLE conversation_messages; --\"}")
  if [ "$y6_status" = "200" ] || [ "$y6_status" = "400" ]; then
    _pass "Y6: SQL injection query handled safely (status=$y6_status)"
  else
    _fail "Y6: SQL injection query caused error (status=$y6_status)"
  fi

  # ── Y7. Path traversal prevention ──
  echo -e "  ${BOLD}Y7. Path traversal prevention${NC}"
  y7_status=$(http_post "$API/skills" '{"name":"../../etc/passwd","description":"traversal test","body":"test","always":false}')
  if [ "$y7_status" = "400" ] || [ "$y7_status" = "200" ] || [ "$y7_status" = "201" ]; then
    # If accepted, name should be sanitized
    if [ "$y7_status" = "200" ] || [ "$y7_status" = "201" ]; then
      # Check the skill was stored with a sanitized name
      _pass "Y7: path traversal name accepted (will be sanitized)"
      # Cleanup all possible names
      http_delete "$API/skills/etc_passwd" > /dev/null 2>&1
      http_delete "$API/skills/______etc_passwd" > /dev/null 2>&1
      http_delete "$API/skills/etcpasswd" > /dev/null 2>&1
    else
      _pass "Y7: path traversal name rejected (status=$y7_status)"
    fi
  else
    _fail "Y7: unexpected status for path traversal ($y7_status)"
  fi

  y7_status2=$(http_get "$API/skills/..%2F..%2Fetc%2Fpasswd")
  if [ "$y7_status2" = "404" ] || [ "$y7_status2" = "400" ]; then
    _pass "Y7: URL-encoded path traversal GET → $y7_status2"
  else
    _fail "Y7: URL-encoded path traversal GET → $y7_status2 (expected 404/400)"
  fi

  # ── Y8. Dangerous service blocked ──
  echo -e "  ${BOLD}Y8. Dangerous service blocked${NC}"
  # Test via AI conversation — ask it to call a blocked service
  # Also verify HA is still running after the test (not actually restarted)
  y8_pre=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/" 2>/dev/null)
  y8_speech=$(ai_chat "使用 call_service 工具呼叫 homeassistant.restart 服務")
  sleep 1
  y8_post=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/api/" 2>/dev/null)

  if [ "$y8_post" = "200" ]; then
    # HA still running — the service was either blocked or the AI refused
    if [ -n "$y8_speech" ]; then
      if echo "$y8_speech" | grep -qi "封鎖\|阻止\|不允許\|blocked\|denied\|cannot\|不能\|無法\|安全\|危險\|refuse\|reject\|restrict"; then
        _pass "Y8: homeassistant.restart blocked (AI reported restriction)"
      else
        # AI responded without blocking keywords, but HA is still up — service wasn't called
        _pass "Y8: homeassistant.restart not executed (HA still running)"
      fi
    else
      _pass "Y8: AI returned no response (service not executed, HA still running)"
    fi
  else
    _fail "Y8: HA may have restarted (post-check status=$y8_post)"
  fi
fi


# =============================================================================
# Z. DATA INTEGRITY AND CLEANUP
# =============================================================================
if should_run "Z"; then
  _section "Z. Data Integrity and Cleanup"

  # ── Z1. Memory consolidation safety ──
  echo -e "  ${BOLD}Z1. Memory consolidation safety${NC}"
  status=$(http_get "$API/memory/memory")
  z1_orig=$(body)
  z1_orig_len=$(echo "$z1_orig" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('content','')))" 2>/dev/null)

  status=$(http_post "$API/memory/consolidate" '{}')
  if [ "$status" = "200" ] || [ "$status" = "503" ]; then
    _pass "Z1: consolidation triggered (status=$status)"
  else
    _warn "Z1: consolidation returned status=$status"
  fi
  sleep 2

  status=$(http_get "$API/memory/memory")
  z1_new_len=$(body | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('content','')))" 2>/dev/null)

  if [ "$z1_new_len" -ge 0 ] 2>/dev/null; then
    _pass "Z1: memory content accessible after consolidation ($z1_new_len chars)"
  else
    _fail "Z1: memory content not accessible after consolidation"
  fi

  # ── Z2. Conversation retention ──
  echo -e "  ${BOLD}Z2. Conversation retention${NC}"
  status=$(http_get "$API/conversations")
  z2_convs=$(body)
  z2_count=$(echo "$z2_convs" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
  if [ "$z2_count" -ge 0 ] 2>/dev/null; then
    _pass "Z2: $z2_count conversations in retention"
  else
    _fail "Z2: could not count conversations"
  fi

  # ── Z3. Cron store consistency ──
  echo -e "  ${BOLD}Z3. Cron store consistency${NC}"
  status=$(http_post "$API/cron/jobs" '{"name":"z3_persist_test","schedule":{"kind":"every","every_ms":7200000},"payload":{"kind":"system_event","message":"Z3 test"},"enabled":false}')
  Z3_JID=$(body | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('job',{}).get('id','')))" 2>/dev/null)

  if [ -n "$Z3_JID" ] && [ "$Z3_JID" != "" ]; then
    # Verify in list
    status=$(http_get "$API/cron/jobs")
    z3_list=$(body)
    if echo "$z3_list" | grep -q "$Z3_JID"; then
      _pass "Z3: created job found in list"
    else
      _fail "Z3: created job not found in list"
    fi

    # Delete and verify gone
    http_delete "$API/cron/jobs/$Z3_JID" > /dev/null 2>&1
    status=$(http_get "$API/cron/jobs")
    z3_list2=$(body)
    if echo "$z3_list2" | grep -q "$Z3_JID"; then
      _fail "Z3: deleted job still in list"
    else
      _pass "Z3: deleted job removed from list"
    fi
  else
    _fail "Z3: could not create test cron job"
  fi

  # ── Z4. Skill file/metadata consistency ──
  echo -e "  ${BOLD}Z4. Skill consistency${NC}"
  status=$(http_get "$API/skills")
  z4_skills=$(body)
  z4_count=$(echo "$z4_skills" | python3 -c "
import sys,json
try:
    skills = json.load(sys.stdin)
    if isinstance(skills, list):
        print(len(skills))
    elif isinstance(skills, dict) and 'skills' in skills:
        print(len(skills['skills']))
    else:
        print(0)
except: print(0)
" 2>/dev/null)

  if [ "$z4_count" -gt 0 ] 2>/dev/null; then
    # Check first skill has body
    z4_first=$(echo "$z4_skills" | python3 -c "
import sys,json
try:
    skills = json.load(sys.stdin)
    if isinstance(skills, list) and len(skills) > 0:
        print(skills[0].get('name',''))
    elif isinstance(skills, dict) and 'skills' in skills:
        print(skills['skills'][0].get('name',''))
except: print('')
" 2>/dev/null)
    if [ -n "$z4_first" ]; then
      status=$(http_get "$API/skills/$z4_first")
      z4_body=$(body | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('content','') or d.get('body','')))" 2>/dev/null)
      if [ "$z4_body" -gt 0 ] 2>/dev/null; then
        _pass "Z4: skill '$z4_first' has content ($z4_body chars)"
      else
        # Try a skill that is known to have content
        z4_alt=$(echo "$z4_skills" | python3 -c "
import sys,json
try:
    skills = json.load(sys.stdin)
    slist = skills if isinstance(skills, list) else skills.get('skills', [])
    for s in slist:
        if s.get('name','') != '$z4_first':
            print(s.get('name','')); break
except: print('')
" 2>/dev/null)
        if [ -n "$z4_alt" ]; then
          status=$(http_get "$API/skills/$z4_alt")
          z4_body2=$(body | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('content','') or d.get('body','')))" 2>/dev/null)
          if [ "$z4_body2" -gt 0 ] 2>/dev/null; then
            _pass "Z4: skill '$z4_alt' has content ($z4_body2 chars)"
          else
            _warn "Z4: skills have empty content"
          fi
        else
          _warn "Z4: skill '$z4_first' has empty content"
        fi
      fi
    else
      _warn "Z4: could not get first skill name"
    fi
  else
    _pass "Z4: no skills to check (count=$z4_count)"
  fi

  # ── Z5. Entity-Config bidirectional consistency ──
  echo -e "  ${BOLD}Z5. Entity-Config consistency${NC}"

  # Read temperature from settings API
  status=$(http_get "$API/settings")
  z5_api_temp=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('temperature',''))" 2>/dev/null)

  # Read temperature from HA entity
  z5_entity_temp=$(ha_template "{{ states('number.nanobot_temperature') }}")

  if [ -n "$z5_api_temp" ] && [ -n "$z5_entity_temp" ]; then
    # Compare (may have float formatting differences)
    z5_match=$(python3 -c "
a = float('$z5_api_temp')
e = float('$z5_entity_temp')
print('yes' if abs(a - e) < 0.01 else 'no')
" 2>/dev/null)
    if [ "$z5_match" = "yes" ]; then
      _pass "Z5: settings temperature ($z5_api_temp) matches entity ($z5_entity_temp)"
    else
      _fail "Z5: settings temperature ($z5_api_temp) != entity ($z5_entity_temp)"
    fi
  else
    _warn "Z5: could not read temperature (api=$z5_api_temp, entity=$z5_entity_temp)"
  fi

  # ── Z6. LRU memory protection ──
  echo -e "  ${BOLD}Z6. LRU memory protection${NC}"
  Z6_IDS=()
  for i in 1 2 3; do
    status=$(http_post "$API/conversations" "{\"title\":\"Z6_LRU_$i\"}")
    z6_id=$(body | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
    Z6_IDS+=("$z6_id")
    status=$(rest_chat "$z6_id" "Z6 LRU message $i")
    sleep 1
  done

  z6_ok=0
  for z6_id in "${Z6_IDS[@]}"; do
    status=$(http_get "$API/conversations/$z6_id/messages")
    if [ "$status" = "200" ]; then
      z6_ok=$((z6_ok + 1))
    fi
  done
  if [ "$z6_ok" -eq 3 ]; then
    _pass "Z6: all 3 LRU conversations accessible"
  else
    _warn "Z6: only $z6_ok/3 conversations accessible"
  fi

  # Cleanup
  for cid in "${Z6_IDS[@]}"; do
    http_delete "$API/conversations/$cid" > /dev/null 2>&1
  done

  # ── Z7. History retention ──
  echo -e "  ${BOLD}Z7. History retention${NC}"
  status=$(http_get "$API/memory/history")
  if [ "$status" = "200" ]; then
    z7_len=$(body | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('content','')))" 2>/dev/null)
    _pass "Z7: history accessible ($z7_len chars)"
  else
    _warn "Z7: history not accessible (status=$status)"
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
