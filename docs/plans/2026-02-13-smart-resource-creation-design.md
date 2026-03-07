# Smart Resource Creation Design

## Problem

AI calls `create_scene`, `create_automation`, `create_script` without providing required parameters:
- `create_scene` missing `entities`
- `create_automation` missing `trigger` and `action`

Example from logs:
```
Error executing tool create_scene: args were: {'name': '全开', 'icon': 'mdi:home'}
Error executing tool create_automation: args were: {'alias': '儲藏室', 'description': '...', 'mode': 'single'}
```

## Solution

Enhance the System Prompt to instruct AI to:
1. Query entities using `search_entities` before creating resources
2. Infer entities based on user intent (e.g., "全開" = all controllable entities ON)
3. Scope by area/context based on conversation

## Design Decisions

1. **Context-based inference**: AI determines scope from conversation context
2. **All HA entity domains**: Not limited to specific types
3. **Query-first approach**: AI must use `search_entities` before `create_*`

## Implementation

Modify `DEFAULT_SYSTEM_PROMPT` in `const.py` to add resource creation guidelines.

## System Prompt Addition

```
## Creating Resources (Scenes, Automations, Scripts)

When user asks to create a scene, automation, or script:

### Step 1: Query Entities
- Use `search_entities` to find relevant entities
- Filter by area if user mentioned a specific area
- If user says "all" or no scope specified, query all entities

### Step 2: Determine Intent
- "全開/turn on all": Set entities to on/open state
- "全關/turn off all": Set entities to off/close state
- Specific settings: Use values mentioned by user

### Step 3: Build Parameters
For create_scene:
- entities: {"entity_id": {"state": "on/off", ...attributes}}

For create_automation:
- trigger: [{"platform": "...", ...}]
- action: [{"service": "...", "target": {"entity_id": "..."}}]

For create_script:
- sequence: [{"service": "...", "target": {"entity_id": "..."}}]

### Example Flow
User: "建立一個全開情境"

1. Call search_entities() to get all entities
2. Build entities dict with all lights/switches set to "on"
3. Call create_scene(name="全開", entities={...})

User: "建立客廳全關情境"

1. Call search_entities(area_id="living_room")
2. Build entities dict with matched entities set to "off"
3. Call create_scene(name="客廳全關", entities={...})
```
