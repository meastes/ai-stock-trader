import csv
import tempfile
import unittest
from pathlib import Path

from update_trades import (
    ASSET_VALUE_FILE,
    CURRENT_ASSETS_FILE,
    TRANSACTION_LOG_FILE,
    initialize_files,
    process_trade,
)
from update_valuation import update_valuation


def _read_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, headers, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


class UpdateValuationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        initialize_files(base_dir=self.base, initial_cash="10000.00", initial_date="2026-02-13")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_adds_daily_snapshot_with_no_trade(self):
        update_valuation(valuation_date="2026-02-14", base_dir=self.base)

        assets = _read_rows(self.base / CURRENT_ASSETS_FILE)
        self.assertEqual(assets, [{"symbol": "CASH", "amount": "10000.00"}])

        transactions = _read_rows(self.base / TRANSACTION_LOG_FILE)
        self.assertEqual(transactions, [])

        values = _read_rows(self.base / ASSET_VALUE_FILE)
        self.assertEqual(
            values[-1],
            {
                "date": "2026-02-14",
                "assets_held": "CASH",
                "asset_values": "CASH:10000.00",
                "portfolio_value": "10000.00",
            },
        )

    def test_uses_supplied_prices_without_recording_transaction(self):
        process_trade(
            action="BUY",
            symbol="AAPL",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-14",
            base_dir=self.base,
        )
        before_transactions = _read_rows(self.base / TRANSACTION_LOG_FILE)

        update_valuation(valuation_date="2026-02-15", prices="AAPL=120", base_dir=self.base)

        after_transactions = _read_rows(self.base / TRANSACTION_LOG_FILE)
        self.assertEqual(after_transactions, before_transactions)

        values = _read_rows(self.base / ASSET_VALUE_FILE)
        self.assertEqual(
            values[-1],
            {
                "date": "2026-02-15",
                "assets_held": "CASH|AAPL",
                "asset_values": "CASH:9000.00|AAPL:1200.00",
                "portfolio_value": "10200.00",
            },
        )

    def test_same_day_valuation_replaces_existing_row(self):
        process_trade(
            action="BUY",
            symbol="AAPL",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-14",
            base_dir=self.base,
        )

        update_valuation(valuation_date="2026-02-14", prices="AAPL=110", base_dir=self.base)

        values = _read_rows(self.base / ASSET_VALUE_FILE)
        self.assertEqual(len(values), 2)
        self.assertEqual(
            values[-1],
            {
                "date": "2026-02-14",
                "assets_held": "CASH|AAPL",
                "asset_values": "CASH:9000.00|AAPL:1100.00",
                "portfolio_value": "10100.00",
            },
        )

    def test_raises_when_held_asset_has_no_price(self):
        _write_rows(
            self.base / CURRENT_ASSETS_FILE,
            headers=["symbol", "amount"],
            rows=[
                {"symbol": "CASH", "amount": "9000.00"},
                {"symbol": "MSFT", "amount": "5"},
            ],
        )

        with self.assertRaisesRegex(ValueError, "Missing valuation price for held symbol MSFT"):
            update_valuation(valuation_date="2026-02-14", base_dir=self.base)


if __name__ == "__main__":
    unittest.main()
