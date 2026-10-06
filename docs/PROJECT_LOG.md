# Project log

## 2026-10-06 — Re-check: which transports can actually deliver financial data

- Reproduced the first-pass results: Binance Spot/Futures, derivative metrics, `ccxt` Binance OHLCV and both `yfinance` symbols still fail on TLS; GitHub still returns HTTP 200.
- Probed ~80 endpoints (exchanges, aggregators, equities/FX/macro, dataset portals, generic internet) and established that the sandbox runs on a **narrow egress allowlist**: only `pypi.org`, `files.pythonhosted.org`, `github.com`, `api.github.com`, `codeload.github.com` and `registry.npmjs.org` answer; every other host completes TCP and then closes the TLS handshake. `https://example.com` fails identically, so this is not a geo-block of exchanges.
- Extended `backend/diagnostics/check_sources.py` with six checks for the transports that do work: GitHub Contents API (raw media type), GitHub search, `codeload` archive, PyPI metadata, PyPI artifact (`files.pythonhosted.org`) and npm registry. The script now prints guidance on where data can be obtained.
- Verified practical limits and recipes: single files up to 90 MB straight from the Contents API, commit-SHA pinning via `?ref=`, `git clone`/`codeload`/tarball for whole repositories, `pip`-installed packages that bundle CSV fixtures (`vega_datasets`, `statsmodels`), and npm tarballs. GitHub's `/raw/` links and release assets stay unusable because they redirect to blocked hosts.
- Downloaded two samples into the git-ignored `data/`: `data/vix-daily.csv` (9,278 rows, 1990-01-02 → 2026-09-22) and `data/btcusdt_daily.csv` (2,339 rows, 2017-08-17 → 2024-01-10). Findings and caveats are in `docs/findings/network_diagnostics.md`.

**Next:** build the loader on static dataset transports (GitHub Contents API with SHA pinning, then PyPI/npm), since live REST feeds are unreachable from this sandbox.

## 2026-10-06 — Initial market-data diagnostics

- Added the diagnostics project structure and script for GitHub, Binance Spot/Futures, derivative metrics, `ccxt`, and `yfinance`.
- Replaced the proposed `requirements.txt` workflow with `uv`, using `pyproject.toml` and a checked-in `uv.lock`.
- Ran the source checks and followed up with curl, OpenSSL, certifi, and OS-CA comparisons. PyPI and GitHub are reachable; GitHub's TLS certificate is issued by the E2B Proxy CA and is trusted by the OS CA bundle but not certifi. Binance and Yahoo Finance connections close during TLS, with no HTTP 451 response. The network is not fully closed, but market-data hosts appear unavailable from this sandbox.
- Updated direct HTTP diagnostics to use the platform CA bundle when available (TLS verification remains enabled). The refreshed report is at `backend/diagnostics/report.json`; it is generated locally and ignored by Git.

**Next:** rerun the diagnostics from a network where Binance and Yahoo Finance are allowed, or confirm the sandbox's domain egress policy with its operator before designing a data-download workflow around these sources.
