# Findings & Decisions

## Requirements
- Full coverage test of ha_mcp_client integration
- Test MCP protocol compliance (SSE, JSON-RPC 2.0)
- Test all MCP tools individually
- Test AI conversation with tool calling loop
- Test conversation history & recorder
- Test security controls (blocked services, auth)
- End-to-end integration tests
- Generate comprehensive test report

## Research Findings
- Codebase has 17 Python source files, 31 MCP tools, 4 AI service providers
- MCP server uses SSE transport with JSON-RPC 2.0
- Protocol version: 2024-11-05
- Max sessions: 50, Max queue: 100 messages
- Conversation entity supports multi-turn tool calling loop
- ConversationRecorder uses SQLite via HA's recorder
- Security: 5 blocked service domains, 3 blocked individual services

## Bugs Found & Fixed

### Bug 1: control_light uses wrong service action (FIXED)
- **File**: `custom_components/ha_mcp_client/mcp/tools/registry.py`
- **Problem**: `_handle_control_light()` passed `action` directly to `call_ha_service()`, resulting in `light.on` (doesn't exist) instead of `light.turn_on`
- **Fix**: Added `service_map = {"on": "turn_on", "off": "turn_off", "toggle": "toggle"}` matching the pattern used by `_handle_control_cover()`

### Bug 2: notifications/initialized method name (FIXED in previous session)
- **File**: `custom_components/ha_mcp_client/mcp/server.py`
- **Problem**: Handler expected `initialized` but MCP spec sends `notifications/initialized`
- **Fix**: Updated handler to match correct method name

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Ollama llama3.1:8b for testing | OpenAI API key provided was invalid (401), Ollama available locally |
| Python requests library | Avoid aiohttp DNS resolver bug |
| Test via both MCP and HA API | Cover protocol layer AND integration layer |
| Sequential test execution | Ordered dependencies between test phases |
| host.containers.internal for Ollama | HA and Ollama on different container networks |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| MCP POST returns 202 (no JSON body) | Built MCPSSESession with background SSE reader thread |
| Conversation goes to wrong agent | Added agent_id parameter to conversation API |
| Entity IDs have suffix duplication | Discovered actual IDs from /api/states |
| OpenAI API key invalid (401) | Switched to Ollama llama3.1:8b |
| Ollama hostname "ollama" not resolved | Used host.containers.internal:11434 |
| Unicode escaping in JSON responses | Parse JSON before string comparison |
| config_entries/reload WS command unknown | Used REST API endpoint instead |

## Resources
- HA REST API: http://localhost:18123/api/
- MCP SSE: http://localhost:18123/api/ha_mcp_client/sse
- MCP Messages: http://localhost:18123/api/ha_mcp_client/sse/messages
- HA WebSocket: ws://localhost:18123/api/websocket
- HA Conversation API: POST /api/conversation/process
- Ollama API: http://host.containers.internal:11434 (from within HA container)
