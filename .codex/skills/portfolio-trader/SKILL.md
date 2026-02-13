---
name: portfolio-trader
description: Research and execute stock trades to maximize total portfolio value using current_assets.csv, transaction_log.csv, and asset_value_tracker.csv. Use when deciding BUY or SELL actions, screening and ranking a broad candidate universe (top 30), running first-pass and second-pass research before committing to trades, marking the portfolio to current market value through update_valuation.py before trading, and recording trades through update_trades.py without editing CSV files directly.
---

# Portfolio Trader

## Overview

Research trade ideas, rank them by expected upside and risk, update portfolio valuation before any trade, then execute orders through `update_trades.py`.

## Required Inputs

- `current_assets.csv` for current cash and holdings
- `transaction_log.csv` for historical trades and last known prices
- `asset_value_tracker.csv` for daily mark-to-market snapshots
- `update_valuation.py` for valuation snapshot writes
- `update_trades.py` for all trade writes

## Workflow

### 1. Read current portfolio state

1. Load holdings and cash from `current_assets.csv`.
2. Load historical trades from `transaction_log.csv`.
3. Identify held symbols (exclude `CASH`), available cash, and concentration risk.

### 2. Perform multi-source research

1. Build a candidate universe with existing holdings plus enough new names to reach at least 30 total symbols.
2. Run a first-pass screen across all 30 symbols using recent catalysts, liquidity, and evidence quality to rank names.
3. Collect evidence from multiple source classes: financial news, company communications, market commentary, and social sentiment.
4. Prefer recent information and verify contradictory claims before acting.
5. Capture source URLs and dates for each thesis.

Reference: `references/research-framework.md`.

### 3. Run second-pass research on top candidates

1. Select the top 5-10 symbols from first-pass ranking for deep validation.
2. Re-check thesis durability with a second-pass process: estimate revisions, valuation sanity, near-term event risk, and contradictory evidence.
3. Score each second-pass symbol on expected return, downside risk, confidence quality, and liquidity/execution quality.
4. Propose no-trade if evidence quality is weak or signals conflict materially.
5. Produce final trade shortlist only from symbols that pass second-pass thresholds.

### 4. Mark portfolio to market before any trade

1. Collect current prices for all held non-cash symbols.
2. Update `asset_value_tracker.csv` before placing any order:

```bash
python3 update_valuation.py \
  --base-dir . \
  --date YYYY-MM-DD \
  --prices AAPL=210.25,MSFT=430.10
```

3. Never edit CSV files manually.

### 5. Execute trades with `update_trades.py`

1. For every order, call:

```bash
python3 update_trades.py \
  --action BUY \
  --symbol NVDA \
  --shares 2 \
  --price 710.50 \
  --date YYYY-MM-DD \
  --prices AAPL=210.25,MSFT=430.10,NVDA=710.50 \
  --base-dir .
```

2. Use `--action SELL` for sells.
3. Include `--prices` for valuation of any currently held symbols when needed.
4. Never write directly to `current_assets.csv`, `transaction_log.csv`, or `asset_value_tracker.csv`.

### 6. Validate post-trade state

1. Confirm `current_assets.csv` reflects expected positions and cash.
2. Confirm `transaction_log.csv` contains the executed trades.
3. Confirm `asset_value_tracker.csv` has an updated row for the trade date.

### 7. Commit updated CSVs to git after all trades

1. Stage only the portfolio tracking CSVs:

```bash
git add current_assets.csv transaction_log.csv asset_value_tracker.csv
```

2. Commit after all planned trades are complete:

```bash
git commit -m "Update portfolio after trade cycle on YYYY-MM-DD"
```

3. Do not include unrelated files in this commit.

## Guardrails

- Maximize portfolio value, not trade count.
- Research at least 30 symbols before selecting trade candidates.
- Require second-pass research validation before placing any order.
- Skip low-conviction ideas.
- Avoid concentrated single-name risk unless evidence quality is exceptional.
- Preserve cash buffer when macro or event risk is elevated.
- Reject action when required pricing data is missing.
- Commit only `current_assets.csv`, `transaction_log.csv`, and `asset_value_tracker.csv` for trade-cycle updates.

## Outputs

Provide:

1. Recommended trades with rationale and confidence.
2. Source-backed research summary with links.
3. Commands executed (valuation update first, then trades).
4. Expected portfolio impact and key risks.
5. Git commit hash for the CSV update commit.
