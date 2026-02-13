import csv
import tempfile
import unittest
from pathlib import Path

from update_trades import (
    ASSET_VALUE_FILE,
    CURRENT_ASSETS_FILE,
    initialize_files,
    process_trade,
)
from update_valuation import update_valuation
from validate_csvs import validate_csv_files


def _read_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, headers, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


class ValidateCsvsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        initialize_files(base_dir=self.base, initial_cash="10000.00", initial_date="2026-02-13")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_returns_no_errors_for_consistent_files(self):
        process_trade(
            action="BUY",
            symbol="AAPL",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-14",
            base_dir=self.base,
        )
        update_valuation(valuation_date="2026-02-15", prices="AAPL=120", base_dir=self.base)

        errors = validate_csv_files(base_dir=self.base)
        self.assertEqual(errors, [])

    def test_detects_mismatch_between_transaction_log_and_current_assets(self):
        process_trade(
            action="BUY",
            symbol="AAPL",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-14",
            base_dir=self.base,
        )

        _write_rows(
            self.base / CURRENT_ASSETS_FILE,
            headers=["symbol", "amount"],
            rows=[
                {"symbol": "CASH", "amount": "9000.00"},
                {"symbol": "AAPL", "amount": "9"},
            ],
        )

        errors = validate_csv_files(base_dir=self.base)
        self.assertTrue(any("cannot reverse BUY for 'AAPL'" in error for error in errors))

    def test_detects_mismatch_between_snapshot_and_expected_holdings(self):
        process_trade(
            action="BUY",
            symbol="AAPL",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-14",
            base_dir=self.base,
        )

        value_rows = _read_rows(self.base / ASSET_VALUE_FILE)
        value_rows[-1]["assets_held"] = "CASH"
        value_rows[-1]["asset_values"] = "CASH:9000.00"
        value_rows[-1]["portfolio_value"] = "9000.00"
        _write_rows(
            self.base / ASSET_VALUE_FILE,
            headers=["date", "assets_held", "asset_values", "portfolio_value"],
            rows=value_rows,
        )

        errors = validate_csv_files(base_dir=self.base)
        self.assertTrue(any("assets_held is ['CASH']" in error for error in errors))

    def test_allows_first_day_trades_without_false_cash_or_symbol_mismatch(self):
        process_trade(
            action="BUY",
            symbol="QQQ",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-13",
            base_dir=self.base,
        )
        process_trade(
            action="BUY",
            symbol="SPY",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-13",
            base_dir=self.base,
        )
        process_trade(
            action="BUY",
            symbol="XLF",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-13",
            base_dir=self.base,
        )
        update_valuation(valuation_date="2026-02-14", prices="QQQ=105,SPY=101,XLF=50", base_dir=self.base)

        errors = validate_csv_files(base_dir=self.base)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
