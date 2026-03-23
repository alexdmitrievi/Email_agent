# Email Agent — Универсальный AI-агент для email-продаж

AI-агент, который автоматизирует email-переписку с клиентами после холодной рассылки. Ведёт клиента по воронке от первого ответа до конверсии в заказ.

**Универсальный:** смена бизнес-ниши = смена одного YAML-файла конфигурации.

## Возможности

- Классификация ответов клиентов через OpenAI GPT-4o
- Автоматические ответы по стадиям воронки
- Отправка PDF-материалов (портфолио, КП, кейсы)
- Продолжение диалога в Telegram
- Бронирование встреч через Google Calendar
- CRM в Google Sheets
- Follow-up для неактивных лидов через n8n
- Уведомление менеджера при готовности клиента

## Готовые конфиги

| Ниша | Файл | Воронка |
|------|------|---------|
| Мебель на заказ | `configs/examples/furniture_ru.yaml` | NEW_REPLY → INTERESTED → MATERIALS_SENT → IN_DISCUSSION → HANDOFF |
| Строительство | `configs/examples/construction_ru.yaml` | NEW_REPLY → INTERESTED → KP_SENT → ESTIMATE_SCHEDULED → IN_DISCUSSION → HANDOFF |
| B2B-консалтинг | `configs/examples/consulting_ru.yaml` | NEW_REPLY → INTERESTED → CASE_STUDY_SENT → DEMO_SCHEDULED → IN_DISCUSSION → HANDOFF |

## Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/alexdmitrievi/Email_agent.git
cd Email_agent

# 2. Скопировать и заполнить .env
cp .env.example .env

# 3. Выбрать бизнес-конфиг
cp configs/examples/furniture_ru.yaml configs/business.yaml
# Или создать свой по шаблону

# 4. Положить credentials
# - credentials/service_account.json (Google Service Account)
# - assets/portfolio.pdf (материалы для клиентов)

# 5. Запустить
docker-compose up -d --build

# Или локально:
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Создание своего конфига

Скопируйте любой пример из `configs/examples/` и измените:

1. **business** — название, описание, контакты
2. **products** — ваши товары/услуги
3. **funnel.stages** — стадии воронки (можно добавить/удалить)
4. **funnel.transitions** — правила переходов между стадиями
5. **stage_instructions** — инструкции AI для каждой стадии
6. **handoff.telegram_keywords** — ключевые слова для передачи менеджеру
7. **tone** — стиль общения
8. **telegram** — приветственное сообщение и подтверждение передачи

## Тесты

```bash
pytest tests/ -v
```

## API Endpoints

| Endpoint | Метод | Описание |
|---|---|---|
| `/health` | GET | Health check |
| `/webhooks/gmail` | POST | Gmail Pub/Sub push |
| `/webhooks/telegram` | POST | Telegram bot webhook |
| `/webhooks/gmail/renew-watch` | POST | Обновление Gmail watch (n8n) |
| `/follow-ups` | POST | Follow-up рассылка (n8n) |

## Стек

- Python 3.12 + FastAPI
- OpenAI GPT-4o
- Gmail API + Google Sheets + Google Calendar + Google Drive
- Telegram Bot API
- n8n (планировщик)
- Docker
