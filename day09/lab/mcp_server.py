"""
mcp_server.py - Standard MCP mock server for Day 09 lab.

Muc tieu:
- Cung cap tool discovery qua list_tools().
- Cung cap tool execution qua dispatch_tool(tool_name, tool_input).
- Khong raise exception ra ngoai dispatch_tool().

Tools:
1) search_kb(query, top_k=3)
2) get_ticket_info(ticket_id)
3) check_access_permission(access_level, requester_role, is_emergency=False)
4) create_ticket(priority, title, description="")
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "search_kb": {
        "name": "search_kb",
        "description": "Semantic search tren Knowledge Base noi bo, tra ve top-k chunks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Noi dung can tim"},
                "top_k": {"type": "integer", "description": "So chunks can tra", "default": 3},
            },
            "required": ["query"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "chunks": {"type": "array"},
                "sources": {"type": "array"},
                "total_found": {"type": "integer"},
            },
        },
    },
    "get_ticket_info": {
        "name": "get_ticket_info",
        "description": "Tra cuu thong tin ticket mock tu he thong noi bo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string", "description": "VD: IT-1234, P1-LATEST"},
            },
            "required": ["ticket_id"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "priority": {"type": "string"},
                "status": {"type": "string"},
                "assignee": {"type": "string"},
                "created_at": {"type": "string"},
                "sla_deadline": {"type": "string"},
                "notifications_sent": {"type": "array"},
            },
        },
    },
    "check_access_permission": {
        "name": "check_access_permission",
        "description": "Kiem tra dieu kien cap quyen theo Access Control SOP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "access_level": {"type": "integer", "description": "Level can cap (1-4)"},
                "requester_role": {"type": "string", "description": "Vai tro nguoi yeu cau"},
                "is_emergency": {"type": "boolean", "description": "Yeu cau khan cap", "default": False},
            },
            "required": ["access_level", "requester_role"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "can_grant": {"type": "boolean"},
                "required_approvers": {"type": "array"},
                "emergency_override": {"type": "boolean"},
                "source": {"type": "string"},
                "notes": {"type": "array"},
            },
        },
    },
    "create_ticket": {
        "name": "create_ticket",
        "description": "Tao ticket moi (MOCK, khong goi he thong that).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                "title": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["priority", "title"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "url": {"type": "string"},
                "created_at": {"type": "string"},
            },
        },
    },
}


MOCK_TICKETS: dict[str, dict[str, Any]] = {
    "P1-LATEST": {
        "ticket_id": "IT-9847",
        "priority": "P1",
        "title": "API Gateway down - toan bo nguoi dung khong dang nhap duoc",
        "status": "in_progress",
        "assignee": "nguyen.van.a@company.internal",
        "created_at": "2026-04-13T22:47:00",
        "sla_deadline": "2026-04-14T02:47:00",
        "escalated": True,
        "escalated_to": "senior_engineer_team",
        "notifications_sent": [
            "slack:#incident-p1",
            "email:incident@company.internal",
            "pagerduty:oncall",
        ],
    },
    "IT-1234": {
        "ticket_id": "IT-1234",
        "priority": "P2",
        "title": "Feature login cham cho mot so user",
        "status": "open",
        "assignee": None,
        "created_at": "2026-04-13T09:15:00",
        "sla_deadline": "2026-04-14T09:15:00",
        "escalated": False,
    },
}


ACCESS_RULES: dict[int, dict[str, Any]] = {
    1: {
        "required_approvers": ["Line Manager"],
        "emergency_can_bypass": False,
        "note": "Read-only access",
    },
    2: {
        "required_approvers": ["Line Manager", "IT Admin"],
        "emergency_can_bypass": True,
        "emergency_bypass_note": "Level 2 cho phep cap tam thoi khi co approval dong thoi.",
        "note": "Standard access",
    },
    3: {
        "required_approvers": ["Line Manager", "IT Admin", "IT Security"],
        "emergency_can_bypass": False,
        "note": "Elevated access",
    },
    4: {
        "required_approvers": ["IT Manager", "CISO"],
        "emergency_can_bypass": False,
        "note": "Admin access",
    },
}


def tool_search_kb(query: str, top_k: int = 3) -> dict[str, Any]:
    """Search KB bang retrieval worker de tai su dung logic retrieval."""
    try:
        from workers.retrieval import retrieve_dense

        chunks = retrieve_dense(query, top_k=top_k)
        sources = sorted({c.get("source", "unknown") for c in chunks})
        return {
            "chunks": chunks,
            "sources": sources,
            "total_found": len(chunks),
        }
    except Exception as exc:
        return {
            "chunks": [],
            "sources": [],
            "total_found": 0,
            "error": f"search_kb_failed: {exc}",
        }


def tool_get_ticket_info(ticket_id: str) -> dict[str, Any]:
    """Tra cuu thong tin ticket tu mock database."""
    ticket = MOCK_TICKETS.get(ticket_id.upper())
    if ticket:
        return ticket
    return {
        "error": f"Ticket '{ticket_id}' khong tim thay trong he thong mock.",
        "available_mock_ids": sorted(MOCK_TICKETS.keys()),
    }


def tool_check_access_permission(
    access_level: int,
    requester_role: str,
    is_emergency: bool = False,
) -> dict[str, Any]:
    """Kiem tra dieu kien cap quyen theo SOP mock."""
    rule = ACCESS_RULES.get(access_level)
    if not rule:
        return {"error": f"Access level {access_level} khong hop le. Levels: 1, 2, 3, 4."}

    notes: list[str] = []
    emergency_override = bool(is_emergency and rule.get("emergency_can_bypass", False))

    if is_emergency and emergency_override:
        note = rule.get("emergency_bypass_note")
        if note:
            notes.append(note)
    elif is_emergency and not emergency_override:
        notes.append(
            f"Level {access_level} khong co emergency bypass. Phai theo quy trinh chuan."
        )

    return {
        "access_level": access_level,
        "requester_role": requester_role,
        "can_grant": True,
        "required_approvers": rule["required_approvers"],
        "approver_count": len(rule["required_approvers"]),
        "emergency_override": emergency_override,
        "notes": notes,
        "source": "access_control_sop.txt",
    }


def tool_create_ticket(priority: str, title: str, description: str = "") -> dict[str, Any]:
    """Tao ticket moi (mock only)."""
    if priority not in {"P1", "P2", "P3", "P4"}:
        return {"error": "priority must be one of: P1, P2, P3, P4"}

    mock_id = f"IT-{9900 + (abs(hash(title)) % 99)}"
    return {
        "ticket_id": mock_id,
        "priority": priority,
        "title": title,
        "description": description[:200],
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "url": f"https://jira.company.internal/browse/{mock_id}",
        "note": "MOCK ticket - khong ton tai trong he thong that",
    }


TOOL_REGISTRY = {
    "search_kb": tool_search_kb,
    "get_ticket_info": tool_get_ticket_info,
    "check_access_permission": tool_check_access_permission,
    "create_ticket": tool_create_ticket,
}


def list_tools() -> list[dict[str, Any]]:
    """MCP discovery API: tra ve danh sach tools va schema."""
    return list(TOOL_SCHEMAS.values())


def _with_default_values(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dien default values theo schema cho cac field optional."""
    schema = TOOL_SCHEMAS[tool_name].get("inputSchema", {})
    properties = schema.get("properties", {})

    payload = dict(tool_input)
    for field_name, field_schema in properties.items():
        if field_name not in payload and "default" in field_schema:
            payload[field_name] = field_schema["default"]
    return payload


def _validate_required_fields(tool_name: str, tool_input: dict[str, Any]) -> list[str]:
    """Kiem tra cac field bat buoc theo schema."""
    required = TOOL_SCHEMAS[tool_name].get("inputSchema", {}).get("required", [])
    return [field for field in required if field not in tool_input]


def _validate_enum_fields(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """Validate cac field co enum trong schema."""
    properties = TOOL_SCHEMAS[tool_name].get("inputSchema", {}).get("properties", {})
    for field_name, field_schema in properties.items():
        if field_name in tool_input and "enum" in field_schema:
            if tool_input[field_name] not in field_schema["enum"]:
                return (
                    f"Field '{field_name}' must be one of {field_schema['enum']}. "
                    f"Got: {tool_input[field_name]}"
                )
    return None


def dispatch_tool(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """
    MCP execution API.

    Contract:
    - Khong raise exception ra ngoai.
    - Luon tra ve dict (result hoac error).
    """
    if tool_name not in TOOL_REGISTRY:
        return {
            "error": f"Tool '{tool_name}' khong ton tai.",
            "available_tools": sorted(TOOL_REGISTRY.keys()),
        }

    if not isinstance(tool_input, dict):
        return {
            "error": "tool_input must be a dict",
            "schema": TOOL_SCHEMAS[tool_name]["inputSchema"],
        }

    try:
        payload = _with_default_values(tool_name, tool_input)

        missing_fields = _validate_required_fields(tool_name, payload)
        if missing_fields:
            return {
                "error": f"Missing required fields: {missing_fields}",
                "schema": TOOL_SCHEMAS[tool_name]["inputSchema"],
            }

        enum_error = _validate_enum_fields(tool_name, payload)
        if enum_error:
            return {
                "error": enum_error,
                "schema": TOOL_SCHEMAS[tool_name]["inputSchema"],
            }

        tool_fn = TOOL_REGISTRY[tool_name]
        return tool_fn(**payload)

    except TypeError as exc:
        return {
            "error": f"Invalid input for tool '{tool_name}': {exc}",
            "schema": TOOL_SCHEMAS[tool_name]["inputSchema"],
        }
    except Exception as exc:
        return {"error": f"Tool '{tool_name}' execution failed: {exc}"}


if __name__ == "__main__":
    print("=" * 60)
    print("MCP Server - Tool Discovery & Demo")
    print("=" * 60)

    print("\nAvailable tools:")
    for tool in list_tools():
        print(f"- {tool['name']}: {tool['description']}")

    print("\nTest: search_kb")
    result = dispatch_tool("search_kb", {"query": "SLA P1 resolution time", "top_k": 2})
    print({"total_found": result.get("total_found"), "sources": result.get("sources")})

    print("\nTest: get_ticket_info")
    ticket = dispatch_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
    print({
        "ticket_id": ticket.get("ticket_id"),
        "priority": ticket.get("priority"),
        "status": ticket.get("status"),
    })

    print("\nTest: check_access_permission")
    perm = dispatch_tool(
        "check_access_permission",
        {"access_level": 3, "requester_role": "contractor", "is_emergency": True},
    )
    print({
        "can_grant": perm.get("can_grant"),
        "required_approvers": perm.get("required_approvers"),
        "emergency_override": perm.get("emergency_override"),
    })

    print("\nTest: invalid tool")
    err = dispatch_tool("nonexistent_tool", {})
    print(err)

    print("\nDone.")
