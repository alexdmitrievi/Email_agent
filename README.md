# Email Agent

AI-агент для автоматизации email-продаж мебельной компании.

## Что делает

- Подхватывает диалог после холодной рассылки Coldy (3 письма)
- Классифицирует ответы клиентов через OpenAI GPT-4o
- Ведёт клиента по воронке: интерес → портфолио → обсуждение → передача менеджеру
- Отправляет PDF-портфолио и письма с HTML-подписью через Gmail API
- Продолжает общение в Telegram
- Отслеживает лидов в Google Sheets
- Автоматически отправляет follow-up через n8n

## Стек

- Python 3.12 + FastAPI
- OpenAI GPT-4o
- Gmail API (Google Workspace)
- Google Sheets API
- Telegram Bot API
- n8n (планировщик)
- Docker

## Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone https://github.com/alexdmitrievi/Email_agent.git
cd Email_agent

# 2. Скопировать и заполнить .env
cp .env.example .env

# 3. Положить credentials
# - credentials/service_account.json (Google Service Account)
# - assets/portfolio.pdf (PDF-портфолио)

# 4. Запустить
docker-compose up -d --build

# Или локально:
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Тесты

```bash
pytest tests/ -v
```

## API Endpoints

| Endpoint | Метод | Описание |
|---|---|---|
| `/health` | GET | Health check |
| `/webhooks/gmail` | POST | Gmail Pub/Sub push notifications |
| `/webhooks/telegram` | POST | Telegram bot webhook |
| `/webhooks/gmail/renew-watch` | POST | Обновление Gmail watch (для n8n) |
| `/follow-ups` | POST | Запуск follow-up рассылки (для n8n) |

## Воронка

```
NEW_REPLY → INTERESTED → PORTFOLIO_SENT → IN_DISCUSSION → HANDOFF_TO_MANAGER → ORDER
```
