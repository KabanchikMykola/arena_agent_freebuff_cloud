# Network diagnostics

**Date:** 2026-10-06 (initial run and re-check, see [Egress allowlist](#egress-allowlist-what-actually-works))

**Environment:** Arena/E2B sandbox; Python 3.11.2; project dependencies installed with `uv`.

## Executive summary

The sandbox can reach PyPI and GitHub. Binance Spot, Binance Futures, and Yahoo Finance did not complete TLS connections in the tests below. This is **not** an HTTP 451 response and does not establish a Binance geo-block. The observed pattern is closest to **scenario (b)** from the original checklist (some public sites work, while market-data hosts do not), with an additional trust-store detail: GitHub is presented through an E2B-issued TLS certificate.

| Service/test | Result | What it tells us |
| --- | --- | --- |
| `pypi.org` via curl | HTTP 200; TLS verifies | Outbound HTTPS is not fully closed. |
| `api.github.com` via curl/system CA | HTTP 200; TLS verifies | GitHub is reachable when the OS trust bundle is used. |
| `api.github.com` via Requests + certifi | Certificate verification fails | certifi does not contain the E2B Proxy CA used for the GitHub connection. |
| Binance Spot / Futures | TLS handshake closed; HTTP 000 | The failure happens before an HTTP response or certificate can be validated. Adding a CA alone is not expected to fix this. |
| Yahoo Finance via yfinance | TLS handshake closed | yfinance could not fetch either BTC-USD or AAPL from this sandbox. |
| `ccxt` package | Version 4.5.85 imports successfully | The package is installed; this does not mean its Binance API call can reach Binance. |

## Environment and trust stores

The environment-variable check for names/values matching `proxy|ssl|cert` returned **no matches**. `requests.utils.get_environ_proxies("https://api.binance.com")` also returned no proxy configuration, so there was no environment proxy URL to repeat explicitly.

Python's default OpenSSL paths were:

```text
DefaultVerifyPaths(
    cafile='/usr/lib/ssl/cert.pem',
    capath='/usr/lib/ssl/certs',
    openssl_cafile_env='SSL_CERT_FILE',
    openssl_cafile='/usr/lib/ssl/cert.pem',
    openssl_capath_env='SSL_CERT_DIR',
    openssl_capath='/usr/lib/ssl/certs'
)
```

In this run, `/usr/lib/ssl/cert.pem` is a symlink to `/etc/ssl/certs/ca-certificates.crt`. Requests' certifi bundle is separate (`certifi.where()` points into the project's `.venv`).

## curl checks

Commands were run with `curl --max-time 10`; the verbose output showed direct connections and no proxy environment variables.

| URL | HTTP | TLS verify result | Result |
| --- | ---: | ---: | --- |
| `https://api.binance.com/api/v3/ping` | `000` | `1` | curl exit 35: `SSL_ERROR_SYSCALL`; TCP connected to `18.238.229.202:443`, then the TLS handshake was closed. |
| `https://pypi.org/simple/` | `200` | `0` | Success; remote IP observed: `151.101.0.223`. |
| `https://api.github.com` | `200` | `0` | Success; remote IP varied between `20.29.134.17` and `140.82.116.5`. |

For GitHub, curl reported:

```text
subject: O=E2B; CN=api.github.com
issuer: O=E2B; CN=E2B Proxy CA
SSL certificate verify ok.
```

This is evidence of TLS interception for the GitHub connection. The system CA bundle trusts that E2B-issued CA; the certifi bundle used by Requests does not.

## Python Requests checks

The explicit `verify=certifi.where()` check for Binance failed with `SSLError` / `SSLZeroReturnError` (the connection closed during TLS). Repeating with the OS CA file produced the same Binance failure. Thus, for Binance, switching CA bundles does not change the observed failure.

| Host | Requests with certifi | Requests with OS CA bundle |
| --- | --- | --- |
| Binance | TLS connection closed | TLS connection closed |
| PyPI | HTTP 200 | HTTP 200 |
| GitHub | `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` | HTTP 200 |

The diagnostics script now uses the platform's CA bundle when one is available, while keeping certificate verification enabled. This makes its GitHub check reflect the trust store used by curl, without disabling TLS verification.

## Market-data diagnostics report

The latest run of `backend/diagnostics/check_sources.py` checked 12 items:

- **OK:** GitHub API (HTTP 200), `ccxt` installed (4.5.85).
- **FAIL:** Binance Spot ping/candle; Binance Futures ping/candle; funding rate; open interest; long/short ratio; `ccxt` Binance OHLCV; yfinance BTC-USD; yfinance AAPL.
- Binance and Yahoo errors are TLS/connection failures, **not** HTTP 451 responses.

The machine-readable run output is `backend/diagnostics/report.json`. It is generated locally and intentionally ignored by Git; rerun the script to refresh it.

## Conclusion and next step (first pass)

1. Scenario **(c)** (all outbound HTTPS closed except the package registry) is ruled out: curl reached both PyPI and GitHub with HTTP 200.
2. Scenario **(a)** applies specifically to GitHub in this sandbox: an E2B Proxy CA-signed certificate is trusted by the OS bundle but not by certifi. Using the OS bundle is a secure fix for that Requests check; `verify=False` is not appropriate.
3. For Binance and Yahoo, the results are most consistent with **destination-specific egress filtering or a gateway closing the TLS handshake** (scenario **(b)** broadly). The tests do not identify the exact network policy, and there was no HTTP 451 to diagnose as a geographic restriction.

Next, rerun the market-data checks from a network where Binance and Yahoo are permitted, or ask the sandbox/network operator whether those domains are intentionally blocked. Do not add large market datasets to Git; keep downloaded data local under `data/`.

## Re-check: where financial data actually comes from

**Date:** 2026-10-06 (second pass). The re-check probed ~80 endpoints with `curl --max-time 8` (DNS → TCP → TLS → HTTP) plus Python `requests`/`pip`, and the extended `check_sources.py` (18 checks).

### Egress allowlist: what actually works

The pattern is not a market-data-specific block. It is a **narrow egress allowlist**: a handful of
infrastructure hosts answer, and every other destination completes the TCP handshake and then has
the TLS handshake closed (`SSL_ERROR_SYSCALL`, HTTP `000`). `https://example.com` fails the same
way, which rules out geo-blocking of exchanges specifically.

| Host | Result |
| --- | --- |
| `pypi.org`, `files.pythonhosted.org` | HTTP 200 |
| `github.com`, `api.github.com`, `codeload.github.com` | HTTP 200 |
| `registry.npmjs.org` | HTTP 200 |
| `raw.githubusercontent.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`, `gist.github.com` | TLS closed |
| `cdn.jsdelivr.net`, `unpkg.com`, `docs.python.org`, `test.pypi.org` | TLS closed |
| Crypto venues: Binance (Spot/Futures/`data-api.binance.vision`/`.us`), Bybit, OKX, Kraken, Coinbase, Bitstamp, KuCoin, Gate.io, Bitget, MEXC, HTX, Deribit, Crypto.com, Gemini, Bitfinex | TLS closed |
| Aggregators: CoinGecko, CoinMarketCap, CryptoCompare, DefiLlama, Fear & Greed, mempool.space, blockchain.info | TLS closed |
| Equities/FX/macro: Yahoo Finance, Stooq, Alpha Vantage, Twelve Data, Polygon, Tiingo, Marketstack, FMP, Nasdaq, SEC, FRED, World Bank, ECB, CBR, MOEX, Frankfurter, er-api, exchangerate.host | TLS closed |
| Dataset portals: Hugging Face, Kaggle, Zenodo, UCI, data.world, GitLab, Quandl/data.nasdaq | TLS closed |
| Generic internet: `google.com`, `example.com`, `arxiv.org`, `api.crossref.org`, `archive.org` | TLS closed |

Consequences: live quotes, streaming feeds, per-request incremental downloads (funding rate, open
interest, long/short ratio) and refresh-at-runtime are **not possible** from this sandbox. Only
static, already-published files that live behind the allowlisted hosts can be fetched.

### Working recipes

**1. GitHub Contents API — one file (main transport)**

```bash
curl -H 'Accept: application/vnd.github.raw' \
  https://api.github.com/repos/<owner>/<repo>/contents/<path/to/file.csv> -o data/<file>.csv
```

- Verified byte-for-byte on a 482 KB CSV and on a 90 MB CSV (no redirect to the blocked `raw.githubusercontent.com`).
- `GH_TOKEN`/`GITHUB_TOKEN` raises limits (5,000 core requests/hour instead of 60; code search 30/min).
- `?ref=<commit-sha>` pins the content for reproducibility (verified identical download).
- Note: the API's `sha` field for a file is a *blob* SHA and cannot be used as `ref`; take the commit SHA from `GET /repos/<o>/<r>/commits?path=<path>`. GitHub's own `/raw/` links and release assets 302 to blocked hosts and do not work.

**2. Discovery — GitHub search**

```bash
# code search finds the CSVs (needs a token); repository search works anonymously
curl -H "Authorization: Bearer $GH_TOKEN" \
  'https://api.github.com/search/code?q=BTCUSDT+extension:csv&per_page=5'
```

`BTCUSDT extension:csv` returns ~33k files, e.g. `Kushagra614/HyperTradeX:data/BTCUSDT_1m.csv`,
`MarkWangchao/my-trading-system:data/BTCUSDT_daily.csv`, plus funding-rate history mirrors.

**3. Whole repositories and archives**

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/<owner>/<repo>   # works
curl -L -o repo.zip https://codeload.github.com/<owner>/<repo>/zip/refs/heads/main  # codeload works
curl -H "Authorization: Bearer $GH_TOKEN" -L -o repo.tgz \
  https://api.github.com/repos/<owner>/<repo>/tarball/<ref>                         # 337 MB verified
```

**4. PyPI — packages that ship datasets**

`pip install` works, so any package bundling CSV/Parquet fixtures is a data source. Verified:
`vega_datasets` (`stocks.csv`: 5 tickers monthly 2000–2010; `ohlc.json`, `us-employment.csv`,
`iowa-electricity.csv`), `statsmodels` (231 CSV datasets: `macrodata`, `ccard`, `copper`, `co2`…).
Arbitrary artifacts are reachable through `https://pypi.org/pypi/<package>/json`.

**5. npm registry — metadata and tarballs**

`registry.npmjs.org` serves both (`vega-datasets` tarball, 17.6 MB, verified), so npm packages with
bundled data work as well.

### Data pulled during the re-check

Both files land in `data/`, which stays out of Git (`data/*.csv`):

| File | Content | Rows | Range |
| --- | --- | ---: | --- |
| `data/vix-daily.csv` | CBOE VIX daily OHLC, `datasets/finance-vix` | 9,278 | 1990-01-02 → 2026-09-22 |
| `data/btcusdt_daily.csv` | BTCUSDT daily OHLCV, mirror of CryptoDataDownload (`kochlisGit/VIT2`) | 2,339 | 2017-08-17 → 2024-01-10 |

### Caveats

- Third-party mirrors carry provenance and staleness risk: check columns, units and the last date before use; prefer curated sources such as the `datasets/*` GitHub org or the upstream project's own repository.
- Crypto funding-rate/open-interest/long-short history only exists as mirrored CSV in third-party repositories, not as a live API.
- Refreshing data requires either re-running the download from an environment with wider egress, or re-pinning a new commit SHA; there is no in-sandbox live feed.

### Updated next step

Design the loader around **static dataset transports** (GitHub Contents API with commit-SHA pinning
first, PyPI/npm packages second) instead of REST APIs of exchanges and aggregators. If live or
up-to-date data is required, confirm the sandbox egress policy with its operator or run the fetch
step outside the sandbox.
