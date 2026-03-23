"""Multimodal attachment processing — GPT-4o vision for images/docs."""

import base64
import logging
from pathlib import Path

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# Supported image types for GPT-4o vision
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
SUPPORTED_TYPES = IMAGE_TYPES | {".pdf"}


async def analyze_attachment(file_path: str, context: str = "") -> str:
    """Analyze an attachment using GPT-4o vision (for images) or text extraction.

    Returns a brief Russian-language summary of the attachment content.
    """
    path = Path(file_path)
    if not path.exists():
        return ""

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_TYPES:
        return f"[Файл: {path.name}]"

    if suffix in IMAGE_TYPES:
        return await _analyze_image(path, context)

    return f"[Документ: {path.name}]"


async def _analyze_image(path: Path, context: str) -> str:
    """Analyze an image using GPT-4o vision."""
    with open(path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    suffix = path.suffix.lower().lstrip(".")
    mime = f"image/{suffix}" if suffix != "jpg" else "image/jpeg"

    system_msg = (
        "Ты — помощник менеджера по продажам. Клиент прислал изображение. "
        "Кратко опиши что на нём (2-3 предложения на русском). "
        "Если это чертёж, план помещения или фото интерьера — отметь это."
    )
    if context:
        system_msg += f"\nКонтекст переписки: {context}"

    response = await _client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_data}"}},
                    {"type": "text", "text": "Опиши это изображение кратко."},
                ],
            },
        ],
        max_tokens=200,
    )

    summary = response.choices[0].message.content.strip()
    logger.info("Image analysis for %s: %s", path.name, summary[:100])
    return summary


async def describe_attachments(attachments: list[dict], context: str = "") -> str:
    """Analyze multiple attachments and return combined summary.

    attachments: list of {"filename": str, "path": str}
    """
    if not attachments:
        return ""

    summaries = []
    for att in attachments:
        summary = await analyze_attachment(att["path"], context)
        if summary:
            summaries.append(f"- {att['filename']}: {summary}")

    if summaries:
        return "Клиент приложил файлы:\n" + "\n".join(summaries)
    return ""
