# Freebuff Cloud — диагностика источников рыночных данных

Зависимости Python описаны в `pyproject.toml` и управляются через [uv](https://docs.astral.sh/uv/); `requirements.txt` не используется.

## Установка и запуск

```bash
uv sync
uv run python backend/diagnostics/check_sources.py
```

Скрипт независимо проверяет GitHub API, Binance Spot и Futures, метрики Binance, `ccxt` и `yfinance`, а также транспорт данных, который в этой песочнице реально работает: GitHub Contents API (raw), GitHub search, `codeload`, PyPI (метаданные и `files.pythonhosted.org`) и npm registry. У сетевых запросов настроен таймаут 10 секунд; прямые HTTP-проверки используют системный CA bundle, если он доступен (проверка TLS не отключается). Результат выводится в консоль и записывается в `backend/diagnostics/report.json`.

Локальные CSV/Parquet-файлы в `data/` и сгенерированный отчёт диагностики не добавляются в Git. Для новых зависимостей используйте `uv add <package>`.

## Откуда брать финансовые данные

В песочнице работает узкий egress-allowlist: живые API бирж и агрегаторов недоступны (TLS обрывается), доступны только `pypi.org`, `files.pythonhosted.org`, `github.com`, `api.github.com`, `codeload.github.com` и `registry.npmjs.org`. Подробности — в `docs/findings/network_diagnostics.md`. Основной способ загрузки исторических данных:

```bash
curl -H 'Accept: application/vnd.github.raw' \
  'https://api.github.com/repos/<owner>/<repo>/contents/<path.csv>?ref=<commit-sha>' \
  -o data/<file>.csv
```

Дополнительно: `git clone` и `codeload` для целых репозиториев, `pip install` для пакетов со встроенными CSV (`vega_datasets`, `statsmodels`), npm-tarballs для JS-пакетов с данными.
