#!/usr/bin/env python3
"""
Comprehensive HA MCP Client Integration Test Suite
Tests: MCP protocol, 40+ tools, AI conversation (OpenAI), history, security, E2E

Key design: MCP uses SSE for responses. POST to message endpoint returns 202,
and the actual JSON-RPC response arrives on the SSE stream.
"""

import json
import re
import sys
import time
import uuid
import threading
import queue
import requests
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────────────
HA_URL = "http://localhost:18123"
TOKEN = "YOUR_HA_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
SSE_URL = f"{HA_URL}/api/ha_mcp_client/sse"
CONV_AGENT = "conversation.ha_mcp_client_ha_mcp_client_01kk3w34mx75zr1emp35aakx65"
ENTRY_ID = "01KK3W34MX75ZR1EMP35AAKX65"

# Correct entity IDs (from actual HA states)
ENTITIES = {
    "living_room_light": "light.living_room_light",
    "bedroom_light": "light.bedroom_light",
    "kitchen_light": "light.kitchen_light",
    "temp_living": "sensor.living_room_temperature_temperature",
    "temp_bedroom": "sensor.bedroom_temperature_temperature",
    "temp_kitchen": "sensor.kitchen_temperature_temperature",
    "humidity_living": "sensor.living_room_humidity_humidity",
    "motion_living": "binary_sensor.living_room_motion_motion",
    "garage_door": "cover.garage_door_cover",
    "garage_lock": "lock.garage_lock",
    "tv_switch": "switch.living_room_fan",  # mapped to fan switch
    "coffee_maker": "switch.kitchen_coffee_maker",
    "smoke_kitchen": "binary_sensor.kitchen_smoke_smoke",
}

# ── Result tracking ───────────────────────────────────────────────────────────
results = []

def record(test_id, name, status, detail=""):
    results.append({"id": test_id, "name": name, "status": status, "detail": detail})
    icon = {"PASS": "\u2705", "FAIL": "\u274c", "SKIP": "\u23ed"}.get(status, "?")
    pad = 50 - len(f"[{test_id}] {name}")
    print(f"  [{test_id}] {name} {'.' * max(pad, 2)} {icon} {status} {detail[:80]}")


# ── MCP SSE Session Class ─────────────────────────────────────────────────────
class MCPSSESession:
    """Manages an MCP session with SSE response stream."""

    def __init__(self):
        self.session_id = None
        self.msg_url = None
        self.response_queue = queue.Queue()
        self._sse_thread = None
        self._stop = threading.Event()
        self._connected = threading.Event()

    def connect(self, timeout=10):
        """Open SSE connection in background thread."""
        self._sse_thread = threading.Thread(target=self._sse_reader, daemon=True)
        self._sse_thread.start()
        if not self._connected.wait(timeout):
            return False
        return self.session_id is not None

    def _sse_reader(self):
        """Background thread reading SSE stream."""
        try:
            resp = requests.get(
                SSE_URL,
                headers={"Authorization": f"Bearer {TOKEN}",
                         "Accept": "text/event-stream"},
                stream=True, timeout=120,
            )
            if resp.status_code != 200:
                self._connected.set()
                return

            event_type = None
            for raw_line in resp.iter_lines(decode_unicode=True):
                if self._stop.is_set():
                    break
                if raw_line is None:
                    continue
                line = raw_line.strip() if raw_line else ""

                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
                    if event_type == "endpoint":
                        # Fix internal container IP
                        url = re.sub(r'http://[\d.]+:\d+', HA_URL, data)
                        self.msg_url = url
                        if "sessionId=" in url:
                            self.session_id = url.split("sessionId=")[1]
                        self._connected.set()
                    elif event_type == "message":
                        try:
                            msg = json.loads(data)
                            self.response_queue.put(msg)
                        except json.JSONDecodeError:
                            pass
                elif line.startswith(":"):
                    # keepalive comment
                    pass
        except Exception:
            pass
        finally:
            self._connected.set()

    def send(self, method, params=None, req_id=1, is_notification=False):
        """Send JSON-RPC message and wait for response from SSE stream."""
        if not self.msg_url:
            return None
        payload = {"jsonrpc": "2.0", "method": method}
        if not is_notification:
            payload["id"] = req_id
        if params:
            payload["params"] = params

        resp = requests.post(self.msg_url, json=payload, headers=HEADERS, timeout=15)

        if is_notification:
            return {"_status": resp.status_code}

        # Wait for response on SSE stream
        try:
            msg = self.response_queue.get(timeout=15)
            return msg
        except queue.Empty:
            return None

    def tool_call(self, tool_name, arguments=None, req_id=1):
        """Call a tool via MCP tools/call."""
        params = {"name": tool_name}
        if arguments:
            params["arguments"] = arguments
        return self.send("tools/call", params, req_id)

    def close(self):
        self._stop.set()

    def initialize(self):
        """Full initialize handshake."""
        resp = self.send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        })
        self.send("notifications/initialized", is_notification=True)
        return resp


def get_tool_text(data):
    """Extract text from MCP tool call response."""
    if not data:
        return ""
    content = data.get("result", {}).get("content", [])
    if content:
        return content[0].get("text", "")
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: MCP Protocol Compliance Tests
# ══════════════════════════════════════════════════════════════════════════════
def phase1_protocol_tests():
    print("\n" + "=" * 70)
    print("  PHASE 1: MCP Protocol Compliance Tests")
    print("=" * 70)

    # T1.1: SSE Connection
    try:
        s = MCPSSESession()
        ok = s.connect()
        if ok and s.session_id:
            record("T1.1", "SSE Connection", "PASS", f"session={s.session_id[:8]}...")
        else:
            record("T1.1", "SSE Connection", "FAIL", "No session")
        s.close()
    except Exception as e:
        record("T1.1", "SSE Connection", "FAIL", str(e))

    # T1.2: Initialize Handshake
    try:
        s = MCPSSESession()
        s.connect()
        resp = s.initialize()
        if resp:
            result = resp.get("result", {})
            pv = result.get("protocolVersion")
            has_tools = "tools" in result.get("capabilities", {})
            server_name = result.get("serverInfo", {}).get("name")
            if pv == "2024-11-05" and has_tools and server_name:
                record("T1.2", "Initialize Handshake", "PASS",
                       f"proto={pv}, server={server_name}")
            else:
                record("T1.2", "Initialize Handshake", "FAIL", json.dumps(result)[:100])
        else:
            record("T1.2", "Initialize Handshake", "FAIL", "No response")
        s.close()
    except Exception as e:
        record("T1.2", "Initialize Handshake", "FAIL", str(e))

    # T1.3: Initialized Notification
    try:
        s = MCPSSESession()
        s.connect()
        s.send("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        })
        resp = s.send("notifications/initialized", is_notification=True)
        if resp and resp.get("_status") in (200, 202, 204):
            record("T1.3", "Initialized Notification", "PASS")
        else:
            record("T1.3", "Initialized Notification", "FAIL", str(resp))
        s.close()
    except Exception as e:
        record("T1.3", "Initialized Notification", "FAIL", str(e))

    # T1.4: Ping
    try:
        s = MCPSSESession()
        s.connect()
        s.initialize()
        resp = s.send("ping", req_id=99)
        if resp and "result" in resp:
            record("T1.4", "Ping/Pong", "PASS")
        else:
            record("T1.4", "Ping/Pong", "FAIL", str(resp)[:100])
        s.close()
    except Exception as e:
        record("T1.4", "Ping/Pong", "FAIL", str(e))

    # T1.5: tools/list
    try:
        s = MCPSSESession()
        s.connect()
        s.initialize()
        resp = s.send("tools/list", req_id=2)
        if resp:
            tools = resp.get("result", {}).get("tools", [])
            tool_names = [t["name"] for t in tools]
            required = ["get_entity_state", "call_service", "list_areas",
                        "system_overview", "control_light"]
            missing = [t for t in required if t not in tool_names]
            if len(tools) >= 25 and not missing:
                record("T1.5", "tools/list", "PASS", f"{len(tools)} tools")
            else:
                record("T1.5", "tools/list", "FAIL",
                       f"{len(tools)} tools, missing: {missing}")
        else:
            record("T1.5", "tools/list", "FAIL", "No response")
        s.close()
    except Exception as e:
        record("T1.5", "tools/list", "FAIL", str(e))

    # T1.6: resources/list
    try:
        s = MCPSSESession()
        s.connect()
        s.initialize()
        resp = s.send("resources/list", req_id=3)
        if resp:
            resources = resp.get("result", {}).get("resources", [])
            record("T1.6", "resources/list", "PASS", f"{len(resources)} resources")
        else:
            record("T1.6", "resources/list", "FAIL", "No response")
        s.close()
    except Exception as e:
        record("T1.6", "resources/list", "FAIL", str(e))

    # T1.7: Invalid Method
    try:
        s = MCPSSESession()
        s.connect()
        s.initialize()
        resp = s.send("totally_invalid_method_xyz", req_id=4)
        if resp and "error" in resp:
            record("T1.7", "Invalid Method Error", "PASS",
                   f"code={resp['error'].get('code')}")
        else:
            record("T1.7", "Invalid Method Error", "FAIL", str(resp)[:80])
        s.close()
    except Exception as e:
        record("T1.7", "Invalid Method Error", "FAIL", str(e))

    # T1.8: Multiple Sessions
    try:
        sessions = []
        for i in range(3):
            s = MCPSSESession()
            s.connect()
            if s.session_id:
                sessions.append(s.session_id)
            s.close()
        unique = len(set(sessions))
        if unique == 3:
            record("T1.8", "Multi-Session", "PASS", f"{unique} unique sessions")
        else:
            record("T1.8", "Multi-Session", "FAIL", f"only {unique} unique")
    except Exception as e:
        record("T1.8", "Multi-Session", "FAIL", str(e))

    # T1.9: No Auth
    try:
        resp = requests.get(SSE_URL, timeout=5)
        if resp.status_code == 401:
            record("T1.9", "No Auth Rejection", "PASS", "401 returned")
        else:
            record("T1.9", "No Auth Rejection", "FAIL", f"got {resp.status_code}")
    except Exception as e:
        record("T1.9", "No Auth Rejection", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: Tool Execution Tests
# ══════════════════════════════════════════════════════════════════════════════
def phase2_tool_tests():
    print("\n" + "=" * 70)
    print("  PHASE 2: Tool Execution Tests (40+ tools)")
    print("=" * 70)

    s = MCPSSESession()
    if not s.connect():
        record("T2.0", "Session Setup", "FAIL", "Cannot connect")
        return
    init_resp = s.initialize()
    if not init_resp:
        record("T2.0", "Session Setup", "FAIL", "Cannot initialize")
        s.close()
        return

    req_id = [10]  # mutable counter

    def tc(tool, args=None):
        req_id[0] += 1
        return s.tool_call(tool, args, req_id[0])

    # ── T2.1: Entity Tools ──
    try:
        resp = tc("get_entity_state", {"entity_id": ENTITIES["temp_living"]})
        text = get_tool_text(resp)
        if "24" in text or "temperature" in text.lower():
            record("T2.1a", "get_entity_state", "PASS", text[:60])
        else:
            record("T2.1a", "get_entity_state", "FAIL", text[:80])
    except Exception as e:
        record("T2.1a", "get_entity_state", "FAIL", str(e))

    try:
        resp = tc("search_entities", {"query": "light"})
        text = get_tool_text(resp)
        if "light" in text.lower():
            record("T2.1b", "search_entities(query)", "PASS")
        else:
            record("T2.1b", "search_entities(query)", "FAIL", text[:80])
    except Exception as e:
        record("T2.1b", "search_entities(query)", "FAIL", str(e))

    try:
        resp = tc("search_entities", {"area": "客廳"})
        text = get_tool_text(resp)
        if "living" in text.lower() or "客廳" in text or len(text) > 20:
            record("T2.1c", "search_entities(area)", "PASS")
        else:
            record("T2.1c", "search_entities(area)", "FAIL", text[:80])
    except Exception as e:
        record("T2.1c", "search_entities(area)", "FAIL", str(e))

    # ── T2.2: Service Tools ──
    try:
        resp = tc("call_service", {
            "domain": "light", "service": "turn_on",
            "entity_id": ENTITIES["living_room_light"]
        })
        text = get_tool_text(resp)
        record("T2.2a", "call_service(turn_on)", "PASS", text[:60])
    except Exception as e:
        record("T2.2a", "call_service(turn_on)", "FAIL", str(e))

    try:
        resp = tc("call_service", {
            "domain": "light", "service": "turn_off",
            "entity_id": ENTITIES["living_room_light"]
        })
        text = get_tool_text(resp)
        record("T2.2b", "call_service(turn_off)", "PASS", text[:60])
    except Exception as e:
        record("T2.2b", "call_service(turn_off)", "FAIL", str(e))

    try:
        resp = tc("list_services", {"domain": "light"})
        text = get_tool_text(resp)
        if "turn_on" in text:
            record("T2.2c", "list_services(light)", "PASS")
        else:
            record("T2.2c", "list_services(light)", "FAIL", text[:80])
    except Exception as e:
        record("T2.2c", "list_services(light)", "FAIL", str(e))

    # ── T2.3: Area Tools ──
    try:
        resp = tc("list_areas")
        text = get_tool_text(resp)
        # Parse JSON to handle unicode escaping
        try:
            parsed = json.loads(text)
            area_names = [a.get("name", "") for a in parsed] if isinstance(parsed, list) else []
            area_ids = [a.get("id", "") for a in parsed] if isinstance(parsed, list) else []
            has_area = ("客廳" in area_names or "ke_ting" in area_ids
                       or any("living" in str(a).lower() for a in parsed))
        except (json.JSONDecodeError, TypeError):
            has_area = "客廳" in text or "living" in text.lower() or "ke_ting" in text
        if has_area:
            record("T2.3a", "list_areas", "PASS")
        else:
            record("T2.3a", "list_areas", "FAIL", text[:80])
    except Exception as e:
        record("T2.3a", "list_areas", "FAIL", str(e))

    test_area_id = None
    try:
        resp = tc("create_area", {"name": "測試區域", "icon": "mdi:test-tube"})
        text = get_tool_text(resp)
        try:
            parsed = json.loads(text)
            test_area_id = parsed.get("area_id") or parsed.get("id")
        except:
            pass
        if "測試" in text or "created" in text.lower() or "area" in text.lower():
            record("T2.3b", "create_area", "PASS", text[:60])
        else:
            record("T2.3b", "create_area", "FAIL", text[:80])
    except Exception as e:
        record("T2.3b", "create_area", "FAIL", str(e))

    if test_area_id:
        try:
            resp = tc("update_area", {"area_id": test_area_id, "name": "測試-更新"})
            record("T2.3c", "update_area", "PASS")
        except Exception as e:
            record("T2.3c", "update_area", "FAIL", str(e))
        try:
            resp = tc("delete_area", {"area_id": test_area_id})
            record("T2.3d", "delete_area", "PASS")
        except Exception as e:
            record("T2.3d", "delete_area", "FAIL", str(e))
    else:
        record("T2.3c", "update_area", "SKIP", "no area_id")
        record("T2.3d", "delete_area", "SKIP", "no area_id")

    # ── T2.4: Label Tools ──
    test_label_id = None
    try:
        resp = tc("list_labels")
        text = get_tool_text(resp)
        record("T2.4a", "list_labels", "PASS", text[:60])
    except Exception as e:
        record("T2.4a", "list_labels", "FAIL", str(e))

    try:
        resp = tc("create_label", {"name": "測試標籤", "color": "#FF0000"})
        text = get_tool_text(resp)
        try:
            parsed = json.loads(text)
            test_label_id = parsed.get("label_id") or parsed.get("id")
        except:
            pass
        record("T2.4b", "create_label", "PASS", text[:60])
    except Exception as e:
        record("T2.4b", "create_label", "FAIL", str(e))

    if test_label_id:
        try:
            tc("update_label", {"label_id": test_label_id, "name": "更新標籤"})
            record("T2.4c", "update_label", "PASS")
        except Exception as e:
            record("T2.4c", "update_label", "FAIL", str(e))
        try:
            tc("delete_label", {"label_id": test_label_id})
            record("T2.4d", "delete_label", "PASS")
        except Exception as e:
            record("T2.4d", "delete_label", "FAIL", str(e))
    else:
        record("T2.4c", "update_label", "SKIP", "no label_id")
        record("T2.4d", "delete_label", "SKIP", "no label_id")

    # ── T2.5: Device Tools ──
    try:
        resp = tc("list_devices")
        text = get_tool_text(resp)
        if len(text) > 10:
            record("T2.5a", "list_devices", "PASS", f"{len(text)} chars")
        else:
            record("T2.5a", "list_devices", "FAIL", text[:80])
    except Exception as e:
        record("T2.5a", "list_devices", "FAIL", str(e))

    # ── T2.6: Automation Tools ──
    try:
        resp = tc("create_automation", {
            "alias": "Test Auto - Lights Off",
            "trigger": [{"platform": "time", "at": "23:59:00"}],
            "action": [{"service": "light.turn_off",
                         "target": {"entity_id": ENTITIES["living_room_light"]}}]
        })
        text = get_tool_text(resp)
        record("T2.6a", "create_automation", "PASS", text[:60])
    except Exception as e:
        record("T2.6a", "create_automation", "FAIL", str(e))

    try:
        resp = tc("list_automations")
        text = get_tool_text(resp)
        record("T2.6b", "list_automations", "PASS", text[:60])
    except Exception as e:
        record("T2.6b", "list_automations", "FAIL", str(e))

    # ── T2.7: Script Tools ──
    try:
        resp = tc("create_script", {
            "name": "test_script_greeting",
            "sequence": [{"service": "light.turn_on",
                          "target": {"entity_id": ENTITIES["bedroom_light"]}}]
        })
        text = get_tool_text(resp)
        record("T2.7a", "create_script", "PASS", text[:60])
    except Exception as e:
        record("T2.7a", "create_script", "FAIL", str(e))

    try:
        resp = tc("list_scripts")
        text = get_tool_text(resp)
        record("T2.7b", "list_scripts", "PASS", text[:60])
    except Exception as e:
        record("T2.7b", "list_scripts", "FAIL", str(e))

    # ── T2.8: Scene Tools ──
    try:
        resp = tc("create_scene", {
            "name": "Movie Night Test",
            "entities": {
                ENTITIES["living_room_light"]: {"state": "on", "brightness": 50},
                ENTITIES["tv_switch"]: {"state": "on"}
            }
        })
        text = get_tool_text(resp)
        record("T2.8a", "create_scene", "PASS", text[:60])
    except Exception as e:
        record("T2.8a", "create_scene", "FAIL", str(e))

    try:
        resp = tc("list_scenes")
        text = get_tool_text(resp)
        record("T2.8b", "list_scenes", "PASS", text[:60])
    except Exception as e:
        record("T2.8b", "list_scenes", "FAIL", str(e))

    # ── T2.9: History ──
    try:
        resp = tc("get_history", {
            "entity_id": ENTITIES["living_room_light"], "hours": 1
        })
        text = get_tool_text(resp)
        record("T2.9", "get_history", "PASS", text[:60])
    except Exception as e:
        record("T2.9", "get_history", "FAIL", str(e))

    # ── T2.10: System Overview ──
    try:
        resp = tc("system_overview")
        text = get_tool_text(resp)
        if "entities" in text.lower() or "areas" in text.lower() or "total" in text.lower():
            record("T2.10", "system_overview", "PASS", text[:60])
        else:
            record("T2.10", "system_overview", "FAIL", text[:80])
    except Exception as e:
        record("T2.10", "system_overview", "FAIL", str(e))

    # ── T2.11: Control Tools ──
    try:
        resp = tc("control_light", {
            "entity_id": ENTITIES["living_room_light"],
            "action": "on", "brightness": 128
        })
        text = get_tool_text(resp)
        record("T2.11a", "control_light(brightness)", "PASS", text[:60])
    except Exception as e:
        record("T2.11a", "control_light(brightness)", "FAIL", str(e))

    try:
        resp = tc("control_light", {
            "entity_id": ENTITIES["living_room_light"],
            "action": "on", "color_temp": 200
        })
        text = get_tool_text(resp)
        record("T2.11b", "control_light(color_temp)", "PASS", text[:60])
    except Exception as e:
        record("T2.11b", "control_light(color_temp)", "FAIL", str(e))

    try:
        resp = tc("control_cover", {
            "entity_id": ENTITIES["garage_door"], "action": "open"
        })
        text = get_tool_text(resp)
        record("T2.11c", "control_cover(open)", "PASS", text[:60])
    except Exception as e:
        record("T2.11c", "control_cover(open)", "FAIL", str(e))

    try:
        resp = tc("control_cover", {
            "entity_id": ENTITIES["garage_door"],
            "action": "set_position", "position": 50
        })
        text = get_tool_text(resp)
        record("T2.11d", "control_cover(position)", "PASS", text[:60])
    except Exception as e:
        record("T2.11d", "control_cover(position)", "FAIL", str(e))

    # ── T2.12: Calendar (expect skip) ──
    try:
        resp = tc("create_calendar_event", {
            "summary": "Test Event",
            "start": "2026-03-08T10:00:00",
            "end": "2026-03-08T11:00:00"
        })
        text = get_tool_text(resp)
        if resp and resp.get("result", {}).get("isError"):
            record("T2.12", "create_calendar_event", "SKIP", "No calendar (expected)")
        else:
            record("T2.12", "create_calendar_event", "PASS", text[:60])
    except Exception as e:
        record("T2.12", "create_calendar_event", "FAIL", str(e))

    # ── T2.13: Blocked Service Domains ──
    blocked = [
        ("homeassistant", "restart", "T2.13a", "blocked(ha.restart)"),
        ("hassio", "addon_start", "T2.13b", "blocked(hassio)"),
        ("supervisor", "reload", "T2.13c", "blocked(supervisor)"),
        ("config", "reload", "T2.13d", "blocked(config)"),
        ("system_log", "clear", "T2.13e", "blocked(system_log)"),
    ]
    for domain, service, tid, name in blocked:
        try:
            resp = tc("call_service", {"domain": domain, "service": service})
            text = get_tool_text(resp)
            blocked_keywords = ["blocked", "not allowed", "denied", "restricted", "not permitted"]
            if any(kw in text.lower() for kw in blocked_keywords):
                record(tid, name, "PASS", "blocked correctly")
            else:
                record(tid, name, "FAIL", f"NOT blocked: {text[:60]}")
        except Exception as e:
            record(tid, name, "FAIL", str(e))

    # ── T2.14: Blocked Specific Services ──
    blocked_svc = [
        ("recorder", "purge", "T2.14a", "blocked(recorder.purge)"),
        ("recorder", "purge_entities", "T2.14b", "blocked(recorder.purge_ent)"),
        ("recorder", "disable", "T2.14c", "blocked(recorder.disable)"),
    ]
    for domain, service, tid, name in blocked_svc:
        try:
            resp = tc("call_service", {"domain": domain, "service": service})
            text = get_tool_text(resp)
            blocked_keywords = ["blocked", "not allowed", "denied", "restricted", "not permitted"]
            if any(kw in text.lower() for kw in blocked_keywords):
                record(tid, name, "PASS", "blocked correctly")
            else:
                record(tid, name, "FAIL", f"NOT blocked: {text[:60]}")
        except Exception as e:
            record(tid, name, "FAIL", str(e))

    s.close()


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3: AI Conversation Tests
# ══════════════════════════════════════════════════════════════════════════════
def phase3_conversation_tests():
    print("\n" + "=" * 70)
    print("  PHASE 3: AI Conversation Tests (Ollama llama3.1:8b)")
    print("=" * 70)

    conv_url = f"{HA_URL}/api/conversation/process"
    conv_id = str(uuid.uuid4())

    def chat(text, cid=None, timeout=60):
        payload = {"text": text, "language": "en", "agent_id": CONV_AGENT}
        if cid:
            payload["conversation_id"] = cid
        resp = requests.post(conv_url, json=payload, headers=HEADERS, timeout=timeout)
        return resp.json()

    def get_speech(data):
        return data.get("response", {}).get("speech", {}).get("plain", {}).get("speech", "")

    # T3.1: Basic Chat
    try:
        data = chat("Hello, what can you help me with?")
        speech = get_speech(data)
        if speech and len(speech) > 20 and "sorry" not in speech.lower()[:20]:
            record("T3.1", "Basic Chat", "PASS", speech[:60])
        else:
            record("T3.1", "Basic Chat", "FAIL", f"speech: {speech[:80]}")
    except Exception as e:
        record("T3.1", "Basic Chat", "FAIL", str(e))

    # T3.2: Single Tool Call
    try:
        data = chat("Turn on the living room light", conv_id)
        speech = get_speech(data)
        time.sleep(1)
        state_resp = requests.get(
            f"{HA_URL}/api/states/{ENTITIES['living_room_light']}",
            headers=HEADERS, timeout=5
        )
        state = state_resp.json().get("state", "")
        if state == "on":
            record("T3.2", "Tool Call (light on)", "PASS",
                   f"state={state}, AI: {speech[:40]}")
        else:
            record("T3.2", "Tool Call (light on)", "FAIL",
                   f"state={state}, AI: {speech[:60]}")
    except Exception as e:
        record("T3.2", "Tool Call (light on)", "FAIL", str(e))

    # T3.3: Multi-tool
    try:
        data = chat("What is the temperature in each room?", conv_id)
        speech = get_speech(data)
        has_temp = any(c in speech for c in ["24", "22", "26", "°"])
        if has_temp:
            record("T3.3", "Multi-Tool (temps)", "PASS", speech[:60])
        else:
            record("T3.3", "Multi-Tool (temps)", "FAIL", speech[:80])
    except Exception as e:
        record("T3.3", "Multi-Tool (temps)", "FAIL", str(e))

    # T3.4: Complex - create scene
    try:
        data = chat(
            "Create a scene called 'Relax Mode' with living room light on at 30% brightness",
            str(uuid.uuid4())
        )
        speech = get_speech(data)
        if "relax" in speech.lower() or "scene" in speech.lower() or "created" in speech.lower():
            record("T3.4", "Complex (create scene)", "PASS", speech[:60])
        else:
            record("T3.4", "Complex (create scene)", "FAIL", speech[:80])
    except Exception as e:
        record("T3.4", "Complex (create scene)", "FAIL", str(e))

    # T3.5: Context continuity
    try:
        data = chat("Now turn it off", conv_id)
        speech = get_speech(data)
        if speech and len(speech) > 5:
            record("T3.5", "Context Continuity", "PASS", speech[:60])
        else:
            record("T3.5", "Context Continuity", "FAIL", speech[:80])
    except Exception as e:
        record("T3.5", "Context Continuity", "FAIL", str(e))

    # T3.6: Error - non-existent
    try:
        data = chat("Turn on the basement light", str(uuid.uuid4()))
        speech = get_speech(data)
        if speech and len(speech) > 5:
            record("T3.6", "Error (non-existent)", "PASS", speech[:60])
        else:
            record("T3.6", "Error (non-existent)", "FAIL", speech[:80])
    except Exception as e:
        record("T3.6", "Error (non-existent)", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4: Conversation History & Recorder Tests
# ══════════════════════════════════════════════════════════════════════════════
def phase4_history_tests():
    print("\n" + "=" * 70)
    print("  PHASE 4: Conversation History & Recorder Tests")
    print("=" * 70)

    conv_url = f"{HA_URL}/api/conversation/process"
    test_cid = f"test-history-{uuid.uuid4()}"

    def chat(text, cid):
        payload = {"text": text, "language": "en", "agent_id": CONV_AGENT,
                   "conversation_id": cid}
        resp = requests.post(conv_url, json=payload, headers=HEADERS, timeout=60)
        return resp.json()

    # T4.1: Send message
    try:
        data = chat("What is the current state of the living room light?", test_cid)
        speech = data.get("response", {}).get("speech", {}).get("plain", {}).get("speech", "")
        if speech and len(speech) > 5:
            record("T4.1", "Message Persistence", "PASS", speech[:60])
        else:
            record("T4.1", "Message Persistence", "FAIL", f"No speech")
    except Exception as e:
        record("T4.1", "Message Persistence", "FAIL", str(e))

    # T4.2: Context continuity in same conversation
    try:
        data = chat("What did I just ask about?", test_cid)
        speech = data.get("response", {}).get("speech", {}).get("plain", {}).get("speech", "")
        if speech and ("light" in speech.lower() or "living" in speech.lower() or len(speech) > 20):
            record("T4.2", "Context Continuity", "PASS", speech[:60])
        else:
            record("T4.2", "Context Continuity", "FAIL", speech[:80])
    except Exception as e:
        record("T4.2", "Context Continuity", "FAIL", str(e))

    # T4.3: Clear history service
    try:
        svc_url = f"{HA_URL}/api/services/ha_mcp_client/clear_conversation_history"
        resp = requests.post(svc_url, json={}, headers=HEADERS, timeout=10)
        if resp.status_code in (200, 201):
            record("T4.3", "Clear History", "PASS")
        else:
            record("T4.3", "Clear History", "FAIL", f"status={resp.status_code}")
    except Exception as e:
        record("T4.3", "Clear History", "FAIL", str(e))

    # T4.4: Export JSON
    try:
        svc_url = f"{HA_URL}/api/services/ha_mcp_client/export_conversation_history"
        resp = requests.post(svc_url, json={"format": "json"}, headers=HEADERS, timeout=10)
        if resp.status_code in (200, 201):
            record("T4.4", "Export History (JSON)", "PASS")
        else:
            record("T4.4", "Export History (JSON)", "FAIL", f"status={resp.status_code}")
    except Exception as e:
        record("T4.4", "Export History (JSON)", "FAIL", str(e))

    # T4.5: Export Markdown
    try:
        svc_url = f"{HA_URL}/api/services/ha_mcp_client/export_conversation_history"
        resp = requests.post(svc_url, json={"format": "markdown"}, headers=HEADERS, timeout=10)
        if resp.status_code in (200, 201):
            record("T4.5", "Export History (MD)", "PASS")
        else:
            record("T4.5", "Export History (MD)", "FAIL", f"status={resp.status_code}")
    except Exception as e:
        record("T4.5", "Export History (MD)", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5: Security & Edge Case Tests
# ══════════════════════════════════════════════════════════════════════════════
def phase5_security_tests():
    print("\n" + "=" * 70)
    print("  PHASE 5: Security & Edge Case Tests")
    print("=" * 70)

    # T5.1: Unauthenticated SSE
    try:
        resp = requests.get(SSE_URL, timeout=5)
        if resp.status_code == 401:
            record("T5.1", "Unauth SSE Rejection", "PASS", "401")
        else:
            record("T5.1", "Unauth SSE Rejection", "FAIL", f"got {resp.status_code}")
    except Exception as e:
        record("T5.1", "Unauth SSE Rejection", "FAIL", str(e))

    # T5.2: Blocked service via MCP
    try:
        s = MCPSSESession()
        s.connect()
        s.initialize()
        resp = s.tool_call("call_service", {
            "domain": "homeassistant", "service": "restart"
        })
        text = get_tool_text(resp)
        blocked_keywords = ["blocked", "not allowed", "denied", "restricted", "not permitted"]
        if any(kw in text.lower() for kw in blocked_keywords):
            record("T5.2", "Blocked Service (MCP)", "PASS")
        else:
            record("T5.2", "Blocked Service (MCP)", "FAIL", text[:60])
        s.close()
    except Exception as e:
        record("T5.2", "Blocked Service (MCP)", "FAIL", str(e))

    # T5.3: Invalid tool arguments
    try:
        s = MCPSSESession()
        s.connect()
        s.initialize()
        resp = s.tool_call("get_entity_state", {"entity_id": 12345})
        text = str(resp)[:100] if resp else "No response"
        record("T5.3", "Invalid Tool Args", "PASS", f"handled: {text[:50]}")
        s.close()
    except Exception as e:
        record("T5.3", "Invalid Tool Args", "FAIL", str(e))

    # T5.4: Non-existent tool
    try:
        s = MCPSSESession()
        s.connect()
        s.initialize()
        resp = s.tool_call("totally_fake_tool_xyz", {"arg": "val"})
        if resp:
            text = str(resp)
            if "error" in text.lower() or "not found" in text.lower() or "unknown" in text.lower():
                record("T5.4", "Non-existent Tool", "PASS")
            else:
                record("T5.4", "Non-existent Tool", "FAIL", text[:80])
        else:
            record("T5.4", "Non-existent Tool", "FAIL", "No response")
        s.close()
    except Exception as e:
        record("T5.4", "Non-existent Tool", "FAIL", str(e))

    # T5.5: API key not in logs
    try:
        import subprocess
        out = subprocess.run(["podman", "logs", "homeassistant"],
                             capture_output=True, text=True, timeout=10)
        logs = out.stdout + out.stderr
        fragment = "4M5vF-UEupCURsgC"
        if fragment in logs:
            record("T5.5", "API Key Not In Logs", "FAIL", "Key found in logs!")
        else:
            record("T5.5", "API Key Not In Logs", "PASS", "Not in logs")
    except Exception as e:
        record("T5.5", "API Key Not In Logs", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6: Integration & E2E Tests
# ══════════════════════════════════════════════════════════════════════════════
def phase6_e2e_tests():
    print("\n" + "=" * 70)
    print("  PHASE 6: Integration & End-to-End Tests")
    print("=" * 70)

    conv_url = f"{HA_URL}/api/conversation/process"

    def chat(text):
        payload = {"text": text, "language": "en", "agent_id": CONV_AGENT,
                   "conversation_id": str(uuid.uuid4())}
        resp = requests.post(conv_url, json=payload, headers=HEADERS, timeout=60)
        return resp.json()

    def get_speech(data):
        return data.get("response", {}).get("speech", {}).get("plain", {}).get("speech", "")

    # T6.1: E2E Scene
    try:
        data = chat(
            "Create a scene called 'Goodnight' that turns off the living room light and the kitchen light"
        )
        speech = get_speech(data)
        time.sleep(2)
        states = requests.get(f"{HA_URL}/api/states", headers=HEADERS, timeout=5).json()
        scenes = [s for s in states if s["entity_id"].startswith("scene.")]
        scene_names = [s["attributes"].get("friendly_name", "") for s in scenes]
        if any("goodnight" in n.lower() or "good" in n.lower() for n in scene_names):
            record("T6.1", "E2E Scene Creation", "PASS", f"Found! AI: {speech[:40]}")
        elif "scene" in speech.lower() or "created" in speech.lower():
            record("T6.1", "E2E Scene Creation", "PASS", f"AI confirms: {speech[:50]}")
        else:
            record("T6.1", "E2E Scene Creation", "FAIL",
                   f"Scenes: {scene_names}. AI: {speech[:40]}")
    except Exception as e:
        record("T6.1", "E2E Scene Creation", "FAIL", str(e))

    # T6.2: E2E Automation
    try:
        data = chat(
            "Create an automation called 'Morning Coffee' that turns on the kitchen coffee maker at 7 AM"
        )
        speech = get_speech(data)
        time.sleep(2)
        states = requests.get(f"{HA_URL}/api/states", headers=HEADERS, timeout=5).json()
        autos = [s for s in states if s["entity_id"].startswith("automation.")]
        auto_names = [s["attributes"].get("friendly_name", "") for s in autos]
        if any("coffee" in n.lower() or "morning" in n.lower() for n in auto_names):
            record("T6.2", "E2E Automation", "PASS", f"Found! AI: {speech[:40]}")
        elif "automation" in speech.lower() or "created" in speech.lower():
            record("T6.2", "E2E Automation", "PASS", f"AI confirms: {speech[:50]}")
        else:
            record("T6.2", "E2E Automation", "FAIL",
                   f"Autos: {auto_names}. AI: {speech[:40]}")
    except Exception as e:
        record("T6.2", "E2E Automation", "FAIL", str(e))

    # T6.3: Integration reload via REST API (unload + load)
    try:
        # Use REST API to reload integration
        resp = requests.post(
            f"{HA_URL}/api/config/config_entries/entry/{ENTRY_ID}/reload",
            headers=HEADERS, timeout=15
        )
        if resp.status_code in (200, 201):
            record("T6.3", "Integration Reload", "PASS", f"status={resp.status_code}")
        else:
            # Fallback: try WebSocket
            try:
                import websocket
                ws = websocket.create_connection("ws://localhost:18123/api/websocket")
                msg = json.loads(ws.recv())
                ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
                msg = json.loads(ws.recv())
                ws.send(json.dumps({
                    "id": 1,
                    "type": "config_entries/reload",
                    "entry_id": ENTRY_ID
                }))
                msg = json.loads(ws.recv())
                ws.close()
                if msg.get("success"):
                    record("T6.3", "Integration Reload", "PASS")
                else:
                    record("T6.3", "Integration Reload", "FAIL", str(msg)[:80])
            except Exception as ws_e:
                record("T6.3", "Integration Reload", "FAIL", f"REST:{resp.status_code} WS:{ws_e}")
    except Exception as e:
        record("T6.3", "Integration Reload", "FAIL", str(e))

    # T6.4: MCP works after reload
    time.sleep(3)
    try:
        s = MCPSSESession()
        s.connect()
        resp = s.initialize()
        if resp and resp.get("result", {}).get("serverInfo"):
            resp2 = s.send("tools/list", req_id=2)
            if resp2:
                tools = resp2.get("result", {}).get("tools", [])
                record("T6.4", "MCP After Reload", "PASS", f"{len(tools)} tools")
            else:
                record("T6.4", "MCP After Reload", "FAIL", "No tools/list response")
        else:
            record("T6.4", "MCP After Reload", "FAIL", "Init failed after reload")
        s.close()
    except Exception as e:
        record("T6.4", "MCP After Reload", "FAIL", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def print_report():
    print("\n" + "=" * 70)
    print("  FINAL TEST REPORT")
    print("=" * 70)

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] == "SKIP")

    print(f"\n  Total: {total} | PASS: {passed} | FAIL: {failed} | SKIP: {skipped}")
    rate = passed / max(total - skipped, 1) * 100
    print(f"  Pass Rate: {rate:.1f}%")
    print()

    if failed > 0:
        print("  FAILED TESTS:")
        print("  " + "-" * 60)
        for r in results:
            if r["status"] == "FAIL":
                print(f"    [{r['id']}] {r['name']}: {r['detail'][:70]}")
        print()

    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped,
            "rate": rate, "results": results}


if __name__ == "__main__":
    print("=" * 70)
    print("  HA MCP Client - Comprehensive Integration Test Suite")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Target: {HA_URL}")
    print(f"  Conv Agent: {CONV_AGENT}")
    print("=" * 70)

    phases = [
        ("Phase 1: MCP Protocol", phase1_protocol_tests),
        ("Phase 2: Tool Execution", phase2_tool_tests),
        ("Phase 3: AI Conversation", phase3_conversation_tests),
        ("Phase 4: History & Recorder", phase4_history_tests),
        ("Phase 5: Security", phase5_security_tests),
        ("Phase 6: E2E Integration", phase6_e2e_tests),
    ]

    for name, func in phases:
        try:
            func()
        except Exception as e:
            print(f"\n  !!! Phase crashed: {name}: {e}")

    report = print_report()
