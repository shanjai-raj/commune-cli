"""commune describe — hierarchical, context-efficient API manifest.

Designed so agents never load more than they need:

  commune describe                  → tiny index (~20 lines): group names + descriptions
  commune describe messages         → just that group's commands with full params
  commune describe messages.send    → just that one command
  commune describe --full           → everything (for caching / offline use)
"""

from __future__ import annotations

from typing import Optional

import typer

from .. import __version__
from ..output import print_json

app = typer.Typer(help="Machine-readable API surface manifest.", no_args_is_help=False)


# ── Group index (tiny — this is what `commune describe` returns) ──────────

_GROUPS: dict[str, str] = {
    "messages":      "Send and list emails",
    "inboxes":       "Create, list, update, delete inboxes and configure webhooks",
    "threads":       "List threads, read messages, triage (status, tags, assign)",
    "domains":       "Custom domain management and DNS verification",
    "search":        "Semantic full-text search across threads",
    "delivery":      "Delivery metrics, events, and suppressions",
    "sms":           "Send SMS, view conversations, search messages",
    "phone-numbers": "Provision and manage phone numbers",
    "webhooks":      "Webhook delivery log and health",
    "attachments":   "Upload files and get download URLs",
    "credits":       "Credit balance and purchasable bundles",
    "dmarc":         "DMARC reports and compliance summary",
    "data":          "Data deletion requests (GDPR)",
    "config":        "CLI config, agent registration, API keys",
}


# ── Type definitions ──────────────────────────────────────────────────────

_TYPES: dict[str, dict] = {
    "Domain": {
        "id": "string (uuid)",
        "name": "string",
        "status": "string (verified | pending | failed)",
        "region": "string",
    },
    "DnsRecord": {
        "type": "string (MX | TXT | CNAME)",
        "name": "string",
        "value": "string",
        "priority": "integer | null",
        "status": "string (verified | pending)",
    },
    "Inbox": {
        "id": "string (uuid)",
        "local_part": "string",
        "address": "string (full email)",
        "display_name": "string | null",
        "webhook": "object | null",
        "domain_id": "string (uuid)",
        "domain_name": "string",
        "created_at": "string (ISO 8601)",
    },
    "Thread": {
        "thread_id": "string",
        "subject": "string",
        "message_count": "integer",
        "last_message_at": "string (ISO 8601)",
        "first_message_at": "string (ISO 8601)",
        "snippet": "string",
        "last_direction": "string (inbound | outbound)",
        "inbox_id": "string (uuid)",
        "domain_id": "string (uuid)",
        "has_attachments": "boolean",
    },
    "Message": {
        "id": "string",
        "thread_id": "string",
        "direction": "string (inbound | outbound)",
        "from": "string",
        "to": "array of string",
        "subject": "string",
        "content": "string (plain text)",
        "content_html": "string | null",
        "created_at": "string (ISO 8601)",
        "attachments": "array of Attachment",
    },
    "DeliveryMetrics": {
        "sent": "integer",
        "delivered": "integer",
        "bounced": "integer",
        "complained": "integer",
        "failed": "integer",
        "delivery_rate": "number (0-1)",
        "bounce_rate": "number (0-1)",
        "complaint_rate": "number (0-1)",
    },
    "PhoneNumber": {
        "id": "string",
        "phone_number": "string (E.164)",
        "friendly_name": "string | null",
        "type": "string (TollFree | Local)",
        "status": "string",
    },
    "SmsMessage": {
        "id": "string",
        "thread_id": "string",
        "direction": "string (inbound | outbound)",
        "body": "string",
        "status": "string",
        "created_at": "string (ISO 8601)",
    },
}

# Which types each group uses (for scoped output)
_GROUP_TYPES: dict[str, list[str]] = {
    "messages":      ["Message"],
    "inboxes":       ["Inbox"],
    "threads":       ["Thread", "Message"],
    "domains":       ["Domain", "DnsRecord"],
    "search":        ["Thread"],
    "delivery":      ["DeliveryMetrics"],
    "sms":           ["SmsMessage"],
    "phone-numbers": ["PhoneNumber"],
    "webhooks":      [],
    "attachments":   [],
    "credits":       [],
    "dmarc":         [],
    "data":          [],
    "config":        [],
}


# ── Commands (full detail) ────────────────────────────────────────────────

_COMMANDS: dict[str, dict] = {
    # ── Domains ───────────────────────────────────────────────────────
    "domains.list": {
        "description": "List all domains in the organization",
        "method": "GET /v1/domains",
        "parameters": {},
        "returns": "Domain[]",
    },
    "domains.get": {
        "description": "Get a specific domain by ID",
        "method": "GET /v1/domains/{domain_id}",
        "parameters": {
            "domain_id": {"type": "string", "required": True},
        },
        "returns": "Domain",
    },
    "domains.create": {
        "description": "Add a custom domain to the organization",
        "method": "POST /v1/domains",
        "parameters": {
            "--name": {"type": "string", "required": True, "description": "Domain name (e.g. company.com)"},
            "--region": {"type": "string", "required": False, "description": "Region hint"},
        },
        "returns": "Domain",
    },
    "domains.verify": {
        "description": "Trigger DNS verification for a domain",
        "method": "POST /v1/domains/{domain_id}/verify",
        "parameters": {
            "domain_id": {"type": "string", "required": True},
        },
        "returns": "Domain",
    },
    "domains.records": {
        "description": "Get required DNS records (MX, SPF, DKIM, DMARC) for a domain",
        "method": "GET /v1/domains/{domain_id}/records",
        "parameters": {
            "domain_id": {"type": "string", "required": True},
        },
        "returns": "DnsRecord[]",
    },
    # ── Inboxes ──────────────────────────────────────────────────────
    "inboxes.list": {
        "description": "List all inboxes in the organization",
        "method": "GET /v1/inboxes",
        "parameters": {
            "--domain-id": {"type": "string", "required": False, "description": "Filter by domain"},
        },
        "returns": "Inbox[]",
    },
    "inboxes.get": {
        "description": "Get a specific inbox",
        "method": "GET /v1/inboxes/{inbox_id}",
        "parameters": {
            "inbox_id": {"type": "string", "required": True},
        },
        "returns": "Inbox",
    },
    "inboxes.create": {
        "description": "Create a new email inbox — instant, no verification needed",
        "method": "POST /v1/inboxes",
        "parameters": {
            "--local-part": {"type": "string", "required": True, "description": "Part before @ (e.g. support)"},
            "--domain-id": {"type": "string", "required": False, "description": "Domain ID (omit for commune.email)"},
            "--name": {"type": "string", "required": False, "description": "Display name"},
            "--webhook-url": {"type": "url", "required": False, "description": "URL to receive inbound emails"},
        },
        "returns": "Inbox",
    },
    "inboxes.update": {
        "description": "Update inbox settings",
        "method": "PATCH /v1/inboxes/{inbox_id}",
        "parameters": {
            "inbox_id": {"type": "string", "required": True},
            "--name": {"type": "string", "required": False},
            "--display-name": {"type": "string", "required": False},
        },
        "returns": "Inbox",
    },
    "inboxes.delete": {
        "description": "Permanently delete an inbox",
        "method": "DELETE /v1/domains/{domain_id}/inboxes/{inbox_id}",
        "parameters": {
            "--domain-id": {"type": "string", "required": True},
            "--inbox-id": {"type": "string", "required": True},
        },
        "returns": "confirmation",
    },
    "inboxes.set-webhook": {
        "description": "Set the webhook URL for inbound emails on an inbox",
        "method": "POST /v1/domains/{domain_id}/inboxes/{inbox_id}/webhook",
        "parameters": {
            "--domain-id": {"type": "string", "required": True},
            "--inbox-id": {"type": "string", "required": True},
            "--url": {"type": "url", "required": True, "description": "Webhook endpoint URL"},
            "--secret": {"type": "string", "required": False, "description": "HMAC-SHA256 signing secret"},
        },
        "returns": "Inbox",
    },
    "inboxes.extraction-schema.set": {
        "description": "Set AI extraction schema on an inbox (extracts structured JSON from inbound emails)",
        "method": "POST /v1/domains/{domain_id}/inboxes/{inbox_id}/extraction-schema",
        "parameters": {
            "--domain-id": {"type": "string", "required": True},
            "--inbox-id": {"type": "string", "required": True},
            "--name": {"type": "string", "required": True},
            "--schema": {"type": "json", "required": True, "description": "JSON Schema object"},
        },
        "returns": "schema confirmation",
    },
    # ── Messages ─────────────────────────────────────────────────────
    "messages.send": {
        "description": "Send an email. Pass --thread-id to reply in an existing thread.",
        "method": "POST /v1/messages/send",
        "parameters": {
            "--to": {"type": "string", "required": True, "description": "Recipient email (repeatable)"},
            "--subject": {"type": "string", "required": True, "description": "Subject line"},
            "--text": {"type": "string", "required": False, "description": "Plain text body. Use '-' for stdin."},
            "--html": {"type": "string", "required": False, "description": "HTML body"},
            "--from": {"type": "string", "required": False, "description": "Sender address (must be in your org)"},
            "--inbox-id": {"type": "string", "required": False},
            "--domain-id": {"type": "string", "required": False},
            "--cc": {"type": "string", "required": False, "description": "CC address (repeatable)"},
            "--bcc": {"type": "string", "required": False, "description": "BCC address (repeatable)"},
            "--reply-to": {"type": "string", "required": False},
            "--thread-id": {"type": "string", "required": False, "description": "Reply in this thread"},
        },
        "returns": "{ message_id, thread_id }",
    },
    "messages.list": {
        "description": "List messages with optional filters",
        "method": "GET /v1/messages",
        "parameters": {
            "--inbox-id": {"type": "string", "required": False},
            "--domain-id": {"type": "string", "required": False},
            "--sender": {"type": "string", "required": False},
            "--limit": {"type": "integer", "required": False, "default": 20},
            "--order": {"type": "string", "required": False, "enum": ["asc", "desc"]},
            "--before": {"type": "string (ISO 8601)", "required": False},
            "--after": {"type": "string (ISO 8601)", "required": False},
            "--cursor": {"type": "string", "required": False},
        },
        "returns": "Message[]",
    },
    # ── Threads ──────────────────────────────────────────────────────
    "threads.list": {
        "description": "List email threads",
        "method": "GET /v1/threads",
        "parameters": {
            "--inbox-id": {"type": "string", "required": False},
            "--domain-id": {"type": "string", "required": False},
            "--limit": {"type": "integer", "required": False, "default": 20},
            "--cursor": {"type": "string", "required": False},
            "--order": {"type": "string", "required": False, "enum": ["asc", "desc"]},
        },
        "returns": "Thread[]",
    },
    "threads.messages": {
        "description": "Get all messages in a thread",
        "method": "GET /v1/threads/{thread_id}/messages",
        "parameters": {
            "thread_id": {"type": "string", "required": True},
            "--limit": {"type": "integer", "required": False, "default": 50},
            "--order": {"type": "string", "required": False, "enum": ["asc", "desc"]},
        },
        "returns": "Message[]",
    },
    "threads.metadata": {
        "description": "Get thread metadata: status, tags, assignment, participants",
        "method": "GET /v1/threads/{thread_id}",
        "parameters": {
            "thread_id": {"type": "string", "required": True},
        },
        "returns": "Thread with metadata",
    },
    "threads.set-status": {
        "description": "Set thread triage status",
        "method": "PATCH /v1/threads/{thread_id}",
        "parameters": {
            "thread_id": {"type": "string", "required": True},
            "--status": {"type": "string", "required": True, "enum": ["open", "needs_reply", "waiting", "closed"]},
        },
        "returns": "Thread",
    },
    "threads.tags.add": {
        "description": "Add tags to a thread (additive)",
        "method": "POST /v1/threads/{thread_id}/tags",
        "parameters": {
            "thread_id": {"type": "string", "required": True},
            "tags": {"type": "string", "required": True, "description": "Comma-separated tags"},
        },
        "returns": "Thread",
    },
    "threads.tags.remove": {
        "description": "Remove tags from a thread",
        "method": "DELETE /v1/threads/{thread_id}/tags",
        "parameters": {
            "thread_id": {"type": "string", "required": True},
            "tags": {"type": "string", "required": True, "description": "Comma-separated tags"},
        },
        "returns": "Thread",
    },
    "threads.assign": {
        "description": "Assign a thread to a user or agent",
        "method": "PATCH /v1/threads/{thread_id}",
        "parameters": {
            "thread_id": {"type": "string", "required": True},
            "--to": {"type": "string", "required": False, "description": "Assignee (omit to unassign)"},
        },
        "returns": "Thread",
    },
    "threads.contacts": {
        "description": "List people extracted from email conversations",
        "method": "GET /api/graph (type=people)",
        "parameters": {},
        "returns": "Contact[]",
    },
    "threads.companies": {
        "description": "List companies inferred from email conversations",
        "method": "GET /api/graph (type=companies)",
        "parameters": {},
        "returns": "Company[]",
    },
    # ── Search ───────────────────────────────────────────────────────
    "search.threads": {
        "description": "Semantic full-text search across email threads",
        "method": "GET /v1/search/threads",
        "parameters": {
            "query": {"type": "string", "required": True, "description": "Natural language search query"},
            "--inbox-id": {"type": "string", "required": False},
            "--domain-id": {"type": "string", "required": False},
            "--limit": {"type": "integer", "required": False, "default": 10},
        },
        "returns": "Thread[]",
    },
    # ── Attachments ──────────────────────────────────────────────────
    "attachments.upload": {
        "description": "Upload a file as an email attachment",
        "method": "POST /v1/attachments/upload",
        "parameters": {
            "file": {"type": "file path", "required": True},
        },
        "returns": "{ attachment_id, filename, size }",
    },
    "attachments.url": {
        "description": "Get a presigned download URL for an attachment",
        "method": "GET /v1/attachments/{attachment_id}/url",
        "parameters": {
            "attachment_id": {"type": "string", "required": True},
            "--expires-in": {"type": "integer", "required": False, "description": "Seconds until URL expires"},
        },
        "returns": "{ url, expires_at }",
    },
    # ── Delivery ─────────────────────────────────────────────────────
    "delivery.metrics": {
        "description": "Get delivery metrics: sent, delivered, bounced, spam rate",
        "method": "GET /v1/delivery/metrics",
        "parameters": {
            "--domain-id": {"type": "string", "required": False},
            "--inbox-id": {"type": "string", "required": False},
            "--period": {"type": "string", "required": False, "enum": ["24h", "7d", "30d"], "default": "7d"},
        },
        "returns": "DeliveryMetrics",
    },
    "delivery.events": {
        "description": "List delivery events: sent, bounce, complaint, open, click",
        "method": "GET /v1/delivery/events",
        "parameters": {
            "--domain-id": {"type": "string", "required": False},
            "--inbox-id": {"type": "string", "required": False},
            "--message-id": {"type": "string", "required": False},
            "--event-type": {"type": "string", "required": False},
            "--limit": {"type": "integer", "required": False, "default": 20},
        },
        "returns": "DeliveryEvent[]",
    },
    "delivery.suppressions": {
        "description": "List suppressed addresses (bounces and spam complaints)",
        "method": "GET /v1/delivery/suppressions",
        "parameters": {
            "--domain-id": {"type": "string", "required": False},
            "--inbox-id": {"type": "string", "required": False},
            "--limit": {"type": "integer", "required": False, "default": 20},
        },
        "returns": "Suppression[]",
    },
    "delivery.check": {
        "description": "Check if an email address is suppressed before sending",
        "method": "GET /v1/delivery/suppressions",
        "parameters": {
            "address": {"type": "string", "required": True},
        },
        "returns": "{ suppressed: boolean, reason: string | null }",
    },
    # ── Webhooks ─────────────────────────────────────────────────────
    "webhooks.list": {
        "description": "List webhook delivery attempts",
        "method": "GET /v1/webhooks/deliveries",
        "parameters": {
            "--inbox-id": {"type": "string", "required": False},
            "--status": {"type": "string", "required": False},
            "--limit": {"type": "integer", "required": False, "default": 20},
        },
        "returns": "WebhookDelivery[]",
    },
    "webhooks.retry": {
        "description": "Retry a failed webhook delivery",
        "method": "POST /v1/webhooks/deliveries/{delivery_id}/retry",
        "parameters": {
            "delivery_id": {"type": "string", "required": True},
        },
        "returns": "WebhookDelivery",
    },
    "webhooks.health": {
        "description": "Get overall webhook delivery health stats",
        "method": "GET /v1/webhooks/health",
        "parameters": {},
        "returns": "{ success_rate, total, failed, avg_latency_ms }",
    },
    # ── DMARC ────────────────────────────────────────────────────────
    "dmarc.reports": {
        "description": "List DMARC aggregate reports for a domain",
        "method": "GET /v1/dmarc/reports",
        "parameters": {
            "--domain": {"type": "string", "required": True},
            "--limit": {"type": "integer", "required": False},
        },
        "returns": "DmarcReport[]",
    },
    "dmarc.summary": {
        "description": "Get DMARC compliance summary for a domain",
        "method": "GET /v1/dmarc/summary",
        "parameters": {
            "--domain": {"type": "string", "required": True},
            "--days": {"type": "integer", "required": False},
        },
        "returns": "DmarcSummary",
    },
    # ── Phone Numbers ────────────────────────────────────────────────
    "phone-numbers.list": {
        "description": "List all provisioned phone numbers",
        "method": "GET /v1/phone-numbers",
        "parameters": {},
        "returns": "PhoneNumber[]",
    },
    "phone-numbers.get": {
        "description": "Get a specific phone number",
        "method": "GET /v1/phone-numbers/{phone_number_id}",
        "parameters": {
            "phone_number_id": {"type": "string", "required": True},
        },
        "returns": "PhoneNumber",
    },
    "phone-numbers.available": {
        "description": "Browse available phone numbers before purchasing",
        "method": "GET /v1/phone-numbers/available",
        "parameters": {
            "--type": {"type": "string", "required": False, "enum": ["TollFree", "Local"]},
            "--country": {"type": "string", "required": False},
            "--limit": {"type": "integer", "required": False},
        },
        "returns": "PhoneNumber[]",
    },
    "phone-numbers.provision": {
        "description": "Purchase and activate a phone number",
        "method": "POST /v1/phone-numbers",
        "parameters": {
            "--phone-number": {"type": "string (E.164)", "required": False},
            "--type": {"type": "string", "required": False, "enum": ["TollFree", "Local"]},
            "--friendly-name": {"type": "string", "required": False},
        },
        "returns": "PhoneNumber",
    },
    # ── SMS ──────────────────────────────────────────────────────────
    "sms.send": {
        "description": "Send an SMS message",
        "method": "POST /v1/sms/send",
        "parameters": {
            "--to": {"type": "string (E.164)", "required": True},
            "--body": {"type": "string", "required": True},
            "--phone-number-id": {"type": "string", "required": False},
        },
        "returns": "{ message_id, thread_id, status, credits_charged }",
    },
    "sms.conversations": {
        "description": "List SMS conversation summaries",
        "method": "GET /v1/sms/conversations",
        "parameters": {
            "--phone-number-id": {"type": "string", "required": False},
            "--limit": {"type": "integer", "required": False},
        },
        "returns": "SmsConversation[]",
    },
    "sms.thread": {
        "description": "Get all messages in an SMS thread",
        "method": "GET /v1/sms/threads/{remote_number}",
        "parameters": {
            "remote_number": {"type": "string (E.164)", "required": True},
            "--phone-number-id": {"type": "string", "required": True},
        },
        "returns": "SmsMessage[]",
    },
    "sms.search": {
        "description": "Semantic search across SMS history",
        "method": "GET /v1/sms/search",
        "parameters": {
            "query": {"type": "string", "required": True},
            "--phone-number-id": {"type": "string", "required": False},
            "--limit": {"type": "integer", "required": False},
        },
        "returns": "SmsMessage[]",
    },
    # ── Credits ──────────────────────────────────────────────────────
    "credits.balance": {
        "description": "Get current credit balance and usage",
        "method": "GET /v1/credits/balance",
        "parameters": {},
        "returns": "{ available, used, total }",
    },
    "credits.bundles": {
        "description": "List purchasable credit packages",
        "method": "GET /v1/credits/bundles",
        "parameters": {},
        "returns": "CreditBundle[]",
    },
    # ── Data ─────────────────────────────────────────────────────────
    "data.delete-request": {
        "description": "Initiate a data deletion request (GDPR). Returns a confirmation token.",
        "method": "POST /v1/data/deletion-request",
        "parameters": {
            "--email": {"type": "string", "required": True, "description": "Email address to delete data for"},
        },
        "returns": "{ id, status, token }",
    },
    "data.delete-confirm": {
        "description": "Confirm and execute a data deletion request. Irreversible.",
        "method": "POST /v1/data/deletion-request/{id}/confirm",
        "parameters": {
            "id": {"type": "string", "required": True},
        },
        "returns": "{ id, status }",
    },
    # ── Config ───────────────────────────────────────────────────────
    "config.register": {
        "description": "Self-register as an agent using Ed25519 keypair. No dashboard required.",
        "method": "POST /v1/auth/agent-register → /v1/auth/agent-verify",
        "parameters": {
            "--name": {"type": "string", "required": True, "description": "Agent display name"},
            "--purpose": {"type": "string", "required": True, "description": "What this agent does (1-3 sentences)"},
            "--org-name": {"type": "string", "required": True, "description": "Organization name"},
            "--org-slug": {"type": "string", "required": True, "description": "Unique slug → becomes slug@commune.email"},
        },
        "returns": "{ agent_id, inbox_email }",
    },
    "config.status": {
        "description": "Show org details, tier, and basic stats",
        "method": "GET /v1/agent/org",
        "parameters": {},
        "returns": "{ org_name, org_id, tier, status }",
    },
    "config.keys.list": {
        "description": "List all API keys for the org",
        "method": "GET /v1/agent/api-keys",
        "parameters": {},
        "returns": "ApiKey[]",
    },
    "config.keys.revoke": {
        "description": "Revoke an API key. Immediate and irreversible.",
        "method": "DELETE /v1/agent/api-keys/{key_id}",
        "parameters": {
            "key_id": {"type": "string", "required": True},
        },
        "returns": "confirmation",
    },
}


# ── Output builders ───────────────────────────────────────────────────────


def _build_index() -> dict:
    """Tiny top-level index. ~25 lines of JSON."""
    return {
        "commune": __version__,
        "auth": "COMMUNE_API_KEY env var or commune config register",
        "output": "JSON to stdout, errors to stderr, exit codes 0-5",
        "pagination": "cursor-based: --limit, --cursor, --order",
        "groups": _GROUPS,
        "usage": "commune describe <group> for commands, commune describe <group.command> for details",
    }


def _build_group(group: str) -> dict:
    """One group with all its commands and relevant types."""
    commands = {k: v for k, v in _COMMANDS.items() if k.startswith(group + ".")}
    types = {}
    for type_name in _GROUP_TYPES.get(group, []):
        if type_name in _TYPES:
            types[type_name] = _TYPES[type_name]

    result: dict = {
        "group": group,
        "description": _GROUPS.get(group, ""),
        "commands": commands,
    }
    if types:
        result["types"] = types
    return result


def _build_command(cmd_key: str) -> dict:
    """Single command with full detail."""
    cmd = _COMMANDS.get(cmd_key)
    if not cmd:
        return {"error": f"Unknown command: {cmd_key}", "available": sorted(_COMMANDS.keys())}
    return {"command": cmd_key, **cmd}


def _build_full() -> dict:
    """Full manifest (for caching / offline use)."""
    return {
        "name": "commune",
        "version": __version__,
        "description": "Email and SMS infrastructure for AI agents",
        "base_url": "https://api.commune.email",
        "auth": {
            "method": "bearer_token",
            "env_var": "COMMUNE_API_KEY",
            "key_prefix": "comm_",
            "setup": "commune config register --name <name> --purpose <purpose> --org-name <org> --org-slug <slug>",
        },
        "output_contract": {
            "list_envelope": {"data": "array", "has_more": "boolean", "next_cursor": "string | null"},
            "error_envelope": {"error": {"code": "string", "message": "string", "status_code": "integer"}},
            "exit_codes": {"0": "success", "1": "error", "2": "auth", "3": "not found", "4": "rate limit", "5": "network"},
        },
        "groups": _GROUPS,
        "commands": _COMMANDS,
        "types": _TYPES,
        "pagination": {"limit": "1-100 (default 20)", "cursor": "from next_cursor", "order": "asc | desc"},
    }


# ── Animated TTY display ─────────────────────────────────────────────────


def _show_describe_tty(target: Optional[str] = None) -> None:
    """Animated display for TTY."""
    import time

    from rich.console import Console, Group
    from rich.live import Live
    from rich.padding import Padding
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    console = Console(highlight=False)

    header = Text(no_wrap=True)
    header.append("  COMMUNE", style="bold rgb(0,210,255)")
    header.append("  ·  ", style="dim")

    if target is None:
        header.append("API Surface", style="italic white")
        header.append(f"  v{__version__}", style="bold yellow")

        tbl = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        tbl.add_column("group", style="bold bright_cyan", no_wrap=True, min_width=16)
        tbl.add_column("sep", style="dim", no_wrap=True, width=1)
        tbl.add_column("desc", style="dim white")
        for group, desc in _GROUPS.items():
            tbl.add_row(group, "·", desc)

        def build_frame(stage: int) -> Group:
            parts: list = []
            parts.append(Padding(Rule(characters="─", style="rgb(0,178,255)"), (0, 2, 0, 2)))
            parts.append(Padding(header, (0, 2, 0, 2)))
            if stage >= 1:
                parts.append(Padding(Rule(characters="─", style="dim"), (1, 2, 0, 2)))
                parts.append(Padding(tbl, (0, 2, 0, 2)))
            if stage >= 2:
                foot = Text()
                foot.append("\n  commune describe <group>", style="bold cyan")
                foot.append("  to drill down", style="dim")
                parts.append(Padding(foot, (0, 2, 0, 2)))
            return Group(*parts)

        if not console.is_terminal:
            console.print(build_frame(2))
            return

        with Live(build_frame(0), console=console, refresh_per_second=30, transient=False) as live:
            time.sleep(0.08)
            live.update(build_frame(1))
            time.sleep(0.1)
            live.update(build_frame(2))

    elif "." in target:
        # Single command
        cmd = _COMMANDS.get(target)
        if not cmd:
            console.print(f"[red]Unknown command:[/red] {target}")
            return

        header.append(target, style="bold white")
        console.print(Rule(characters="─", style="rgb(0,178,255)"))
        console.print(Padding(header, (0, 2, 0, 2)))
        console.print(Padding(Text(cmd["description"], style="dim"), (0, 2, 0, 4)))
        console.print(Padding(Text(cmd["method"], style="bold dim"), (0, 2, 0, 4)))
        if cmd["parameters"]:
            console.print()
            tbl = Table(box=None, show_header=True, padding=(0, 1))
            tbl.add_column("Parameter", style="bold bright_cyan")
            tbl.add_column("Type", style="dim")
            tbl.add_column("Required", style="dim")
            tbl.add_column("Description", style="dim white")
            for pname, pinfo in cmd["parameters"].items():
                req = "yes" if pinfo.get("required") else ""
                desc = pinfo.get("description", "")
                if pinfo.get("enum"):
                    desc += f" [{' | '.join(pinfo['enum'])}]"
                if pinfo.get("default") is not None:
                    desc += f" (default: {pinfo['default']})"
                tbl.add_row(pname, pinfo.get("type", ""), req, desc)
            console.print(Padding(tbl, (0, 2, 0, 4)))
        console.print(Padding(Text(f"Returns: {cmd['returns']}", style="dim"), (1, 2, 0, 4)))

    else:
        # Group
        group = target
        if group not in _GROUPS:
            console.print(f"[red]Unknown group:[/red] {group}")
            console.print(f"[dim]Available: {', '.join(_GROUPS.keys())}[/dim]")
            return

        header.append(group, style="bold white")
        header.append(f"  {_GROUPS[group]}", style="dim")

        commands = {k: v for k, v in _COMMANDS.items() if k.startswith(group + ".")}
        tbl = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        tbl.add_column("cmd", style="bold bright_cyan", no_wrap=True, min_width=28)
        tbl.add_column("desc", style="dim white")
        for cname, cinfo in commands.items():
            tbl.add_row(cname, cinfo["description"])

        console.print(Rule(characters="─", style="rgb(0,178,255)"))
        console.print(Padding(header, (0, 2, 0, 2)))
        console.print(Padding(Rule(characters="─", style="dim"), (1, 2, 0, 2)))
        console.print(Padding(tbl, (0, 2, 0, 2)))
        foot = Text()
        foot.append(f"\n  commune describe {group}.<command>", style="bold cyan")
        foot.append("  for parameters and details", style="dim")
        console.print(Padding(foot, (0, 2, 0, 2)))


# ── Command ───────────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def describe(
    ctx: typer.Context,
    target: Optional[str] = typer.Argument(
        None,
        help="What to describe: nothing (index), group name, or group.command.",
    ),
    full: bool = typer.Option(False, "--full", help="Output the complete manifest (all commands, types, everything)."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Hierarchical API surface manifest — progressive disclosure.

    \b
    commune describe                  Index of all groups (~20 lines)
    commune describe messages         Commands in the messages group
    commune describe messages.send    Full detail for one command
    commune describe --full           Complete manifest (all commands + types)
    """
    from ..state import AppState

    state: AppState = ctx.obj or AppState()
    use_json = json_output or state.should_json()

    if full:
        print_json(_build_full())
        return

    if target is None:
        if use_json:
            print_json(_build_index())
        else:
            _show_describe_tty()
        return

    # Check if it's a specific command (has a dot)
    if "." in target:
        if use_json:
            print_json(_build_command(target))
        else:
            _show_describe_tty(target)
        return

    # Must be a group name
    if target in _GROUPS:
        if use_json:
            print_json(_build_group(target))
        else:
            _show_describe_tty(target)
        return

    # Unknown
    if use_json:
        print_json({"error": f"Unknown group or command: {target}", "available_groups": list(_GROUPS.keys())})
    else:
        from rich.console import Console
        Console(highlight=False).print(f"[red]Unknown:[/red] {target}")
        Console(highlight=False).print(f"[dim]Groups: {', '.join(_GROUPS.keys())}[/dim]")
