# Upstream source sync and validation scope

This candidate preserves fork commit `eff8a7320fcf0b473b135690fa1a5b0d9b022a83` and merges upstream main `5c553b5222044f6a5527bd377b4104c50ee0ad28` (aihf 2.2.0 → 2.7.2). The sync adds paper-fund state, intraday sessions, scorecards, allocation and optional x402 payments. Source sync and synthetic CI do not establish an installed service's deployed revision or authorize a provider, wallet or live-trading run.

## Upstream API and data migration

Upstream removes the earlier `hedge_fund.backtesting` per-model `BacktestEngine`, `BacktestResult`, `PerformanceMetrics` and `Trade` exports and its `python -m hedge_fund.backtesting` entrypoint. The old `hedge_fund.event_study` package is also removed. External callers using them must migrate or remain on their existing release; this fork does not fabricate compatibility shims. A repository source/documentation scan found no remaining callers of those removed APIs. This does not inspect external notebooks, scripts or installed consumers.

The current supported CLI is `aihf backtest MANDATE --universe ...` and `aihf paper create|tick|run|stop|status|list|halt|resume ...`; the earlier mandate/`--tickers`/`--backtest` command shape is replaced. Current results use `FundBacktestResult` with session records. Mandates require schema version 2 and explicit supported strategy modes. Preserve original user mandates, research results, paper directories and provider configuration before upgrading; older data is not silently rewritten into a claimed compatible format. New ownership/checkpoint behavior and crash recovery are described in [PAPER-OWNERSHIP.md](PAPER-OWNERSHIP.md).

## Repairs and validation

The candidate includes regression repairs for invalid cost-adjusted fills, checkpoint-cache corruption detection, cooperative writer ownership, safe runner stop requests, provider-origin pagination, stale mixed-age quote display, intraday daily-data eligibility, finite configuration and saved-mandate filename containment. Review the final PR diff and exact-commit CI for the final list and results. A checkpoint checksum detects changed bytes; it does not authenticate a writer or prevent a malicious same-user recomputation.

The quality workflow uses ordinary hosted Linux and Windows runners with read-only GitHub permissions. Dependency installation is separate from tests. Provider/wallet credentials are blank, dotenv auto-discovery and user/repository files are denied while explicit temporary test fixtures are allowed, and Python socket connections during tests are limited to loopback/Unix event-loop support. Test fakes exercise synthetic data and books. Live provider smoke tests remain skipped. No pipeline deploys an application, publishes a package, calls a trading broker or moves funds.

## Platform behavior

Runner liveness on Windows uses a non-signaling process-handle query. A POSIX zero-signal probe is unsafe there because zero represents a console control event. Runner stop remains a cooperative token-bound request; acknowledgement does not prove the process has exited.

On Windows, credentials entered through the TUI are kept only in the current process environment. They are not written to or merged into an existing credential file, and must be supplied again at the next independent launch. A reviewed Windows ACL or OS-vault persistence adapter is not implemented. On POSIX, saving uses an owner-readable/writable (0600) temporary file before writing secret bytes, flushes it, and atomically replaces the credential file; failed writes preserve the previous file and environment.

Redo preserves a superseded ledger record before removing it from the live chain. An existing byte-identical archive can be reused; a conflicting archive stops the operation and retains both records for inspection. Archive integrity remains distinct from authenticated provenance.

## Limits requiring separate evidence

- Historical company sector/industry classification currently uses latest company facts, so reclassifications can cause historical lookahead. Day-only fundamentals and earnings signals in minute mode are conservatively restricted to the previous calendar day; timestamped news/releases retain bar-time filtering.
- Analyst IC observations and strategy returns can overlap and correlate. For minute funds, the reported IC `n_dates` groups eligible full session timestamps, so it can count multiple bars from one date. The displayed t-statistic and minimum evidence counts do not prove independent observations or predictive trading fitness.
- Universe selection, survivorship, provider history corrections, point-in-time availability and actual transaction costs require research validation beyond synthetic fixtures. LLM blind prompts reduce identifying information and cannot remove model-training lookahead.
- Cooperative ownership relies on local filesystem atomic directory semantics and users respecting the public APIs. It is not a distributed lease or an authorization boundary.
- Exact installed-runtime ownership, external service deployment, real market/provider behavior, funded-wallet operation and investment suitability remain unverified. Passing CI is no financial-performance or production sign-off.
