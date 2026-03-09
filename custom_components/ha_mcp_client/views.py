"""REST API views for HA MCP Client chat panel."""

import logging
import uuid
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _get_recorder(hass: HomeAssistant):
    """Get the first available recorder from any entry."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "recorder" in entry_data:
            return entry_data["recorder"]
    return None


def _get_user_id(request: web.Request) -> str | None:
    """Extract user_id from the authenticated request."""
    user = request.get("hass_user")
    if user:
        return user.id
    return None


class ConversationsListView(HomeAssistantView):
    """View to list or create conversations."""

    url = f"/api/{DOMAIN}/conversations"
    name = f"api:{DOMAIN}:conversations"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """List all conversations for the current user."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        conversations = await recorder.list_conversations(user_id)
        return self.json(conversations)

    async def post(self, request: web.Request) -> web.Response:
        """Create a new conversation."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            body = {}

        title = body.get("title", "新對話")
        conv_id = str(uuid.uuid4())

        result = await recorder.create_conversation(
            conversation_id=conv_id,
            user_id=user_id,
            title=title,
        )
        if not result:
            return self.json_message("Failed to create conversation", status_code=500)

        return self.json(result, status_code=201)


class ConversationDetailView(HomeAssistantView):
    """View to update or delete a single conversation."""

    url = f"/api/{DOMAIN}/conversations/{{conversation_id}}"
    name = f"api:{DOMAIN}:conversation_detail"
    requires_auth = True

    async def patch(self, request: web.Request, conversation_id: str) -> web.Response:
        """Update conversation title or archive it."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        title = body.get("title")
        is_archived = body.get("is_archived")

        ok = await recorder.update_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            title=title,
            is_archived=is_archived,
        )
        if not ok:
            return self.json_message("Conversation not found", status_code=404)
        return self.json({"success": True})

    async def delete(self, request: web.Request, conversation_id: str) -> web.Response:
        """Soft-delete a conversation."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        ok = await recorder.update_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            is_archived=True,
        )
        if not ok:
            return self.json_message("Conversation not found", status_code=404)
        return self.json({"success": True})


class ConversationMessagesView(HomeAssistantView):
    """View to get or send messages in a conversation."""

    url = f"/api/{DOMAIN}/conversations/{{conversation_id}}/messages"
    name = f"api:{DOMAIN}:conversation_messages"
    requires_auth = True

    async def get(self, request: web.Request, conversation_id: str) -> web.Response:
        """Get messages for a conversation."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        # Verify ownership
        conv = await recorder.get_conversation(conversation_id, user_id)
        if not conv:
            return self.json_message("Conversation not found", status_code=404)

        limit = int(request.query.get("limit", "50"))
        offset = int(request.query.get("offset", "0"))

        messages = await recorder.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit,
            offset=offset,
        )
        return self.json(messages)

    async def post(self, request: web.Request, conversation_id: str) -> web.Response:
        """Send a message and get AI response."""
        hass = request.app["hass"]
        user_id = _get_user_id(request)
        if not user_id:
            return self.json_message("Unauthorized", status_code=401)

        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        # Verify ownership
        conv = await recorder.get_conversation(conversation_id, user_id)
        if not conv:
            return self.json_message("Conversation not found", status_code=404)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        message = body.get("message", "").strip()
        if not message:
            return self.json_message("Message is required", status_code=400)

        # Use HA conversation API to process the message
        try:
            result = await hass.services.async_call(
                "conversation",
                "process",
                {
                    "text": message,
                    "agent_id": _get_agent_id(hass),
                    "conversation_id": conversation_id,
                },
                blocking=True,
                return_response=True,
            )

            ai_response = ""
            if result and "response" in result:
                speech = result["response"].get("speech", {})
                if isinstance(speech, dict):
                    ai_response = speech.get("plain", {}).get("speech", "")
                elif isinstance(speech, str):
                    ai_response = speech

            # Update conversation title if it's the first message
            if conv.get("title") == "新對話" and message:
                new_title = message[:50]
                await recorder.update_conversation(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    title=new_title,
                )

            # Touch updated_at
            await recorder.touch_conversation(conversation_id)

            # Update input_text entities
            await _sync_input_text(hass, message, ai_response)

            return self.json({
                "user_message": message,
                "ai_response": ai_response,
                "conversation_id": conversation_id,
            })

        except Exception as e:
            _LOGGER.error("Error processing message: %s", e, exc_info=True)
            return self.json_message(
                "An internal error occurred while processing the message.",
                status_code=500,
            )


def _get_skills_loader(hass: HomeAssistant):
    """Get the first available SkillsLoader from any entry."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "skills_loader" in entry_data:
            return entry_data["skills_loader"]
    return None


def _get_memory_store(hass: HomeAssistant):
    """Get the first available MemoryStore from any entry."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "memory_store" in entry_data:
            return entry_data["memory_store"]
    return None


class MemoryView(HomeAssistantView):
    """View to read all memory sections at once."""

    url = f"/api/{DOMAIN}/memory"
    name = f"api:{DOMAIN}:memory"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get all memory sections."""
        hass = request.app["hass"]
        store = _get_memory_store(hass)
        if not store:
            return self.json_message("Memory store not available", status_code=503)

        memory = await store.read_long_term()
        soul = await store.read_soul()
        user = await store.read_user()
        history = await store.read_history()
        stats = await store.get_stats()

        return self.json({
            "memory": memory,
            "soul": soul,
            "user": user,
            "history": history,
            "stats": stats,
        })


class MemorySectionView(HomeAssistantView):
    """View to read or update a specific memory section."""

    url = f"/api/{DOMAIN}/memory/{{section}}"
    name = f"api:{DOMAIN}:memory_section"
    requires_auth = True

    async def get(self, request: web.Request, section: str) -> web.Response:
        """Get a specific memory section."""
        hass = request.app["hass"]
        store = _get_memory_store(hass)
        if not store:
            return self.json_message("Memory store not available", status_code=503)

        if section == "memory":
            content = await store.read_long_term()
        elif section == "soul":
            content = await store.read_soul()
        elif section == "user":
            content = await store.read_user()
        elif section == "history":
            content = await store.read_history()
        elif section == "stats":
            stats = await store.get_stats()
            return self.json(stats)
        else:
            return self.json_message(
                f"Unknown section: {section}. Use: memory, soul, user, history, stats",
                status_code=400,
            )

        return self.json({"section": section, "content": content})

    async def put(self, request: web.Request, section: str) -> web.Response:
        """Update a specific memory section."""
        hass = request.app["hass"]
        store = _get_memory_store(hass)
        if not store:
            return self.json_message("Memory store not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        content = body.get("content", "")

        if section == "memory":
            await store.write_long_term(content)
        elif section == "soul":
            await store.write_soul(content)
        elif section == "user":
            await store.write_user(content)
        else:
            return self.json_message(
                f"Cannot write to section: {section}. Writable: memory, soul, user",
                status_code=400,
            )

        return self.json({"success": True, "section": section, "length": len(content)})


class MemorySearchView(HomeAssistantView):
    """View to search conversation history."""

    url = f"/api/{DOMAIN}/memory/search"
    name = f"api:{DOMAIN}:memory_search"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Search HISTORY.md with a regex pattern."""
        hass = request.app["hass"]
        store = _get_memory_store(hass)
        if not store:
            return self.json_message("Memory store not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        pattern = body.get("pattern", "")
        if not pattern:
            return self.json_message("pattern is required", status_code=400)

        # Validate regex pattern to prevent ReDoS
        import re as _re
        try:
            _re.compile(pattern)
        except _re.error:
            return self.json_message("Invalid regex pattern", status_code=400)

        # Limit pattern length to prevent excessive backtracking
        if len(pattern) > 200:
            return self.json_message(
                "Pattern too long (max 200 characters)", status_code=400
            )

        limit = body.get("limit", 20)
        results = await store.search_history(pattern)
        truncated = len(results) > limit
        results = results[:limit]

        return self.json({
            "pattern": pattern,
            "matches": results,
            "count": len(results),
            "truncated": truncated,
        })


class MemoryConsolidateView(HomeAssistantView):
    """View to trigger AI-driven memory consolidation."""

    url = f"/api/{DOMAIN}/memory/consolidate"
    name = f"api:{DOMAIN}:memory_consolidate"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Trigger memory consolidation using AI to summarize recent conversations."""
        hass = request.app["hass"]
        store = _get_memory_store(hass)
        if not store:
            return self.json_message("Memory store not available", status_code=503)

        # Get recorder and config
        recorder = _get_recorder(hass)
        if not recorder:
            return self.json_message("Recorder not available", status_code=503)

        from .const import CONF_MEMORY_WINDOW, DEFAULT_MEMORY_WINDOW

        # Find AI service from conversation entity
        ai_service = None
        memory_window = DEFAULT_MEMORY_WINDOW

        for entry_data in hass.data.get(DOMAIN, {}).values():
            if isinstance(entry_data, dict):
                overrides = entry_data.get("runtime_settings", {})
                memory_window = overrides.get(CONF_MEMORY_WINDOW, memory_window)

        entity_comp = hass.data.get("entity_components", {}).get("conversation")
        if entity_comp:
            for entity in entity_comp.entities:
                if hasattr(entity, "_ai_service") and entity._ai_service:
                    ai_service = entity._ai_service
                    break

        if not ai_service:
            return self.json_message(
                "AI service not available for consolidation", status_code=503
            )

        # Gather recent messages from the most recent conversation
        user_id = _get_user_id(request) or ""
        conversations = await recorder.list_conversations(user_id)
        if not conversations:
            return self.json({"info": "No conversations to consolidate"})

        recent = conversations[0]
        conv_id = recent.get("id") if isinstance(recent, dict) else getattr(recent, "id", None)
        if not conv_id:
            return self.json({"info": "No conversation ID found"})

        msg_records = await recorder.get_conversation_messages(
            conv_id, limit=memory_window
        )
        messages = []
        for m in msg_records:
            role = m.get("role", "user") if isinstance(m, dict) else getattr(m, "role", "user")
            content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
            messages.append({"role": role, "content": content or ""})

        if not messages:
            return self.json({"info": "No recent messages to consolidate"})

        success = await store.consolidate(
            conversation_id="manual_consolidation",
            messages=messages,
            ai_service=ai_service,
            memory_window=memory_window,
        )

        if success:
            stats = await store.get_stats()
            return self.json({"success": True, "stats": stats})
        return self.json_message("Consolidation failed", status_code=500)


class SkillsListView(HomeAssistantView):
    """View to list or create skills."""

    url = f"/api/{DOMAIN}/skills"
    name = f"api:{DOMAIN}:skills"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """List all skills."""
        hass = request.app["hass"]
        loader = _get_skills_loader(hass)
        if not loader:
            return self.json_message("Skills loader not available", status_code=503)

        skills = await loader.list_skills()
        stats = await loader.get_stats()
        return self.json({"skills": skills, "stats": stats})

    async def post(self, request: web.Request) -> web.Response:
        """Create a new skill."""
        hass = request.app["hass"]
        loader = _get_skills_loader(hass)
        if not loader:
            return self.json_message("Skills loader not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        name = body.get("name", "").strip()
        description = body.get("description", "").strip()
        content = body.get("content", "")
        always = body.get("always", False)

        if not name or not description:
            return self.json_message(
                "name and description are required", status_code=400
            )

        result = await loader.create_skill(
            name=name,
            description=description,
            content=content,
            always=always,
        )

        if "error" in result:
            return self.json_message(result["error"], status_code=400)
        return self.json(result, status_code=201)


class SkillDetailView(HomeAssistantView):
    """View to read, update, or delete a single skill."""

    url = f"/api/{DOMAIN}/skills/{{skill_name}}"
    name = f"api:{DOMAIN}:skill_detail"
    requires_auth = True

    async def get(self, request: web.Request, skill_name: str) -> web.Response:
        """Get a skill's full content."""
        hass = request.app["hass"]
        loader = _get_skills_loader(hass)
        if not loader:
            return self.json_message("Skills loader not available", status_code=503)

        content = await loader.read_skill(skill_name)
        if content is None:
            return self.json_message(
                f"Skill '{skill_name}' not found", status_code=404
            )

        meta = await loader.get_skill_metadata(skill_name)
        return self.json({
            "name": skill_name,
            "content": content,
            "metadata": meta,
        })

    async def put(self, request: web.Request, skill_name: str) -> web.Response:
        """Update a skill."""
        hass = request.app["hass"]
        loader = _get_skills_loader(hass)
        if not loader:
            return self.json_message("Skills loader not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        result = await loader.update_skill(
            name=skill_name,
            content=body.get("content"),
            description=body.get("description"),
            always=body.get("always"),
        )

        if "error" in result:
            return self.json_message(result["error"], status_code=404)
        return self.json(result)

    async def delete(self, request: web.Request, skill_name: str) -> web.Response:
        """Delete a skill."""
        hass = request.app["hass"]
        loader = _get_skills_loader(hass)
        if not loader:
            return self.json_message("Skills loader not available", status_code=503)

        result = await loader.delete_skill(skill_name)
        if "error" in result:
            return self.json_message(result["error"], status_code=404)
        return self.json(result)


def _get_cron_service(hass: HomeAssistant):
    """Get the first available CronService from any entry."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if isinstance(entry_data, dict) and "cron_service" in entry_data:
            return entry_data["cron_service"]
    return None


class CronJobsListView(HomeAssistantView):
    """View to list or create cron jobs."""

    url = f"/api/{DOMAIN}/cron/jobs"
    name = f"api:{DOMAIN}:cron_jobs"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """List all cron jobs."""
        hass = request.app["hass"]
        svc = _get_cron_service(hass)
        if not svc:
            return self.json_message("Cron service not available", status_code=503)

        jobs = await svc.list_jobs()
        stats = await svc.get_stats()
        return self.json({
            "jobs": [j.to_dict() for j in jobs],
            "stats": stats,
        })

    async def post(self, request: web.Request) -> web.Response:
        """Create a new cron job."""
        hass = request.app["hass"]
        svc = _get_cron_service(hass)
        if not svc:
            return self.json_message("Cron service not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        name = body.get("name", "").strip()
        schedule = body.get("schedule")
        if not name or not schedule:
            return self.json_message(
                "name and schedule are required", status_code=400
            )

        try:
            job = await svc.add_job(
                name=name,
                schedule=schedule,
                payload=body.get("payload"),
                enabled=body.get("enabled", True),
                delete_after_run=body.get("delete_after_run", False),
            )
            return self.json(job.to_dict(), status_code=201)
        except Exception as e:
            return self.json_message(str(e), status_code=400)


class CronJobDetailView(HomeAssistantView):
    """View to get, update, or delete a single cron job."""

    url = f"/api/{DOMAIN}/cron/jobs/{{job_id}}"
    name = f"api:{DOMAIN}:cron_job_detail"
    requires_auth = True

    async def get(self, request: web.Request, job_id: str) -> web.Response:
        """Get a cron job by ID."""
        hass = request.app["hass"]
        svc = _get_cron_service(hass)
        if not svc:
            return self.json_message("Cron service not available", status_code=503)

        job = await svc.get_job(job_id)
        if not job:
            return self.json_message(f"Job '{job_id}' not found", status_code=404)
        return self.json(job.to_dict())

    async def patch(self, request: web.Request, job_id: str) -> web.Response:
        """Update a cron job."""
        hass = request.app["hass"]
        svc = _get_cron_service(hass)
        if not svc:
            return self.json_message("Cron service not available", status_code=503)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        job = await svc.update_job(job_id, body)
        if not job:
            return self.json_message(f"Job '{job_id}' not found", status_code=404)
        return self.json(job.to_dict())

    async def delete(self, request: web.Request, job_id: str) -> web.Response:
        """Delete a cron job."""
        hass = request.app["hass"]
        svc = _get_cron_service(hass)
        if not svc:
            return self.json_message("Cron service not available", status_code=503)

        ok = await svc.remove_job(job_id)
        if not ok:
            return self.json_message(f"Job '{job_id}' not found", status_code=404)
        return self.json({"success": True, "removed": job_id})


class CronJobTriggerView(HomeAssistantView):
    """View to manually trigger a cron job."""

    url = f"/api/{DOMAIN}/cron/jobs/{{job_id}}/trigger"
    name = f"api:{DOMAIN}:cron_job_trigger"
    requires_auth = True

    async def post(self, request: web.Request, job_id: str) -> web.Response:
        """Trigger a cron job immediately."""
        hass = request.app["hass"]
        svc = _get_cron_service(hass)
        if not svc:
            return self.json_message("Cron service not available", status_code=503)

        ok = await svc.trigger_job(job_id)
        if not ok:
            return self.json_message(f"Job '{job_id}' not found", status_code=404)
        return self.json({"success": True, "triggered": job_id})


class CronToAutomationView(HomeAssistantView):
    """View to convert a cron job to a native HA automation."""

    url = f"/api/{DOMAIN}/cron/jobs/{{job_id}}/to_automation"
    name = f"api:{DOMAIN}:cron_to_automation"
    requires_auth = True

    async def post(self, request: web.Request, job_id: str) -> web.Response:
        """Convert a cron job to an HA automation."""
        hass = request.app["hass"]
        svc = _get_cron_service(hass)
        if not svc:
            return self.json_message("Cron service not available", status_code=503)

        job = await svc.get_job(job_id)
        if not job:
            return self.json_message(f"Job '{job_id}' not found", status_code=404)

        try:
            body = await request.json()
        except Exception:
            body = {}

        alias = body.get("alias")
        keep_cron_job = body.get("keep_cron_job", True)

        from .mcp.tools.helpers import cron_to_automation
        result = await cron_to_automation(
            hass,
            cron_job=job,
            alias=alias,
            keep_cron_job=keep_cron_job,
        )

        if not result.get("success"):
            return self.json(result, status_code=400)

        # Remove the original cron job if keep_cron_job is False
        if not keep_cron_job:
            await svc.remove_job(job_id)

        return self.json(result, status_code=201)


class CronBlueprintsListView(HomeAssistantView):
    """View to list available cron blueprints."""

    url = f"/api/{DOMAIN}/blueprints"
    name = f"api:{DOMAIN}:cron_blueprints"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """List built-in cron blueprints."""
        from pathlib import Path

        bp_dir = Path(__file__).parent / "blueprints" / "automation"
        if not bp_dir.exists():
            return self.json({"blueprints": [], "count": 0})

        import yaml

        # Custom loader that handles HA-specific !input tags
        class _BPLoader(yaml.SafeLoader):
            pass

        _BPLoader.add_constructor(
            "!input",
            lambda loader, node: f"__input__{loader.construct_scalar(node)}",
        )

        blueprints = []
        for f in sorted(bp_dir.glob("*.yaml")):
            try:
                content = f.read_text(encoding="utf-8")
                data = yaml.load(content, Loader=_BPLoader)  # noqa: S506
                bp_meta = data.get("blueprint", {})
                blueprints.append({
                    "filename": f.name,
                    "name": bp_meta.get("name", f.stem),
                    "description": bp_meta.get("description", ""),
                    "inputs": list(bp_meta.get("input", {}).keys()),
                })
            except Exception:
                pass

        return self.json({"blueprints": blueprints, "count": len(blueprints)})


class CronBlueprintsInstallView(HomeAssistantView):
    """View to install cron blueprints to HA."""

    url = f"/api/{DOMAIN}/blueprints/install"
    name = f"api:{DOMAIN}:cron_blueprints_install"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Install built-in cron blueprints to HA's blueprint directory."""
        from pathlib import Path
        import shutil

        hass = request.app["hass"]
        src_dir = Path(__file__).parent / "blueprints" / "automation"
        if not src_dir.exists():
            return self.json_message("No built-in blueprints found", status_code=404)

        try:
            body = await request.json()
        except Exception:
            body = {}

        blueprint_id = body.get("blueprint_id")

        # Validate specific blueprint exists
        if blueprint_id:
            src_file = src_dir / blueprint_id
            if not src_file.is_file():
                return self.json_message(
                    f"Blueprint '{blueprint_id}' not found", status_code=404
                )

        dest_dir = Path(hass.config.path("blueprints", "automation", "ha_mcp_client"))
        installed = []
        errors = []

        def _do_install():
            dest_dir.mkdir(parents=True, exist_ok=True)
            if blueprint_id:
                files = [src_dir / blueprint_id]
            else:
                files = sorted(src_dir.glob("*.yaml"))
            for f in files:
                try:
                    dest = dest_dir / f.name
                    shutil.copy2(str(f), str(dest))
                    installed.append(f.name)
                except Exception as e:
                    errors.append({"file": f.name, "error": str(e)})

        await hass.async_add_executor_job(_do_install)

        return self.json({
            "success": len(errors) == 0,
            "installed": installed,
            "count": len(installed),
            "errors": errors,
        })


def _get_config_entry(hass: HomeAssistant):
    """Get the first config entry and its data dict."""
    for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
        if isinstance(entry_data, dict):
            # Find the actual ConfigEntry object
            entry = hass.config_entries.async_get_entry(entry_id)
            return entry, entry_data
    return None, None


class SettingsView(HomeAssistantView):
    """View to read and update AI settings at runtime."""

    url = f"/api/{DOMAIN}/settings"
    name = f"api:{DOMAIN}:settings"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get current AI settings."""
        from .const import (
            CONF_AI_SERVICE, CONF_MODEL, CONF_SYSTEM_PROMPT,
            CONF_MAX_TOOL_CALLS, CONF_TEMPERATURE, CONF_MAX_TOKENS,
            CONF_MEMORY_WINDOW, CONF_ENABLE_CONVERSATION_HISTORY,
            CONF_HISTORY_RETENTION_DAYS,
            DEFAULT_SYSTEM_PROMPT, DEFAULT_MAX_TOOL_CALLS,
            DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS, DEFAULT_MEMORY_WINDOW,
            DEFAULT_HISTORY_RETENTION_DAYS,
        )

        hass = request.app["hass"]
        entry, data = _get_config_entry(hass)
        if not entry:
            return self.json_message("No config entry found", status_code=503)

        config = entry.data
        # Runtime overrides stored in data dict take priority
        overrides = data.get("runtime_settings", {})

        settings = {
            "ai_service": config.get(CONF_AI_SERVICE, ""),
            "model": overrides.get("model", config.get(CONF_MODEL, "")),
            "temperature": overrides.get(
                "temperature",
                config.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
            ),
            "max_tokens": overrides.get(
                "max_tokens",
                config.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
            ),
            "system_prompt": overrides.get(
                "system_prompt",
                config.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
            ),
            "max_tool_calls": overrides.get(
                "max_tool_calls",
                config.get(CONF_MAX_TOOL_CALLS, DEFAULT_MAX_TOOL_CALLS),
            ),
            "memory_window": overrides.get(
                "memory_window",
                config.get(CONF_MEMORY_WINDOW, DEFAULT_MEMORY_WINDOW),
            ),
            "enable_conversation_history": config.get(
                CONF_ENABLE_CONVERSATION_HISTORY, True
            ),
            "history_retention_days": config.get(
                CONF_HISTORY_RETENTION_DAYS, DEFAULT_HISTORY_RETENTION_DAYS
            ),
        }
        return self.json(settings)

    async def patch(self, request: web.Request) -> web.Response:
        """Update AI settings at runtime (no restart needed)."""
        hass = request.app["hass"]
        entry, data = _get_config_entry(hass)
        if not entry:
            return self.json_message("No config entry found", status_code=503)

        try:
            body = await request.json()
        except Exception:
            return self.json_message("Invalid JSON", status_code=400)

        # Only allow safe runtime-mutable fields
        allowed = {
            "model", "temperature", "max_tokens",
            "system_prompt", "max_tool_calls", "memory_window",
        }
        updates = {k: v for k, v in body.items() if k in allowed}
        if not updates:
            return self.json_message(
                f"No valid fields. Allowed: {', '.join(sorted(allowed))}",
                status_code=400,
            )

        # Validate ranges
        if "temperature" in updates:
            t = updates["temperature"]
            if not isinstance(t, (int, float)) or t < 0 or t > 2:
                return self.json_message(
                    "temperature must be 0.0-2.0", status_code=400
                )
        if "max_tokens" in updates:
            mt = updates["max_tokens"]
            if not isinstance(mt, int) or mt < 100 or mt > 128000:
                return self.json_message(
                    "max_tokens must be 100-128000", status_code=400
                )
        if "max_tool_calls" in updates:
            mc = updates["max_tool_calls"]
            if not isinstance(mc, int) or mc < 1 or mc > 50:
                return self.json_message(
                    "max_tool_calls must be 1-50", status_code=400
                )
        if "memory_window" in updates:
            mw = updates["memory_window"]
            if not isinstance(mw, int) or mw < 10 or mw > 500:
                return self.json_message(
                    "memory_window must be 10-500", status_code=400
                )

        # Store in runtime_settings dict (in-memory, survives until restart)
        if "runtime_settings" not in data:
            data["runtime_settings"] = {}
        data["runtime_settings"].update(updates)

        # If model changed, re-init the AI service on the conversation entity
        if "model" in updates:
            for state in hass.states.async_all("conversation"):
                if DOMAIN in state.entity_id:
                    entity = hass.data.get("conversation", {}).get(
                        state.entity_id
                    )
                    if hasattr(entity, "_setup_ai_service"):
                        entity._setup_ai_service()
                    break

        _LOGGER.info("AI settings updated: %s", list(updates.keys()))
        return self.json({"success": True, "updated": updates})


def _get_agent_id(hass: HomeAssistant) -> str | None:
    """Get the HA MCP Client conversation agent ID."""
    for state in hass.states.async_all("conversation"):
        if DOMAIN in state.entity_id:
            return state.entity_id
    return None


async def _sync_input_text(
    hass: HomeAssistant, user_message: str, ai_response: str
) -> None:
    """Sync latest messages to input_text entities."""
    from .const import INPUT_TEXT_USER, INPUT_TEXT_AI

    try:
        # Set state directly — the entities may not exist via input_text component,
        # but we can set state for any entity_id
        hass.states.async_set(
            INPUT_TEXT_USER,
            user_message[:255],
            {"friendly_name": "MCP 使用者輸入", "icon": "mdi:account-voice"},
        )
        hass.states.async_set(
            INPUT_TEXT_AI,
            ai_response[:255],
            {"friendly_name": "MCP AI 回覆", "icon": "mdi:robot"},
        )
    except Exception as e:
        _LOGGER.warning("Failed to sync input_text: %s", e)
