# Task Plan: Deploy & Test HA MCP Client

## Goal
Deploy ha_mcp_client + hass-virtual to the `homeassistant` container (port 18123, with PostgreSQL), configure virtual entities across 4 areas, and verify MCP functionality.

## Environment
- **HA Container**: `homeassistant` → port 18123, config at `/var/tmp/vibe-kanban/worktrees/8573-homeassistant-do/podman_docker_app/homeassistant/config`
- **DB Container**: `homeassistant-postgres` (pgvector:pg16)
- **Network**: `homeassistant_default`
- **DB Creds**: user=homeassistant, pass=ha_secure_password_change_me, db=homeassistant

## Phases

### Phase 1: Start containers & prepare HA config `status: pending`
- [ ] Start homeassistant-postgres
- [ ] Start homeassistant
- [ ] Wait for HA to initialize
- [ ] Create/update configuration.yaml with recorder postgres URL
- [ ] Verify HA is accessible at http://localhost:18123

### Phase 2: Install hass-virtual `status: pending`
- [ ] Download hass-virtual to custom_components/virtual/
- [ ] Create virtual.yaml with 17 entities across 4 areas
- [ ] Add virtual config to configuration.yaml
- [ ] Restart HA to load virtual integration

### Phase 3: Deploy ha_mcp_client `status: pending`
- [ ] Copy ha_mcp_client to custom_components/ha_mcp_client/
- [ ] Install Python dependencies (anthropic, openai, httpx) in container
- [ ] Restart HA to load MCP integration

### Phase 4: HA onboarding & integration setup `status: pending`
- [ ] Complete HA onboarding (create user account)
- [ ] Add Virtual integration via UI
- [ ] Create 4 areas (客廳, 臥室, 廚房, 車庫)
- [ ] Assign virtual devices to areas
- [ ] Add ha_mcp_client integration via UI

### Phase 5: Verify & test `status: pending`
- [ ] Verify 17 virtual entities visible
- [ ] Test MCP SSE endpoint /api/mcp/sse
- [ ] Test tool calls via MCP
- [ ] Verify recorder using PostgreSQL

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| (none yet) | | |
