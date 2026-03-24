#!/bin/bash
# =============================================================================
# Автоматическая настройка Google Cloud для Email Agent
# =============================================================================
# Требования: установленный gcloud CLI (https://cloud.google.com/sdk/docs/install)
#
# Использование:
#   chmod +x scripts/setup_gcloud.sh
#   ./scripts/setup_gcloud.sh
#
# Этот скрипт автоматизирует шаги 1-5 из docs/google_cloud_setup.md
# Шаг 4b (Domain-Wide Delegation в admin.google.com) нужно сделать вручную!
# =============================================================================

set -euo pipefail

# ---- Настройки (ИЗМЕНИТЕ ПОД СЕБЯ) ----
PROJECT_ID="${PROJECT_ID:-email-agent-$(date +%s | tail -c 7)}"
SERVICE_ACCOUNT_NAME="email-agent"
TOPIC_NAME="gmail-push"
SUBSCRIPTION_NAME="gmail-push-sub"
PUSH_ENDPOINT="${PUSH_ENDPOINT:-https://YOUR-DOMAIN.com/webhooks/gmail}"
REGION="europe-west1"

echo "============================================"
echo "  Email Agent — Google Cloud Setup"
echo "============================================"
echo ""
echo "Project ID: $PROJECT_ID"
echo "Push endpoint: $PUSH_ENDPOINT"
echo ""

# ---- Шаг 1: Создание проекта ----
echo "[1/7] Creating project..."
gcloud projects create "$PROJECT_ID" --name="Email Agent" 2>/dev/null || echo "  Project already exists"
gcloud config set project "$PROJECT_ID"
echo "  Done: project $PROJECT_ID"

# ---- Шаг 2: Включение API ----
echo ""
echo "[2/7] Enabling APIs..."
gcloud services enable \
  gmail.googleapis.com \
  sheets.googleapis.com \
  calendar-json.googleapis.com \
  drive.googleapis.com \
  pubsub.googleapis.com \
  iam.googleapis.com
echo "  Done: 6 APIs enabled"

# ---- Шаг 3: Создание Service Account ----
echo ""
echo "[3/7] Creating Service Account..."
SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
  --display-name="Email Agent Service Account" 2>/dev/null || echo "  SA already exists"
echo "  SA email: $SA_EMAIL"

# ---- Шаг 3b: Скачивание ключа ----
echo ""
echo "[4/7] Creating SA key..."
mkdir -p credentials
KEY_FILE="credentials/service_account.json"
if [ -f "$KEY_FILE" ]; then
  echo "  Key already exists: $KEY_FILE"
else
  gcloud iam service-accounts keys create "$KEY_FILE" \
    --iam-account="$SA_EMAIL"
  echo "  Key saved: $KEY_FILE"
fi

# ---- Шаг 4a: Включение Domain-Wide Delegation ----
echo ""
echo "[5/7] Enabling domain-wide delegation..."
# Получаем Client ID для настройки в admin.google.com
CLIENT_ID=$(gcloud iam service-accounts describe "$SA_EMAIL" --format="value(uniqueId)")
echo "  Client ID: $CLIENT_ID"
echo ""
echo "  ╔══════════════════════════════════════════════════════════╗"
echo "  ║  РУЧНОЙ ШАГ! Откройте admin.google.com:                ║"
echo "  ║  Security → API controls → Domain-wide delegation       ║"
echo "  ║  → Add new → Client ID: $CLIENT_ID"
echo "  ║  OAuth Scopes (одной строкой):                          ║"
echo "  ║  https://www.googleapis.com/auth/gmail.modify,          ║"
echo "  ║  https://www.googleapis.com/auth/gmail.send,            ║"
echo "  ║  https://www.googleapis.com/auth/spreadsheets,          ║"
echo "  ║  https://www.googleapis.com/auth/calendar,              ║"
echo "  ║  https://www.googleapis.com/auth/drive.readonly         ║"
echo "  ╚══════════════════════════════════════════════════════════╝"
echo ""
read -p "  Нажмите Enter после настройки в admin.google.com..."

# ---- Шаг 5a: Создание Pub/Sub Topic ----
echo ""
echo "[6/7] Creating Pub/Sub topic..."
FULL_TOPIC="projects/${PROJECT_ID}/topics/${TOPIC_NAME}"
gcloud pubsub topics create "$TOPIC_NAME" 2>/dev/null || echo "  Topic already exists"

# Даём Gmail права на публикацию
gcloud pubsub topics add-iam-policy-binding "$TOPIC_NAME" \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher" 2>/dev/null
echo "  Topic: $FULL_TOPIC"
echo "  Gmail push rights granted"

# ---- Шаг 5b: Создание Push Subscription ----
echo ""
echo "[7/7] Creating push subscription..."
if [ "$PUSH_ENDPOINT" = "https://YOUR-DOMAIN.com/webhooks/gmail" ]; then
  echo "  PUSH_ENDPOINT не задан! Создаём pull-подписку (позже переключите на push):"
  gcloud pubsub subscriptions create "$SUBSCRIPTION_NAME" \
    --topic="$TOPIC_NAME" 2>/dev/null || echo "  Subscription already exists"
  echo "  Когда будет домен, выполните:"
  echo "    gcloud pubsub subscriptions modify-push-config $SUBSCRIPTION_NAME \\"
  echo "      --push-endpoint='https://ваш-домен.com/webhooks/gmail'"
else
  gcloud pubsub subscriptions create "$SUBSCRIPTION_NAME" \
    --topic="$TOPIC_NAME" \
    --push-endpoint="$PUSH_ENDPOINT" 2>/dev/null || echo "  Subscription already exists"
  echo "  Push endpoint: $PUSH_ENDPOINT"
fi

# ---- Итог ----
echo ""
echo "============================================"
echo "  Готово! Добавьте в .env:"
echo "============================================"
echo ""
echo "GOOGLE_SERVICE_ACCOUNT_FILE=credentials/service_account.json"
echo "GOOGLE_PUBSUB_TOPIC=$FULL_TOPIC"
echo "GOOGLE_DELEGATED_EMAIL=ваша-почта@вашдомен.com"
echo ""
echo "Не забудьте:"
echo "  1. Создать Google Sheet и дать доступ: $SA_EMAIL"
echo "  2. Настроить domain-wide delegation (если ещё не сделали)"
echo "  3. Указать GOOGLE_SHEET_ID в .env"
echo ""
