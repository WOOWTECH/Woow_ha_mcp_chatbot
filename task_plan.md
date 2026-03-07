# Task Plan: Comprehensive HA MCP Client Integration Testing

## Goal
Perform a full-coverage test of the ha_mcp_client integration, covering MCP protocol compliance, all 40+ tool executions, AI conversation with OpenAI (tool calling loop), conversation history/recorder, security controls, and end-to-end flows — to identify and fix any bugs before production use.

## Current Phase
Phase 0 (PRD & Setup)

## Environment
- **HA URL**: http://localhost:18123
- **MCP SSE**: http://localhost:18123/api/ha_mcp_client/sse
- **MCP Messages**: http://localhost:18123/api/ha_mcp_client/sse/messages
- **HA Admin**: admin / admin123
- **Long-lived Token**: YOUR_HA_TOKEN_HERE
- **Entry ID**: 01KK3W34MX75ZR1EMP35AAKX65
- **AI Service**: OpenAI (gpt-4-turbo) with provided API key
- **Virtual Entities**: 17 across 4 areas (客廳, 臥室, 廚房, 車庫)
- **Containers**: homeassistant (port 18123), homeassistant-postgres, ollama

## Phases

### Phase 0: PRD Creation & Environment Setup
- [x] Explore codebase and understand all components
- [x] Create PRD document
- [ ] Switch AI service from Ollama to OpenAI
- [ ] Verify HA container health
- **Status:** in_progress

### Phase 1: MCP Protocol Compliance Tests
- [ ] T1.1: SSE connection establishment & heartbeat
- [ ] T1.2: Initialize handshake (protocol version, capabilities, server info)
- [ ] T1.3: Initialized notification (both forms)
- [ ] T1.4: Ping/pong
- [ ] T1.5: tools/list — verify all 40+ tools returned with correct schemas
- [ ] T1.6: resources/list — verify empty list returned
- [ ] T1.7: Invalid method handling (error response)
- [ ] T1.8: Session management (multiple concurrent sessions)
- [ ] T1.9: Authentication — reject unauthenticated requests
- **Status:** pending

### Phase 2: Tool Execution Tests (tools/call via MCP)
- [ ] T2.1: Entity tools — get_entity_state, search_entities, assign_entity_to_area, assign_entity_to_labels
- [ ] T2.2: Service tools — call_service (turn_on/off), list_services
- [ ] T2.3: Area tools — list/create/update/delete areas
- [ ] T2.4: Label tools — list/create/update/delete labels
- [ ] T2.5: Device tools — list_devices (filtered by area)
- [ ] T2.6: Automation tools — create/list/toggle/trigger
- [ ] T2.7: Script tools — create/list/run
- [ ] T2.8: Scene tools — create/list/activate
- [ ] T2.9: History tools — get_history
- [ ] T2.10: System tools — system_overview
- [ ] T2.11: Control tools — control_light, control_climate, control_cover
- [ ] T2.12: Calendar tools — create_calendar_event
- [ ] T2.13: Security — blocked service domains
- [ ] T2.14: Security — blocked specific services
- **Status:** pending

### Phase 3: AI Conversation Tests (via HA Conversation API with OpenAI)
- [ ] T3.1: Basic conversation — simple question
- [ ] T3.2: Single tool call — "Turn on the living room light"
- [ ] T3.3: Multi-tool call — "What's the temperature in each room?"
- [ ] T3.4: Complex scenario — "Create an automation for all lights off at midnight"
- [ ] T3.5: Conversation context continuity
- [ ] T3.6: Max tool calls limit
- [ ] T3.7: Error handling — non-existent entity
- [ ] T3.8: System prompt validation
- **Status:** pending

### Phase 4: Conversation History & Recorder Tests
- [ ] T4.1: Messages persisted to DB
- [ ] T4.2: Load conversation history for context
- [ ] T4.3: Clear conversation history service
- [ ] T4.4: Export history (JSON)
- [ ] T4.5: Export history (Markdown)
- [ ] T4.6: Per-user isolation
- **Status:** pending

### Phase 5: Security & Edge Case Tests
- [ ] T5.1: Unauthenticated MCP access rejection
- [ ] T5.2: Blocked service via MCP
- [ ] T5.3: Invalid tool arguments
- [ ] T5.4: Non-existent tool call
- [ ] T5.5: Oversized message handling
- [ ] T5.6: API key not exposed in logs
- **Status:** pending

### Phase 6: Integration & End-to-End Tests
- [ ] T6.1: E2E — AI creates scene via conversation
- [ ] T6.2: E2E — AI creates automation via conversation
- [ ] T6.3: Config flow update — change settings
- [ ] T6.4: Integration reload
- **Status:** pending

### Phase 7: Report Generation
- [ ] Compile all test results
- [ ] Document bugs found
- [ ] Generate summary report with pass/fail matrix
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use OpenAI (gpt-4-turbo) | User provided OpenAI API key, good tool calling support |
| Test via MCP SSE + HA REST API | Cover both MCP protocol and HA conversation integration |
| Python requests for MCP testing | Avoid aiohttp DNS resolver bug found previously |
| Test all 40+ tools individually | Ensure complete coverage |
| Use long-lived token for auth | Stable auth across all test phases |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| (none yet) | - | - |
