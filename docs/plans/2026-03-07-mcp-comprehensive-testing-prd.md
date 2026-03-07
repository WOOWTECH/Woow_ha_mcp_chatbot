# PRD: Comprehensive HA MCP Client Integration Testing

## 1. Overview

### 1.1 Purpose
Perform a comprehensive, systematic test of the ha_mcp_client Home Assistant integration to validate all components: MCP protocol compliance, 40+ tool executions, AI conversation with OpenAI tool calling, conversation history persistence, security controls, and end-to-end user workflows.

### 1.2 Scope
- **In Scope**: MCP protocol, all tools, AI conversation (OpenAI), history/recorder, security, config flow, E2E
- **Out of Scope**: Performance/load testing, UI rendering tests, multi-user concurrent testing

### 1.3 AI Service Configuration
- **Provider**: OpenAI
- **Model**: gpt-4-turbo
- **API Key**: YOUR_OPENAI_API_KEY_HERE

---

## 2. Test Environment

### 2.1 Infrastructure
| Component | Details |
|-----------|---------|
| HA Container | `homeassistant` on port 18123 |
| DB Container | `homeassistant-postgres` (pgvector:pg16) |
| AI Container | `ollama` on port 11434 (backup) |
| HA URL | http://localhost:18123 |
| MCP SSE Endpoint | http://localhost:18123/api/ha_mcp_client/sse |
| MCP Message Endpoint | http://localhost:18123/api/ha_mcp_client/sse/messages |
| HA Admin Credentials | admin / admin123 |
| HA Auth Token | (long-lived access token from onboarding) |

### 2.2 Virtual Entities (17 total, 4 areas)

#### 客廳 (Living Room) — 6 entities
| Entity ID | Type | Purpose |
|-----------|------|---------|
| light.living_room_main_light | light | Main ceiling light (brightness, color_temp) |
| light.living_room_ambient_light | light | Ambient/accent light (RGB color) |
| sensor.living_room_temperature | sensor | Temperature sensor (24°C) |
| sensor.living_room_humidity | sensor | Humidity sensor (55%) |
| binary_sensor.living_room_motion | binary_sensor | Motion detection |
| switch.living_room_tv | switch | TV power switch |

#### 臥室 (Bedroom) — 4 entities
| Entity ID | Type | Purpose |
|-----------|------|---------|
| light.bedroom_light | light | Bedroom light (brightness, color_temp) |
| sensor.bedroom_temperature | sensor | Temperature (22°C) |
| binary_sensor.bedroom_window | binary_sensor | Window contact sensor |
| switch.bedroom_fan | switch | Fan switch |

#### 廚房 (Kitchen) — 4 entities
| Entity ID | Type | Purpose |
|-----------|------|---------|
| light.kitchen_light | light | Kitchen ceiling light |
| sensor.kitchen_temperature | sensor | Temperature (26°C) |
| binary_sensor.kitchen_smoke | binary_sensor | Smoke detector |
| switch.kitchen_coffee_maker | switch | Coffee maker switch |

#### 車庫 (Garage) — 3 entities
| Entity ID | Type | Purpose |
|-----------|------|---------|
| cover.garage_door | cover | Garage door (open/close/position) |
| lock.garage_lock | lock | Garage lock |
| binary_sensor.garage_occupancy | binary_sensor | Occupancy sensor |

---

## 3. Test Phases

### Phase 1: MCP Protocol Compliance (9 tests)

Tests validate the SSE-based MCP server follows the MCP specification (protocol version 2024-11-05).

| ID | Test | Method | Expected Result |
|----|------|--------|-----------------|
| T1.1 | SSE Connection | GET /api/ha_mcp_client/sse with auth | 200, receive "endpoint" event with message URL |
| T1.2 | Initialize Handshake | POST initialize to message URL | Response with protocolVersion, capabilities.tools, serverInfo |
| T1.3 | Initialized Notification | POST notifications/initialized | No error (accepted silently) |
| T1.4 | Ping/Pong | POST ping method | Response with empty result {} |
| T1.5 | tools/list | POST tools/list | Array of 40+ tools with name, description, inputSchema |
| T1.6 | resources/list | POST resources/list | Empty resources array |
| T1.7 | Invalid Method | POST unknown_method | JSON-RPC error response with code -32601 |
| T1.8 | Multi-Session | Open 3 concurrent SSE connections | All 3 get independent sessions |
| T1.9 | No Auth | GET /api/ha_mcp_client/sse without token | 401 Unauthorized |

### Phase 2: Tool Execution Tests (14 test groups, 40+ individual tests)

Each tool is called via MCP `tools/call` method with appropriate arguments.

#### T2.1: Entity Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| get_entity_state | entity_id: "sensor.living_room_temperature" | state: "24", attributes with unit |
| search_entities | query: "light" | Returns all light entities |
| search_entities | area: "客廳" | Returns 6 living room entities |
| assign_entity_to_area | entity_id, area_id | Entity reassigned successfully |

#### T2.2: Service Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| call_service | domain: "light", service: "turn_on", entity_id: "light.living_room_main_light" | Light turned on |
| call_service | domain: "light", service: "turn_off", entity_id: "light.living_room_main_light" | Light turned off |
| call_service | domain: "switch", service: "toggle", entity_id: "switch.living_room_tv" | Switch toggled |
| list_services | domain: "light" | Lists light services (turn_on, turn_off, toggle) |
| list_services | (no filter) | Lists all available services |

#### T2.3: Area Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| list_areas | (none) | 4 areas: 客廳, 臥室, 廚房, 車庫 |
| create_area | name: "測試區域", icon: "mdi:test-tube" | New area created with ID |
| update_area | area_id, name: "測試區域-更新" | Area renamed |
| delete_area | area_id | Area deleted |

#### T2.4: Label Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| list_labels | (none) | Current labels list |
| create_label | name: "測試標籤", color: "#FF0000" | Label created |
| update_label | label_id, name: "更新標籤" | Label updated |
| delete_label | label_id | Label deleted |

#### T2.5: Device Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| list_devices | (none) | All devices |
| list_devices | area: "客廳" | Only living room devices |

#### T2.6: Automation Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| create_automation | alias, trigger, action | Automation created |
| list_automations | (none) | Shows created automation |
| toggle_automation | entity_id, enabled: false | Automation disabled |
| trigger_automation | entity_id | Automation triggered manually |

#### T2.7: Script Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| create_script | name: "test_script", sequence | Script created |
| list_scripts | (none) | Shows created script |
| run_script | entity_id | Script executed |

#### T2.8: Scene Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| create_scene | name: "movie_mode", entities | Scene created |
| list_scenes | (none) | Shows created scene |
| activate_scene | entity_id | Scene activated, entities set |

#### T2.9: History Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| get_history | entity_id: "light.living_room_main_light", hours: 1 | State change history |

#### T2.10: System Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| system_overview | (none) | Entity counts, area counts, by domain breakdown |

#### T2.11: Control Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| control_light | entity_id, action: "on", brightness: 128 | Light on at 50% brightness |
| control_light | entity_id, action: "on", color_temp: 200 | Light with warm color temp |
| control_cover | entity_id: "cover.garage_door", action: "open" | Garage door opens |
| control_cover | entity_id, action: "set_position", position: 50 | Door at 50% |

#### T2.12: Calendar Tools
| Tool | Arguments | Expected |
|------|-----------|----------|
| create_calendar_event | (skip if no calendar entity) | Calendar event created or graceful error |

#### T2.13-14: Security Tests
| Tool | Arguments | Expected |
|------|-----------|----------|
| call_service | domain: "homeassistant", service: "restart" | BLOCKED response |
| call_service | domain: "hassio", service: "* " | BLOCKED response |
| call_service | domain: "supervisor", service: "*" | BLOCKED response |
| call_service | domain: "recorder", service: "purge" | BLOCKED response |

### Phase 3: AI Conversation Tests (8 tests)

Tests use HA's conversation API with OpenAI (gpt-4-turbo) as the AI backend.

| ID | Test | User Message | Expected Behavior |
|----|------|-------------|-------------------|
| T3.1 | Basic Chat | "Hello, what can you help me with?" | Text response listing capabilities |
| T3.2 | Single Tool | "Turn on the living room main light" | AI calls call_service/control_light, light turns on |
| T3.3 | Multi Tool | "What is the temperature in each room?" | AI calls get_entity_state for 3-4 temperature sensors |
| T3.4 | Complex | "Create a scene called 'Movie Night' with living room ambient light at 20% and TV on" | AI calls create_scene with correct entities |
| T3.5 | Context | (follow-up) "Now turn it off" | AI understands "it" from context, turns off correct entity |
| T3.6 | Tool Limit | "Check every entity state one by one" | Stops at max_tool_calls (10) with partial response |
| T3.7 | Error | "Turn on the basement light" | Graceful error (no such entity), user-friendly message |
| T3.8 | System Prompt | "Create an automation" | AI follows system prompt addon guidance |

### Phase 4: Conversation History & Recorder Tests (6 tests)

| ID | Test | Method | Expected |
|----|------|--------|----------|
| T4.1 | Persistence | Send message, check DB | Message row in ha_mcp_client_messages |
| T4.2 | Load History | New conversation with same ID | Previous context available |
| T4.3 | Clear History | Call clear_conversation_history service | History cleared for user |
| T4.4 | Export JSON | Call export_conversation_history (format: json) | Valid JSON output |
| T4.5 | Export Markdown | Call export_conversation_history (format: markdown) | Formatted markdown |
| T4.6 | User Isolation | Different user's history | Not accessible cross-user |

### Phase 5: Security & Edge Case Tests (6 tests)

| ID | Test | Method | Expected |
|----|------|--------|----------|
| T5.1 | No Auth | SSE without Bearer token | 401 Unauthorized |
| T5.2 | Blocked Domain | tools/call with homeassistant.restart | blocked=True in response |
| T5.3 | Bad Args | tools/call with wrong argument types | Graceful error response |
| T5.4 | Unknown Tool | tools/call with "nonexistent_tool" | Tool not found error |
| T5.5 | Large Payload | POST 1MB+ message | Handled gracefully |
| T5.6 | Key Security | Check HA logs for API key | API key not in plaintext |

### Phase 6: Integration & E2E Tests (4 tests)

| ID | Test | Steps | Expected |
|----|------|-------|----------|
| T6.1 | Scene E2E | Conversation creates scene → verify via HA API | Scene exists and works |
| T6.2 | Automation E2E | Conversation creates automation → trigger → verify | Automation fires correctly |
| T6.3 | Config Update | Change AI service settings via options flow API | Settings updated, service reconfigured |
| T6.4 | Reload | Unload and reload integration entry | All services restored |

---

## 4. Test Execution Strategy

### 4.1 Test Script Architecture
- Single comprehensive Python test script (`tests/test_comprehensive.py`)
- Uses `requests` library (not aiohttp, due to DNS resolver bug)
- SSE parsing via line-by-line stream reading
- Results logged to `progress.md` and console
- URL rewriting for internal container IPs (regex: `http://[\d.]+:8123` → `http://127.0.0.1:18123`)

### 4.2 Execution Order
1. Phase 0: Setup (switch to OpenAI, verify health)
2. Phase 1: Protocol tests (foundation)
3. Phase 2: Tool tests (direct tool calls)
4. Phase 3: AI conversation tests (AI + tools)
5. Phase 4: History tests (persistence)
6. Phase 5: Security tests (edge cases)
7. Phase 6: E2E tests (full workflows)
8. Phase 7: Report generation

### 4.3 Pass/Fail Criteria
- **PASS**: Expected result matches actual result
- **FAIL**: Unexpected error, wrong result, or missing data
- **SKIP**: Prerequisite not met (e.g., no calendar entity)
- **Overall**: All phases must have >90% pass rate

---

## 5. Deliverables

1. `tests/test_comprehensive.py` — Automated test script
2. `progress.md` — Real-time test results log
3. `docs/plans/2026-03-07-mcp-comprehensive-testing-prd.md` — This PRD
4. Final test report with pass/fail matrix and bug list

---

## 6. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| OpenAI API rate limits | Add delays between conversation tests |
| Container network issues | Use URL rewriting for internal IPs |
| aiohttp bug | Use requests library |
| Token expiration | Long-lived token valid for 1 year |
| Virtual entity limitations | Test within virtual entity capabilities |
