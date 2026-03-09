"""CRUD operations for HA Helper entities via storage collection API."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

HELPER_DOMAINS = frozenset({
    "input_boolean",
    "input_number",
    "input_select",
    "input_text",
    "input_datetime",
    "input_button",
    "timer",
    "counter",
})

# Valid fields for each helper type (create / update)
TYPE_FIELDS: dict[str, set[str]] = {
    "input_boolean": {"name", "icon", "initial"},
    "input_number": {
        "name", "icon", "initial", "min", "max", "step",
        "mode", "unit_of_measurement",
    },
    "input_select": {"name", "icon", "initial", "options"},
    "input_text": {"name", "icon", "initial", "min", "max", "pattern", "mode"},
    "input_datetime": {"name", "icon", "initial", "has_date", "has_time"},
    "input_button": {"name", "icon"},
    "timer": {"name", "icon", "duration", "restore"},
    "counter": {
        "name", "icon", "initial", "step", "minimum", "maximum", "restore",
    },
}

# Required fields for create
REQUIRED_FIELDS: dict[str, set[str]] = {
    "input_boolean": {"name"},
    "input_number": {"name", "min", "max"},
    "input_select": {"name", "options"},
    "input_text": {"name"},
    "input_datetime": {"name"},
    "input_button": {"name"},
    "timer": {"name"},
    "counter": {"name"},
}

# Storage collection key patterns to try
_COLLECTION_KEYS = [
    "{domain}_storage_collection",        # Most helper domains
    "{domain}",                           # Some domains store dict with collection key
]


class HelpersCrud:
    """CRUD operations for HA Helper entities."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _get_collection(self, domain: str):
        """Get storage collection for a helper domain.

        The storage collection is held by DictStorageCollectionWebsocket
        instances which register websocket commands like '{domain}/create'.
        We extract the collection by finding the handler and accessing its
        __self__.storage_collection attribute.
        """
        # Approach: find the websocket handler for '{domain}/create'
        # and extract storage_collection from the handler's bound instance.
        ws_handlers = self.hass.data.get("websocket_api", {})
        create_cmd = f"{domain}/create"
        handler_info = ws_handlers.get(create_cmd)

        if handler_info is not None:
            handler_func = handler_info[0]
            # The handler is wrapped: require_admin(async_response(ws_create_item))
            # We need to unwrap to get the bound method's __self__
            coll = self._extract_collection_from_handler(handler_func)
            if coll is not None:
                return coll

        _LOGGER.warning(
            "Storage collection not found for domain '%s'. "
            "Ensure the %s integration is loaded.",
            domain, domain,
        )
        return None

    @staticmethod
    def _extract_collection_from_handler(handler):
        """Extract storage_collection from a wrapped websocket handler."""
        # Unwrap decorators to find the DictStorageCollectionWebsocket method
        func = handler
        for _ in range(10):  # max unwrap depth
            # Check if this is a bound method with storage_collection
            if hasattr(func, '__self__') and hasattr(func.__self__, 'storage_collection'):
                return func.__self__.storage_collection
            # Check closure variables
            if hasattr(func, '__wrapped__'):
                func = func.__wrapped__
                continue
            if hasattr(func, '__closure__') and func.__closure__:
                for cell in func.__closure__:
                    try:
                        cell_val = cell.cell_contents
                    except ValueError:
                        continue
                    # Check if the cell contains the handler or collection
                    if hasattr(cell_val, '__self__') and hasattr(cell_val.__self__, 'storage_collection'):
                        return cell_val.__self__.storage_collection
                    if callable(cell_val) and cell_val is not func:
                        result = HelpersCrud._extract_collection_from_handler(cell_val)
                        if result is not None:
                            return result
                break
            break
        return None

    def _get_item_id_from_entity(self, entity_id: str) -> str | None:
        """Get storage collection item ID from entity_id via entity registry."""
        registry = er.async_get(self.hass)
        entry = registry.async_get(entity_id)
        if entry is None:
            return None
        return entry.unique_id

    async def list_helpers(
        self, type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all helper entities, optionally filtered by type."""
        domains = (
            [type_filter] if type_filter and type_filter in HELPER_DOMAINS
            else sorted(HELPER_DOMAINS)
        )

        result: list[dict[str, Any]] = []
        for domain in domains:
            states = self.hass.states.async_all(domain)
            for state in states:
                attrs = dict(state.attributes)
                result.append({
                    "entity_id": state.entity_id,
                    "type": domain,
                    "name": attrs.pop("friendly_name", state.entity_id),
                    "state": state.state,
                    "icon": attrs.pop("icon", None),
                    "attributes": attrs,
                })
        return result

    async def get_helper(self, entity_id: str) -> dict[str, Any]:
        """Get a single helper's details."""
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        if domain not in HELPER_DOMAINS:
            return {
                "error": f"'{domain}' is not a helper domain. "
                         f"Valid: {', '.join(sorted(HELPER_DOMAINS))}",
            }

        state = self.hass.states.get(entity_id)
        if state is None:
            return {"error": f"Entity '{entity_id}' not found"}

        attrs = dict(state.attributes)
        return {
            "entity_id": state.entity_id,
            "type": domain,
            "name": attrs.pop("friendly_name", state.entity_id),
            "state": state.state,
            "icon": attrs.pop("icon", None),
            "attributes": attrs,
        }

    async def create_helper(
        self, helper_type: str, **params: Any,
    ) -> dict[str, Any]:
        """Create a new helper entity."""
        if helper_type not in HELPER_DOMAINS:
            return {
                "error": f"Invalid helper type '{helper_type}'. "
                         f"Valid: {', '.join(sorted(HELPER_DOMAINS))}",
            }

        # Validate required fields
        required = REQUIRED_FIELDS[helper_type]
        missing = required - set(params.keys())
        if missing:
            return {
                "error": f"Missing required fields for {helper_type}: "
                         f"{', '.join(sorted(missing))}",
            }

        # Filter to only valid fields for this type
        valid = TYPE_FIELDS[helper_type]
        filtered = {k: v for k, v in params.items() if k in valid}

        # Get storage collection
        collection = self._get_collection(helper_type)
        if collection is None:
            return {
                "error": f"Storage collection for '{helper_type}' not available. "
                         f"Is the {helper_type} integration loaded?",
            }

        try:
            item = await collection.async_create_item(filtered)
        except ValueError as exc:
            return {"error": f"Validation error: {exc}"}
        except Exception as exc:
            _LOGGER.error("Failed to create %s: %s", helper_type, exc)
            return {"error": f"Failed to create {helper_type}: {exc}"}

        # Build expected entity_id
        name = filtered.get("name", "")
        slug = name.lower().replace(" ", "_").replace("-", "_")
        entity_id = f"{helper_type}.{slug}"

        # Try to get the actual entity_id from the item
        item_id = getattr(item, "id", None) or (
            item.get("id") if isinstance(item, dict) else None
        )

        return {
            "success": True,
            "entity_id": entity_id,
            "type": helper_type,
            "name": name,
            "id": item_id,
        }

    async def update_helper(
        self, entity_id: str, **params: Any,
    ) -> dict[str, Any]:
        """Update an existing helper entity."""
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        if domain not in HELPER_DOMAINS:
            return {
                "error": f"'{domain}' is not a helper domain. "
                         f"Valid: {', '.join(sorted(HELPER_DOMAINS))}",
            }

        # Get item ID from entity registry
        item_id = self._get_item_id_from_entity(entity_id)
        if item_id is None:
            return {"error": f"Entity '{entity_id}' not found in registry"}

        # Filter to valid fields for this type
        valid = TYPE_FIELDS[domain]
        filtered = {k: v for k, v in params.items() if k in valid}

        if not filtered:
            return {"error": "No valid fields to update"}

        # Get collection and update
        collection = self._get_collection(domain)
        if collection is None:
            return {
                "error": f"Storage collection for '{domain}' not available.",
            }

        try:
            await collection.async_update_item(item_id, filtered)
        except KeyError:
            return {"error": f"Item '{item_id}' not found in collection"}
        except ValueError as exc:
            return {"error": f"Validation error: {exc}"}
        except Exception as exc:
            _LOGGER.error("Failed to update %s: %s", entity_id, exc)
            return {"error": f"Failed to update {entity_id}: {exc}"}

        return {
            "success": True,
            "entity_id": entity_id,
            "type": domain,
            "updated_fields": list(filtered.keys()),
        }

    async def delete_helper(self, entity_id: str) -> dict[str, Any]:
        """Delete a helper entity."""
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        if domain not in HELPER_DOMAINS:
            return {
                "error": f"'{domain}' is not a helper domain. "
                         f"Valid: {', '.join(sorted(HELPER_DOMAINS))}",
            }

        # Get item ID from entity registry
        item_id = self._get_item_id_from_entity(entity_id)
        if item_id is None:
            return {"error": f"Entity '{entity_id}' not found in registry"}

        # Get collection and delete
        collection = self._get_collection(domain)
        if collection is None:
            return {
                "error": f"Storage collection for '{domain}' not available.",
            }

        try:
            await collection.async_delete_item(item_id)
        except KeyError:
            return {"error": f"Item '{item_id}' not found in collection"}
        except Exception as exc:
            _LOGGER.error("Failed to delete %s: %s", entity_id, exc)
            return {"error": f"Failed to delete {entity_id}: {exc}"}

        return {
            "success": True,
            "deleted": entity_id,
        }
