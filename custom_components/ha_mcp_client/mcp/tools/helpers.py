"""Helper functions for MCP tools."""

import logging
from typing import Any
from datetime import date, datetime, timedelta, timezone

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import label_registry as lr

_LOGGER = logging.getLogger(__name__)

# Blocked domains/services to prevent destructive operations via AI tool calls
BLOCKED_SERVICE_DOMAINS = frozenset({
    "homeassistant",
    "hassio",
    "supervisor",
    "config",
    "system_log",
})

BLOCKED_SERVICES = frozenset({
    ("recorder", "purge"),
    ("recorder", "purge_entities"),
    ("recorder", "disable"),
})


async def get_entity_state(hass: HomeAssistant, entity_id: str) -> dict[str, Any] | None:
    """Get the current state of an entity."""
    state = hass.states.get(entity_id)
    if state is None:
        return None

    return format_state(state)


def format_state(state: State) -> dict[str, Any]:
    """Format a state object for output."""
    return {
        "entity_id": state.entity_id,
        "state": state.state,
        "attributes": dict(state.attributes),
        "last_changed": state.last_changed.isoformat(),
        "last_updated": state.last_updated.isoformat(),
    }


async def call_ha_service(
    hass: HomeAssistant,
    domain: str,
    service: str,
    service_data: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call a Home Assistant service."""
    # Security: block dangerous domains and services
    if domain in BLOCKED_SERVICE_DOMAINS:
        _LOGGER.warning("Blocked service call to restricted domain: %s.%s", domain, service)
        return {
            "success": False,
            "error": f"Service domain '{domain}' is restricted for safety",
        }
    if (domain, service) in BLOCKED_SERVICES:
        _LOGGER.warning("Blocked restricted service call: %s.%s", domain, service)
        return {
            "success": False,
            "error": f"Service '{domain}.{service}' is restricted for safety",
        }

    try:
        await hass.services.async_call(
            domain=domain,
            service=service,
            service_data=service_data or {},
            target=target,
            blocking=True,
        )
        return {
            "success": True,
            "message": f"Service {domain}.{service} called successfully",
        }
    except Exception as e:
        _LOGGER.error("Error calling service %s.%s: %s", domain, service, e)
        return {
            "success": False,
            "error": str(e),
        }


async def search_entities(
    hass: HomeAssistant,
    query: str | None = None,
    domain: str | None = None,
    area_id: str | None = None,
    device_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search for entities matching criteria."""
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    results = []
    query_lower = query.lower() if query else None

    for entity_entry in entity_reg.entities.values():
        # Filter by domain
        if domain and not entity_entry.entity_id.startswith(f"{domain}."):
            continue

        # Filter by area
        if area_id and entity_entry.area_id != area_id:
            # Check device area if entity doesn't have direct area
            if entity_entry.device_id:
                device = device_reg.async_get(entity_entry.device_id)
                if not device or device.area_id != area_id:
                    continue
            else:
                continue

        # Filter by device
        if device_id and entity_entry.device_id != device_id:
            continue

        # Filter by query
        if query_lower:
            name = entity_entry.name or entity_entry.original_name or ""
            entity_id = entity_entry.entity_id
            if (
                query_lower not in name.lower()
                and query_lower not in entity_id.lower()
            ):
                continue

        # Get state
        state = hass.states.get(entity_entry.entity_id)
        if state is None:
            continue

        # Get area name
        area_name = None
        if entity_entry.area_id:
            area = area_reg.async_get_area(entity_entry.area_id)
            if area:
                area_name = area.name
        elif entity_entry.device_id:
            device = device_reg.async_get(entity_entry.device_id)
            if device and device.area_id:
                area = area_reg.async_get_area(device.area_id)
                if area:
                    area_name = area.name

        results.append(
            {
                "entity_id": entity_entry.entity_id,
                "name": entity_entry.name or entity_entry.original_name,
                "state": state.state,
                "domain": entity_entry.domain,
                "area": area_name,
                "device_id": entity_entry.device_id,
            }
        )

        if len(results) >= limit:
            break

    return results


def format_entity_info(entity_data: dict[str, Any]) -> str:
    """Format entity information for display."""
    lines = [
        f"Entity: {entity_data.get('entity_id', 'Unknown')}",
        f"Name: {entity_data.get('name', 'Unknown')}",
        f"State: {entity_data.get('state', 'Unknown')}",
    ]

    if entity_data.get("area"):
        lines.append(f"Area: {entity_data['area']}")

    if entity_data.get("attributes"):
        lines.append("Attributes:")
        for key, value in entity_data["attributes"].items():
            lines.append(f"  {key}: {value}")

    return "\n".join(lines)


async def get_areas(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get all areas."""
    area_reg = ar.async_get(hass)
    return [
        {
            "id": area.id,
            "name": area.name,
            "aliases": list(area.aliases) if area.aliases else [],
        }
        for area in area_reg.async_list_areas()
    ]


async def get_devices(
    hass: HomeAssistant,
    area_id: str | None = None,
) -> list[dict[str, Any]]:
    """Get devices, optionally filtered by area."""
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    results = []
    for device in device_reg.devices.values():
        if area_id and device.area_id != area_id:
            continue

        area_name = None
        if device.area_id:
            area = area_reg.async_get_area(device.area_id)
            if area:
                area_name = area.name

        results.append(
            {
                "id": device.id,
                "name": device.name or device.name_by_user,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "area": area_name,
                "area_id": device.area_id,
            }
        )

    return results


async def get_services(
    hass: HomeAssistant,
    domain: str | None = None,
) -> dict[str, Any]:
    """Get available services."""
    services = hass.services.async_services()

    if domain:
        return {domain: services.get(domain, {})}

    return services


async def get_automations(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get all automations."""
    results = []

    for state in hass.states.async_all("automation"):
        results.append(
            {
                "entity_id": state.entity_id,
                "name": state.attributes.get("friendly_name", state.entity_id),
                "state": state.state,
                "last_triggered": state.attributes.get("last_triggered"),
            }
        )

    return results


async def get_scripts(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get all scripts."""
    results = []

    for state in hass.states.async_all("script"):
        results.append(
            {
                "entity_id": state.entity_id,
                "name": state.attributes.get("friendly_name", state.entity_id),
                "state": state.state,
                "last_triggered": state.attributes.get("last_triggered"),
            }
        )

    return results


async def get_history(
    hass: HomeAssistant,
    entity_id: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get entity history."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.history import state_changes_during_period

    if start_time is None:
        start_time = datetime.now(timezone.utc) - timedelta(hours=24)

    if end_time is None:
        end_time = datetime.now(timezone.utc)

    try:
        recorder = get_instance(hass)
        history = await recorder.async_add_executor_job(
            state_changes_during_period,
            hass,
            start_time,
            end_time,
            entity_id,
        )

        results = []
        entity_history = history.get(entity_id, [])
        for state in entity_history[:limit]:
            results.append(format_state(state))

        return results
    except Exception as e:
        _LOGGER.error("Error getting history for %s: %s", entity_id, e)
        return []


async def get_service_schema(
    hass: HomeAssistant,
    domain: str,
    service: str,
) -> dict[str, Any]:
    """Get the schema for a specific service."""
    services = hass.services.async_services()

    if domain not in services:
        return {
            "success": False,
            "error": f"Domain '{domain}' not found",
        }

    domain_services = services[domain]
    if service not in domain_services:
        return {
            "success": False,
            "error": f"Service '{domain}.{service}' not found",
            "available_services": list(domain_services.keys()),
        }

    service_info = domain_services[service]

    # Build fields info
    fields = {}
    if hasattr(service_info, "schema") and service_info.schema:
        schema = service_info.schema
        if hasattr(schema, "schema"):
            for key, validator in schema.schema.items():
                field_name = str(key)
                field_info = {
                    "required": hasattr(key, "default") and key.default is None,
                }
                # Try to get description
                if hasattr(validator, "description"):
                    field_info["description"] = validator.description
                fields[field_name] = field_info

    return {
        "success": True,
        "domain": domain,
        "service": service,
        "description": service_info.description if hasattr(service_info, "description") else None,
        "fields": fields,
    }


async def create_automation(
    hass: HomeAssistant,
    alias: str,
    trigger: list[dict[str, Any]],
    action: list[dict[str, Any]],
    description: str | None = None,
    mode: str = "single",
    condition: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a new automation in Home Assistant."""
    import uuid

    try:
        # Generate unique ID
        automation_id = str(uuid.uuid4()).replace("-", "")[:12]

        # Build automation config
        config = {
            "id": automation_id,
            "alias": alias,
            "trigger": trigger,
            "action": action,
            "mode": mode,
        }

        if description:
            config["description"] = description
        if condition:
            config["condition"] = condition

        # Write to automations.yaml and reload
        import yaml

        config_path = hass.config.path("automations.yaml")

        def _write_automation():
            # Read existing automations
            try:
                with open(config_path, "r") as f:
                    existing = yaml.safe_load(f) or []
            except FileNotFoundError:
                existing = []
            if not isinstance(existing, list):
                existing = []

            # Append new automation
            existing.append(config)

            # Write back
            with open(config_path, "w") as f:
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)

        await hass.async_add_executor_job(_write_automation)

        # Reload automations
        await hass.services.async_call("automation", "reload", blocking=True)

        # Generate entity_id
        entity_id = f"automation.{alias.lower().replace(' ', '_').replace('-', '_')}"

        return {
            "success": True,
            "automation_id": automation_id,
            "entity_id": entity_id,
            "message": f"自動化「{alias}」已建立",
        }

    except Exception as e:
        _LOGGER.error("Error creating automation: %s", e)
        return {
            "success": False,
            "error": "creation_failed",
            "message": f"建立自動化失敗：{str(e)}",
        }


async def create_script(
    hass: HomeAssistant,
    name: str,
    sequence: list[dict[str, Any]],
    description: str | None = None,
    mode: str = "single",
    fields: dict[str, Any] | None = None,
    icon: str | None = None,
) -> dict[str, Any]:
    """Create a new script in Home Assistant."""
    import re
    import yaml

    try:
        # Generate script_id from name
        script_id = name.lower().replace(" ", "_").replace("-", "_")
        script_id = re.sub(r'[^a-z0-9_]', '', script_id)
        if not script_id:
            import uuid
            script_id = f"script_{str(uuid.uuid4()).replace('-', '')[:8]}"

        # Build script config
        config = {
            "alias": name,
            "sequence": sequence,
            "mode": mode,
        }

        if description:
            config["description"] = description
        if fields:
            config["fields"] = fields
        if icon:
            config["icon"] = icon

        # Write to scripts.yaml and reload (same pattern as create_automation)
        config_path = hass.config.path("scripts.yaml")

        def _write_script():
            try:
                with open(config_path, "r") as f:
                    existing = yaml.safe_load(f) or {}
            except FileNotFoundError:
                existing = {}
            if not isinstance(existing, dict):
                existing = {}

            existing[script_id] = config

            with open(config_path, "w") as f:
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)

        await hass.async_add_executor_job(_write_script)

        # Reload scripts
        await hass.services.async_call("script", "reload", blocking=True)

        entity_id = f"script.{script_id}"

        return {
            "success": True,
            "script_id": script_id,
            "entity_id": entity_id,
            "message": f"腳本「{name}」已建立",
        }

    except Exception as e:
        _LOGGER.error("Error creating script: %s", e)
        return {
            "success": False,
            "error": "creation_failed",
            "message": f"建立腳本失敗：{str(e)}",
        }


async def create_scene(
    hass: HomeAssistant,
    name: str,
    entities: dict[str, Any],
    icon: str | None = None,
) -> dict[str, Any]:
    """Create a new persistent scene in Home Assistant.

    Writes to scenes.yaml and reloads, so the scene persists across restarts.

    Args:
        hass: Home Assistant instance
        name: Scene name
        entities: Dict of entity_id to state. Example: {"light.living_room": {"state": "on", "brightness": 255}}
        icon: Optional MDI icon
    """
    import re
    import yaml

    try:
        # Generate scene_id - must be valid slug (ASCII only)
        scene_id = name.lower().replace(" ", "_").replace("-", "_")
        scene_id = re.sub(r'[^a-z0-9_]', '', scene_id)
        if not scene_id:
            import uuid
            scene_id = f"scene_{str(uuid.uuid4()).replace('-', '')[:8]}"

        config: dict[str, Any] = {
            "id": scene_id,
            "name": name,
            "entities": entities,
        }
        if icon:
            config["icon"] = icon

        config_path = hass.config.path("scenes.yaml")

        def _write_scene():
            try:
                with open(config_path, "r") as f:
                    existing = yaml.safe_load(f) or []
            except FileNotFoundError:
                existing = []
            if not isinstance(existing, list):
                existing = []
            existing.append(config)
            with open(config_path, "w") as f:
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)

        await hass.async_add_executor_job(_write_scene)
        await hass.services.async_call("scene", "reload", blocking=True)

        entity_id = f"scene.{scene_id}"

        return {
            "success": True,
            "scene_id": scene_id,
            "entity_id": entity_id,
            "message": f"情境「{name}」已建立（持久化），entity_id: {entity_id}",
        }

    except Exception as e:
        _LOGGER.error("Error creating scene: %s", e)
        return {
            "success": False,
            "error": "creation_failed",
            "message": f"建立情境失敗：{str(e)}",
        }


async def create_calendar_event(
    hass: HomeAssistant,
    calendar_entity_id: str,
    summary: str,
    start: str,
    end: str,
    description: str | None = None,
    location: str | None = None,
    all_day: bool = False,
) -> dict[str, Any]:
    """Create a calendar event.

    Args:
        hass: Home Assistant instance
        calendar_entity_id: Calendar entity ID (e.g., 'calendar.home')
        summary: Event title/summary
        start: Start date(time). ISO format datetime (e.g., '2024-01-15T10:00:00')
               or date-only for all-day events (e.g., '2024-01-15')
        end: End date(time). ISO format datetime or date-only for all-day events.
        description: Optional event description
        location: Optional event location
        all_day: If True, creates an all-day event using start_date/end_date.
                 Also auto-detected if start/end are date-only (no 'T').
    """
    try:
        # Validate calendar entity exists
        state = hass.states.get(calendar_entity_id)
        if state is None:
            available = [
                s.entity_id
                for s in hass.states.async_all("calendar")
            ]
            return {
                "success": False,
                "error": "entity_not_found",
                "message": (
                    f"Calendar entity '{calendar_entity_id}' not found. "
                    f"Available calendars: {available}"
                ),
            }

        # Auto-detect all-day events: date-only strings (no 'T') indicate all-day
        is_all_day = all_day or ('T' not in start and 'T' not in end)

        if is_all_day:
            # Extract date-only portion (strip any time component)
            start_date = start.split("T")[0]
            end_date = end.split("T")[0]
            service_data = {
                "summary": summary,
                "start_date": start_date,
                "end_date": end_date,
            }
        else:
            service_data = {
                "summary": summary,
                "start_date_time": start,
                "end_date_time": end,
            }

        if description:
            service_data["description"] = description
        if location:
            service_data["location"] = location

        await hass.services.async_call(
            "calendar",
            "create_event",
            service_data=service_data,
            target={"entity_id": calendar_entity_id},
            blocking=True,
        )

        return {
            "success": True,
            "calendar": calendar_entity_id,
            "summary": summary,
            "message": f"日曆事件「{summary}」已建立",
        }

    except Exception as e:
        _LOGGER.error("Error creating calendar event: %s", e)
        return {
            "success": False,
            "error": "creation_failed",
            "message": f"建立日曆事件失敗：{str(e)}",
        }


async def create_area(
    hass: HomeAssistant,
    name: str,
    icon: str | None = None,
    floor_id: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new area in Home Assistant.

    Args:
        hass: Home Assistant instance
        name: Area name (e.g., '客廳', 'Living Room')
        icon: Optional MDI icon (e.g., 'mdi:sofa')
        floor_id: Optional floor ID to assign the area to
        labels: Optional list of label IDs to assign
    """
    try:
        area_reg = ar.async_get(hass)

        # Check if area already exists
        existing = area_reg.async_get_area_by_name(name)
        if existing:
            return {
                "success": False,
                "error": "already_exists",
                "message": f"分區「{name}」已存在",
                "area_id": existing.id,
            }

        # Create area
        labels_set = set(labels) if labels else None
        area = area_reg.async_create(
            name=name,
            icon=icon,
            floor_id=floor_id,
            labels=labels_set,
        )

        return {
            "success": True,
            "area_id": area.id,
            "name": area.name,
            "message": f"分區「{name}」已建立",
        }

    except Exception as e:
        _LOGGER.error("Error creating area: %s", e)
        return {
            "success": False,
            "error": "creation_failed",
            "message": f"建立分區失敗：{str(e)}",
        }


async def create_label(
    hass: HomeAssistant,
    name: str,
    color: str | None = None,
    icon: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a new label in Home Assistant.

    Args:
        hass: Home Assistant instance
        name: Label name (e.g., '重要', 'Important')
        color: Optional color in hex format (e.g., 'ff0000' for red)
        icon: Optional MDI icon (e.g., 'mdi:star')
        description: Optional description
    """
    try:
        label_reg = lr.async_get(hass)

        # Check if label already exists
        existing = label_reg.async_get_label_by_name(name)
        if existing:
            return {
                "success": False,
                "error": "already_exists",
                "message": f"標籤「{name}」已存在",
                "label_id": existing.label_id,
            }

        # Create label
        label = label_reg.async_create(
            name=name,
            color=color,
            icon=icon,
            description=description,
        )

        return {
            "success": True,
            "label_id": label.label_id,
            "name": label.name,
            "message": f"標籤「{name}」已建立",
        }

    except Exception as e:
        _LOGGER.error("Error creating label: %s", e)
        return {
            "success": False,
            "error": "creation_failed",
            "message": f"建立標籤失敗：{str(e)}",
        }


async def get_labels(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get all labels."""
    label_reg = lr.async_get(hass)
    return [
        {
            "label_id": label.label_id,
            "name": label.name,
            "color": label.color,
            "icon": label.icon,
            "description": label.description,
        }
        for label in label_reg.async_list_labels()
    ]


async def update_area(
    hass: HomeAssistant,
    area_id: str,
    name: str | None = None,
    icon: str | None = None,
    floor_id: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Update an existing area in Home Assistant.

    Args:
        hass: Home Assistant instance
        area_id: Area ID to update
        name: New name for the area
        icon: New MDI icon
        floor_id: New floor ID
        labels: New list of label IDs
    """
    try:
        area_reg = ar.async_get(hass)

        # Check if area exists
        area = area_reg.async_get_area(area_id)
        if not area:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到分區 ID: {area_id}",
            }

        # Build update kwargs
        kwargs: dict[str, Any] = {}
        if name is not None:
            kwargs["name"] = name
        if icon is not None:
            kwargs["icon"] = icon
        if floor_id is not None:
            kwargs["floor_id"] = floor_id
        if labels is not None:
            kwargs["labels"] = set(labels)

        if not kwargs:
            return {
                "success": False,
                "error": "no_changes",
                "message": "沒有指定要更新的內容",
            }

        # Update area
        updated = area_reg.async_update(area_id, **kwargs)

        return {
            "success": True,
            "area_id": updated.id,
            "name": updated.name,
            "message": f"分區「{updated.name}」已更新",
        }

    except Exception as e:
        _LOGGER.error("Error updating area: %s", e)
        return {
            "success": False,
            "error": "update_failed",
            "message": f"更新分區失敗：{str(e)}",
        }


async def delete_area(
    hass: HomeAssistant,
    area_id: str,
) -> dict[str, Any]:
    """Delete an area from Home Assistant.

    Args:
        hass: Home Assistant instance
        area_id: Area ID to delete
    """
    try:
        area_reg = ar.async_get(hass)

        # Check if area exists
        area = area_reg.async_get_area(area_id)
        if not area:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到分區 ID: {area_id}",
            }

        area_name = area.name
        area_reg.async_delete(area_id)

        return {
            "success": True,
            "message": f"分區「{area_name}」已刪除",
        }

    except Exception as e:
        _LOGGER.error("Error deleting area: %s", e)
        return {
            "success": False,
            "error": "delete_failed",
            "message": f"刪除分區失敗：{str(e)}",
        }


async def update_label(
    hass: HomeAssistant,
    label_id: str,
    name: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Update an existing label in Home Assistant.

    Args:
        hass: Home Assistant instance
        label_id: Label ID to update
        name: New name for the label
        color: New color in hex format
        icon: New MDI icon
        description: New description
    """
    try:
        label_reg = lr.async_get(hass)

        # Check if label exists
        label = label_reg.async_get_label(label_id)
        if not label:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到標籤 ID: {label_id}",
            }

        # Build update kwargs
        kwargs: dict[str, Any] = {}
        if name is not None:
            kwargs["name"] = name
        if color is not None:
            kwargs["color"] = color
        if icon is not None:
            kwargs["icon"] = icon
        if description is not None:
            kwargs["description"] = description

        if not kwargs:
            return {
                "success": False,
                "error": "no_changes",
                "message": "沒有指定要更新的內容",
            }

        # Update label
        updated = label_reg.async_update(label_id, **kwargs)

        return {
            "success": True,
            "label_id": updated.label_id,
            "name": updated.name,
            "message": f"標籤「{updated.name}」已更新",
        }

    except Exception as e:
        _LOGGER.error("Error updating label: %s", e)
        return {
            "success": False,
            "error": "update_failed",
            "message": f"更新標籤失敗：{str(e)}",
        }


async def delete_label(
    hass: HomeAssistant,
    label_id: str,
) -> dict[str, Any]:
    """Delete a label from Home Assistant.

    Args:
        hass: Home Assistant instance
        label_id: Label ID to delete
    """
    try:
        label_reg = lr.async_get(hass)

        # Check if label exists
        label = label_reg.async_get_label(label_id)
        if not label:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到標籤 ID: {label_id}",
            }

        label_name = label.name
        label_reg.async_delete(label_id)

        return {
            "success": True,
            "message": f"標籤「{label_name}」已刪除",
        }

    except Exception as e:
        _LOGGER.error("Error deleting label: %s", e)
        return {
            "success": False,
            "error": "delete_failed",
            "message": f"刪除標籤失敗：{str(e)}",
        }


async def assign_entity_to_area(
    hass: HomeAssistant,
    entity_id: str,
    area_id: str | None,
) -> dict[str, Any]:
    """Assign an entity to an area.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID to assign
        area_id: Area ID to assign to, or None to remove from area
    """
    try:
        entity_reg = er.async_get(hass)
        area_reg = ar.async_get(hass)

        # Check if entity exists
        entity = entity_reg.async_get(entity_id)
        if not entity:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到實體: {entity_id}",
            }

        # Check if area exists (if specified)
        if area_id:
            area = area_reg.async_get_area(area_id)
            if not area:
                return {
                    "success": False,
                    "error": "area_not_found",
                    "message": f"找不到分區 ID: {area_id}",
                }
            area_name = area.name
        else:
            area_name = None

        # Update entity
        entity_reg.async_update_entity(entity_id, area_id=area_id)

        if area_id:
            return {
                "success": True,
                "entity_id": entity_id,
                "area_id": area_id,
                "message": f"實體「{entity_id}」已分配到分區「{area_name}」",
            }
        else:
            return {
                "success": True,
                "entity_id": entity_id,
                "message": f"實體「{entity_id}」已從分區中移除",
            }

    except Exception as e:
        _LOGGER.error("Error assigning entity to area: %s", e)
        return {
            "success": False,
            "error": "assign_failed",
            "message": f"分配實體到分區失敗：{str(e)}",
        }


async def list_todo_items(
    hass: HomeAssistant,
    entity_id: str,
    status: str | None = None,
) -> dict[str, Any]:
    """List items in a todo list.

    Args:
        hass: Home Assistant instance
        entity_id: Todo entity ID (e.g., 'todo.shopping_list')
        status: Filter by status: 'needs_action' or 'completed'
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            available = [s.entity_id for s in hass.states.async_all("todo")]
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到待辦清單: {entity_id}",
                "available": available,
            }

        service_data: dict[str, Any] = {}
        if status:
            service_data["status"] = [status]

        result = await hass.services.async_call(
            "todo",
            "get_items",
            service_data=service_data,
            target={"entity_id": entity_id},
            blocking=True,
            return_response=True,
        )

        return {"success": True, "entity_id": entity_id, "items": result}

    except Exception as e:
        _LOGGER.error("Error listing todo items for %s: %s", entity_id, e)
        return {
            "success": False,
            "error": "list_failed",
            "message": f"列出待辦事項失敗：{str(e)}",
        }


async def add_todo_item(
    hass: HomeAssistant,
    entity_id: str,
    item: str,
    due_date: str | None = None,
    due_datetime: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Add an item to a todo list.

    Args:
        hass: Home Assistant instance
        entity_id: Todo entity ID
        item: Item name/summary
        due_date: Optional due date (YYYY-MM-DD)
        due_datetime: Optional due datetime (ISO 8601)
        description: Optional description
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到待辦清單: {entity_id}",
            }

        service_data: dict[str, Any] = {"item": item}
        if due_date:
            service_data["due_date"] = due_date
        if due_datetime:
            service_data["due_datetime"] = due_datetime
        if description:
            service_data["description"] = description

        await hass.services.async_call(
            "todo",
            "add_item",
            service_data=service_data,
            target={"entity_id": entity_id},
            blocking=True,
        )

        return {
            "success": True,
            "entity_id": entity_id,
            "item": item,
            "message": f"已新增待辦事項「{item}」",
        }

    except Exception as e:
        _LOGGER.error("Error adding todo item: %s", e)
        return {
            "success": False,
            "error": "add_failed",
            "message": f"新增待辦事項失敗：{str(e)}",
        }


async def update_todo_item(
    hass: HomeAssistant,
    entity_id: str,
    item: str,
    rename: str | None = None,
    status: str | None = None,
    due_date: str | None = None,
    due_datetime: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Update a todo item.

    Args:
        hass: Home Assistant instance
        entity_id: Todo entity ID
        item: Current item name to update
        rename: New name for the item
        status: New status ('needs_action' or 'completed')
        due_date: New due date (YYYY-MM-DD)
        due_datetime: New due datetime (ISO 8601)
        description: New description
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到待辦清單: {entity_id}",
            }

        service_data: dict[str, Any] = {"item": item}
        if rename:
            service_data["rename"] = rename
        if status:
            service_data["status"] = status
        if due_date:
            service_data["due_date"] = due_date
        if due_datetime:
            service_data["due_datetime"] = due_datetime
        if description:
            service_data["description"] = description

        await hass.services.async_call(
            "todo",
            "update_item",
            service_data=service_data,
            target={"entity_id": entity_id},
            blocking=True,
        )

        changes = []
        if rename:
            changes.append(f"重命名為「{rename}」")
        if status:
            changes.append(f"狀態改為 {status}")
        if due_date or due_datetime:
            changes.append("截止日期已更新")

        return {
            "success": True,
            "entity_id": entity_id,
            "item": item,
            "message": f"已更新待辦事項「{item}」：{', '.join(changes) if changes else '已更新'}",
        }

    except Exception as e:
        _LOGGER.error("Error updating todo item: %s", e)
        return {
            "success": False,
            "error": "update_failed",
            "message": f"更新待辦事項失敗：{str(e)}",
        }


async def remove_todo_item(
    hass: HomeAssistant,
    entity_id: str,
    item: str,
) -> dict[str, Any]:
    """Remove an item from a todo list.

    Args:
        hass: Home Assistant instance
        entity_id: Todo entity ID
        item: Item name to remove
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到待辦清單: {entity_id}",
            }

        await hass.services.async_call(
            "todo",
            "remove_item",
            service_data={"item": item},
            target={"entity_id": entity_id},
            blocking=True,
        )

        return {
            "success": True,
            "entity_id": entity_id,
            "item": item,
            "message": f"已移除待辦事項「{item}」",
        }

    except Exception as e:
        _LOGGER.error("Error removing todo item: %s", e)
        return {
            "success": False,
            "error": "remove_failed",
            "message": f"移除待辦事項失敗：{str(e)}",
        }


async def remove_completed_todo_items(
    hass: HomeAssistant,
    entity_id: str,
) -> dict[str, Any]:
    """Remove all completed items from a todo list.

    Args:
        hass: Home Assistant instance
        entity_id: Todo entity ID
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到待辦清單: {entity_id}",
            }

        await hass.services.async_call(
            "todo",
            "remove_completed_items",
            target={"entity_id": entity_id},
            blocking=True,
        )

        return {
            "success": True,
            "entity_id": entity_id,
            "message": "已清除所有已完成的待辦事項",
        }

    except Exception as e:
        _LOGGER.error("Error removing completed todo items: %s", e)
        return {
            "success": False,
            "error": "remove_failed",
            "message": f"清除已完成待辦事項失敗：{str(e)}",
        }


async def list_calendar_events(
    hass: HomeAssistant,
    calendar_entity_id: str,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """List calendar events in a time range.

    Args:
        hass: Home Assistant instance
        calendar_entity_id: Calendar entity ID (e.g., 'calendar.home')
        start: Start time (ISO 8601), defaults to today 00:00
        end: End time (ISO 8601), defaults to 7 days from start
    """
    try:
        state = hass.states.get(calendar_entity_id)
        if state is None:
            available = [s.entity_id for s in hass.states.async_all("calendar")]
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到日曆: {calendar_entity_id}",
                "available": available,
            }

        now = datetime.now(timezone.utc)
        if start:
            start_dt = datetime.fromisoformat(start)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        else:
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if end:
            end_dt = datetime.fromisoformat(end)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        else:
            end_dt = start_dt + timedelta(days=7)

        # Use HA's calendar platform to get events
        entity_component = hass.data.get("entity_components", {}).get("calendar")
        if entity_component is None:
            # Fallback: try hass.data["calendar"]
            entity_component = hass.data.get("calendar")

        if entity_component is None:
            return {
                "success": False,
                "error": "calendar_not_loaded",
                "message": "日曆元件未載入",
            }

        # Get the calendar entity
        if hasattr(entity_component, "get_entity"):
            entity = entity_component.get_entity(calendar_entity_id)
        else:
            entity = None

        if entity is None:
            # Try alternative approach via entity platform
            for platform_entity in entity_component.entities:
                if platform_entity.entity_id == calendar_entity_id:
                    entity = platform_entity
                    break

        if entity is None:
            return {
                "success": False,
                "error": "entity_not_accessible",
                "message": f"無法存取日曆實體: {calendar_entity_id}",
            }

        events = await entity.async_get_events(hass, start_dt, end_dt)

        result = []
        for event in events:
            event_dict: dict[str, Any] = {
                "summary": event.summary,
                "start": str(event.start),
                "end": str(event.end),
            }
            if hasattr(event, "uid") and event.uid:
                event_dict["uid"] = event.uid
            if hasattr(event, "description") and event.description:
                event_dict["description"] = event.description
            if hasattr(event, "location") and event.location:
                event_dict["location"] = event.location
            if hasattr(event, "recurrence_id") and event.recurrence_id:
                event_dict["recurrence_id"] = event.recurrence_id
            result.append(event_dict)

        return {
            "success": True,
            "calendar": calendar_entity_id,
            "start": str(start_dt),
            "end": str(end_dt),
            "count": len(result),
            "events": result,
        }

    except Exception as e:
        _LOGGER.error("Error listing calendar events: %s", e)
        return {
            "success": False,
            "error": "list_failed",
            "message": f"列出日曆事件失敗：{str(e)}",
        }


async def update_calendar_event(
    hass: HomeAssistant,
    calendar_entity_id: str,
    uid: str,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    recurrence_id: str | None = None,
) -> dict[str, Any]:
    """Update a calendar event.

    Args:
        hass: Home Assistant instance
        calendar_entity_id: Calendar entity ID
        uid: Event UID (from list_calendar_events)
        summary: New event title
        start: New start time (ISO 8601)
        end: New end time (ISO 8601)
        description: New description
        location: New location
        recurrence_id: Recurrence instance ID for recurring events
    """
    try:
        state = hass.states.get(calendar_entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到日曆: {calendar_entity_id}",
            }

        # Build event update object
        event: dict[str, Any] = {}
        if summary is not None:
            event["summary"] = summary
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location
        if start is not None:
            # HA _parse_event expects "dtstart"/"dtend" keys with date/datetime objects
            if "T" not in start:
                event["dtstart"] = date.fromisoformat(start)
            else:
                event["dtstart"] = datetime.fromisoformat(start)
        if end is not None:
            if "T" not in end:
                event["dtend"] = date.fromisoformat(end)
            else:
                event["dtend"] = datetime.fromisoformat(end)

        if not event:
            return {
                "success": False,
                "error": "no_changes",
                "message": "沒有指定要更新的內容",
            }

        # Get the calendar entity
        entity_component = hass.data.get("entity_components", {}).get("calendar")
        if entity_component is None:
            entity_component = hass.data.get("calendar")

        entity = None
        if entity_component:
            if hasattr(entity_component, "get_entity"):
                entity = entity_component.get_entity(calendar_entity_id)
            if entity is None:
                for platform_entity in entity_component.entities:
                    if platform_entity.entity_id == calendar_entity_id:
                        entity = platform_entity
                        break

        if entity is None:
            return {
                "success": False,
                "error": "entity_not_accessible",
                "message": f"無法存取日曆實體: {calendar_entity_id}",
            }

        await entity.async_update_event(
            uid,
            event,
            recurrence_id=recurrence_id,
        )

        return {
            "success": True,
            "calendar": calendar_entity_id,
            "uid": uid,
            "message": f"日曆事件已更新",
        }

    except Exception as e:
        _LOGGER.error("Error updating calendar event: %s", e)
        return {
            "success": False,
            "error": "update_failed",
            "message": f"更新日曆事件失敗：{str(e)}",
        }


async def delete_calendar_event(
    hass: HomeAssistant,
    calendar_entity_id: str,
    uid: str,
    recurrence_id: str | None = None,
) -> dict[str, Any]:
    """Delete a calendar event.

    Args:
        hass: Home Assistant instance
        calendar_entity_id: Calendar entity ID
        uid: Event UID (from list_calendar_events)
        recurrence_id: Recurrence instance ID for recurring events
    """
    try:
        state = hass.states.get(calendar_entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到日曆: {calendar_entity_id}",
            }

        # Get the calendar entity
        entity_component = hass.data.get("entity_components", {}).get("calendar")
        if entity_component is None:
            entity_component = hass.data.get("calendar")

        entity = None
        if entity_component:
            if hasattr(entity_component, "get_entity"):
                entity = entity_component.get_entity(calendar_entity_id)
            if entity is None:
                for platform_entity in entity_component.entities:
                    if platform_entity.entity_id == calendar_entity_id:
                        entity = platform_entity
                        break

        if entity is None:
            return {
                "success": False,
                "error": "entity_not_accessible",
                "message": f"無法存取日曆實體: {calendar_entity_id}",
            }

        await entity.async_delete_event(
            uid,
            recurrence_id=recurrence_id,
        )

        return {
            "success": True,
            "calendar": calendar_entity_id,
            "uid": uid,
            "message": "日曆事件已刪除",
        }

    except Exception as e:
        _LOGGER.error("Error deleting calendar event: %s", e)
        return {
            "success": False,
            "error": "delete_failed",
            "message": f"刪除日曆事件失敗：{str(e)}",
        }


async def update_scene(
    hass: HomeAssistant,
    entity_id: str,
    name: str | None = None,
    icon: str | None = None,
    entities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update a scene in Home Assistant.

    Args:
        hass: Home Assistant instance
        entity_id: Scene entity ID (e.g., 'scene.movie_night')
        name: New name for the scene
        icon: New MDI icon
        entities: Updated entity states dict
    """
    import yaml

    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到情境: {entity_id}",
            }

        # Extract scene_id from entity_id
        scene_id = entity_id.replace("scene.", "", 1)

        config_path = hass.config.path("scenes.yaml")

        def _update_scene():
            try:
                with open(config_path, "r") as f:
                    scenes = yaml.safe_load(f) or []
            except FileNotFoundError:
                return None

            if not isinstance(scenes, list):
                return None

            # Find the scene by id or name
            found_idx = None
            for idx, scene in enumerate(scenes):
                sid = scene.get("id", "")
                if sid == scene_id:
                    found_idx = idx
                    break

            if found_idx is None:
                # Try matching by entity_id pattern
                for idx, scene in enumerate(scenes):
                    scene_name = scene.get("name", "")
                    import re
                    generated_id = scene_name.lower().replace(" ", "_").replace("-", "_")
                    generated_id = re.sub(r'[^a-z0-9_]', '', generated_id)
                    if generated_id == scene_id:
                        found_idx = idx
                        break

            if found_idx is None:
                return None

            # Update fields
            if name is not None:
                scenes[found_idx]["name"] = name
            if icon is not None:
                scenes[found_idx]["icon"] = icon
            if entities is not None:
                scenes[found_idx]["entities"] = entities

            with open(config_path, "w") as f:
                yaml.dump(scenes, f, default_flow_style=False, allow_unicode=True)

            return scenes[found_idx]

        updated = await hass.async_add_executor_job(_update_scene)

        if updated is None:
            return {
                "success": False,
                "error": "not_found_in_yaml",
                "message": f"在 scenes.yaml 中找不到情境: {entity_id}",
            }

        await hass.services.async_call("scene", "reload", blocking=True)

        return {
            "success": True,
            "entity_id": entity_id,
            "message": f"情境「{updated.get('name', scene_id)}」已更新",
        }

    except Exception as e:
        _LOGGER.error("Error updating scene: %s", e)
        return {
            "success": False,
            "error": "update_failed",
            "message": f"更新情境失敗：{str(e)}",
        }


async def delete_scene(
    hass: HomeAssistant,
    entity_id: str,
) -> dict[str, Any]:
    """Delete a scene from Home Assistant.

    Args:
        hass: Home Assistant instance
        entity_id: Scene entity ID (e.g., 'scene.movie_night')
    """
    import yaml

    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到情境: {entity_id}",
            }

        scene_id = entity_id.replace("scene.", "", 1)
        scene_name = state.attributes.get("friendly_name", entity_id)

        config_path = hass.config.path("scenes.yaml")

        def _delete_scene():
            try:
                with open(config_path, "r") as f:
                    scenes = yaml.safe_load(f) or []
            except FileNotFoundError:
                return False

            if not isinstance(scenes, list):
                return False

            original_len = len(scenes)

            # Remove matching scene
            import re
            scenes = [
                s for s in scenes
                if not (
                    s.get("id", "") == scene_id
                    or re.sub(r'[^a-z0-9_]', '', s.get("name", "").lower().replace(" ", "_").replace("-", "_")) == scene_id
                )
            ]

            if len(scenes) == original_len:
                return False

            with open(config_path, "w") as f:
                yaml.dump(scenes, f, default_flow_style=False, allow_unicode=True)

            return True

        deleted = await hass.async_add_executor_job(_delete_scene)

        if not deleted:
            return {
                "success": False,
                "error": "not_found_in_yaml",
                "message": f"在 scenes.yaml 中找不到情境: {entity_id}",
            }

        await hass.services.async_call("scene", "reload", blocking=True)

        return {
            "success": True,
            "message": f"情境「{scene_name}」已刪除",
        }

    except Exception as e:
        _LOGGER.error("Error deleting scene: %s", e)
        return {
            "success": False,
            "error": "delete_failed",
            "message": f"刪除情境失敗：{str(e)}",
        }


async def list_blueprints(
    hass: HomeAssistant,
    domain: str,
) -> dict[str, Any]:
    """List installed blueprints.

    Args:
        hass: Home Assistant instance
        domain: Blueprint domain ('automation' or 'script')
    """
    try:
        if domain not in ("automation", "script"):
            return {
                "success": False,
                "error": "invalid_domain",
                "message": f"無效的藍圖域: {domain}。可用的域: automation, script",
            }

        blueprint_data = hass.data.get("blueprint", {})
        domain_blueprints = blueprint_data.get(domain)

        if domain_blueprints is None:
            return {
                "success": True,
                "domain": domain,
                "count": 0,
                "blueprints": [],
                "message": f"沒有找到 {domain} 藍圖",
            }

        blueprints = await domain_blueprints.async_get_blueprints()

        result = []
        for path, bp in blueprints.items():
            if bp is not None:
                metadata = bp.metadata or {} if hasattr(bp, "metadata") else {}
                result.append({
                    "path": path,
                    "name": metadata.get("name", path),
                    "description": metadata.get("description", ""),
                    "domain": metadata.get("domain", domain),
                })

        return {
            "success": True,
            "domain": domain,
            "count": len(result),
            "blueprints": result,
        }

    except Exception as e:
        _LOGGER.error("Error listing blueprints: %s", e)
        return {
            "success": False,
            "error": "list_failed",
            "message": f"列出藍圖失敗：{str(e)}",
        }


async def import_blueprint(
    hass: HomeAssistant,
    url: str,
) -> dict[str, Any]:
    """Import a blueprint from a URL.

    Args:
        hass: Home Assistant instance
        url: Blueprint source URL (GitHub, HA Community, etc.)
    """
    try:
        from homeassistant.components.blueprint import importer

        result = await importer.fetch_blueprint_from_url(hass, url)

        if result is None:
            return {
                "success": False,
                "error": "import_failed",
                "message": f"無法從 URL 匯入藍圖: {url}",
            }

        # Save the blueprint
        blueprint = result.blueprint
        metadata = blueprint.metadata or {}
        domain = metadata.get("domain", "automation")

        blueprint_data = hass.data.get("blueprint", {})
        domain_blueprints = blueprint_data.get(domain)

        if domain_blueprints is None:
            return {
                "success": False,
                "error": "domain_not_found",
                "message": f"藍圖域 {domain} 未載入",
            }

        # Save with suggested filename
        suggested_filename = result.suggested_filename
        await domain_blueprints.async_add_blueprint(blueprint, suggested_filename)

        return {
            "success": True,
            "domain": domain,
            "name": metadata.get("name", suggested_filename),
            "path": suggested_filename,
            "message": f"藍圖「{metadata.get('name', suggested_filename)}」已匯入",
        }

    except Exception as e:
        _LOGGER.error("Error importing blueprint from %s: %s", url, e)
        return {
            "success": False,
            "error": "import_failed",
            "message": f"匯入藍圖失敗：{str(e)}",
        }


async def assign_entity_to_labels(
    hass: HomeAssistant,
    entity_id: str,
    label_ids: list[str],
) -> dict[str, Any]:
    """Assign labels to an entity.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID to assign labels to
        label_ids: List of label IDs to assign (replaces existing labels)
    """
    try:
        entity_reg = er.async_get(hass)
        label_reg = lr.async_get(hass)

        # Check if entity exists
        entity = entity_reg.async_get(entity_id)
        if not entity:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到實體: {entity_id}",
            }

        # Validate all labels exist
        valid_labels = []
        for label_id in label_ids:
            label = label_reg.async_get_label(label_id)
            if label:
                valid_labels.append(label_id)
            else:
                _LOGGER.warning("Label not found: %s", label_id)

        # Update entity with labels
        entity_reg.async_update_entity(entity_id, labels=set(valid_labels))

        return {
            "success": True,
            "entity_id": entity_id,
            "labels": valid_labels,
            "message": f"實體「{entity_id}」已分配 {len(valid_labels)} 個標籤",
        }

    except Exception as e:
        _LOGGER.error("Error assigning labels to entity: %s", e)
        return {
            "success": False,
            "error": "assign_failed",
            "message": f"分配標籤到實體失敗：{str(e)}",
        }


# ===== Phase 2: P1 tools =====


async def send_notification(
    hass: HomeAssistant,
    message: str,
    title: str | None = None,
    target: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a notification via Home Assistant.

    Args:
        hass: Home Assistant instance
        message: Notification message content
        title: Optional notification title
        target: Notification service target (e.g., 'notify.mobile_app_phone').
                If not specified, uses 'notify.notify' (broadcast).
        data: Optional extra data (image URL, action buttons, etc.)
    """
    try:
        # Determine service to call
        if target:
            # target could be "notify.mobile_app_phone" or just "mobile_app_phone"
            if target.startswith("notify."):
                domain = "notify"
                service = target.replace("notify.", "", 1)
            else:
                domain = "notify"
                service = target
        else:
            domain = "notify"
            service = "notify"

        # Verify the service exists
        services = hass.services.async_services()
        notify_services = services.get("notify", {})
        if service not in notify_services:
            available = list(notify_services.keys())
            return {
                "success": False,
                "error": "service_not_found",
                "message": f"找不到通知服務: notify.{service}",
                "available": [f"notify.{s}" for s in available],
            }

        service_data: dict[str, Any] = {"message": message}
        if title is not None:
            service_data["title"] = title
        if data is not None:
            service_data["data"] = data

        await hass.services.async_call(
            domain, service, service_data=service_data, blocking=True,
        )

        return {
            "success": True,
            "service": f"notify.{service}",
            "message": f"通知已發送：{message[:50]}{'...' if len(message) > 50 else ''}",
        }

    except Exception as e:
        _LOGGER.error("Error sending notification: %s", e)
        return {
            "success": False,
            "error": "send_failed",
            "message": f"發送通知失敗：{str(e)}",
        }


async def control_input_helper(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
    value: Any = None,
) -> dict[str, Any]:
    """Control an input helper entity (input_boolean, input_number, input_select, etc.).

    Automatically routes to the correct service based on entity_id domain prefix.

    Args:
        hass: Home Assistant instance
        entity_id: Input helper entity ID (e.g., 'input_boolean.guest_mode')
        action: Action to perform (turn_on, turn_off, toggle, set_value, increment,
                decrement, select_option, select_next, select_previous, set_datetime, press)
        value: Value for set_value/select_option/set_datetime actions
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到輸入輔助實體: {entity_id}",
            }

        # Extract domain from entity_id
        domain = entity_id.split(".")[0]
        valid_domains = {
            "input_boolean", "input_number", "input_select",
            "input_datetime", "input_button", "input_text",
        }
        if domain not in valid_domains:
            return {
                "success": False,
                "error": "invalid_domain",
                "message": f"不支援的輸入輔助類型: {domain}。支援的類型: {', '.join(sorted(valid_domains))}",
            }

        # Route action to correct domain service
        # Map valid actions per domain
        domain_actions = {
            "input_boolean": {"turn_on", "turn_off", "toggle"},
            "input_number": {"set_value", "increment", "decrement"},
            "input_select": {"select_option", "select_next", "select_previous", "set_options"},
            "input_datetime": {"set_datetime"},
            "input_button": {"press"},
            "input_text": {"set_value"},
        }

        valid_actions = domain_actions.get(domain, set())
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"{domain} 不支援 {action}。可用的動作: {', '.join(sorted(valid_actions))}",
            }

        # Build service data
        service_data: dict[str, Any] = {"entity_id": entity_id}

        if action == "set_value" and value is not None:
            service_data["value"] = value
        elif action == "select_option" and value is not None:
            service_data["option"] = value
        elif action == "set_datetime" and value is not None:
            # value can be datetime string, date string, or time string
            if isinstance(value, str):
                if "T" in value or " " in value:
                    service_data["datetime"] = value
                elif ":" in value:
                    service_data["time"] = value
                else:
                    service_data["date"] = value
            else:
                service_data["datetime"] = str(value)
        elif action == "set_options" and value is not None:
            service_data["options"] = value

        await hass.services.async_call(
            domain, action, service_data=service_data, blocking=True,
        )

        new_state = hass.states.get(entity_id)
        return {
            "success": True,
            "entity_id": entity_id,
            "action": action,
            "state": new_state.state if new_state else "unknown",
            "message": f"已對 {entity_id} 執行 {action}",
        }

    except Exception as e:
        _LOGGER.error("Error controlling input helper: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制輸入輔助失敗：{str(e)}",
        }


async def control_timer(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
    duration: str | None = None,
) -> dict[str, Any]:
    """Control a timer entity (start, pause, cancel, finish, change).

    Args:
        hass: Home Assistant instance
        entity_id: Timer entity ID (e.g., 'timer.kitchen')
        action: Action to perform (start, pause, cancel, finish, change)
        duration: Duration in HH:MM:SS format (for start and change actions)
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到計時器: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "timer":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"實體不是計時器: {entity_id}",
            }

        valid_actions = {"start", "pause", "cancel", "finish", "change"}
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用的動作: {', '.join(sorted(valid_actions))}",
            }

        service_data: dict[str, Any] = {"entity_id": entity_id}
        if duration is not None and action in ("start", "change"):
            service_data["duration"] = duration

        await hass.services.async_call(
            "timer", action, service_data=service_data, blocking=True,
        )

        new_state = hass.states.get(entity_id)
        return {
            "success": True,
            "entity_id": entity_id,
            "action": action,
            "state": new_state.state if new_state else "unknown",
            "message": f"計時器 {entity_id} 已執行 {action}",
        }

    except Exception as e:
        _LOGGER.error("Error controlling timer: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制計時器失敗：{str(e)}",
        }


async def control_fan(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
    percentage: int | None = None,
    preset_mode: str | None = None,
    direction: str | None = None,
    oscillating: bool | None = None,
) -> dict[str, Any]:
    """Control a fan entity.

    Args:
        hass: Home Assistant instance
        entity_id: Fan entity ID (e.g., 'fan.bedroom')
        action: Action (turn_on, turn_off, toggle, set_percentage,
                set_preset_mode, set_direction, oscillate)
        percentage: Fan speed percentage (0-100)
        preset_mode: Preset mode name
        direction: Fan direction ('forward' or 'reverse')
        oscillating: Whether to oscillate
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到風扇: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "fan":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"實體不是風扇: {entity_id}",
            }

        valid_actions = {
            "turn_on", "turn_off", "toggle",
            "set_percentage", "set_preset_mode", "set_direction", "oscillate",
            "increase_speed", "decrease_speed",
        }
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用的動作: {', '.join(sorted(valid_actions))}",
            }

        service_data: dict[str, Any] = {"entity_id": entity_id}

        if action == "turn_on":
            if percentage is not None:
                service_data["percentage"] = percentage
            if preset_mode is not None:
                service_data["preset_mode"] = preset_mode
        elif action == "set_percentage" and percentage is not None:
            service_data["percentage"] = percentage
        elif action == "set_preset_mode" and preset_mode is not None:
            service_data["preset_mode"] = preset_mode
        elif action == "set_direction" and direction is not None:
            service_data["direction"] = direction
        elif action == "oscillate" and oscillating is not None:
            service_data["oscillating"] = oscillating
        # increase_speed / decrease_speed use percentage_step if provided
        elif action in ("increase_speed", "decrease_speed"):
            if percentage is not None:
                service_data["percentage_step"] = percentage

        await hass.services.async_call(
            "fan", action, service_data=service_data, blocking=True,
        )

        new_state = hass.states.get(entity_id)
        return {
            "success": True,
            "entity_id": entity_id,
            "action": action,
            "state": new_state.state if new_state else "unknown",
            "message": f"風扇 {entity_id} 已執行 {action}",
        }

    except Exception as e:
        _LOGGER.error("Error controlling fan: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制風扇失敗：{str(e)}",
        }


async def delete_automation(
    hass: HomeAssistant,
    entity_id: str,
) -> dict[str, Any]:
    """Delete an automation from Home Assistant.

    Removes from automations.yaml and reloads.

    Args:
        hass: Home Assistant instance
        entity_id: Automation entity ID (e.g., 'automation.motion_light')
    """
    import yaml

    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到自動化: {entity_id}",
            }

        automation_name = state.attributes.get("friendly_name", entity_id)
        # Extract automation_id: the id field in automations.yaml
        # HA stores it in the entity's unique_id or we can match by alias
        automation_slug = entity_id.replace("automation.", "", 1)

        config_path = hass.config.path("automations.yaml")

        def _delete_automation():
            try:
                with open(config_path, "r") as f:
                    automations = yaml.safe_load(f) or []
            except FileNotFoundError:
                return False

            if not isinstance(automations, list):
                return False

            original_len = len(automations)

            # Match by id field or by alias-derived slug
            import re
            automations = [
                a for a in automations
                if not (
                    a.get("id", "") == automation_slug
                    or re.sub(r'[^a-z0-9_]', '', a.get("alias", "").lower().replace(" ", "_").replace("-", "_")) == automation_slug
                )
            ]

            if len(automations) == original_len:
                return False

            with open(config_path, "w") as f:
                yaml.dump(automations, f, default_flow_style=False, allow_unicode=True)

            return True

        deleted = await hass.async_add_executor_job(_delete_automation)

        if not deleted:
            return {
                "success": False,
                "error": "not_found_in_yaml",
                "message": f"在 automations.yaml 中找不到自動化: {entity_id}",
            }

        await hass.services.async_call("automation", "reload", blocking=True)

        return {
            "success": True,
            "message": f"自動化「{automation_name}」已刪除",
        }

    except Exception as e:
        _LOGGER.error("Error deleting automation: %s", e)
        return {
            "success": False,
            "error": "delete_failed",
            "message": f"刪除自動化失敗：{str(e)}",
        }


async def delete_script(
    hass: HomeAssistant,
    entity_id: str,
) -> dict[str, Any]:
    """Delete a script from Home Assistant.

    Removes from scripts.yaml and reloads.

    Args:
        hass: Home Assistant instance
        entity_id: Script entity ID (e.g., 'script.morning_routine')
    """
    import yaml

    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到腳本: {entity_id}",
            }

        script_name = state.attributes.get("friendly_name", entity_id)
        script_id = entity_id.replace("script.", "", 1)

        config_path = hass.config.path("scripts.yaml")

        def _delete_script():
            try:
                with open(config_path, "r") as f:
                    scripts = yaml.safe_load(f) or {}
            except FileNotFoundError:
                return False

            if not isinstance(scripts, dict):
                return False

            if script_id not in scripts:
                return False

            del scripts[script_id]

            with open(config_path, "w") as f:
                yaml.dump(scripts, f, default_flow_style=False, allow_unicode=True)

            return True

        deleted = await hass.async_add_executor_job(_delete_script)

        if not deleted:
            return {
                "success": False,
                "error": "not_found_in_yaml",
                "message": f"在 scripts.yaml 中找不到腳本: {entity_id}",
            }

        await hass.services.async_call("script", "reload", blocking=True)

        return {
            "success": True,
            "message": f"腳本「{script_name}」已刪除",
        }

    except Exception as e:
        _LOGGER.error("Error deleting script: %s", e)
        return {
            "success": False,
            "error": "delete_failed",
            "message": f"刪除腳本失敗：{str(e)}",
        }


# ===== Phase 3: P2 domain coverage =====


async def control_media_player(
    hass: HomeAssistant,
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
    """Control a media player entity.

    Args:
        hass: Home Assistant instance
        entity_id: Media player entity ID
        action: Action to perform (media_play, media_pause, media_stop,
                media_next_track, media_previous_track, volume_up, volume_down,
                volume_set, volume_mute, turn_on, turn_off, toggle,
                select_source, play_media, shuffle_set, repeat_set)
        volume_level: Volume level 0.0-1.0 (for volume_set)
        is_volume_muted: Mute state (for volume_mute)
        media_content_id: Media ID (for play_media)
        media_content_type: Media type (for play_media)
        source: Input source name (for select_source)
        shuffle: Shuffle mode (for shuffle_set)
        repeat: Repeat mode off/all/one (for repeat_set)
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到媒體播放器: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "media_player":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"實體不是媒體播放器: {entity_id}",
            }

        valid_actions = {
            "media_play", "media_pause", "media_stop",
            "media_next_track", "media_previous_track",
            "volume_up", "volume_down", "volume_set", "volume_mute",
            "turn_on", "turn_off", "toggle",
            "select_source", "play_media", "shuffle_set", "repeat_set",
            "media_seek", "select_sound_mode",
        }
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用: {', '.join(sorted(valid_actions))}",
            }

        service_data: dict[str, Any] = {"entity_id": entity_id}

        if action == "volume_set" and volume_level is not None:
            service_data["volume_level"] = volume_level
        elif action == "volume_mute" and is_volume_muted is not None:
            service_data["is_volume_muted"] = is_volume_muted
        elif action == "play_media":
            if media_content_id is not None:
                service_data["media_content_id"] = media_content_id
            if media_content_type is not None:
                service_data["media_content_type"] = media_content_type
        elif action == "select_source" and source is not None:
            service_data["source"] = source
        elif action == "shuffle_set" and shuffle is not None:
            service_data["shuffle"] = shuffle
        elif action == "repeat_set" and repeat is not None:
            service_data["repeat"] = repeat
        elif action == "media_seek" and seek_position is not None:
            service_data["seek_position"] = seek_position
        elif action == "select_sound_mode" and sound_mode is not None:
            service_data["sound_mode"] = sound_mode
        elif action == "turn_on":
            if volume_level is not None:
                service_data["volume_level"] = volume_level
            if source is not None:
                service_data["source"] = source

        await hass.services.async_call(
            "media_player", action, service_data=service_data, blocking=True,
        )

        new_state = hass.states.get(entity_id)
        return {
            "success": True,
            "entity_id": entity_id,
            "action": action,
            "state": new_state.state if new_state else "unknown",
            "message": f"媒體播放器 {entity_id} 已執行 {action}",
        }

    except Exception as e:
        _LOGGER.error("Error controlling media player: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制媒體播放器失敗：{str(e)}",
        }


async def control_lock(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
) -> dict[str, Any]:
    """Control a lock entity.

    Args:
        hass: Home Assistant instance
        entity_id: Lock entity ID
        action: Action to perform (lock, unlock, open)
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到門鎖: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "lock":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"實體不是門鎖: {entity_id}",
            }

        valid_actions = {"lock", "unlock", "open"}
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用: {', '.join(sorted(valid_actions))}",
            }

        await hass.services.async_call(
            "lock", action,
            service_data={"entity_id": entity_id},
            blocking=True,
        )

        new_state = hass.states.get(entity_id)
        return {
            "success": True,
            "entity_id": entity_id,
            "action": action,
            "state": new_state.state if new_state else "unknown",
            "message": f"門鎖 {entity_id} 已執行 {action}",
        }

    except Exception as e:
        _LOGGER.error("Error controlling lock: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制門鎖失敗：{str(e)}",
        }


async def speak_tts(
    hass: HomeAssistant,
    entity_id: str,
    message: str,
    media_player_entity_id: str | None = None,
    language: str | None = None,
    cache: bool = True,
) -> dict[str, Any]:
    """Speak text via TTS service.

    Args:
        hass: Home Assistant instance
        entity_id: TTS entity ID (e.g., tts.google_translate_en_com)
        message: Text to speak
        media_player_entity_id: Optional media player to play on (for tts.speak)
        language: Language code (e.g., 'zh-TW', 'en-US')
        cache: Whether to cache the TTS audio (default True)
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到 TTS 實體: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "tts":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"entity_id 必須是 tts 域: {entity_id}",
            }

        # Find available TTS services
        services = hass.services.async_services()
        tts_services = services.get("tts", {})

        if not tts_services:
            return {
                "success": False,
                "error": "no_tts_service",
                "message": "沒有可用的 TTS 服務",
            }

        # Prefer cloud_say > speak > first available
        if "cloud_say" in tts_services:
            tts_service = "cloud_say"
        elif "speak" in tts_services:
            tts_service = "speak"
        else:
            tts_service = next(iter(tts_services))

        service_data: dict[str, Any] = {
            "message": message,
            "cache": cache,
        }
        if language is not None:
            service_data["language"] = language

        if tts_service == "speak":
            # tts.speak targets TTS entity via entity_id,
            # and uses media_player_entity_id for the speaker
            service_data["entity_id"] = entity_id
            if media_player_entity_id:
                service_data["media_player_entity_id"] = media_player_entity_id
        else:
            # tts.cloud_say and others use entity_id for the media player
            if media_player_entity_id:
                service_data["entity_id"] = media_player_entity_id
            else:
                service_data["entity_id"] = entity_id

        await hass.services.async_call(
            "tts", tts_service, service_data=service_data, blocking=True,
        )

        return {
            "success": True,
            "entity_id": entity_id,
            "service": f"tts.{tts_service}",
            "message": f"已播報：{message[:50]}{'...' if len(message) > 50 else ''}",
        }

    except Exception as e:
        _LOGGER.error("Error speaking TTS: %s", e)
        return {
            "success": False,
            "error": "tts_failed",
            "message": f"TTS 播報失敗：{str(e)}",
        }


async def control_persistent_notification(
    hass: HomeAssistant,
    action: str,
    message: str | None = None,
    title: str | None = None,
    notification_id: str | None = None,
) -> dict[str, Any]:
    """Manage persistent notifications in Home Assistant.

    Args:
        hass: Home Assistant instance
        action: Action (create, dismiss, dismiss_all)
        message: Notification message (required for create)
        title: Notification title (optional, for create)
        notification_id: Notification ID (required for dismiss; optional for create)
    """
    try:
        valid_actions = {"create", "dismiss", "dismiss_all"}
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用: {', '.join(sorted(valid_actions))}",
            }

        if action == "create":
            if not message:
                return {
                    "success": False,
                    "error": "missing_message",
                    "message": "建立持久通知需要 message 參數",
                }
            service_data: dict[str, Any] = {"message": message}
            if title is not None:
                service_data["title"] = title
            if notification_id is not None:
                service_data["notification_id"] = notification_id

            await hass.services.async_call(
                "persistent_notification", "create",
                service_data=service_data, blocking=True,
            )
            return {
                "success": True,
                "action": "create",
                "notification_id": notification_id,
                "message": f"持久通知已建立：{message[:50]}{'...' if len(message) > 50 else ''}",
            }

        elif action == "dismiss":
            if not notification_id:
                return {
                    "success": False,
                    "error": "missing_notification_id",
                    "message": "關閉持久通知需要 notification_id 參數",
                }
            await hass.services.async_call(
                "persistent_notification", "dismiss",
                service_data={"notification_id": notification_id},
                blocking=True,
            )
            return {
                "success": True,
                "action": "dismiss",
                "notification_id": notification_id,
                "message": f"持久通知 {notification_id} 已關閉",
            }

        else:  # dismiss_all
            await hass.services.async_call(
                "persistent_notification", "dismiss_all",
                blocking=True,
            )
            return {
                "success": True,
                "action": "dismiss_all",
                "message": "所有持久通知已關閉",
            }

    except Exception as e:
        _LOGGER.error("Error managing persistent notification: %s", e)
        return {
            "success": False,
            "error": "notification_failed",
            "message": f"持久通知操作失敗：{str(e)}",
        }


async def control_counter(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
    value: int | None = None,
) -> dict[str, Any]:
    """Control a counter entity.

    Args:
        hass: Home Assistant instance
        entity_id: Counter entity ID
        action: Action (increment, decrement, reset, set_value)
        value: Value for set_value action
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到計數器: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "counter":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"實體不是計數器: {entity_id}",
            }

        valid_actions = {"increment", "decrement", "reset", "set_value"}
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用: {', '.join(sorted(valid_actions))}",
            }

        service_data: dict[str, Any] = {"entity_id": entity_id}
        if action == "set_value" and value is not None:
            service_data["value"] = value

        await hass.services.async_call(
            "counter", action, service_data=service_data, blocking=True,
        )

        new_state = hass.states.get(entity_id)
        return {
            "success": True,
            "entity_id": entity_id,
            "action": action,
            "state": new_state.state if new_state else "unknown",
            "message": f"計數器 {entity_id} 已執行 {action}",
        }

    except Exception as e:
        _LOGGER.error("Error controlling counter: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制計數器失敗：{str(e)}",
        }


async def manage_backup(
    hass: HomeAssistant,
    action: str = "create",
) -> dict[str, Any]:
    """Manage Home Assistant backups.

    Args:
        hass: Home Assistant instance
        action: Action (create, create_automatic)
    """
    try:
        valid_actions = {"create", "create_automatic"}
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用: {', '.join(sorted(valid_actions))}",
            }

        services = hass.services.async_services()
        backup_services = services.get("backup", {})
        if action not in backup_services:
            return {
                "success": False,
                "error": "service_not_available",
                "message": f"備份服務 backup.{action} 不可用",
                "available": [f"backup.{s}" for s in backup_services],
            }

        await hass.services.async_call(
            "backup", action, blocking=True,
        )

        return {
            "success": True,
            "action": action,
            "message": f"備份已開始（{action}）",
        }

    except Exception as e:
        _LOGGER.error("Error managing backup: %s", e)
        return {
            "success": False,
            "error": "backup_failed",
            "message": f"備份操作失敗：{str(e)}",
        }


async def control_camera(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
    filename: str | None = None,
    media_player: str | None = None,
    format: str | None = None,
    duration: int | None = None,
    lookback: int | None = None,
) -> dict[str, Any]:
    """Control a camera entity.

    Args:
        hass: Home Assistant instance
        entity_id: Camera entity ID
        action: Action (snapshot, turn_on, turn_off,
                enable_motion_detection, disable_motion_detection,
                play_stream, record)
        filename: File path for snapshot/record
        media_player: Media player entity for play_stream
        format: Stream format for play_stream (default: hls)
        duration: Recording duration in seconds
        lookback: Lookback seconds before recording start
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到攝影機: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "camera":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"實體不是攝影機: {entity_id}",
            }

        valid_actions = {
            "snapshot", "turn_on", "turn_off",
            "enable_motion_detection", "disable_motion_detection",
            "play_stream", "record",
        }
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用: {', '.join(sorted(valid_actions))}",
            }

        service_data: dict[str, Any] = {"entity_id": entity_id}

        if action == "snapshot":
            if filename:
                service_data["filename"] = filename
            else:
                service_data["filename"] = f"/config/www/snapshot_{entity_id.split('.')[1]}.jpg"
        elif action == "play_stream":
            if media_player:
                service_data["media_player"] = media_player
            if format:
                service_data["format"] = format
        elif action == "record":
            if filename:
                service_data["filename"] = filename
            else:
                service_data["filename"] = f"/config/www/record_{entity_id.split('.')[1]}.mp4"
            if duration is not None:
                service_data["duration"] = duration
            if lookback is not None:
                service_data["lookback"] = lookback

        await hass.services.async_call(
            "camera", action, service_data=service_data, blocking=True,
        )

        result: dict[str, Any] = {
            "success": True,
            "entity_id": entity_id,
            "action": action,
            "message": f"攝影機 {entity_id} 已執行 {action}",
        }
        if action in ("snapshot", "record"):
            result["filename"] = service_data["filename"]

        return result

    except Exception as e:
        _LOGGER.error("Error controlling camera: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制攝影機失敗：{str(e)}",
        }


async def control_switch(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
) -> dict[str, Any]:
    """Control a switch entity.

    Args:
        hass: Home Assistant instance
        entity_id: Switch entity ID
        action: Action (turn_on, turn_off, toggle)
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到開關: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "switch":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"實體不是開關: {entity_id}",
            }

        valid_actions = {"turn_on", "turn_off", "toggle"}
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用: {', '.join(sorted(valid_actions))}",
            }

        await hass.services.async_call(
            "switch", action,
            service_data={"entity_id": entity_id},
            blocking=True,
        )

        new_state = hass.states.get(entity_id)
        return {
            "success": True,
            "entity_id": entity_id,
            "action": action,
            "state": new_state.state if new_state else "unknown",
            "message": f"開關 {entity_id} 已執行 {action}",
        }

    except Exception as e:
        _LOGGER.error("Error controlling switch: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制開關失敗：{str(e)}",
        }


# ---------------------------------------------------------------------------
# Phase 4: CRUD 補完 + 增強 + 新域
# ---------------------------------------------------------------------------


async def update_automation(
    hass: HomeAssistant,
    entity_id: str,
    alias: str | None = None,
    description: str | None = None,
    trigger: list[dict[str, Any]] | None = None,
    condition: list[dict[str, Any]] | None = None,
    action: list[dict[str, Any]] | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Update an existing automation in automations.yaml.

    Args:
        hass: Home Assistant instance
        entity_id: Automation entity ID
        alias: New alias/name
        description: New description
        trigger: New trigger list
        condition: New condition list
        action: New action list
        mode: Execution mode (single, restart, queued, parallel)
    """
    import yaml

    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到自動化: {entity_id}",
            }

        automation_slug = entity_id.replace("automation.", "", 1)
        config_path = hass.config.path("automations.yaml")

        # Look up the automation's unique_id from entity registry
        # which matches the "id" field in automations.yaml
        from homeassistant.helpers import entity_registry as er
        ent_reg = er.async_get(hass)
        entry = ent_reg.async_get(entity_id)
        automation_unique_id = entry.unique_id if entry else None

        def _update_automation():
            import re

            try:
                with open(config_path, "r") as f:
                    automations = yaml.safe_load(f) or []
            except FileNotFoundError:
                return None

            if not isinstance(automations, list):
                return None

            target = None
            for a in automations:
                aid = a.get("id", "")
                a_alias = a.get("alias", "")
                a_slug = re.sub(
                    r"[^a-z0-9_]", "",
                    a_alias.lower().replace(" ", "_").replace("-", "_"),
                )
                if (
                    aid == automation_slug
                    or a_slug == automation_slug
                    or (automation_unique_id and aid == automation_unique_id)
                ):
                    target = a
                    break

            if target is None:
                return None

            # Apply updates
            if alias is not None:
                target["alias"] = alias
            if description is not None:
                target["description"] = description
            if trigger is not None:
                target["trigger"] = trigger
            if condition is not None:
                target["condition"] = condition
            if action is not None:
                target["action"] = action
            if mode is not None:
                target["mode"] = mode

            with open(config_path, "w") as f:
                yaml.dump(automations, f, default_flow_style=False, allow_unicode=True)

            return target.get("alias", automation_slug)

        result_alias = await hass.async_add_executor_job(_update_automation)

        if result_alias is None:
            return {
                "success": False,
                "error": "not_found_in_yaml",
                "message": f"在 automations.yaml 中找不到自動化: {entity_id}",
            }

        await hass.services.async_call("automation", "reload", blocking=True)

        return {
            "success": True,
            "entity_id": entity_id,
            "message": f"自動化「{result_alias}」已更新",
        }

    except Exception as e:
        _LOGGER.error("Error updating automation: %s", e)
        return {
            "success": False,
            "error": "update_failed",
            "message": f"更新自動化失敗：{str(e)}",
        }


async def update_script(
    hass: HomeAssistant,
    entity_id: str,
    alias: str | None = None,
    description: str | None = None,
    sequence: list[dict[str, Any]] | None = None,
    mode: str | None = None,
    icon: str | None = None,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update an existing script in scripts.yaml.

    Args:
        hass: Home Assistant instance
        entity_id: Script entity ID
        alias: New alias/name
        description: New description
        sequence: New action sequence
        mode: Execution mode (single, restart, queued, parallel)
        icon: New icon
        fields: New input fields definition
    """
    import yaml

    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "not_found",
                "message": f"找不到腳本: {entity_id}",
            }

        script_id = entity_id.replace("script.", "", 1)
        config_path = hass.config.path("scripts.yaml")

        def _update_script():
            try:
                with open(config_path, "r") as f:
                    scripts = yaml.safe_load(f) or {}
            except FileNotFoundError:
                return None

            if not isinstance(scripts, dict):
                return None

            if script_id not in scripts:
                return None

            target = scripts[script_id]

            if alias is not None:
                target["alias"] = alias
            if description is not None:
                target["description"] = description
            if sequence is not None:
                target["sequence"] = sequence
            if mode is not None:
                target["mode"] = mode
            if icon is not None:
                target["icon"] = icon
            if fields is not None:
                target["fields"] = fields

            with open(config_path, "w") as f:
                yaml.dump(scripts, f, default_flow_style=False, allow_unicode=True)

            return target.get("alias", script_id)

        result_alias = await hass.async_add_executor_job(_update_script)

        if result_alias is None:
            return {
                "success": False,
                "error": "not_found_in_yaml",
                "message": f"在 scripts.yaml 中找不到腳本: {entity_id}",
            }

        await hass.services.async_call("script", "reload", blocking=True)

        return {
            "success": True,
            "entity_id": entity_id,
            "message": f"腳本「{result_alias}」已更新",
        }

    except Exception as e:
        _LOGGER.error("Error updating script: %s", e)
        return {
            "success": False,
            "error": "update_failed",
            "message": f"更新腳本失敗：{str(e)}",
        }


async def control_valve(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
    position: int | None = None,
) -> dict[str, Any]:
    """Control a valve entity.

    Args:
        hass: Home Assistant instance
        entity_id: Valve entity ID
        action: Action (open, close, stop, set_position, toggle)
        position: Valve position 0-100 (for set_position)
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到閥門: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "valve":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"實體不是閥門: {entity_id}",
            }

        service_map = {
            "open": "open_valve",
            "close": "close_valve",
            "stop": "stop_valve",
            "toggle": "toggle",
        }

        valid_actions = set(service_map.keys()) | {"set_position"}
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用: {', '.join(sorted(valid_actions))}",
            }

        service_data: dict[str, Any] = {"entity_id": entity_id}

        if action == "set_position":
            if position is None:
                return {
                    "success": False,
                    "error": "missing_parameter",
                    "message": "set_position 需要提供 position 參數",
                }
            service_data["position"] = position
            service = "set_valve_position"
        else:
            service = service_map[action]

        await hass.services.async_call(
            "valve", service, service_data=service_data, blocking=True,
        )

        new_state = hass.states.get(entity_id)
        return {
            "success": True,
            "entity_id": entity_id,
            "action": action,
            "state": new_state.state if new_state else "unknown",
            "message": f"閥門 {entity_id} 已執行 {action}",
        }

    except Exception as e:
        _LOGGER.error("Error controlling valve: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制閥門失敗：{str(e)}",
        }


async def control_number(
    hass: HomeAssistant,
    entity_id: str,
    value: float,
) -> dict[str, Any]:
    """Set value of a number entity.

    Args:
        hass: Home Assistant instance
        entity_id: Number entity ID
        value: Value to set (must be within entity min/max range)
    """
    try:
        state = hass.states.get(entity_id)
        if state is None:
            return {
                "success": False,
                "error": "entity_not_found",
                "message": f"找不到 number 實體: {entity_id}",
            }

        domain = entity_id.split(".")[0]
        if domain != "number":
            return {
                "success": False,
                "error": "invalid_entity",
                "message": f"實體不是 number 域: {entity_id}",
            }

        # Validate against min/max
        attrs = state.attributes
        min_val = attrs.get("min")
        max_val = attrs.get("max")
        step = attrs.get("step")

        if min_val is not None and value < min_val:
            return {
                "success": False,
                "error": "out_of_range",
                "message": f"值 {value} 低於最小值 {min_val}",
            }
        if max_val is not None and value > max_val:
            return {
                "success": False,
                "error": "out_of_range",
                "message": f"值 {value} 超過最大值 {max_val}",
            }

        await hass.services.async_call(
            "number",
            "set_value",
            service_data={"entity_id": entity_id, "value": value},
            blocking=True,
        )

        new_state = hass.states.get(entity_id)
        return {
            "success": True,
            "entity_id": entity_id,
            "value": value,
            "state": new_state.state if new_state else "unknown",
            "message": f"Number {entity_id} 已設定為 {value}",
        }

    except Exception as e:
        _LOGGER.error("Error controlling number: %s", e)
        return {
            "success": False,
            "error": "control_failed",
            "message": f"控制 number 失敗：{str(e)}",
        }


async def control_shopping_list(
    hass: HomeAssistant,
    action: str,
    name: str | None = None,
) -> dict[str, Any]:
    """Manage the built-in HA shopping list.

    Args:
        hass: Home Assistant instance
        action: Action (add_item, remove_item, complete_item, incomplete_item,
                complete_all, incomplete_all, clear_completed, sort)
        name: Item name (required for add/remove/complete/incomplete)
    """
    try:
        services = hass.services.async_services()
        if "shopping_list" not in services:
            return {
                "success": False,
                "error": "not_available",
                "message": "購物清單整合未啟用",
            }

        valid_actions = {
            "add_item", "remove_item", "complete_item", "incomplete_item",
            "complete_all", "incomplete_all", "clear_completed", "sort",
        }
        if action not in valid_actions:
            return {
                "success": False,
                "error": "invalid_action",
                "message": f"不支援的動作: {action}。可用: {', '.join(sorted(valid_actions))}",
            }

        # Actions requiring item name
        item_actions = {"add_item", "remove_item", "complete_item", "incomplete_item"}
        if action in item_actions and not name:
            return {
                "success": False,
                "error": "missing_parameter",
                "message": f"{action} 需要提供 name 參數",
            }

        # Map actions to HA services
        service_map = {
            "add_item": "add_item",
            "remove_item": "remove_item",
            "complete_item": "complete_item",
            "incomplete_item": "incomplete_item",
            "complete_all": "complete_all",
            "incomplete_all": "incomplete_all",
            "clear_completed": "clear_completed_items",
            "sort": "sort",
        }

        service_data: dict[str, Any] = {}
        if name:
            service_data["name"] = name

        await hass.services.async_call(
            "shopping_list",
            service_map[action],
            service_data=service_data,
            blocking=True,
        )

        return {
            "success": True,
            "action": action,
            "name": name,
            "message": f"購物清單已執行 {action}" + (f"：{name}" if name else ""),
        }

    except Exception as e:
        _LOGGER.error("Error managing shopping list: %s", e)
        return {
            "success": False,
            "error": "shopping_list_failed",
            "message": f"購物清單操作失敗：{str(e)}",
        }
