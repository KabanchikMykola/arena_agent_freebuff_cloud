# Project log

## 2026-10-06 — Initial market-data diagnostics

- Added the diagnostics project structure and script for GitHub, Binance Spot/Futures, derivative metrics, `ccxt`, and `yfinance`.
- Replaced the proposed `requirements.txt` workflow with `uv`, using `pyproject.toml` and a checked-in `uv.lock`.
- Ran the source checks and followed up with curl, OpenSSL, certifi, and OS-CA comparisons. PyPI and GitHub are reachable; GitHub's TLS certificate is issued by the E2B Proxy CA and is trusted by the OS CA bundle but not certifi. Binance and Yahoo Finance connections close during TLS, with no HTTP 451 response. The network is not fully closed, but market-data hosts appear unavailable from this sandbox.
- Updated direct HTTP diagnostics to use the platform CA bundle when available (TLS verification remains enabled). The refreshed report is at `backend/diagnostics/report.json`; it is generated locally and ignored by Git.

**Next:** rerun the diagnostics from a network where Binance and Yahoo Finance are allowed, or confirm the sandbox's domain egress policy with its operator before designing a data-download workflow around these sources.
