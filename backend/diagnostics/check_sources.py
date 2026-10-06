"""Check whether the market-data services needed by the project are reachable.

Run from the repository root with:
    uv run python backend/diagnostics/check_sources.py
"""

from __future__ import annotations

import json
import math
import ssl
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TIMEOUT_SECONDS = 10
REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = Path(__file__).with_name("report.json")


def _platform_ca_bundle() -> str | bool:
    """Use the OS trust store when available, retaining Requests' secure default otherwise."""
    paths = ssl.get_default_verify_paths()
    if paths.cafile and Path(paths.cafile).is_file():
        return paths.cafile
    if paths.capath and Path(paths.capath).is_dir():
        return paths.capath
    return True


TLS_CA_BUNDLE = _platform_ca_bundle()


class DiagnosticError(RuntimeError):
    """An endpoint responded, but not with usable diagnostic data."""


def _get_json(url: str, *, params: dict[str, Any] | None = None) -> tuple[Any, int]:
    """GET JSON with a bounded HTTP timeout; requests is imported lazily."""
    import requests

    response = requests.get(
        url,
        params=params,
        timeout=TIMEOUT_SECONDS,
        verify=TLS_CA_BUNDLE,
    )
    response.raise_for_status()
    return response.json(), response.status_code


def _iso_from_milliseconds(value: Any) -> str | None:
    try:
        timestamp = float(value) / 1000
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def check_github_api() -> dict[str, Any]:
    payload, status = _get_json("https://api.github.com")
    if not isinstance(payload, dict):
        raise DiagnosticError("unexpected response from GitHub API")
    return {"http_status": status}


def check_binance_spot_ping() -> dict[str, Any]:
    _, status = _get_json("https://api.binance.com/api/v3/ping")
    return {"http_status": status}


def check_binance_spot_candles() -> dict[str, Any]:
    payload, status = _get_json(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": "BTCUSDT", "interval": "1d", "limit": 1},
    )
    if not isinstance(payload, list) or not payload:
        raise DiagnosticError("empty or invalid candle response")
    candle = payload[-1]
    if not isinstance(candle, list) or len(candle) < 6:
        raise DiagnosticError("unexpected candle format")
    return {
        "http_status": status,
        "rows": len(payload),
        "candle_time_utc": _iso_from_milliseconds(candle[0]),
    }


def check_binance_futures_ping() -> dict[str, Any]:
    _, status = _get_json("https://fapi.binance.com/fapi/v1/ping")
    return {"http_status": status}


def check_binance_futures_candles() -> dict[str, Any]:
    payload, status = _get_json(
        "https://fapi.binance.com/fapi/v1/klines",
        params={"symbol": "BTCUSDT", "interval": "1d", "limit": 1},
    )
    if not isinstance(payload, list) or not payload:
        raise DiagnosticError("empty or invalid candle response")
    candle = payload[-1]
    if not isinstance(candle, list) or len(candle) < 6:
        raise DiagnosticError("unexpected candle format")
    return {
        "http_status": status,
        "rows": len(payload),
        "candle_time_utc": _iso_from_milliseconds(candle[0]),
    }


def check_binance_funding_rate() -> dict[str, Any]:
    payload, status = _get_json(
        "https://fapi.binance.com/fapi/v1/fundingRate",
        params={"symbol": "BTCUSDT", "limit": 1},
    )
    if (
        not isinstance(payload, list)
        or not payload
        or not isinstance(payload[-1], dict)
    ):
        raise DiagnosticError("empty or invalid funding-rate response")
    row = payload[-1]
    return {
        "http_status": status,
        "rows": len(payload),
        "funding_rate": row.get("fundingRate"),
        "funding_time_utc": _iso_from_milliseconds(row.get("fundingTime")),
    }


def check_binance_open_interest() -> dict[str, Any]:
    payload, status = _get_json(
        "https://fapi.binance.com/fapi/v1/openInterest",
        params={"symbol": "BTCUSDT"},
    )
    if not isinstance(payload, dict) or "openInterest" not in payload:
        raise DiagnosticError("missing openInterest in response")
    return {"http_status": status, "open_interest": payload["openInterest"]}


def check_binance_long_short_ratio() -> dict[str, Any]:
    payload, status = _get_json(
        "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
        params={"symbol": "BTCUSDT", "period": "1h", "limit": 1},
    )
    if (
        not isinstance(payload, list)
        or not payload
        or not isinstance(payload[-1], dict)
    ):
        raise DiagnosticError("empty or invalid long/short-ratio response")
    row = payload[-1]
    return {
        "http_status": status,
        "rows": len(payload),
        "long_short_ratio": row.get("longShortRatio"),
        "period": row.get("timestamp"),
    }


def check_ccxt_version() -> dict[str, Any]:
    import ccxt

    return {"version": getattr(ccxt, "__version__", "unknown")}


def check_ccxt_ohlcv() -> dict[str, Any]:
    import ccxt

    exchange = ccxt.binance({"timeout": TIMEOUT_SECONDS * 1000})
    candles = exchange.fetch_ohlcv("BTC/USDT", "1d", limit=5)
    if not candles:
        raise DiagnosticError("ccxt returned no OHLCV candles")
    return {
        "rows": len(candles),
        "last_candle_time_utc": _iso_from_milliseconds(candles[-1][0]),
    }


def _check_yfinance_history(symbol: str) -> dict[str, Any]:
    import logging

    import yfinance as yf

    # yfinance otherwise writes its own per-request errors to stderr; the
    # diagnostic table/report below is the single source of failure details.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    history = yf.Ticker(symbol).history(period="5d", timeout=TIMEOUT_SECONDS)
    if history is None or history.empty:
        raise DiagnosticError("no data returned (empty history)")

    details: dict[str, Any] = {
        "rows": len(history),
        "last_date": str(history.index[-1])[:10],
    }
    if "Close" in history:
        try:
            close = float(history["Close"].iloc[-1])
            details["last_close"] = close if math.isfinite(close) else None
        except (TypeError, ValueError, IndexError):
            details["last_close"] = None
    return details


def check_yfinance_btc() -> dict[str, Any]:
    return _check_yfinance_history("BTC-USD")


def check_yfinance_aapl() -> dict[str, Any]:
    return _check_yfinance_history("AAPL")


CHECKS: tuple[tuple[str, str, Callable[[], dict[str, Any]]], ...] = (
    ("GitHub API", "Internet", check_github_api),
    ("Binance Spot: ping", "Binance Spot", check_binance_spot_ping),
    ("Binance Spot: BTCUSDT 1d candle", "Binance Spot", check_binance_spot_candles),
    ("Binance Futures: ping", "Binance Futures", check_binance_futures_ping),
    (
        "Binance Futures: BTCUSDT 1d candle",
        "Binance Futures",
        check_binance_futures_candles,
    ),
    ("Binance funding rate", "Binance metrics", check_binance_funding_rate),
    ("Binance open interest", "Binance metrics", check_binance_open_interest),
    (
        "Binance global long/short ratio",
        "Binance metrics",
        check_binance_long_short_ratio,
    ),
    ("ccxt version", "ccxt package", check_ccxt_version),
    ("ccxt: BTC/USDT 1d OHLCV", "ccxt data", check_ccxt_ohlcv),
    ("yfinance: BTC-USD history", "yfinance BTC-USD", check_yfinance_btc),
    ("yfinance: AAPL history", "yfinance AAPL", check_yfinance_aapl),
)

SOURCE_GROUPS: tuple[tuple[str, str], ...] = (
    ("GitHub / internet", "Internet"),
    ("Binance Spot REST", "Binance Spot"),
    ("Binance Futures REST", "Binance Futures"),
    ("Binance derivative metrics", "Binance metrics"),
    ("ccxt installed", "ccxt package"),
    ("ccxt Binance OHLCV", "ccxt data"),
    ("yfinance BTC-USD", "yfinance BTC-USD"),
    ("yfinance AAPL", "yfinance AAPL"),
)


def _error_message(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None and status_code > 0:
        reason = getattr(response, "reason", "")
        return f"HTTP {status_code} {reason}".strip()

    message = " ".join(str(exc).split())
    lowered = f"{type(exc).__name__} {message}".lower()
    if "timeout" in lowered or "timed out" in lowered:
        return f"timeout (limit {TIMEOUT_SECONDS}s): {message or type(exc).__name__}"
    if "ssl" in lowered or "tls" in lowered:
        return f"TLS/SSL error: {message or type(exc).__name__}"
    if any(
        hint in lowered
        for hint in (
            "nameresolutionerror",
            "name resolution",
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname",
        )
    ):
        return f"DNS error: {message or type(exc).__name__}"
    if isinstance(exc, ImportError):
        return f"dependency unavailable: {message or type(exc).__name__}"
    if type(exc).__name__ == "JSONDecodeError":
        return "invalid JSON response"
    return f"{type(exc).__name__}: {message or 'no details'}"


def _run_check(
    name: str, source: str, check: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        details = check()
        return {
            "name": name,
            "source": source,
            "ok": True,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": None,
            "details": details,
        }
    except Exception as exc:  # noqa: BLE001 - isolate failures in each optional network check.
        return {
            "name": name,
            "source": source,
            "ok": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": _error_message(exc),
            "details": None,
        }


def _compact_details(result: dict[str, Any]) -> str:
    if not result["ok"]:
        return str(result["error"] or "unknown error")

    details = result.get("details") or {}
    if not details:
        return "OK"
    return "; ".join(
        f"{key}={value}" for key, value in details.items() if value is not None
    )


def _clip(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 1:
        return value[:width]
    return value[: width - 1] + "…"


def _print_table(results: list[dict[str, Any]]) -> None:
    headers = ("Проверка", "Статус", "мс", "Детали / ошибка")
    rows = [
        (
            str(result["name"]),
            "OK" if result["ok"] else "FAIL",
            f"{result['elapsed_ms']:.2f}",
            _compact_details(result),
        )
        for result in results
    ]
    widths = (
        min(max(len(headers[0]), *(len(row[0]) for row in rows)), 42),
        len(headers[1]),
        max(len(headers[2]), max(len(row[2]) for row in rows)),
        76,
    )

    def line(values: tuple[str, ...]) -> str:
        return (
            "| "
            + " | ".join(
                _clip(value, width).ljust(width) for value, width in zip(values, widths)
            )
            + " |"
        )

    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    print(separator)
    print(line(headers))
    print(separator)
    for row in rows:
        print(line(row))
    print(separator)


def _build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    for label, source in SOURCE_GROUPS:
        matching = [result for result in results if result["source"] == source]
        passed = sum(bool(result["ok"]) for result in matching)
        total = len(matching)
        status = "OK" if passed == total else "PARTIAL" if passed else "FAIL"
        sources.append(
            {"name": label, "status": status, "passed": passed, "total": total}
        )
    return {
        "passed": sum(bool(result["ok"]) for result in results),
        "failed": sum(not result["ok"] for result in results),
        "total": len(results),
        "sources": sources,
    }


def _print_summary(summary: dict[str, Any]) -> None:
    print("\nСводка источников:")
    for source in summary["sources"]:
        print(
            f"  {source['status']:<7} {source['name']} "
            f"({source['passed']}/{source['total']} проверок)"
        )

    available = [
        source["name"] for source in summary["sources"] if source["status"] == "OK"
    ]
    partial = [
        source["name"] for source in summary["sources"] if source["status"] == "PARTIAL"
    ]
    unavailable = [
        source["name"] for source in summary["sources"] if source["status"] == "FAIL"
    ]
    print("\nВывод:")
    print(f"  Доступны: {', '.join(available) if available else 'нет'}.")
    print(f"  Частично доступны: {', '.join(partial) if partial else 'нет'}.")
    print(f"  Недоступны: {', '.join(unavailable) if unavailable else 'нет'}.")
    print(
        "  Для загрузчика используйте источники со статусом OK; для PARTIAL ориентируйтесь на конкретные успешные проверки."
    )
    print(
        "  HTTP 451 обычно указывает на региональное ограничение; timeout/DNS чаще говорит о сетевой недоступности."
    )


def main() -> int:
    results = [_run_check(name, source, check) for name, source, check in CHECKS]
    summary = _build_summary(results)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "timeout_seconds": TIMEOUT_SECONDS,
        "tls_ca_bundle": (
            TLS_CA_BUNDLE
            if isinstance(TLS_CA_BUNDLE, str)
            else "requests default (certifi)"
        ),
        "summary": summary,
        "tests": results,
    }

    print("Проверка источников рыночных данных")
    _print_table(results)
    _print_summary(summary)

    try:
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        report_path = REPORT_PATH.relative_to(REPO_ROOT)
        print(f"\nJSON-отчёт: {report_path}")
    except OSError as exc:
        print(
            f"\nНе удалось записать JSON-отчёт: {_error_message(exc)}", file=sys.stderr
        )
        return 2

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
