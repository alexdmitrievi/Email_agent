# Настройка Google Cloud для Email Agent

Пошаговая инструкция от создания проекта до рабочего агента.

---

## Шаг 1: Создание Google Cloud проекта

1. Откройте [console.cloud.google.com](https://console.cloud.google.com)
2. Войдите аккаунтом Google Workspace (тем, с которого отправляются письма через Coldy)
3. Вверху нажмите на выпадающий список проектов → **"New Project"**
4. Название: `email-agent` (или любое другое)
5. Нажмите **Create**
6. Дождитесь создания и переключитесь на этот проект

**Запишите Project ID** — он понадобится позже (например: `email-agent-123456`)

---

## Шаг 2: Включение API

Перейдите в **APIs & Services → Library** и включите (кнопка "Enable") каждый из этих API:

1. **Gmail API** — `https://console.cloud.google.com/apis/library/gmail.googleapis.com`
2. **Google Sheets API** — `https://console.cloud.google.com/apis/library/sheets.googleapis.com`
3. **Google Calendar API** — `https://console.cloud.google.com/apis/library/calendar-json.googleapis.com`
4. **Google Drive API** — `https://console.cloud.google.com/apis/library/drive.googleapis.com`
5. **Cloud Pub/Sub API** — `https://console.cloud.google.com/apis/library/pubsub.googleapis.com`

Или через gcloud CLI (если установлен):

```bash
gcloud services enable \
  gmail.googleapis.com \
  sheets.googleapis.com \
  calendar-json.googleapis.com \
  drive.googleapis.com \
  pubsub.googleapis.com
```

---

## Шаг 3: Создание Service Account

1. Перейдите в **IAM & Admin → Service Accounts**
   `https://console.cloud.google.com/iam-admin/serviceaccounts`
2. Нажмите **"+ Create Service Account"**
3. Заполните:
   - Name: `email-agent`
   - Description: `Service account for Email Agent`
4. Нажмите **Create and Continue**
5. Роль: пропустите (Skip)
6. Нажмите **Done**

### Создание ключа:
1. Кликните на созданный Service Account
2. Вкладка **Keys → Add Key → Create New Key**
3. Формат: **JSON**
4. Скачается файл — **переименуйте его в `service_account.json`**
5. Положите в `credentials/service_account.json` в папке проекта

**Запишите email Service Account** — он выглядит как:
`email-agent@email-agent-123456.iam.gserviceaccount.com`

---

## Шаг 4: Domain-Wide Delegation (ВАЖНО!)

Это даёт Service Account право действовать от имени пользователей Google Workspace.

### 4a. Включить делегирование в Google Cloud:
1. Перейдите в **IAM & Admin → Service Accounts**
2. Кликните на ваш Service Account
3. Нажмите **"Show Advanced Settings"** (или три точки → Edit)
4. Поставьте галочку **"Enable Google Workspace domain-wide delegation"**
5. Если нет этой опции — нажмите **"Manage domain-wide delegation"**
6. Сохраните

**Запишите Client ID** (число, например: `117234567890123456789`)

### 4b. Настроить в Google Workspace Admin:
1. Откройте [admin.google.com](https://admin.google.com)
2. Войдите как администратор Google Workspace
3. Перейдите в **Security → Access and data control → API controls**
4. Нажмите **"Manage domain-wide delegation"**
5. Нажмите **"Add new"**
6. Заполните:
   - **Client ID**: тот, что записали выше
   - **OAuth Scopes** (вставьте ВСЕ через запятую, одной строкой):

```
https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/drive.readonly
```

7. Нажмите **Authorize**

---

## Шаг 5: Настройка Pub/Sub

### 5a. Создать Topic:
1. Перейдите в **Pub/Sub → Topics**
   `https://console.cloud.google.com/cloudpubsub/topic/list`
2. Нажмите **"+ Create Topic"**
3. Topic ID: `gmail-push`
4. Снимите галочку "Add a default subscription"
5. Нажмите **Create**

Полное имя топика: `projects/YOUR_PROJECT_ID/topics/gmail-push`

### 5b. Дать Gmail права на публикацию:
1. Кликните на созданный topic `gmail-push`
2. Справа нажмите **"Show Info Panel"** (или вкладка Permissions)
3. Нажмите **"Add Principal"**
4. В поле "New principals" введите: `gmail-api-push@system.gserviceaccount.com`
5. Роль: **Pub/Sub Publisher**
6. Нажмите **Save**

Или через gcloud CLI:

```bash
# Создать topic
gcloud pubsub topics create gmail-push

# Дать Gmail права на публикацию
gcloud pubsub topics add-iam-policy-binding gmail-push \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

### 5c. Создать Push Subscription:
1. Перейдите в **Pub/Sub → Subscriptions**
2. Нажмите **"+ Create Subscription"**
3. Заполните:
   - Subscription ID: `gmail-push-sub`
   - Select a Cloud Pub/Sub topic: `gmail-push`
   - Delivery type: **Push**
   - Endpoint URL: `https://ВАШ-ДОМЕН.com/webhooks/gmail`
   - (опционально) Authentication: None (или добавьте verification token)
4. Нажмите **Create**

> **ВАЖНО:** URL должен быть HTTPS с валидным SSL-сертификатом. Pub/Sub не работает с HTTP или self-signed сертификатами.

Или через gcloud:

```bash
gcloud pubsub subscriptions create gmail-push-sub \
  --topic=gmail-push \
  --push-endpoint="https://ваш-домен.com/webhooks/gmail"
```

---

## Шаг 6: Создание Google Sheet (CRM)

1. Откройте [sheets.google.com](https://sheets.google.com)
2. Создайте новую таблицу
3. Переименуйте лист в **`Leads`** (именно так, с большой буквы)
4. В первую строку впишите заголовки:

| A | B | C | D | E | F | G | H | I |
|---|---|---|---|---|---|---|---|---|
| Email | Name | Company | Stage | Last Contact | Notes | Telegram | Thread ID | Follow-up Count |

5. **Дайте доступ Service Account:**
   - Нажмите "Share" (Поделиться)
   - Введите email Service Account: `email-agent@email-agent-123456.iam.gserviceaccount.com`
   - Роль: **Editor**
   - Нажмите Share

6. **Скопируйте Sheet ID** из URL:
   `https://docs.google.com/spreadsheets/d/ЭТОТ_ID_НУЖЕН/edit`

---

## Шаг 7: Заполнение .env

```bash
cd Email_agent
cp .env.example .env
```

Откройте `.env` и заполните:

```env
# OpenAI
OPENAI_API_KEY=sk-ваш-ключ-openai

# Google
GOOGLE_SERVICE_ACCOUNT_FILE=credentials/service_account.json
GOOGLE_DELEGATED_EMAIL=ваша-почта@вашдомен.com     # почта Google Workspace
GOOGLE_PUBSUB_TOPIC=projects/ВАШ-PROJECT-ID/topics/gmail-push
GOOGLE_PUBSUB_VERIFICATION_TOKEN=любая-случайная-строка

# Google Sheets
GOOGLE_SHEET_ID=ID-из-URL-таблицы

# Telegram (заполните после создания бота)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_MANAGER_CHAT_ID=...
TELEGRAM_BOT_LINK=https://t.me/ваш_бот

# n8n
N8N_API_URL=http://localhost:5678/api/v1
N8N_API_KEY=ваш-n8n-api-key

# Business config
BUSINESS_CONFIG_PATH=configs/business.yaml

# Database + Redis (если Docker)
DATABASE_URL=postgresql+asyncpg://agent:agent@postgres:5432/email_agent
REDIS_URL=redis://redis:6379/0

# Admin
ADMIN_SECRET=придумайте-длинный-случайный-токен

# App
APP_BASE_URL=https://ваш-домен.com
```

---

## Шаг 8: Проверка

После заполнения .env и `docker-compose up -d`:

1. **Health check:**
```bash
curl https://ваш-домен.com/health
# Ожидаемый ответ: {"status":"ok","config":"ok","database":"ok","redis":"ok","gmail":"ok"}
```

2. **Тест Gmail watch:**
```bash
curl -X POST https://ваш-домен.com/webhooks/gmail/renew-watch
# Ожидаемый ответ: {"status":"ok","watch":{...}}
```

3. **Тест отправки:** отправьте тестовое письмо на вашу Google Workspace почту и проверьте:
   - В логах Docker: `docker-compose logs -f agent`
   - В Google Sheet: должна появиться новая строка с лидом

---

## Частые проблемы

| Проблема | Решение |
|----------|---------|
| `403 Forbidden` при Gmail API | Domain-wide delegation не настроен (Шаг 4b) |
| `404 Not Found` при Pub/Sub | Неправильный Topic name в .env |
| Pub/Sub не приходят уведомления | Push URL не HTTPS, или SSL невалидный |
| `Sheets API: permission denied` | Service Account не добавлен как Editor в таблицу |
| Gmail watch возвращает ошибку | `gmail-api-push@system.gserviceaccount.com` не добавлен как Publisher в topic |
