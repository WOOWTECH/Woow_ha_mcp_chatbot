"""MCP Tool Registry - manages all available tools."""

import inspect
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
    list_todo_items,
    add_todo_item,
    update_todo_item,
    remove_todo_item,
    remove_completed_todo_items,
    list_calendar_events,
    update_calendar_event,
    delete_calendar_event,
    update_scene,
    delete_scene,
    list_blueprints,
    import_blueprint,
    send_notification,
    control_input_helper,
    control_timer,
    control_fan,
    delete_automation,
    delete_script,
    bulk_delete_scenes,
    bulk_delete_automations,
    bulk_delete_scripts,
    control_media_player,
    control_lock,
    speak_tts,
    control_persistent_notification,
    control_counter,
    manage_backup,
    control_camera,
    control_switch,
    update_automation,
    update_script,
    control_valve,
    control_number,
    control_shopping_list,
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
    # Cached handler signature — populated at registration time
    _valid_params: frozenset[str] = field(default_factory=frozenset, repr=False)
    _has_var_keyword: bool = field(default=False, repr=False)


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
                description="Control a climate device (thermostat, AC) — mode, temperature, fan, swing, preset, humidity",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Climate entity ID",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["turn_on", "turn_off"],
                            "description": "Turn the climate device on or off",
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
                        "fan_mode": {
                            "type": "string",
                            "description": "Fan mode (e.g., auto, low, medium, high)",
                        },
                        "swing_mode": {
                            "type": "string",
                            "description": "Swing mode (e.g., off, vertical, horizontal, both)",
                        },
                        "preset_mode": {
                            "type": "string",
                            "description": "Preset mode (e.g., eco, away, boost, comfort)",
                        },
                        "humidity": {
                            "type": "number",
                            "description": "Target humidity percentage",
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
                description="Control a cover (blinds, garage door, etc.) including tilt",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Cover entity ID",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "open", "close", "stop", "toggle", "set_position",
                                "open_tilt", "close_tilt", "stop_tilt", "toggle_tilt", "set_tilt_position",
                            ],
                            "description": "Action to perform",
                        },
                        "position": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Position 0-100 (for set_position)",
                        },
                        "tilt_position": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Tilt position 0-100 (for set_tilt_position)",
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
                            "description": "Start datetime in ISO format (e.g., '2024-01-15T10:00:00') or date-only for all-day events (e.g., '2024-01-15')",
                        },
                        "end": {
                            "type": "string",
                            "description": "End datetime in ISO format (e.g., '2024-01-15T11:00:00') or date-only for all-day events (e.g., '2024-01-16')",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional event description",
                        },
                        "location": {
                            "type": "string",
                            "description": "Optional event location",
                        },
                        "all_day": {
                            "type": "boolean",
                            "description": "If true, creates an all-day event. Also auto-detected when start/end are date-only strings.",
                        },
                    },
                    "required": ["calendar_entity_id", "summary", "start", "end"],
                },
                handler=self._handle_create_calendar_event,
                category="calendar",
            )
        )

        # Calendar List/Update/Delete
        self.register(
            ToolDefinition(
                name="list_calendar_events",
                description="List calendar events in a time range. Defaults to the next 7 days if no range specified.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_entity_id": {
                            "type": "string",
                            "description": "Calendar entity ID (e.g., 'calendar.home' or 'calendar.family')",
                        },
                        "start": {
                            "type": "string",
                            "description": "Start time (ISO 8601 format), defaults to today 00:00",
                        },
                        "end": {
                            "type": "string",
                            "description": "End time (ISO 8601 format), defaults to 7 days from start",
                        },
                    },
                    "required": ["calendar_entity_id"],
                },
                handler=self._handle_list_calendar_events,
                category="calendar",
            )
        )

        self.register(
            ToolDefinition(
                name="update_calendar_event",
                description="Update a calendar event's summary, time, description, or location. Use list_calendar_events first to get the event UID.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_entity_id": {
                            "type": "string",
                            "description": "Calendar entity ID",
                        },
                        "uid": {
                            "type": "string",
                            "description": "Event UID (from list_calendar_events)",
                        },
                        "summary": {
                            "type": "string",
                            "description": "New event title",
                        },
                        "start": {
                            "type": "string",
                            "description": "New start time (ISO 8601)",
                        },
                        "end": {
                            "type": "string",
                            "description": "New end time (ISO 8601)",
                        },
                        "description": {
                            "type": "string",
                            "description": "New event description",
                        },
                        "location": {
                            "type": "string",
                            "description": "New event location",
                        },
                        "recurrence_id": {
                            "type": "string",
                            "description": "Recurrence instance ID for recurring events",
                        },
                    },
                    "required": ["calendar_entity_id", "uid"],
                },
                handler=self._handle_update_calendar_event,
                category="calendar",
            )
        )

        self.register(
            ToolDefinition(
                name="delete_calendar_event",
                description="Delete a calendar event. Use list_calendar_events first to get the event UID.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_entity_id": {
                            "type": "string",
                            "description": "Calendar entity ID",
                        },
                        "uid": {
                            "type": "string",
                            "description": "Event UID (from list_calendar_events)",
                        },
                        "recurrence_id": {
                            "type": "string",
                            "description": "Recurrence instance ID (to delete a single instance of recurring event)",
                        },
                    },
                    "required": ["calendar_entity_id", "uid"],
                },
                handler=self._handle_delete_calendar_event,
                category="calendar",
            )
        )

        # Todo CRUD Tools
        self.register(
            ToolDefinition(
                name="list_todo_items",
                description="List items in a todo list. Use search_entities(domain='todo') first to find available todo lists.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Todo entity ID (e.g., 'todo.shopping_list')",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["needs_action", "completed"],
                            "description": "Filter by status: needs_action=pending, completed=done",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_list_todo_items,
                category="todo",
            )
        )

        self.register(
            ToolDefinition(
                name="add_todo_item",
                description="Add an item to a todo list",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Todo entity ID (e.g., 'todo.shopping_list')",
                        },
                        "item": {
                            "type": "string",
                            "description": "Item name/summary",
                        },
                        "due_date": {
                            "type": "string",
                            "description": "Optional due date (YYYY-MM-DD)",
                        },
                        "due_datetime": {
                            "type": "string",
                            "description": "Optional due datetime (ISO 8601)",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional item description",
                        },
                    },
                    "required": ["entity_id", "item"],
                },
                handler=self._handle_add_todo_item,
                category="todo",
            )
        )

        self.register(
            ToolDefinition(
                name="update_todo_item",
                description="Update a todo item (rename, mark complete/incomplete, change due date). Use list_todo_items first to see current items.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Todo entity ID",
                        },
                        "item": {
                            "type": "string",
                            "description": "Current item name to update",
                        },
                        "rename": {
                            "type": "string",
                            "description": "New name for the item",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["needs_action", "completed"],
                            "description": "New status",
                        },
                        "due_date": {
                            "type": "string",
                            "description": "New due date (YYYY-MM-DD)",
                        },
                        "due_datetime": {
                            "type": "string",
                            "description": "New due datetime (ISO 8601)",
                        },
                        "description": {
                            "type": "string",
                            "description": "New description",
                        },
                    },
                    "required": ["entity_id", "item"],
                },
                handler=self._handle_update_todo_item,
                category="todo",
            )
        )

        self.register(
            ToolDefinition(
                name="remove_todo_item",
                description="Remove an item from a todo list. Use list_todo_items first to see current items.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Todo entity ID",
                        },
                        "item": {
                            "type": "string",
                            "description": "Item name to remove",
                        },
                    },
                    "required": ["entity_id", "item"],
                },
                handler=self._handle_remove_todo_item,
                category="todo",
            )
        )

        self.register(
            ToolDefinition(
                name="remove_completed_todo_items",
                description="Remove all completed items from a todo list",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Todo entity ID",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_remove_completed_todo_items,
                category="todo",
            )
        )

        # Scene Update/Delete
        self.register(
            ToolDefinition(
                name="update_scene",
                description="Update a scene's name, icon, or entity states. Use list_scenes first to find the entity_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Scene entity ID (e.g., 'scene.movie_night')",
                        },
                        "name": {
                            "type": "string",
                            "description": "New scene name",
                        },
                        "icon": {
                            "type": "string",
                            "description": "New MDI icon (e.g., 'mdi:movie')",
                        },
                        "entities": {
                            "type": "object",
                            "description": "Updated entity states dict (e.g., {'light.living_room': {'state': 'on', 'brightness': 128}})",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_update_scene,
                category="scene",
            )
        )

        self.register(
            ToolDefinition(
                name="delete_scene",
                description="Delete a scene. Use list_scenes first to find the entity_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Scene entity ID (e.g., 'scene.movie_night')",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_delete_scene,
                category="scene",
            )
        )

        self.register(
            ToolDefinition(
                name="bulk_delete_scenes",
                description="Bulk delete multiple scenes at once. More efficient than deleting one by one (single YAML write + single reload). Use list_scenes first to find entity_ids.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of scene entity IDs to delete (e.g., ['scene.a', 'scene.b'])",
                        },
                    },
                    "required": ["entity_ids"],
                },
                handler=self._handle_bulk_delete_scenes,
                category="scene",
            )
        )

        # Blueprint Tools
        self.register(
            ToolDefinition(
                name="list_blueprints",
                description="List installed automation or script blueprints",
                input_schema={
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "enum": ["automation", "script"],
                            "description": "Blueprint domain: 'automation' or 'script'",
                        },
                    },
                    "required": ["domain"],
                },
                handler=self._handle_list_blueprints,
                category="blueprint",
            )
        )

        self.register(
            ToolDefinition(
                name="import_blueprint",
                description="Import a blueprint from a URL (GitHub, Home Assistant Community, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Blueprint source URL (GitHub raw URL or HA Community forum link)",
                        },
                    },
                    "required": ["url"],
                },
                handler=self._handle_import_blueprint,
                category="blueprint",
            )
        )

        # ===== Phase 2: P1 tools =====

        self.register(
            ToolDefinition(
                name="send_notification",
                description="Send a notification to a device or notification service",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Notification message content",
                        },
                        "title": {
                            "type": "string",
                            "description": "Notification title (optional)",
                        },
                        "target": {
                            "type": "string",
                            "description": "Notification service target (e.g., 'notify.mobile_app_phone'). Defaults to 'notify.notify' (broadcast).",
                        },
                        "data": {
                            "type": "object",
                            "description": "Extra data (image URL, action buttons, etc.)",
                        },
                    },
                    "required": ["message"],
                },
                handler=self._handle_send_notification,
                category="notification",
            )
        )

        self.register(
            ToolDefinition(
                name="control_input_helper",
                description="Control an input helper entity (input_boolean, input_number, input_select, input_datetime, input_button, input_text)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Input helper entity ID (e.g., 'input_boolean.guest_mode')",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "turn_on", "turn_off", "toggle",
                                "set_value", "increment", "decrement",
                                "select_option", "select_next", "select_previous", "set_options",
                                "set_datetime", "press",
                            ],
                            "description": "Action to perform",
                        },
                        "value": {
                            "description": "Value for set_value/select_option/set_datetime/set_options actions",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_input_helper,
                category="input_helper",
            )
        )

        self.register(
            ToolDefinition(
                name="control_timer",
                description="Control a timer entity (start, pause, cancel, finish, change duration)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Timer entity ID (e.g., 'timer.kitchen')",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["start", "pause", "cancel", "finish", "change"],
                            "description": "Action to perform",
                        },
                        "duration": {
                            "type": "string",
                            "description": "Duration in HH:MM:SS format (for start and change actions)",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_timer,
                category="timer",
            )
        )

        self.register(
            ToolDefinition(
                name="control_fan",
                description="Control a fan entity (turn on/off, speed, oscillation, direction)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Fan entity ID (e.g., 'fan.bedroom')",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "turn_on", "turn_off", "toggle",
                                "set_percentage", "set_preset_mode",
                                "set_direction", "oscillate",
                                "increase_speed", "decrease_speed",
                            ],
                            "description": "Action to perform",
                        },
                        "percentage": {
                            "type": "integer",
                            "description": "Fan speed percentage (0-100)",
                        },
                        "preset_mode": {
                            "type": "string",
                            "description": "Preset mode name",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["forward", "reverse"],
                            "description": "Fan direction",
                        },
                        "oscillating": {
                            "type": "boolean",
                            "description": "Whether to oscillate",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_fan,
                category="fan",
            )
        )

        self.register(
            ToolDefinition(
                name="delete_automation",
                description="Delete an automation (removes from automations.yaml and reloads)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Automation entity ID (e.g., 'automation.motion_light')",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_delete_automation,
                category="automation",
            )
        )

        self.register(
            ToolDefinition(
                name="bulk_delete_automations",
                description="Bulk delete multiple automations at once. More efficient than deleting one by one (single YAML write + single reload). Use list_automations first to find entity_ids.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of automation entity IDs to delete (e.g., ['automation.a', 'automation.b'])",
                        },
                    },
                    "required": ["entity_ids"],
                },
                handler=self._handle_bulk_delete_automations,
                category="automation",
            )
        )

        self.register(
            ToolDefinition(
                name="delete_script",
                description="Delete a script (removes from scripts.yaml and reloads)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Script entity ID (e.g., 'script.morning_routine')",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_delete_script,
                category="script",
            )
        )

        self.register(
            ToolDefinition(
                name="bulk_delete_scripts",
                description="Bulk delete multiple scripts at once. More efficient than deleting one by one (single YAML write + single reload). Use list_scripts first to find entity_ids.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of script entity IDs to delete (e.g., ['script.a', 'script.b'])",
                        },
                    },
                    "required": ["entity_ids"],
                },
                handler=self._handle_bulk_delete_scripts,
                category="script",
            )
        )

        # ===== Phase 3: P2 domain coverage =====

        self.register(
            ToolDefinition(
                name="control_media_player",
                description="Control a media player (play, pause, volume, source, shuffle, repeat)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Media player entity ID (e.g., 'media_player.living_room')",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "media_play", "media_pause", "media_stop",
                                "media_next_track", "media_previous_track",
                                "volume_up", "volume_down", "volume_set", "volume_mute",
                                "turn_on", "turn_off", "toggle",
                                "select_source", "play_media", "shuffle_set", "repeat_set",
                                "media_seek", "select_sound_mode",
                            ],
                            "description": "Action to perform",
                        },
                        "volume_level": {
                            "type": "number",
                            "description": "Volume level 0.0-1.0 (for volume_set)",
                        },
                        "is_volume_muted": {
                            "type": "boolean",
                            "description": "Mute state (for volume_mute)",
                        },
                        "media_content_id": {
                            "type": "string",
                            "description": "Media content ID (for play_media)",
                        },
                        "media_content_type": {
                            "type": "string",
                            "description": "Media content type: music, video, playlist, etc. (for play_media)",
                        },
                        "source": {
                            "type": "string",
                            "description": "Input source name (for select_source)",
                        },
                        "shuffle": {
                            "type": "boolean",
                            "description": "Shuffle mode (for shuffle_set)",
                        },
                        "repeat": {
                            "type": "string",
                            "enum": ["off", "all", "one"],
                            "description": "Repeat mode (for repeat_set)",
                        },
                        "seek_position": {
                            "type": "number",
                            "description": "Seek position in seconds (for media_seek)",
                        },
                        "sound_mode": {
                            "type": "string",
                            "description": "Sound mode name (for select_sound_mode)",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_media_player,
                category="media_player",
            )
        )

        self.register(
            ToolDefinition(
                name="control_lock",
                description="Control a smart lock (lock, unlock, open)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Lock entity ID (e.g., 'lock.front_door')",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["lock", "unlock", "open"],
                            "description": "Action to perform",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_lock,
                category="lock",
            )
        )

        self.register(
            ToolDefinition(
                name="speak_tts",
                description="Speak text via TTS (text-to-speech) service",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "TTS entity ID (e.g., tts.google_translate_en_com)",
                        },
                        "message": {
                            "type": "string",
                            "description": "Text to speak",
                        },
                        "media_player_entity_id": {
                            "type": "string",
                            "description": "Optional media player entity ID to play on",
                        },
                        "language": {
                            "type": "string",
                            "description": "Language code (e.g., 'zh-TW', 'en-US')",
                        },
                        "cache": {
                            "type": "boolean",
                            "description": "Whether to cache TTS audio (default: true)",
                        },
                    },
                    "required": ["entity_id", "message"],
                },
                handler=self._handle_speak_tts,
                category="tts",
            )
        )

        self.register(
            ToolDefinition(
                name="control_persistent_notification",
                description="Create, dismiss, or dismiss all persistent notifications in HA frontend",
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "dismiss", "dismiss_all"],
                            "description": "Action to perform",
                        },
                        "message": {
                            "type": "string",
                            "description": "Notification message (required for create)",
                        },
                        "title": {
                            "type": "string",
                            "description": "Notification title (optional, for create)",
                        },
                        "notification_id": {
                            "type": "string",
                            "description": "Notification ID (required for dismiss; optional for create)",
                        },
                    },
                    "required": ["action"],
                },
                handler=self._handle_control_persistent_notification,
                category="notification",
            )
        )

        self.register(
            ToolDefinition(
                name="control_counter",
                description="Control a counter entity (increment, decrement, reset, set value)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Counter entity ID (e.g., 'counter.guests')",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["increment", "decrement", "reset", "set_value"],
                            "description": "Action to perform",
                        },
                        "value": {
                            "type": "integer",
                            "description": "Value for set_value action",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_counter,
                category="counter",
            )
        )

        self.register(
            ToolDefinition(
                name="manage_backup",
                description="Create a Home Assistant backup",
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["create", "create_automatic"],
                            "description": "Backup action (default: create)",
                        },
                    },
                },
                handler=self._handle_manage_backup,
                category="backup",
            )
        )

        self.register(
            ToolDefinition(
                name="control_camera",
                description="Control a camera (snapshot, turn on/off, motion detection)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Camera entity ID (e.g., 'camera.front_door')",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "snapshot", "turn_on", "turn_off",
                                "enable_motion_detection", "disable_motion_detection",
                                "play_stream", "record",
                            ],
                            "description": "Action to perform",
                        },
                        "filename": {
                            "type": "string",
                            "description": "File path for snapshot/record (default: /config/www/snapshot_<name>.jpg)",
                        },
                        "media_player": {
                            "type": "string",
                            "description": "Media player entity ID for play_stream target",
                        },
                        "format": {
                            "type": "string",
                            "enum": ["hls"],
                            "description": "Stream format for play_stream (default: hls)",
                        },
                        "duration": {
                            "type": "integer",
                            "description": "Recording duration in seconds (for record)",
                        },
                        "lookback": {
                            "type": "integer",
                            "description": "Lookback seconds to include before recording (for record)",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_camera,
                category="camera",
            )
        )

        self.register(
            ToolDefinition(
                name="control_switch",
                description="Control a smart switch (turn on, turn off, toggle)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Switch entity ID (e.g., 'switch.garden_light')",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["turn_on", "turn_off", "toggle"],
                            "description": "Action to perform",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_switch,
                category="switch",
            )
        )

        # Phase 4: CRUD 補完 + 新域覆蓋

        self.register(
            ToolDefinition(
                name="update_automation",
                description="Update an existing automation (modify triggers, conditions, actions, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Automation entity ID (e.g., 'automation.motion_light')",
                        },
                        "alias": {
                            "type": "string",
                            "description": "New name/alias for the automation",
                        },
                        "description": {
                            "type": "string",
                            "description": "New description",
                        },
                        "trigger": {
                            "type": "array",
                            "description": "New trigger list",
                            "items": {"type": "object"},
                        },
                        "condition": {
                            "type": "array",
                            "description": "New condition list",
                            "items": {"type": "object"},
                        },
                        "action": {
                            "type": "array",
                            "description": "New action list",
                            "items": {"type": "object"},
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["single", "restart", "queued", "parallel"],
                            "description": "Execution mode",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_update_automation,
                category="automation",
            )
        )

        self.register(
            ToolDefinition(
                name="update_script",
                description="Update an existing script (modify sequence, mode, fields, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Script entity ID (e.g., 'script.morning_routine')",
                        },
                        "alias": {
                            "type": "string",
                            "description": "New name/alias for the script",
                        },
                        "description": {
                            "type": "string",
                            "description": "New description",
                        },
                        "sequence": {
                            "type": "array",
                            "description": "New action sequence",
                            "items": {"type": "object"},
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["single", "restart", "queued", "parallel"],
                            "description": "Execution mode",
                        },
                        "icon": {
                            "type": "string",
                            "description": "New icon (e.g., 'mdi:script')",
                        },
                        "fields": {
                            "type": "object",
                            "description": "Input fields definition",
                        },
                    },
                    "required": ["entity_id"],
                },
                handler=self._handle_update_script,
                category="script",
            )
        )

        self.register(
            ToolDefinition(
                name="control_valve",
                description="Control a valve entity (water valve, gas valve, irrigation)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Valve entity ID (e.g., 'valve.water_main')",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["open", "close", "stop", "set_position", "toggle"],
                            "description": "Action to perform",
                        },
                        "position": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Valve position 0-100 (for set_position)",
                        },
                    },
                    "required": ["entity_id", "action"],
                },
                handler=self._handle_control_valve,
                category="valve",
            )
        )

        self.register(
            ToolDefinition(
                name="control_number",
                description="Set the value of a number entity (device-specific numeric parameters)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "Number entity ID (e.g., 'number.speaker_volume')",
                        },
                        "value": {
                            "type": "number",
                            "description": "Value to set (must be within entity min/max range)",
                        },
                    },
                    "required": ["entity_id", "value"],
                },
                handler=self._handle_control_number,
                category="number",
            )
        )

        self.register(
            ToolDefinition(
                name="control_shopping_list",
                description="Manage the HA shopping list (add, remove, complete, sort items)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "add_item", "remove_item",
                                "complete_item", "incomplete_item",
                                "complete_all", "incomplete_all",
                                "clear_completed", "sort",
                            ],
                            "description": "Action to perform",
                        },
                        "name": {
                            "type": "string",
                            "description": "Item name (required for add/remove/complete/incomplete)",
                        },
                    },
                    "required": ["action"],
                },
                handler=self._handle_control_shopping_list,
                category="shopping_list",
            )
        )

        # ── Memory Tools ──
        self.register(
            ToolDefinition(
                name="memory_get",
                description=(
                    "Get the current memory state: long-term memory (MEMORY.md), "
                    "soul (SOUL.md), user profile (USER.md), and statistics."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "section": {
                            "type": "string",
                            "enum": ["all", "memory", "soul", "user", "stats"],
                            "description": (
                                "Which section to retrieve. "
                                "'all' returns everything (default), "
                                "'memory' for MEMORY.md only, "
                                "'soul' for SOUL.md, "
                                "'user' for USER.md, "
                                "'stats' for memory statistics."
                            ),
                        },
                    },
                },
                handler=self._handle_memory_get,
                category="memory",
            )
        )

        self.register(
            ToolDefinition(
                name="memory_save",
                description=(
                    "Save content to a memory file. Use this to update long-term "
                    "memory, soul definition, or user profile."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "enum": ["memory", "soul", "user"],
                            "description": (
                                "Which file to write: "
                                "'memory' for MEMORY.md (long-term facts), "
                                "'soul' for SOUL.md (personality), "
                                "'user' for USER.md (user profile)."
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": "The full markdown content to write.",
                        },
                    },
                    "required": ["target", "content"],
                },
                handler=self._handle_memory_save,
                category="memory",
            )
        )

        self.register(
            ToolDefinition(
                name="memory_search",
                description=(
                    "Search the conversation history log (HISTORY.md) using a "
                    "regex pattern. Returns matching lines."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": (
                                "Regex pattern to search for in HISTORY.md. "
                                "Case-insensitive. Example: 'light.*bedroom'"
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results to return (default: 20)",
                            "default": 20,
                        },
                    },
                    "required": ["pattern"],
                },
                handler=self._handle_memory_search,
                category="memory",
            )
        )

        self.register(
            ToolDefinition(
                name="memory_append_history",
                description=(
                    "Append an entry to the conversation history log (HISTORY.md). "
                    "Use [YYYY-MM-DD HH:MM] timestamp prefix for searchability."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "entry": {
                            "type": "string",
                            "description": (
                                "The history entry to append. Should start with "
                                "[YYYY-MM-DD HH:MM] timestamp."
                            ),
                        },
                    },
                    "required": ["entry"],
                },
                handler=self._handle_memory_append_history,
                category="memory",
            )
        )

        self.register(
            ToolDefinition(
                name="memory_consolidate",
                description=(
                    "Manually trigger memory consolidation. This uses the AI to "
                    "summarize recent conversation history into long-term memory "
                    "(MEMORY.md) and append a timestamped entry to HISTORY.md."
                ),
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_memory_consolidate,
                category="memory",
            )
        )

        # ── Skills Tools ──
        self.register(
            ToolDefinition(
                name="list_skills",
                description=(
                    "List all installed AI skills with their name, description, "
                    "and always-on status."
                ),
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_list_skills,
                category="skills",
            )
        )

        self.register(
            ToolDefinition(
                name="read_skill",
                description=(
                    "Read the full SKILL.md content of a skill. "
                    "Use this to learn a skill's detailed instructions before using it."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The skill name (directory name)",
                        },
                    },
                    "required": ["name"],
                },
                handler=self._handle_read_skill,
                category="skills",
            )
        )

        self.register(
            ToolDefinition(
                name="create_skill",
                description=(
                    "Create a new AI skill. Provide name, description, "
                    "and the markdown body content."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Skill name (lowercase, alphanumeric + hyphens/underscores)",
                        },
                        "description": {
                            "type": "string",
                            "description": "One-line description of what the skill does",
                        },
                        "content": {
                            "type": "string",
                            "description": "The markdown body content (instructions for the AI)",
                        },
                        "always": {
                            "type": "boolean",
                            "description": "If true, always inject into system prompt (default: false)",
                            "default": False,
                        },
                    },
                    "required": ["name", "description", "content"],
                },
                handler=self._handle_create_skill,
                category="skills",
            )
        )

        self.register(
            ToolDefinition(
                name="update_skill",
                description=(
                    "Update an existing skill's content, description, or always-on status."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The skill name to update",
                        },
                        "content": {
                            "type": "string",
                            "description": "New full content (frontmatter + body). Omit to keep current body.",
                        },
                        "description": {
                            "type": "string",
                            "description": "New description. Omit to keep current.",
                        },
                        "always": {
                            "type": "boolean",
                            "description": "New always-on status. Omit to keep current.",
                        },
                    },
                    "required": ["name"],
                },
                handler=self._handle_update_skill,
                category="skills",
            )
        )

        self.register(
            ToolDefinition(
                name="delete_skill",
                description="Delete a skill and its directory.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The skill name to delete",
                        },
                    },
                    "required": ["name"],
                },
                handler=self._handle_delete_skill,
                category="skills",
            )
        )

        self.register(
            ToolDefinition(
                name="toggle_skill",
                description="Toggle a skill's always-on injection into the system prompt.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The skill name to toggle",
                        },
                        "always": {
                            "type": "boolean",
                            "description": "True to always inject, false for on-demand only",
                        },
                    },
                    "required": ["name", "always"],
                },
                handler=self._handle_toggle_skill,
                category="skills",
            )
        )

        # ── Cron Scheduling Tools ──

        self.register(
            ToolDefinition(
                name="cron_add",
                description=(
                    "Add a scheduled cron job. Schedule types: "
                    "'at' (one-time at Unix ms), 'every' (interval in ms), "
                    "'cron' (cron expression like '0 8 * * *'). "
                    "Payload types: 'agent_turn' (trigger AI conversation with message), "
                    "'system_event' (fire HA event)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Human-readable job name",
                        },
                        "schedule": {
                            "type": "object",
                            "description": (
                                "Schedule config. Examples: "
                                "{\"kind\":\"every\",\"every_ms\":3600000} for hourly, "
                                "{\"kind\":\"cron\",\"cron\":\"0 8 * * *\",\"tz\":\"Asia/Taipei\"} for daily 8am, "
                                "{\"kind\":\"at\",\"at_ms\":1710000000000} for one-time"
                            ),
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["at", "every", "cron"],
                                },
                                "at_ms": {"type": "integer"},
                                "every_ms": {"type": "integer"},
                                "cron": {"type": "string"},
                                "tz": {"type": "string"},
                            },
                            "required": ["kind"],
                        },
                        "payload": {
                            "type": "object",
                            "description": "Payload config: {\"kind\":\"agent_turn\",\"message\":\"...\"}",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["agent_turn", "system_event"],
                                },
                                "message": {"type": "string"},
                            },
                        },
                        "enabled": {
                            "type": "boolean",
                            "description": "Whether the job is enabled (default: true)",
                        },
                        "delete_after_run": {
                            "type": "boolean",
                            "description": "Delete job after first execution (default: false)",
                        },
                    },
                    "required": ["name", "schedule"],
                },
                handler=self._handle_cron_add,
                category="cron",
            )
        )

        self.register(
            ToolDefinition(
                name="cron_list",
                description="List all scheduled cron jobs with their status and next run time.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._handle_cron_list,
                category="cron",
            )
        )

        self.register(
            ToolDefinition(
                name="cron_remove",
                description="Remove a scheduled cron job by its ID.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "The job ID to remove",
                        },
                    },
                    "required": ["job_id"],
                },
                handler=self._handle_cron_remove,
                category="cron",
            )
        )

        self.register(
            ToolDefinition(
                name="cron_update",
                description="Update a cron job's fields (name, schedule, payload, enabled).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "The job ID to update",
                        },
                        "updates": {
                            "type": "object",
                            "description": (
                                "Fields to update. Can include: name, enabled, "
                                "delete_after_run, schedule, payload"
                            ),
                        },
                    },
                    "required": ["job_id", "updates"],
                },
                handler=self._handle_cron_update,
                category="cron",
            )
        )

        self.register(
            ToolDefinition(
                name="cron_trigger",
                description="Manually trigger a cron job execution immediately.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "The job ID to trigger",
                        },
                    },
                    "required": ["job_id"],
                },
                handler=self._handle_cron_trigger,
                category="cron",
            )
        )

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool."""
        # Cache handler signature at registration time to avoid
        # calling inspect.signature on every tool execution.
        sig = inspect.signature(tool.handler)
        tool._valid_params = frozenset(sig.parameters.keys()) - {"self"}
        tool._has_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
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
            # Uses cached signature data from registration time
            if tool._has_var_keyword:
                filtered_args = arguments
            else:
                filtered_args = {k: v for k, v in arguments.items() if k in tool._valid_params}
                dropped = set(arguments.keys()) - tool._valid_params
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
    ) -> dict[str, Any]:
        """Handle call_service tool."""
        service_data = data or {}
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
        all_states = self.hass.states.async_all()
        areas = await get_areas(self.hass)
        automations = await get_automations(self.hass)
        scripts = await get_scripts(self.hass)

        # Count entities by domain in single pass
        domain_counts: dict[str, int] = {}
        for state in all_states:
            domain = state.entity_id.split(".")[0]
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        return {
            "total_entities": len(all_states),
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
            "turn_on": "turn_on",
            "turn_off": "turn_off",
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
        action: str | None = None,
        hvac_mode: str | None = None,
        temperature: float | None = None,
        target_temp_high: float | None = None,
        target_temp_low: float | None = None,
        fan_mode: str | None = None,
        swing_mode: str | None = None,
        preset_mode: str | None = None,
        humidity: float | None = None,
    ) -> dict[str, Any]:
        """Handle control_climate tool."""
        # Validate at least one control parameter is given
        has_params = any(v is not None for v in (
            action, hvac_mode, temperature, target_temp_high,
            target_temp_low, fan_mode, swing_mode, preset_mode, humidity,
        ))
        if not has_params:
            return {
                "success": False,
                "error": "missing_parameters",
                "message": "至少需要一個控制參數 (action, hvac_mode, temperature 等)。",
            }

        results = []

        if action in ("turn_on", "turn_off"):
            result = await call_ha_service(
                self.hass,
                "climate",
                action,
                target={"entity_id": entity_id},
            )
            results.append(result)

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

        if fan_mode is not None:
            result = await call_ha_service(
                self.hass,
                "climate",
                "set_fan_mode",
                service_data={"fan_mode": fan_mode},
                target={"entity_id": entity_id},
            )
            results.append(result)

        if swing_mode is not None:
            result = await call_ha_service(
                self.hass,
                "climate",
                "set_swing_mode",
                service_data={"swing_mode": swing_mode},
                target={"entity_id": entity_id},
            )
            results.append(result)

        if preset_mode is not None:
            result = await call_ha_service(
                self.hass,
                "climate",
                "set_preset_mode",
                service_data={"preset_mode": preset_mode},
                target={"entity_id": entity_id},
            )
            results.append(result)

        if humidity is not None:
            result = await call_ha_service(
                self.hass,
                "climate",
                "set_humidity",
                service_data={"humidity": humidity},
                target={"entity_id": entity_id},
            )
            results.append(result)

        return {"results": results}

    async def _handle_control_cover(
        self,
        entity_id: str,
        action: str,
        position: int | None = None,
        tilt_position: int | None = None,
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

        if action == "set_tilt_position" and tilt_position is not None:
            return await call_ha_service(
                self.hass,
                "cover",
                "set_cover_tilt_position",
                service_data={"tilt_position": tilt_position},
                target={"entity_id": entity_id},
            )

        service_map = {
            "open": "open_cover",
            "close": "close_cover",
            "stop": "stop_cover",
            "toggle": "toggle",
            "open_tilt": "open_cover_tilt",
            "close_tilt": "close_cover_tilt",
            "stop_tilt": "stop_cover_tilt",
            "toggle_tilt": "toggle_cover_tilt",
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
        all_day: bool = False,
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
            all_day=all_day,
        )

    async def _handle_list_calendar_events(
        self,
        calendar_entity_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """Handle list_calendar_events tool."""
        return await list_calendar_events(
            self.hass,
            calendar_entity_id=calendar_entity_id,
            start=start,
            end=end,
        )

    async def _handle_update_calendar_event(
        self,
        calendar_entity_id: str,
        uid: str,
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
        recurrence_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle update_calendar_event tool."""
        return await update_calendar_event(
            self.hass,
            calendar_entity_id=calendar_entity_id,
            uid=uid,
            summary=summary,
            start=start,
            end=end,
            description=description,
            location=location,
            recurrence_id=recurrence_id,
        )

    async def _handle_delete_calendar_event(
        self,
        calendar_entity_id: str,
        uid: str,
        recurrence_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle delete_calendar_event tool."""
        return await delete_calendar_event(
            self.hass,
            calendar_entity_id=calendar_entity_id,
            uid=uid,
            recurrence_id=recurrence_id,
        )

    async def _handle_list_todo_items(
        self,
        entity_id: str,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Handle list_todo_items tool."""
        return await list_todo_items(
            self.hass,
            entity_id=entity_id,
            status=status,
        )

    async def _handle_add_todo_item(
        self,
        entity_id: str,
        item: str,
        due_date: str | None = None,
        due_datetime: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Handle add_todo_item tool."""
        return await add_todo_item(
            self.hass,
            entity_id=entity_id,
            item=item,
            due_date=due_date,
            due_datetime=due_datetime,
            description=description,
        )

    async def _handle_update_todo_item(
        self,
        entity_id: str,
        item: str,
        rename: str | None = None,
        status: str | None = None,
        due_date: str | None = None,
        due_datetime: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Handle update_todo_item tool."""
        return await update_todo_item(
            self.hass,
            entity_id=entity_id,
            item=item,
            rename=rename,
            status=status,
            due_date=due_date,
            due_datetime=due_datetime,
            description=description,
        )

    async def _handle_remove_todo_item(
        self,
        entity_id: str,
        item: str,
    ) -> dict[str, Any]:
        """Handle remove_todo_item tool."""
        return await remove_todo_item(
            self.hass,
            entity_id=entity_id,
            item=item,
        )

    async def _handle_remove_completed_todo_items(
        self,
        entity_id: str,
    ) -> dict[str, Any]:
        """Handle remove_completed_todo_items tool."""
        return await remove_completed_todo_items(
            self.hass,
            entity_id=entity_id,
        )

    async def _handle_update_scene(
        self,
        entity_id: str,
        name: str | None = None,
        icon: str | None = None,
        entities: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle update_scene tool."""
        return await update_scene(
            self.hass,
            entity_id=entity_id,
            name=name,
            icon=icon,
            entities=entities,
        )

    async def _handle_delete_scene(
        self,
        entity_id: str,
    ) -> dict[str, Any]:
        """Handle delete_scene tool."""
        return await delete_scene(
            self.hass,
            entity_id=entity_id,
        )

    async def _handle_bulk_delete_scenes(
        self,
        entity_ids: list[str],
    ) -> dict[str, Any]:
        """Handle bulk_delete_scenes tool."""
        return await bulk_delete_scenes(
            self.hass,
            entity_ids=entity_ids,
        )

    async def _handle_list_blueprints(
        self,
        domain: str,
    ) -> dict[str, Any]:
        """Handle list_blueprints tool."""
        return await list_blueprints(
            self.hass,
            domain=domain,
        )

    async def _handle_import_blueprint(
        self,
        url: str,
    ) -> dict[str, Any]:
        """Handle import_blueprint tool."""
        return await import_blueprint(
            self.hass,
            url=url,
        )

    # ===== Phase 2 handlers =====

    async def _handle_send_notification(
        self,
        message: str,
        title: str | None = None,
        target: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle send_notification tool."""
        return await send_notification(
            self.hass,
            message=message,
            title=title,
            target=target,
            data=data,
        )

    async def _handle_control_input_helper(
        self,
        entity_id: str,
        action: str,
        value: Any = None,
    ) -> dict[str, Any]:
        """Handle control_input_helper tool."""
        return await control_input_helper(
            self.hass,
            entity_id=entity_id,
            action=action,
            value=value,
        )

    async def _handle_control_timer(
        self,
        entity_id: str,
        action: str,
        duration: str | None = None,
    ) -> dict[str, Any]:
        """Handle control_timer tool."""
        return await control_timer(
            self.hass,
            entity_id=entity_id,
            action=action,
            duration=duration,
        )

    async def _handle_control_fan(
        self,
        entity_id: str,
        action: str,
        percentage: int | None = None,
        preset_mode: str | None = None,
        direction: str | None = None,
        oscillating: bool | None = None,
    ) -> dict[str, Any]:
        """Handle control_fan tool."""
        return await control_fan(
            self.hass,
            entity_id=entity_id,
            action=action,
            percentage=percentage,
            preset_mode=preset_mode,
            direction=direction,
            oscillating=oscillating,
        )

    async def _handle_delete_automation(
        self,
        entity_id: str,
    ) -> dict[str, Any]:
        """Handle delete_automation tool."""
        return await delete_automation(
            self.hass,
            entity_id=entity_id,
        )

    async def _handle_bulk_delete_automations(
        self,
        entity_ids: list[str],
    ) -> dict[str, Any]:
        """Handle bulk_delete_automations tool."""
        return await bulk_delete_automations(
            self.hass,
            entity_ids=entity_ids,
        )

    async def _handle_delete_script(
        self,
        entity_id: str,
    ) -> dict[str, Any]:
        """Handle delete_script tool."""
        return await delete_script(
            self.hass,
            entity_id=entity_id,
        )

    async def _handle_bulk_delete_scripts(
        self,
        entity_ids: list[str],
    ) -> dict[str, Any]:
        """Handle bulk_delete_scripts tool."""
        return await bulk_delete_scripts(
            self.hass,
            entity_ids=entity_ids,
        )

    # ===== Phase 3 handlers =====

    async def _handle_control_media_player(
        self,
        entity_id: str,
        action: str,
        volume_level: float | None = None,
        is_volume_muted: bool | None = None,
        media_content_id: str | None = None,
        media_content_type: str | None = None,
        source: str | None = None,
        shuffle: bool | None = None,
        repeat: str | None = None,
        seek_position: float | None = None,
        sound_mode: str | None = None,
    ) -> dict[str, Any]:
        """Handle control_media_player tool."""
        return await control_media_player(
            self.hass,
            entity_id=entity_id,
            action=action,
            volume_level=volume_level,
            is_volume_muted=is_volume_muted,
            media_content_id=media_content_id,
            media_content_type=media_content_type,
            source=source,
            shuffle=shuffle,
            repeat=repeat,
            seek_position=seek_position,
            sound_mode=sound_mode,
        )

    async def _handle_control_lock(
        self,
        entity_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Handle control_lock tool."""
        return await control_lock(
            self.hass,
            entity_id=entity_id,
            action=action,
        )

    async def _handle_speak_tts(
        self,
        entity_id: str,
        message: str,
        media_player_entity_id: str | None = None,
        language: str | None = None,
        cache: bool = True,
    ) -> dict[str, Any]:
        """Handle speak_tts tool."""
        return await speak_tts(
            self.hass,
            entity_id=entity_id,
            message=message,
            media_player_entity_id=media_player_entity_id,
            language=language,
            cache=cache,
        )

    async def _handle_control_persistent_notification(
        self,
        action: str,
        message: str | None = None,
        title: str | None = None,
        notification_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle control_persistent_notification tool."""
        return await control_persistent_notification(
            self.hass,
            action=action,
            message=message,
            title=title,
            notification_id=notification_id,
        )

    async def _handle_control_counter(
        self,
        entity_id: str,
        action: str,
        value: int | None = None,
    ) -> dict[str, Any]:
        """Handle control_counter tool."""
        return await control_counter(
            self.hass,
            entity_id=entity_id,
            action=action,
            value=value,
        )

    async def _handle_manage_backup(
        self,
        action: str = "create",
    ) -> dict[str, Any]:
        """Handle manage_backup tool."""
        return await manage_backup(
            self.hass,
            action=action,
        )

    async def _handle_control_camera(
        self,
        entity_id: str,
        action: str,
        filename: str | None = None,
        media_player: str | None = None,
        format: str | None = None,
        duration: int | None = None,
        lookback: int | None = None,
    ) -> dict[str, Any]:
        """Handle control_camera tool."""
        return await control_camera(
            self.hass,
            entity_id=entity_id,
            action=action,
            filename=filename,
            media_player=media_player,
            format=format,
            duration=duration,
            lookback=lookback,
        )

    async def _handle_control_switch(
        self,
        entity_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Handle control_switch tool."""
        return await control_switch(
            self.hass,
            entity_id=entity_id,
            action=action,
        )

    # Phase 4 handlers

    async def _handle_update_automation(
        self,
        entity_id: str,
        alias: str | None = None,
        description: str | None = None,
        trigger: list[dict[str, Any]] | None = None,
        condition: list[dict[str, Any]] | None = None,
        action: list[dict[str, Any]] | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """Handle update_automation tool."""
        return await update_automation(
            self.hass,
            entity_id=entity_id,
            alias=alias,
            description=description,
            trigger=trigger,
            condition=condition,
            action=action,
            mode=mode,
        )

    async def _handle_update_script(
        self,
        entity_id: str,
        alias: str | None = None,
        description: str | None = None,
        sequence: list[dict[str, Any]] | None = None,
        mode: str | None = None,
        icon: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle update_script tool."""
        return await update_script(
            self.hass,
            entity_id=entity_id,
            alias=alias,
            description=description,
            sequence=sequence,
            mode=mode,
            icon=icon,
            fields=fields,
        )

    async def _handle_control_valve(
        self,
        entity_id: str,
        action: str,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Handle control_valve tool."""
        return await control_valve(
            self.hass,
            entity_id=entity_id,
            action=action,
            position=position,
        )

    async def _handle_control_number(
        self,
        entity_id: str,
        value: float,
    ) -> dict[str, Any]:
        """Handle control_number tool."""
        return await control_number(
            self.hass,
            entity_id=entity_id,
            value=value,
        )

    async def _handle_control_shopping_list(
        self,
        action: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Handle control_shopping_list tool."""
        return await control_shopping_list(
            self.hass,
            action=action,
            name=name,
        )

    # ── Memory tool handlers ──

    def _get_memory_store(self):
        """Get the MemoryStore instance from hass.data."""
        from ...const import DOMAIN
        for entry_data in self.hass.data.get(DOMAIN, {}).values():
            if isinstance(entry_data, dict) and "memory_store" in entry_data:
                return entry_data["memory_store"]
        return None

    async def _handle_memory_get(
        self,
        section: str = "all",
    ) -> dict[str, Any]:
        """Handle memory_get tool."""
        store = self._get_memory_store()
        if not store:
            return {"error": "Memory store not available"}

        result: dict[str, Any] = {}
        if section in ("all", "memory"):
            result["memory"] = await store.read_long_term()
        if section in ("all", "soul"):
            result["soul"] = await store.read_soul()
        if section in ("all", "user"):
            result["user"] = await store.read_user()
        if section in ("all", "stats"):
            result["stats"] = await store.get_stats()
        return result

    async def _handle_memory_save(
        self,
        target: str,
        content: str,
    ) -> dict[str, Any]:
        """Handle memory_save tool."""
        store = self._get_memory_store()
        if not store:
            return {"error": "Memory store not available"}

        if target == "memory":
            await store.write_long_term(content)
        elif target == "soul":
            await store.write_soul(content)
        elif target == "user":
            await store.write_user(content)
        else:
            return {"error": f"Unknown target: {target}"}

        return {"success": True, "target": target, "length": len(content)}

    async def _handle_memory_search(
        self,
        pattern: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Handle memory_search tool."""
        store = self._get_memory_store()
        if not store:
            return {"error": "Memory store not available"}

        results = await store.search_history(pattern)
        truncated = len(results) > limit
        results = results[:limit]
        return {
            "pattern": pattern,
            "matches": results,
            "count": len(results),
            "truncated": truncated,
        }

    async def _handle_memory_append_history(
        self,
        entry: str,
    ) -> dict[str, Any]:
        """Handle memory_append_history tool."""
        store = self._get_memory_store()
        if not store:
            return {"error": "Memory store not available"}

        await store.append_history(entry)
        return {"success": True, "entry_length": len(entry)}

    async def _handle_memory_consolidate(self) -> dict[str, Any]:
        """Handle memory_consolidate tool — trigger AI-driven consolidation."""
        from ...const import DOMAIN, CONF_MEMORY_WINDOW, DEFAULT_MEMORY_WINDOW

        store = self._get_memory_store()
        if not store:
            return {"error": "Memory store not available"}

        # Find AI service from the conversation entity
        ai_service = None
        recorder = None
        memory_window = DEFAULT_MEMORY_WINDOW
        for entry_data in self.hass.data.get(DOMAIN, {}).values():
            if isinstance(entry_data, dict):
                if "recorder" in entry_data:
                    recorder = entry_data["recorder"]
                overrides = entry_data.get("runtime_settings", {})
                memory_window = overrides.get(CONF_MEMORY_WINDOW, memory_window)

        # Look up conversation entity's AI service
        entity_comp = self.hass.data.get("entity_components", {}).get("conversation")
        if entity_comp:
            for entity in entity_comp.entities:
                if hasattr(entity, "_ai_service") and entity._ai_service:
                    ai_service = entity._ai_service
                    break

        if not ai_service:
            return {"error": "AI service not available for consolidation"}

        # Gather recent messages from the recorder
        messages: list[dict[str, Any]] = []
        if recorder:
            # Get the most recent conversation across all users
            from ...conversation_recorder import Conversation as ConvModel
            from homeassistant.components.recorder import get_instance
            from sqlalchemy.orm import Session as SASession

            ha_recorder = get_instance(self.hass)

            def _get_recent_conv():
                with SASession(ha_recorder.engine) as session:
                    row = (
                        session.query(ConvModel)
                        .filter(ConvModel.is_archived == False)  # noqa: E712
                        .order_by(ConvModel.updated_at.desc())
                        .first()
                    )
                    return row.id if row else None

            conv_id = await ha_recorder.async_add_executor_job(_get_recent_conv)

            if conv_id:
                msg_records = await recorder.get_conversation_messages(
                    conv_id, limit=memory_window
                )
                for m in msg_records:
                    role = m.get("role", "user") if isinstance(m, dict) else getattr(m, "role", "user")
                    content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
                    messages.append({
                        "role": role,
                        "content": content or "",
                    })

        if not messages:
            return {"info": "No recent messages to consolidate"}

        success = await store.consolidate(
            conversation_id="manual_consolidation",
            messages=messages,
            ai_service=ai_service,
            memory_window=memory_window,
        )

        if success:
            stats = await store.get_stats()
            return {"success": True, "stats": stats}
        return {"error": "Consolidation failed"}

    # ── Skills tool handlers ──

    def _get_skills_loader(self):
        """Get the SkillsLoader instance from hass.data."""
        from ...const import DOMAIN
        for entry_data in self.hass.data.get(DOMAIN, {}).values():
            if isinstance(entry_data, dict) and "skills_loader" in entry_data:
                return entry_data["skills_loader"]
        return None

    async def _handle_list_skills(self) -> dict[str, Any]:
        """Handle list_skills tool."""
        loader = self._get_skills_loader()
        if not loader:
            return {"error": "Skills loader not available"}

        skills = await loader.list_skills()
        stats = await loader.get_stats()
        return {"skills": skills, "stats": stats}

    async def _handle_read_skill(self, name: str) -> dict[str, Any]:
        """Handle read_skill tool."""
        loader = self._get_skills_loader()
        if not loader:
            return {"error": "Skills loader not available"}

        content = await loader.read_skill(name)
        if content is None:
            return {"error": f"Skill '{name}' not found"}
        return {"name": name, "content": content}

    async def _handle_create_skill(
        self,
        name: str,
        description: str,
        content: str,
        always: bool = False,
    ) -> dict[str, Any]:
        """Handle create_skill tool."""
        loader = self._get_skills_loader()
        if not loader:
            return {"error": "Skills loader not available"}

        return await loader.create_skill(
            name=name,
            description=description,
            content=content,
            always=always,
        )

    async def _handle_update_skill(
        self,
        name: str,
        content: str | None = None,
        description: str | None = None,
        always: bool | None = None,
    ) -> dict[str, Any]:
        """Handle update_skill tool."""
        loader = self._get_skills_loader()
        if not loader:
            return {"error": "Skills loader not available"}

        return await loader.update_skill(
            name=name,
            content=content,
            description=description,
            always=always,
        )

    async def _handle_delete_skill(self, name: str) -> dict[str, Any]:
        """Handle delete_skill tool."""
        loader = self._get_skills_loader()
        if not loader:
            return {"error": "Skills loader not available"}

        return await loader.delete_skill(name)

    async def _handle_toggle_skill(
        self, name: str, always: bool
    ) -> dict[str, Any]:
        """Handle toggle_skill tool."""
        loader = self._get_skills_loader()
        if not loader:
            return {"error": "Skills loader not available"}

        return await loader.toggle_skill(name, always)

    # ── Cron tool handlers ──

    def _get_cron_service(self):
        """Get the CronService instance from hass.data."""
        from ...const import DOMAIN
        for entry_data in self.hass.data.get(DOMAIN, {}).values():
            if isinstance(entry_data, dict) and "cron_service" in entry_data:
                return entry_data["cron_service"]
        return None

    async def _handle_cron_add(
        self,
        name: str,
        schedule: dict[str, Any],
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
        delete_after_run: bool = False,
    ) -> dict[str, Any]:
        """Handle cron_add tool."""
        svc = self._get_cron_service()
        if not svc:
            return {"error": "Cron service not available"}

        job = await svc.add_job(
            name=name,
            schedule=schedule,
            payload=payload,
            enabled=enabled,
            delete_after_run=delete_after_run,
        )
        return job.to_dict()

    async def _handle_cron_list(self) -> dict[str, Any]:
        """Handle cron_list tool."""
        svc = self._get_cron_service()
        if not svc:
            return {"error": "Cron service not available"}

        jobs = await svc.list_jobs()
        stats = await svc.get_stats()
        return {
            "jobs": [j.to_dict() for j in jobs],
            "stats": stats,
        }

    async def _handle_cron_remove(self, job_id: str) -> dict[str, Any]:
        """Handle cron_remove tool."""
        svc = self._get_cron_service()
        if not svc:
            return {"error": "Cron service not available"}

        ok = await svc.remove_job(job_id)
        if not ok:
            return {"error": f"Job '{job_id}' not found"}
        return {"success": True, "removed": job_id}

    async def _handle_cron_update(
        self, job_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle cron_update tool."""
        svc = self._get_cron_service()
        if not svc:
            return {"error": "Cron service not available"}

        job = await svc.update_job(job_id, updates)
        if not job:
            return {"error": f"Job '{job_id}' not found"}
        return job.to_dict()

    async def _handle_cron_trigger(self, job_id: str) -> dict[str, Any]:
        """Handle cron_trigger tool."""
        svc = self._get_cron_service()
        if not svc:
            return {"error": "Cron service not available"}

        ok = await svc.trigger_job(job_id)
        if not ok:
            return {"error": f"Job '{job_id}' not found"}
        return {"success": True, "triggered": job_id}
