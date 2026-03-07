"""Helper functions for MCP tools."""

import logging
from typing import Any
from datetime import datetime, timedelta, timezone

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

        # Use the config websocket API to create automation
        from homeassistant.components.automation.config import (
            async_validate_config_item,
        )

        # Validate config first
        try:
            await async_validate_config_item(hass, config)
        except Exception as e:
            return {
                "success": False,
                "error": "validation_failed",
                "message": f"設定驗證失敗：{str(e)}",
            }

        # Create via the config websocket API
        from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
        from homeassistant.components.config import automation as config_automation

        if hasattr(config_automation, "async_create_item"):
            await config_automation.async_create_item(hass, config)
        else:
            return {
                "success": False,
                "error": "unsupported",
                "message": "Automation creation API not available in this HA version",
            }

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
    try:
        # Generate script_id from name
        script_id = name.lower().replace(" ", "_").replace("-", "_")

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

        # Create via the config websocket API
        from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
        from homeassistant.components.config import script as config_script

        if hasattr(config_script, "async_create_item"):
            await config_script.async_create_item(hass, {script_id: config})
        else:
            return {
                "success": False,
                "error": "unsupported",
                "message": "Script creation API not available in this HA version",
            }

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
    """Create a new scene in Home Assistant.

    Args:
        hass: Home Assistant instance
        name: Scene name
        entities: Dict of entity_id to state. Example: {"light.living_room": {"state": "on", "brightness": 255}}
        icon: Optional MDI icon
    """
    try:
        import re

        # Generate scene_id - must be valid slug (ASCII only)
        scene_id = name.lower().replace(" ", "_").replace("-", "_")
        # Keep only ASCII letters, numbers, and underscores
        scene_id = re.sub(r'[^a-z0-9_]', '', scene_id)
        # If empty after removing non-ASCII, generate a unique ID
        if not scene_id:
            import uuid
            scene_id = f"scene_{str(uuid.uuid4()).replace('-', '')[:8]}"

        # Use HA's scene.create service to create a dynamic scene
        # This creates a scene that shows up in the UI immediately
        service_data = {
            "scene_id": scene_id,
            "entities": entities,
        }

        # If we have snapshot entities, add them
        # For now, we use the entities dict directly

        await hass.services.async_call(
            "scene",
            "create",
            service_data,
            blocking=True,
        )

        entity_id = f"scene.{scene_id}"

        return {
            "success": True,
            "scene_id": scene_id,
            "entity_id": entity_id,
            "message": f"情境「{name}」已建立，entity_id: {entity_id}",
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
) -> dict[str, Any]:
    """Create a calendar event.

    Args:
        hass: Home Assistant instance
        calendar_entity_id: Calendar entity ID (e.g., 'calendar.home')
        summary: Event title/summary
        start: Start datetime in ISO format (e.g., '2024-01-15T10:00:00')
        end: End datetime in ISO format (e.g., '2024-01-15T11:00:00')
        description: Optional event description
        location: Optional event location
    """
    try:
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
