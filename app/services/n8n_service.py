"""
n8n integration service.

n8n handles scheduled tasks via its own cron triggers:
1. Gmail watch renewal (every 6 days) → POST /webhooks/gmail/renew-watch
2. Daily follow-ups (10:00 MSK) → POST /follow-ups
3. Daily summary to manager (18:00 MSK) → reads Google Sheets + sends Telegram

This module provides a thin HTTP client for programmatic n8n API calls if needed.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def list_workflows() -> list[dict]:
    """List all n8n workflows."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.N8N_API_URL}/workflows",
            headers={"X-N8N-API-KEY": settings.N8N_API_KEY},
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


async def activate_workflow(workflow_id: str) -> dict:
    """Activate a workflow by ID."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.N8N_API_URL}/workflows/{workflow_id}/activate",
            headers={"X-N8N-API-KEY": settings.N8N_API_KEY},
        )
        resp.raise_for_status()
        return resp.json()


async def execute_workflow(workflow_id: str, payload: dict | None = None) -> dict:
    """Manually trigger a workflow execution."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.N8N_API_URL}/workflows/{workflow_id}/run",
            headers={"X-N8N-API-KEY": settings.N8N_API_KEY},
            json=payload or {},
        )
        resp.raise_for_status()
        return resp.json()
