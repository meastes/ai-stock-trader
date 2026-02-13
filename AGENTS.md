# AGENTS.md

## Project overview
- This repository is a lightweight portfolio tracker built around three CSV files:
  - `current_assets.csv`
  - `transaction_log.csv`
  - `asset_value_tracker.csv`
- Core behavior lives in:
  - `update_trades.py` (records BUY/SELL trades and updates all CSVs)
  - `update_valuation.py` (writes a valuation snapshot without recording a trade)
- Tests live in `tests/` and use Python `unittest`.

## Primary agent workflow
1. Understand current portfolio state from the CSVs.
2. If asked to mark portfolio value to date, run valuation first:
   - `python3 update_valuation.py --date YYYY-MM-DD --prices SYMBOL=PRICE,...`
3. If asked to execute a trade, use:
   - `python3 update_trades.py --action BUY|SELL --symbol TICKER --shares N --price P --date YYYY-MM-DD`
4. Re-run valuation when needed with updated prices.
5. Validate changes with tests.

## Non-negotiable rules
- Do not edit the CSV files manually when processing trades or valuations; use the scripts.
- Preserve CSV header names and column order exactly.
- Use `YYYY-MM-DD` dates.
- Keep `CASH` as the cash position symbol.
- Keep monetary precision at two decimals and share quantities as implemented by existing helpers.

## CSV contracts
- `current_assets.csv`
  - headers: `symbol,amount`
  - includes `CASH` and any held tickers with positive amounts
- `transaction_log.csv`
  - headers: `date,action,symbol,shares,price_per_share,total_transaction_amount`
  - append-only trade log
- `asset_value_tracker.csv`
  - headers: `date,assets_held,asset_values,portfolio_value`
  - one row per date; same-day updates replace the existing row

## Test commands
- Run all tests:
  - `python3 -m unittest discover -s tests`
- Run specific modules:
  - `python3 -m unittest tests.test_update_trades tests.test_update_valuation`

## Skill usage
- For portfolio decision-making and execution workflows, use:
  - `.codex/skills/portfolio-trader/SKILL.md`
- For this repository, prefer following that skill's process for research, ranking, and trade execution steps.
