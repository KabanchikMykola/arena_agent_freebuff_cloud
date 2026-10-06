# Freebuff Cloud — диагностика источников рыночных данных

Зависимости Python описаны в `pyproject.toml` и управляются через [uv](https://docs.astral.sh/uv/); `requirements.txt` не используется.

## Установка и запуск

```bash
uv sync
uv run python backend/diagnostics/check_sources.py
```

Скрипт независимо проверяет GitHub API, Binance Spot и Futures, метрики Binance, `ccxt` и `yfinance`. У сетевых запросов настроен таймаут 10 секунд; прямые HTTP-проверки используют системный CA bundle, если он доступен (проверка TLS не отключается). Результат выводится в консоль и записывается в `backend/diagnostics/report.json`.

Локальные CSV/Parquet-файлы в `data/` и сгенерированный отчёт диагностики не добавляются в Git. Для новых зависимостей используйте `uv add <package>`.
