"""MCP Tool Registry - manages all available tools."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from homeassistant.core import HomeAssistant

from .helpers import (
    get_entity_state,
    call_ha_service,
    search_entities,
    get_areas,
    get_devices,
    get_services,
    get_automations,
    get_scripts,
    get_history,
    create_automation,
    create_script,
    create_scene,
    create_calendar_event,
    create_area,
    create_label,
    get_labels,
    update_area,
    delete_area,
    update_label,
    delete_label,
    assign_entity_to_area,
    assign_entity_to_labels,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Definition of an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    category: str = "general"


class ToolRegistry:
    """Registry for MCP tools."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the tool registry."""
        self.hass = hass
        self._tools: dict[str, ToolDefinition] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        """Register all built-in tools."""
        # Entity Tools
        self.register(
            ToolDefinition(
                name="get_entity_state",
                description="Get the current state of a Home Assistant entity",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "The entity ID (e.g., light.living_room)",
                        }
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_get_entity_state,
                category="entity",
            )
        )

        self.register(
            ToolDefinition(
                name="search_entities",
                description="Search for entities by name, domain, area, or device",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (name or entity_id)",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Filter by domain (e.g., light, switch, sensor)",
                        },
                        "area_id": {
                            "type": "string",
                            "description": "Filter by area ID",
                        },
                        "device_id": {
                            "type": "string",
                            "description": "Filter by device ID",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 50)",
                            "default": 50,
                        },
                    },
                },
                handler=self._handle_search_entities,
                category="entity",
            )
        )

        # Service Tools
        self.register(
            ToolDefinition(
                name="call_service",
                description="Call a Home Assistant service to control devices",
                input_schema={
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "Service domain (e.g., light, switch, climate)",
                        },
                        "service": {
                            "type": "string",
                            "description": "Service name (e.g., turn_on, turn_off, set_temperature)",
                        },
                        "entity_id": {
                            "type": "string",
                            "description": "Target entity ID",
                        },
                        "data": {
                            "type": "object",
                            "description": "Additional service data",
                        },
                    },
                    "required": ["domain", "service"],
                },
                handler=self._handle_call_service,
                category="service",
            )
        )

        self.register(
            ToolDefinition(
                name="list_services",
                description="List available services, optionally filtered by domain",
                input_schema={
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "Filter by domain",
                        },
                    },
                },
                handler=self._handle_list_services,
                category="service",
            )
        )

        # Area and Device Tools
        self.register(
            ToolDefinition(
                name="list_areas",
                description="List all areas in Home Assistant",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_list_areas,
                category="area",
            )
        )

        self.register(
            ToolDefinition(
                name="create_area",
                description="Create a new area in Home Assistant. Areas are used to organize devices and entities by physical location.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the area (e.g., '客廳', 'Living Room', '臥室')",
                        },
                        "icon": {
                            "type": "string",
                            "description": "Optional MDI icon (e.g., 'mdi:sofa', 'mdi:bed')",
                        },
                        "floor_id": {
                            "type": "string",
                            "description": "Optional floor ID to assign the area to",
                        },
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of label IDs to assign to the area",
                        },
                    },
                    "required": ["name"],
                },
                handler=self._handle_create_area,
                category="area",
            )
        )

        self.register(
            ToolDefinition(
                name="list_labels",
                description="List all labels in Home Assistant",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_list_labels,
                category="label",
            )
        )

        self.register(
            ToolDefinition(
                name="create_label",
                description="Create a new label in Home Assistant. Labels are used to categorize and tag entities, devices, and areas.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the label (e.g., '重要', 'Important', '節能')",
                        },
                        "color": {
                            "type": "string",
                            "description": "Optional color in hex format without # (e.g., 'ff0000' for red, '00ff00' for green)",
                        },
                        "icon": {
                            "type": "string",
                            "description": "Optional MDI icon (e.g., 'mdi:star', 'mdi:tag')",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description for the label",
                        },
                    },
                    "required": ["name"],
                },
                handler=self._handle_create_label,
                category="label",
            )
        )

        self.register(
            ToolDefinition(
                name="update_area",
                description="Update an existing area in Home Assistant. Use list_areas first to find the area_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "area_id": {
                            "type": "string",
                            "description": "Area ID to update (use list_areas to find it)",
                        },
                        "name": {
                            "type": "string",
                            "description": "New name for the area",
                        },
                        "icon": {
                            "type": "string",
                            "description": "New MDI icon (e.g., 'mdi:sofa')",
                        },
                        "floor_id": {
                            "type": "string",
                            "description": "New floor ID",
                        },
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "New list of label IDs",
                        },
                    },
                    "required": ["area_id"],
                },
                handler=self._handle_update_area,
                category="area",
            )
        )

        self.register(
            ToolDefinition(
                name="delete_area",
                description="Delete an area from Home Assistant. Use list_areas first to find the area_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "area_id": {
                            "type": "string",
                            "description": "Area ID to delete (use list_areas to find it)",
                        },
                    },
                    "required": ["area_id"],
                },
                handler=self._handle_delete_area,
                category="area",
            )
        )

        self.register(
            ToolDefinition(
                name="update_label",
                description="Update an existing label in Home Assistant. Use list_labels first to find the label_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "label_id": {
                            "type": "string",
                            "description": "Label ID to update (use list_labels to find it)",
                        },
                        "name": {
                            "type": "string",
                            "description": "New name for the label",
                        },
                        "color": {
                            "type": "string",
                            "description": "New color in hex format (e.g., 'ff0000')",
                        },
                        "icon": {
                            "type": "string",
                            "description": "New MDI icon (e.g., 'mdi:star')",
                        },
                        "description": {
                            "type": "string",
                            "description": "New description",
                        },
                    },
                    "required": ["label_id"],
                },
                handler=self._handle_update_label,
                category="label",
            )
        )

        self.register(
            ToolDefinition(
                name="delete_label",
                description="Delete a label from Home Assistant. Use list_labels first to find the label_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "label_id": {
                            "type": "string",
                            "description": "Label ID to delete (use list_labels to find it)",
                        },
                    },
                    "required": ["label_id"],
                },
                handler=self._handle_delete_label,
                category="label",
            )
        )

        self.register(
            ToolDefinition(
                name="assign_entity_to_area",
                description="Assign an entity to an area. Use search_entities to find entity_id and list_areas to find area_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Entity ID to assign (e.g., 'light.living_room')",
                        },
                        "area_id": {
                            "type": "string",
                            "description": "Area ID to assign to, or null to remove from area",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_assign_entity_to_area,
                category="entity",
            )
        )

        self.register(
            ToolDefinition(
                name="assign_entity_to_labels",
                description="Assign labels to an entity. Use search_entities to find entity_id and list_labels to find label_ids.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Entity ID to assign labels to (e.g., 'light.living_room')",
                        },
                        "label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of label IDs to assign (replaces existing labels)",
                        },
                    },
                    "required": ["entity_id", "label_ids"],
                },
                handler=self._handle_assign_entity_to_labels,
                category="entity",
            )
        )

        self.register(
            ToolDefinition(
                name="list_devices",
                description="List devices, optionally filtered by area",
                input_schema={
                    "type": "object",
                    "properties": {
                        "area_id": {
                            "type": "string",
                            "description": "Filter by area ID",
                        },
                    },
                },
                handler=self._handle_list_devices,
                category="device",
            )
        )

        # Automation Tools
        self.register(
            ToolDefinition(
                name="list_automations",
                description="List all automations",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_list_automations,
                category="automation",
            )
        )

        self.register(
            ToolDefinition(
                name="toggle_automation",
                description="Enable or disable an automation",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Automation entity ID",
                        },
                        "enable": {
                            "type": "boolean",
                            "description": "True to enable, False to disable",
                        },
                    },
                    "required": ["entity_id", "enable"],
                },
                handler=self._handle_toggle_automation,
                category="automation",
            )
        )

        self.register(
            ToolDefinition(
                name="trigger_automation",
                description="Manually trigger an automation",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Automation entity ID",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_trigger_automation,
                category="automation",
            )
        )

        self.register(
            ToolDefinition(
                name="create_automation",
                description="""Create a new automation in Home Assistant. IMPORTANT: You MUST provide 'alias', 'trigger', AND 'action' parameters.

REQUIRED WORKFLOW:
1. FIRST call search_entities() to find relevant entities (sensors for triggers, actuators for actions)
2. Build trigger list with proper entity_ids from step 1
3. Build action list with proper entity_ids from step 1
4. THEN call create_automation with all required parameters

NEVER call create_automation without trigger and action parameters!""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "alias": {
                            "type": "string",
                            "description": "REQUIRED: Name/alias for the automation (e.g., 'Turn on lights at sunset')",
                        },
                        "trigger": {
                            "type": "array",
                            "description": "REQUIRED: List of triggers. First use search_entities() to find valid entity IDs. Example: [{'platform': 'state', 'entity_id': 'binary_sensor.motion', 'to': 'on'}]",
                            "items": {"type": "object"},
                        },
                        "action": {
                            "type": "array",
                            "description": "REQUIRED: List of actions. First use search_entities() to find valid entity IDs. Example: [{'service': 'light.turn_on', 'target': {'entity_id': 'light.living_room'}}]",
                            "items": {"type": "object"},
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description of what this automation does",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["single", "restart", "queued", "parallel"],
                            "description": "Execution mode (default: single)",
                        },
                        "condition": {
                            "type": "array",
                            "description": "Optional list of conditions that must be true for actions to run",
                            "items": {"type": "object"},
                        },
                    },
                    "required": ["alias", "trigger", "action"],
                },
                handler=self._handle_create_automation,
                category="automation",
            )
        )

        # Script Tools
        self.register(
            ToolDefinition(
                name="list_scripts",
                description="List all scripts",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_list_scripts,
                category="script",
            )
        )

        self.register(
            ToolDefinition(
                name="run_script",
                description="Run a script",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Script entity ID",
                        },
                        "variables": {
                            "type": "object",
                            "description": "Variables to pass to the script",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_run_script,
                category="script",
            )
        )

        self.register(
            ToolDefinition(
                name="create_script",
                description="""Create a new script in Home Assistant. IMPORTANT: You MUST provide 'name' AND 'sequence' parameters.

REQUIRED WORKFLOW:
1. FIRST call search_entities() to find the entities you want to control
2. Build sequence list with proper entity_ids from step 1
3. THEN call create_script with all required parameters

NEVER call create_script without the 'sequence' parameter!""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "REQUIRED: Name for the script (e.g., 'Morning Routine')",
                        },
                        "sequence": {
                            "type": "array",
                            "description": "REQUIRED: List of actions. First use search_entities() to find valid entity IDs. Example: [{'service': 'light.turn_on', 'target': {'entity_id': 'light.bedroom'}}]",
                            "items": {"type": "object"},
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description of what this script does",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["single", "restart", "queued", "parallel"],
                            "description": "Execution mode (default: single)",
                        },
                        "icon": {
                            "type": "string",
                            "description": "Optional MDI icon (e.g., 'mdi:script')",
                        },
                        "fields": {
                            "type": "object",
                            "description": "Optional input fields/variables the script accepts",
                        },
                    },
                    "required": ["name", "sequence"],
                },
                handler=self._handle_create_script,
                category="script",
            )
        )

        # History Tools
        self.register(
            ToolDefinition(
                name="get_history",
                description="Get historical state changes for an entity",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Entity ID to get history for",
                        },
                        "hours": {
                            "type": "integer",
                            "description": "Number of hours to look back (default: 24)",
                            "default": 24,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of records (default: 100)",
                            "default": 100,
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_get_history,
                category="history",
            )
        )

        # System Tools
        self.register(
            ToolDefinition(
                name="system_overview",
                description="Get an overview of the Home Assistant system",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_system_overview,
                category="system",
            )
        )

        # Light Control
        self.register(
            ToolDefinition(
                name="control_light",
                description="Control a light (turn on/off, set brightness, color)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Light entity ID",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["turn_on", "turn_off", "toggle"],
                            "description": "Action to perform",
                        },
                        "brightness": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 255,
                            "description": "Brightness level (0-255)",
                        },
                        "color_temp": {
                            "type": "integer",
                            "description": "Color temperature in mireds",
                        },
                        "rgb_color": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "RGB color as [r, g, b]",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_light,
                category="light",
            )
        )

        # Climate Control
        self.register(
            ToolDefinition(
                name="control_climate",
                description="Control a climate device (thermostat, AC)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Climate entity ID",
                        },
                        "hvac_mode": {
                            "type": "string",
                            "enum": ["off", "heat", "cool", "heat_cool", "auto", "dry", "fan_only"],
                            "description": "HVAC mode",
                        },
                        "temperature": {
                            "type": "number",
                            "description": "Target temperature",
                        },
                        "target_temp_high": {
                            "type": "number",
                            "description": "High target temperature (for heat_cool mode)",
                        },
                        "target_temp_low": {
                            "type": "number",
                            "description": "Low target temperature (for heat_cool mode)",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_control_climate,
                category="climate",
            )
        )

        # Cover Control
        self.register(
            ToolDefinition(
                name="control_cover",
                description="Control a cover (blinds, garage door, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Cover entity ID",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["open", "close", "stop", "set_position"],
                            "description": "Action to perform",
                        },
                        "position": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Position (0-100, for set_position action)",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_cover,
                category="cover",
            )
        )

        # Scene Tools
        self.register(
            ToolDefinition(
                name="list_scenes",
                description="List all scenes",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_list_scenes,
                category="scene",
            )
        )

        self.register(
            ToolDefinition(
                name="activate_scene",
                description="Activate a scene",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Scene entity ID",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_activate_scene,
                category="scene",
            )
        )

        self.register(
            ToolDefinition(
                name="create_scene",
                description="""Create a new scene in Home Assistant. IMPORTANT: You MUST provide BOTH 'name' AND 'entities' parameters.

REQUIRED WORKFLOW:
1. FIRST call search_entities() to find controllable entities (light.*, switch.*, cover.*, fan.*, climate.*)
2. THEN call create_scene with the entities dict built from step 1

Example: For "全開情境" (turn on all):
- Call search_entities() first
- Build entities dict: {"light.xxx": {"state": "on"}, "switch.xxx": {"state": "on"}, ...}
- Call create_scene(name="全開", entities={...})

NEVER call create_scene without the 'entities' parameter!""",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the scene (e.g., 'Movie Night', '全開')",
                        },
                        "entities": {
                            "type": "object",
                            "description": "REQUIRED: Dict of entity_id to desired state. You MUST use search_entities() first to get valid entity IDs. Example: {'light.living_room': {'state': 'on', 'brightness': 128}, 'switch.fan': {'state': 'on'}}",
                        },
                        "icon": {
                            "type": "string",
                            "description": "Optional MDI icon (e.g., 'mdi:movie')",
                        },
                    },
                    "required": ["name", "entities"],
                },
                handler=self._handle_create_scene,
                category="scene",
            )
        )

        # Calendar Tools
        self.register(
            ToolDefinition(
                name="create_calendar_event",
                description="Create a new event in a Home Assistant calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_entity_id": {
                            "type": "string",
                            "description": "Calendar entity ID (e.g., 'calendar.home' or 'calendar.family')",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Event title/summary",
                        },
                        "start": {
                            "type": "string",
                            "description": "Start datetime in ISO format (e.g., '2024-01-15T10:00:00')",
                        },
                        "end": {
                            "type": "string",
                            "description": "End datetime in ISO format (e.g., '2024-01-15T11:00:00')",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional event description",
                        },
                        "location": {
                            "type": "string",
                            "description": "Optional event location",
                        },
                    },
                    "required": ["calendar_entity_id", "summary", "start", "end"],
                },
                handler=self._handle_create_calendar_event,
                category="calendar",
            )
        )

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        _LOGGER.debug("Registered tool: %s", tool.name)

    def unregister(self, name: str) -> None:
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_all(self) -> list[ToolDefinition]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_by_category(self, category: str) -> list[ToolDefinition]:
        """Get tools by category."""
        return [t for t in self._tools.values() if t.category == category]

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name."""
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")

        _LOGGER.debug("Executing tool %s with args: %s", name, arguments)
        try:
            # Filter arguments to only include expected handler parameters
            import inspect
            sig = inspect.signature(tool.handler)
            valid_params = set(sig.parameters.keys()) - {"self"}
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            if has_var_keyword:
                filtered_args = arguments
            else:
                filtered_args = {k: v for k, v in arguments.items() if k in valid_params}
                dropped = set(arguments.keys()) - valid_params
                if dropped:
                    _LOGGER.warning("Tool %s: dropped unexpected arguments: %s", name, dropped)

            result = await tool.handler(**filtered_args)
            _LOGGER.debug("Tool %s executed successfully", name)
            return result
        except TypeError as te:
            _LOGGER.error("Tool %s argument error: %s", name, te)
            return {"error": f"Invalid arguments for tool '{name}': {te}"}
        except Exception as e:
            _LOGGER.error("Error executing tool %s: %s", name, e)
            raise

    # Tool Handlers

    async def _handle_get_entity_state(self, entity_id: str) -> dict[str, Any]:
        """Handle get_entity_state tool."""
        result = await get_entity_state(self.hass, entity_id)
        if result is None:
            return {"error": f"Entity {entity_id} not found"}
        return result

    async def _handle_search_entities(
        self,
        query: str | None = None,
        domain: str | None = None,
        area_id: str | None = None,
        device_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Handle search_entities tool."""
        return await search_entities(
            self.hass, query, domain, area_id, device_id, limit
        )

    async def _handle_call_service(
        self,
        domain: str,
        service: str,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Handle call_service tool."""
        service_data = data or {}
        # Merge any extra kwargs (e.g. item, brightness) into service_data
        # so AI models that pass service params directly still work.
        for key, value in kwargs.items():
            if key not in service_data:
                service_data[key] = value
        target = None
        if entity_id:
            target = {"entity_id": entity_id}
        return await call_ha_service(self.hass, domain, service, service_data, target)

    async def _handle_list_services(
        self, domain: str | None = None
    ) -> dict[str, Any]:
        """Handle list_services tool."""
        return await get_services(self.hass, domain)

    async def _handle_list_areas(self) -> list[dict[str, Any]]:
        """Handle list_areas tool."""
        return await get_areas(self.hass)

    async def _handle_create_area(
        self,
        name: str,
        icon: str | None = None,
        floor_id: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Handle create_area tool."""
        return await create_area(
            self.hass,
            name=name,
            icon=icon,
            floor_id=floor_id,
            labels=labels,
        )

    async def _handle_list_labels(self) -> list[dict[str, Any]]:
        """Handle list_labels tool."""
        return await get_labels(self.hass)

    async def _handle_create_label(
        self,
        name: str,
        color: str | None = None,
        icon: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Handle create_label tool."""
        return await create_label(
            self.hass,
            name=name,
            color=color,
            icon=icon,
            description=description,
        )

    async def _handle_update_area(
        self,
        area_id: str,
        name: str | None = None,
        icon: str | None = None,
        floor_id: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Handle update_area tool."""
        return await update_area(
            self.hass,
            area_id=area_id,
            name=name,
            icon=icon,
            floor_id=floor_id,
            labels=labels,
        )

    async def _handle_delete_area(
        self,
        area_id: str,
    ) -> dict[str, Any]:
        """Handle delete_area tool."""
        return await delete_area(self.hass, area_id=area_id)

    async def _handle_update_label(
        self,
        label_id: str,
        name: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Handle update_label tool."""
        return await update_label(
            self.hass,
            label_id=label_id,
            name=name,
            color=color,
            icon=icon,
            description=description,
        )

    async def _handle_delete_label(
        self,
        label_id: str,
    ) -> dict[str, Any]:
        """Handle delete_label tool."""
        return await delete_label(self.hass, label_id=label_id)

    async def _handle_assign_entity_to_area(
        self,
        entity_id: str,
        area_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle assign_entity_to_area tool."""
        return await assign_entity_to_area(
            self.hass,
            entity_id=entity_id,
            area_id=area_id,
        )

    async def _handle_assign_entity_to_labels(
        self,
        entity_id: str,
        label_ids: list[str],
    ) -> dict[str, Any]:
        """Handle assign_entity_to_labels tool."""
        return await assign_entity_to_labels(
            self.hass,
            entity_id=entity_id,
            label_ids=label_ids,
        )

    async def _handle_list_devices(
        self, area_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Handle list_devices tool."""
        return await get_devices(self.hass, area_id)

    async def _handle_list_automations(self) -> list[dict[str, Any]]:
        """Handle list_automations tool."""
        return await get_automations(self.hass)

    async def _handle_toggle_automation(
        self, entity_id: str, enable: bool
    ) -> dict[str, Any]:
        """Handle toggle_automation tool."""
        service = "turn_on" if enable else "turn_off"
        return await call_ha_service(
            self.hass, "automation", service, target={"entity_id": entity_id}
        )

    async def _handle_trigger_automation(self, entity_id: str) -> dict[str, Any]:
        """Handle trigger_automation tool."""
        return await call_ha_service(
            self.hass, "automation", "trigger", target={"entity_id": entity_id}
        )

    async def _handle_create_automation(
        self,
        alias: str | None = None,
        trigger: list[dict[str, Any]] | None = None,
        action: list[dict[str, Any]] | None = None,
        description: str | None = None,
        mode: str = "single",
        condition: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Handle create_automation tool."""
        # Validate required parameters and provide helpful error messages
        missing = []
        if not alias:
            missing.append("alias")
        if not trigger:
            missing.append("trigger")
        if not action:
            missing.append("action")

        if missing:
            return {
                "error": f"Missing required parameters: {', '.join(missing)}",
                "message": (
                    "You MUST provide alias, trigger, AND action parameters. "
                    "REQUIRED WORKFLOW: "
                    "1. First call search_entities() to find relevant entities. "
                    "2. Build trigger list: [{'platform': 'state', 'entity_id': 'binary_sensor.xxx', 'to': 'on'}]. "
                    "3. Build action list: [{'service': 'light.turn_on', 'target': {'entity_id': 'light.xxx'}}]. "
                    "4. Then call create_automation(alias='...', trigger=[...], action=[...])."
                ),
                "hint": "Call search_entities() first to find valid entity IDs, then retry with all required parameters.",
            }

        return await create_automation(
            self.hass,
            alias=alias,
            trigger=trigger,
            action=action,
            description=description,
            mode=mode,
            condition=condition,
        )

    async def _handle_list_scripts(self) -> list[dict[str, Any]]:
        """Handle list_scripts tool."""
        return await get_scripts(self.hass)

    async def _handle_run_script(
        self, entity_id: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle run_script tool."""
        return await call_ha_service(
            self.hass,
            "script",
            "turn_on",
            service_data={"variables": variables} if variables else None,
            target={"entity_id": entity_id},
        )

    async def _handle_create_script(
        self,
        name: str | None = None,
        sequence: list[dict[str, Any]] | None = None,
        description: str | None = None,
        mode: str = "single",
        icon: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle create_script tool."""
        # Validate required parameters and provide helpful error messages
        missing = []
        if not name:
            missing.append("name")
        if not sequence:
            missing.append("sequence")

        if missing:
            return {
                "error": f"Missing required parameters: {', '.join(missing)}",
                "message": (
                    "You MUST provide name AND sequence parameters. "
                    "REQUIRED WORKFLOW: "
                    "1. First call search_entities() to find the entities to control. "
                    "2. Build sequence list: [{'service': 'light.turn_on', 'target': {'entity_id': 'light.xxx'}}]. "
                    "3. Then call create_script(name='...', sequence=[...])."
                ),
                "hint": "Call search_entities() first to find valid entity IDs, then retry with all required parameters.",
            }

        return await create_script(
            self.hass,
            name=name,
            sequence=sequence,
            description=description,
            mode=mode,
            icon=icon,
            fields=fields,
        )

    async def _handle_get_history(
        self, entity_id: str, hours: int = 24, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Handle get_history tool."""
        from datetime import datetime, timedelta, timezone

        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        return await get_history(self.hass, entity_id, start_time, None, limit)

    async def _handle_system_overview(self) -> dict[str, Any]:
        """Handle system_overview tool."""
        entity_count = len(self.hass.states.async_all())
        areas = await get_areas(self.hass)
        automations = await get_automations(self.hass)
        scripts = await get_scripts(self.hass)

        # Count entities by domain
        domain_counts: dict[str, int] = {}
        for state in self.hass.states.async_all():
            domain = state.entity_id.split(".")[0]
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        return {
            "total_entities": entity_count,
            "areas": len(areas),
            "automations": len(automations),
            "scripts": len(scripts),
            "entities_by_domain": domain_counts,
        }

    async def _handle_control_light(
        self,
        entity_id: str,
        action: str,
        brightness: int | None = None,
        color_temp: int | None = None,
        rgb_color: list[int] | None = None,
    ) -> dict[str, Any]:
        """Handle control_light tool."""
        service_map = {
            "on": "turn_on",
            "off": "turn_off",
            "toggle": "toggle",
        }
        service = service_map.get(action)
        if service is None:
            return {"error": f"Unknown action: {action}"}

        service_data: dict[str, Any] = {}

        if brightness is not None:
            service_data["brightness"] = brightness
        if color_temp is not None:
            service_data["color_temp"] = color_temp
        if rgb_color is not None:
            service_data["rgb_color"] = rgb_color

        return await call_ha_service(
            self.hass,
            "light",
            service,
            service_data=service_data if service_data else None,
            target={"entity_id": entity_id},
        )

    async def _handle_control_climate(
        self,
        entity_id: str,
        hvac_mode: str | None = None,
        temperature: float | None = None,
        target_temp_high: float | None = None,
        target_temp_low: float | None = None,
    ) -> dict[str, Any]:
        """Handle control_climate tool."""
        results = []

        if hvac_mode:
            result = await call_ha_service(
                self.hass,
                "climate",
                "set_hvac_mode",
                service_data={"hvac_mode": hvac_mode},
                target={"entity_id": entity_id},
            )
            results.append(result)

        if temperature is not None:
            result = await call_ha_service(
                self.hass,
                "climate",
                "set_temperature",
                service_data={"temperature": temperature},
                target={"entity_id": entity_id},
            )
            results.append(result)

        if target_temp_high is not None or target_temp_low is not None:
            service_data: dict[str, Any] = {}
            if target_temp_high is not None:
                service_data["target_temp_high"] = target_temp_high
            if target_temp_low is not None:
                service_data["target_temp_low"] = target_temp_low

            result = await call_ha_service(
                self.hass,
                "climate",
                "set_temperature",
                service_data=service_data,
                target={"entity_id": entity_id},
            )
            results.append(result)

        return {"results": results}

    async def _handle_control_cover(
        self,
        entity_id: str,
        action: str,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Handle control_cover tool."""
        if action == "set_position" and position is not None:
            return await call_ha_service(
                self.hass,
                "cover",
                "set_cover_position",
                service_data={"position": position},
                target={"entity_id": entity_id},
            )

        service_map = {
            "open": "open_cover",
            "close": "close_cover",
            "stop": "stop_cover",
        }
        service = service_map.get(action)
        if service is None:
            return {"error": f"Unknown action: {action}"}

        return await call_ha_service(
            self.hass, "cover", service, target={"entity_id": entity_id}
        )

    async def _handle_list_scenes(self) -> list[dict[str, Any]]:
        """Handle list_scenes tool."""
        results = []
        for state in self.hass.states.async_all("scene"):
            results.append(
                {
                    "entity_id": state.entity_id,
                    "name": state.attributes.get("friendly_name", state.entity_id),
                }
            )
        return results

    async def _handle_activate_scene(self, entity_id: str) -> dict[str, Any]:
        """Handle activate_scene tool."""
        return await call_ha_service(
            self.hass, "scene", "turn_on", target={"entity_id": entity_id}
        )

    async def _handle_create_scene(
        self,
        name: str | None = None,
        entities: dict[str, Any] | None = None,
        icon: str | None = None,
    ) -> dict[str, Any]:
        """Handle create_scene tool."""
        # Validate required parameters and provide helpful error messages
        if not name:
            return {
                "error": "Missing required parameter 'name'",
                "message": "You must provide a name for the scene.",
            }

        if not entities:
            return {
                "error": "Missing required parameter 'entities'",
                "message": (
                    "You MUST provide 'entities' parameter. "
                    "REQUIRED WORKFLOW: "
                    "1. First call search_entities() to find controllable entities. "
                    "2. Then build an entities dict like: "
                    "{'light.xxx': {'state': 'on'}, 'switch.xxx': {'state': 'on'}}. "
                    "3. Then call create_scene(name='...', entities={...})."
                ),
                "hint": "Call search_entities() first, then retry with the entities parameter.",
            }

        return await create_scene(
            self.hass,
            name=name,
            entities=entities,
            icon=icon,
        )

    async def _handle_create_calendar_event(
        self,
        calendar_entity_id: str,
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """Handle create_calendar_event tool."""
        return await create_calendar_event(
            self.hass,
            calendar_entity_id=calendar_entity_id,
            summary=summary,
            start=start,
            end=end,
            description=description,
            location=location,
        )
