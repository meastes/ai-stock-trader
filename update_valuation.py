#!/usr/bin/env python3
"""Update portfolio valuation snapshots without recording a trade."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from update_trades import (
    ASSET_VALUE_FILE,
    CURRENT_ASSETS_FILE,
    TRANSACTION_LOG_FILE,
    TRANSACTION_LOG_HEADERS,
    _last_known_prices,
    _parse_prices,
    _read_assets,
    _read_csv_rows,
    _upsert_asset_value_row,
    initialize_files,
)


def update_valuation(
    valuation_date: str | None = None,
    prices: str | None = None,
    base_dir: str | Path = ".",
) -> None:
    base = Path(base_dir)
    initialize_files(base_dir=base)

    current_assets_path = base / CURRENT_ASSETS_FILE
    transaction_log_path = base / TRANSACTION_LOG_FILE
    asset_value_path = base / ASSET_VALUE_FILE

    snapshot_date = valuation_date or date.today().isoformat()

    assets = _read_assets(current_assets_path)
    tx_rows = _read_csv_rows(transaction_log_path, TRANSACTION_LOG_HEADERS)
    valuation_prices = _last_known_prices(tx_rows)
    valuation_prices.update(_parse_prices(prices))

    _upsert_asset_value_row(asset_value_path, snapshot_date, assets, valuation_prices)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update daily asset valuation without adding a trade transaction.")
    parser.add_argument("--date", dest="valuation_date", default=None, help="Valuation date in YYYY-MM-DD format")
    parser.add_argument(
        "--prices",
        default=None,
        help="Optional valuation prices for held assets, e.g. AAPL=192.12,MSFT=425.50",
    )
    parser.add_argument("--base-dir", default=".", help="Directory containing CSV files")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    update_valuation(
        valuation_date=args.valuation_date,
        prices=args.prices,
        base_dir=args.base_dir,
    )


if __name__ == "__main__":
    main()
