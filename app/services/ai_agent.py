import json
import logging
from pathlib import Path

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
_prompts_dir = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_prompts_dir / name).read_text(encoding="utf-8")


# Stage-specific instructions for response generation
STAGE_INSTRUCTIONS = {
    "NEW_REPLY": "Поблагодари за ответ, представься кратко, задай уточняющий вопрос о потребностях клиента.",
    "INTERESTED": "Предложи отправить портфолио с релевантными примерами. Спроси, какой тип мебели интересует больше всего.",
    "PORTFOLIO_SENT": "Портфолио уже отправлено. Спроси, успел ли клиент ознакомиться. Предложи ответить на вопросы по конкретным позициям.",
    "IN_DISCUSSION": "Продолжай обсуждение. Если это 3+ обмен, естественно предложи продолжить в Telegram для оперативности: '{telegram_link}'. Если клиент готов — предложи подключить менеджера.",
    "HANDOFF_TO_MANAGER": "Подтверди, что персональный менеджер свяжется в ближайшее время. Спроси, удобнее ли по телефону, email или в Telegram.",
}


async def classify_reply(email_body: str) -> dict:
    """Classify an incoming email reply into a category."""
    prompt = _load_prompt("classify_reply.txt").format(email_body=email_body)

    response = await _client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    text = response.choices[0].message.content
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse classification JSON: %s", text)
        result = {"category": "INTERESTED", "confidence": 0.5, "reasoning": "parse_error"}

    logger.info("Classified reply: %s", result)
    return result


async def generate_response(
    stage: str,
    lead_info: dict,
    thread_history: str,
    exchange_count: int,
) -> str:
    """Generate an email reply based on the current funnel stage."""
    system_prompt = _load_prompt("system_prompt.txt").format(
        company_name=settings.COMPANY_NAME
    )

    stage_instructions = STAGE_INSTRUCTIONS.get(stage, STAGE_INSTRUCTIONS["IN_DISCUSSION"])
    if "{telegram_link}" in stage_instructions:
        stage_instructions = stage_instructions.replace(
            "{telegram_link}", settings.TELEGRAM_BOT_LINK
        )

    lead_info_str = ", ".join(f"{k}: {v}" for k, v in lead_info.items() if v)

    user_prompt = _load_prompt("generate_response.txt").format(
        stage=stage,
        lead_info=lead_info_str,
        exchange_count=exchange_count,
        thread_history=thread_history,
        stage_instructions=stage_instructions,
    )

    response = await _client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=500,
    )

    reply = response.choices[0].message.content.strip()
    logger.info("Generated response for stage %s (%d chars)", stage, len(reply))
    return reply


async def generate_telegram_response(
    lead_info: dict,
    conversation_history: list[dict],
) -> str:
    """Generate a Telegram message reply."""
    system_prompt = _load_prompt("system_prompt.txt").format(
        company_name=settings.COMPANY_NAME
    )
    system_prompt += "\n\nСейчас ты общаешься в Telegram. Будь ещё более кратким — 1-3 предложения. Используй неформальный, но уважительный тон."

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)

    response = await _client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=300,
    )

    return response.choices[0].message.content.strip()
