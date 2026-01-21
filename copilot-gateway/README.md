# Copilot OpenAI Gateway

OpenAI-compatible gateway для GitHub Copilot API. Позволяет использовать premium модели Copilot (Claude Opus 4.5, GPT-5.2 и др.) через Droid и другие OpenAI-совместимые клиенты.

## Что это даёт?

- Используй **Claude Opus 4.5** в Droid оплачивая через Copilot подписку
- Используй **GPT-5.2**, **Grok** и другие модели
- Не нужен отдельный API ключ - используется твоя Copilot подписка

## ⚠️ Важно про лимиты!

Copilot снимает лимит **за каждый запрос**, не за токены!
- Opus: ~300 premium запросов/месяц
- Droid делает **5-10 запросов** на один твой вопрос (thinking + tool calls)
- Используй для простых задач, где Droid не будет много думать

## Требования

- macOS / Linux
- Python 3.10+
- GitHub CLI (`gh`) установлен
- **GitHub Copilot подписка** (Pro или Enterprise)

## Быстрый старт

```bash
# 1. Клонировать/скопировать папку copilot-openai-gateway

# 2. Установить зависимости
cd copilot-openai-gateway
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Авторизоваться в gh CLI с copilot scope
gh auth login
gh auth refresh --hostname github.com --scopes copilot

# 4. Создать .env файл
cp .env.example .env
nano .env  # Изменить PROXY_API_KEY на свой секрет

# 5. Запустить gateway
python main.py
# или
uvicorn main:app --host 0.0.0.0 --port 8001
```

Gateway будет на `http://localhost:8001`

## Проверка работы

```bash
# Health check
curl http://localhost:8001/health

# Список моделей
curl http://localhost:8001/v1/models \
  -H "Authorization: Bearer your_proxy_key"

# Тест запроса
curl http://localhost:8001/v1/chat/completions \
  -H "Authorization: Bearer your_proxy_key" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-opus-4.5", "messages": [{"role": "user", "content": "Hi!"}]}'
```

## Настройка Droid

Добавь в `~/.factory/settings.json` в массив `customModels`:

```json
{
  "model": "claude-opus-4-5",
  "id": "custom:Claude-Opus-4.5-(Copilot)-8",
  "index": 8,
  "baseUrl": "http://localhost:8001/v1",
  "apiKey": "your_proxy_key",
  "displayName": "Claude Opus 4.5 (Copilot)",
  "maxOutputTokens": 64000,
  "noImageSupport": false,
  "provider": "generic-chat-completion-api"
}
```

### ⚠️ Важно для Droid!

1. **index** должен быть последовательным (после существующих моделей)
2. **id** должен содержать index в конце: `custom:Name-8` где 8 = index
3. **model** используй с дефисами: `claude-opus-4-5` (не точками)

### Пример полного settings.json

Если уже есть 8 custom моделей (index 0-7), добавь Copilot с index 8:

```json
{
  "customModels": [
    // ... твои существующие модели с index 0-7 ...
    {
      "model": "claude-opus-4-5",
      "id": "custom:Claude-Opus-4.5-(Copilot)-8",
      "index": 8,
      "baseUrl": "http://localhost:8001/v1",
      "apiKey": "droid-gateway-secret-123",
      "displayName": "Claude Opus 4.5 (Copilot)",
      "maxOutputTokens": 64000,
      "noImageSupport": false,
      "provider": "generic-chat-completion-api"
    },
    {
      "model": "gpt-5.2",
      "id": "custom:GPT-5.2-(Copilot)-9",
      "index": 9,
      "baseUrl": "http://localhost:8001/v1",
      "apiKey": "droid-gateway-secret-123",
      "displayName": "GPT-5.2 (Copilot)",
      "maxOutputTokens": 64000,
      "noImageSupport": false,
      "provider": "generic-chat-completion-api"
    }
  ]
}
```

## Доступные модели

Зависит от подписки. Типичный список:

| Модель | Тип | Лимит |
|--------|-----|-------|
| claude-opus-4.5 | Premium | ~300/месяц |
| claude-haiku-4.5 | Standard | больше |
| gpt-5.2 | Premium | ~300/месяц |
| gpt-5.1 | Standard | больше |
| gpt-5 | Standard | больше |
| grok-code-fast-1 | Standard | больше |

> ⚠️ Некоторые модели (claude-sonnet-4.5, gemini-2.5-pro) требуют принятия policy в [Copilot Settings](https://github.com/settings/copilot)

## Автозапуск (опционально)

### macOS (launchd)

Создай `~/Library/LaunchAgents/com.copilot.gateway.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.copilot.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/copilot-openai-gateway/venv/bin/python</string>
        <string>/path/to/copilot-openai-gateway/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/copilot-openai-gateway</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.copilot.gateway.plist
```

## Troubleshooting

### "400 status code (no body)" в Droid
- Проверь что gateway запущен: `curl http://localhost:8001/health`
- Проверь index в settings.json (должен быть последовательным)
- Перезапусти Droid после изменения settings.json

### "Connection error"
- Gateway не запущен или на другом порту

### "JSON Parse error"
- Обнови gateway до последней версии (нужен `object: chat.completion.chunk` в ответе)

### Модель требует policy
- Зайди в https://github.com/settings/copilot и включи нужную модель
