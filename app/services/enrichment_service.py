"""Lead enrichment — extract company data from email domain."""

import logging

import httpx
from sqlalchemy import select

from app.config import settings
from app.db.models import Lead
from app.db.session import async_session

logger = logging.getLogger(__name__)


async def enrich_lead_data(lead_id: int) -> None:
    """Enrich a lead using publicly available data from their email domain."""
    if not settings.ENRICHMENT_ENABLED:
        return

    async with async_session() as session:
        result = await session.execute(select(Lead).where(Lead.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead or not lead.email:
            return

        domain = lead.email.split("@")[-1]

        # Skip free email providers
        free_providers = {"gmail.com", "yahoo.com", "hotmail.com", "mail.ru", "yandex.ru", "outlook.com"}
        if domain in free_providers:
            logger.debug("Skipping enrichment for free email: %s", lead.email)
            return

        # Try to fetch company info from website
        try:
            info = await _fetch_domain_info(domain)
            if info.get("title"):
                lead.company = lead.company or info["title"]
            if info.get("description"):
                lead.industry = info.get("industry", "")
            lead.website = lead.website or f"https://{domain}"
            await session.commit()
            logger.info("Enriched lead %s: company=%s", lead.email, lead.company)
        except Exception as e:
            logger.warning("Enrichment failed for %s: %s", domain, e)


async def _fetch_domain_info(domain: str) -> dict:
    """Fetch basic info from a domain's homepage."""
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        resp = await client.get(f"https://{domain}")
        resp.raise_for_status()
        html = resp.text[:5000]

        # Extract title
        title = ""
        if "<title>" in html.lower():
            start = html.lower().index("<title>") + 7
            end = html.lower().index("</title>", start)
            title = html[start:end].strip()

        return {"title": title, "domain": domain}
