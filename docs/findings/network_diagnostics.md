# Network diagnostics

**Date:** 2026-10-06

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

## Conclusion and next step

1. Scenario **(c)** (all outbound HTTPS closed except the package registry) is ruled out: curl reached both PyPI and GitHub with HTTP 200.
2. Scenario **(a)** applies specifically to GitHub in this sandbox: an E2B Proxy CA-signed certificate is trusted by the OS bundle but not by certifi. Using the OS bundle is a secure fix for that Requests check; `verify=False` is not appropriate.
3. For Binance and Yahoo, the results are most consistent with **destination-specific egress filtering or a gateway closing the TLS handshake** (scenario **(b)** broadly). The tests do not identify the exact network policy, and there was no HTTP 451 to diagnose as a geographic restriction.

Next, rerun the market-data checks from a network where Binance and Yahoo are permitted, or ask the sandbox/network operator whether those domains are intentionally blocked. Do not add large market datasets to Git; keep downloaded data local under `data/`.
