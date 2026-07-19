#!/usr/bin/env bash
# Цикл разработки тест-Mini App БЕЗ sudo.
#
# Почему так: свежий образ в containerd k3s кладётся только через `k3s ctr images
# import`, а его сокет root:root и sudo с паролем — самому не выкатить. Поэтому код
# монтируется в под с хоста (k8s/miniapp-test-dev.yaml), а не пересобирается в образ:
#   - static/ (JS/CSS/HTML) — правка видна сразу по refresh, ничего запускать не надо;
#   - Python — `dev.sh restart` (rollout restart, ~3с, без билда).
#
# Команды (Mini App / бэкенд):
#   dev.sh up          — включить dev-режим Mini App (исходники с хоста)
#   dev.sh restart     — перезапустить под Mini App (подхватить правки Python)
#   dev.sh logs        — живые логи Mini App
#   dev.sh status      — состояние пода Mini App
#   dev.sh down        — вернуть образный тест-деплой Mini App (miniapp-test.yaml)
# Команды (бот / воркер rest_notifier):
#   dev.sh bot-up      — включить dev-режим бота (весь репозиторий с хоста)
#   dev.sh bot-restart — перезапустить бот (подхватить правки воркера/хендлеров)
#   dev.sh bot-logs    — живые логи бота
#   dev.sh bot-status  — состояние пода бота
#   dev.sh bot-down    — вернуть образный тест-бот (bot-test.yaml)
# Общее:
#   dev.sh test        — прогнать pytest на sqlite
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-/home/sk1bid/.kube/config}"
NS=gym-prod
DEPLOY=gym-miniapp
BOT=gym-bot-test
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "${1:-}" in
  up)
    kubectl apply -f "$ROOT/k8s/miniapp-test-dev.yaml"
    kubectl rollout status "deploy/$DEPLOY" -n "$NS" --timeout=90s
    echo "dev-режим Mini App включён: исходники с хоста, пересборка образа не нужна."
    ;;
  restart)
    kubectl rollout restart "deploy/$DEPLOY" -n "$NS"
    kubectl rollout status "deploy/$DEPLOY" -n "$NS" --timeout=90s
    ;;
  logs)
    kubectl logs -f "deploy/$DEPLOY" -n "$NS"
    ;;
  status)
    kubectl get pods -n "$NS" -l app="$DEPLOY" -o wide
    ;;
  down)
    kubectl apply -f "$ROOT/k8s/miniapp-test.yaml"
    kubectl rollout status "deploy/$DEPLOY" -n "$NS" --timeout=90s
    echo "вернулись к образному тест-деплою Mini App (miniapp-test.yaml)."
    ;;
  bot-up)
    kubectl apply -f "$ROOT/k8s/bot-test-dev.yaml"
    kubectl rollout status "deploy/$BOT" -n "$NS" --timeout=90s
    echo "dev-режим бота включён: репозиторий монтируется с хоста, воркер правится рестартом."
    ;;
  bot-restart)
    kubectl rollout restart "deploy/$BOT" -n "$NS"
    kubectl rollout status "deploy/$BOT" -n "$NS" --timeout=90s
    ;;
  bot-logs)
    kubectl logs -f "deploy/$BOT" -n "$NS" -c aiogram-bot
    ;;
  bot-status)
    kubectl get pods -n "$NS" -l app="$BOT" -o wide
    ;;
  bot-down)
    kubectl apply -f "$ROOT/k8s/bot-test.yaml"
    kubectl rollout status "deploy/$BOT" -n "$NS" --timeout=90s
    echo "вернулись к образному тест-боту (bot-test.yaml)."
    ;;
  test)
    cd "$ROOT"
    MINIAPP_BOT_TOKEN="${MINIAPP_BOT_TOKEN:-test}" \
      DB_URL="${DB_URL:-sqlite+aiosqlite:////tmp/gym_dev_test.db}" \
      ./.venv-bot/bin/pytest tests/ -q
    ;;
  *)
    grep -E '^#   dev\.sh' "$0" | sed 's/^#   //'
    exit 1
    ;;
esac
