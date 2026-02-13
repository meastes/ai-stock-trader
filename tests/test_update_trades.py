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


def _read_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class UpdateTradesTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        initialize_files(base_dir=self.base, initial_cash="10000.00", initial_date="2026-02-13")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_buy_trade_updates_all_csvs(self):
        process_trade(
            action="BUY",
            symbol="AAPL",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-14",
            base_dir=self.base,
        )

        assets = _read_rows(self.base / CURRENT_ASSETS_FILE)
        self.assertEqual(
            assets,
            [
                {"symbol": "CASH", "amount": "9000.00"},
                {"symbol": "AAPL", "amount": "10"},
            ],
        )

        transactions = _read_rows(self.base / TRANSACTION_LOG_FILE)
        self.assertEqual(len(transactions), 1)
        self.assertEqual(
            transactions[0],
            {
                "date": "2026-02-14",
                "action": "BUY",
                "symbol": "AAPL",
                "shares": "10",
                "price_per_share": "100.00",
                "total_transaction_amount": "1000.00",
            },
        )

        values = _read_rows(self.base / ASSET_VALUE_FILE)
        self.assertEqual(len(values), 2)
        self.assertEqual(
            values[-1],
            {
                "date": "2026-02-14",
                "assets_held": "CASH|AAPL",
                "asset_values": "CASH:9000.00|AAPL:1000.00",
                "portfolio_value": "10000.00",
            },
        )

    def test_sell_trade_updates_cash_and_removes_symbol_when_zero(self):
        process_trade(
            action="BUY",
            symbol="AAPL",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-14",
            base_dir=self.base,
        )
        process_trade(
            action="SELL",
            symbol="AAPL",
            shares="10",
            price_per_share="120",
            trade_date="2026-02-15",
            base_dir=self.base,
        )

        assets = _read_rows(self.base / CURRENT_ASSETS_FILE)
        self.assertEqual(assets, [{"symbol": "CASH", "amount": "10200.00"}])

        transactions = _read_rows(self.base / TRANSACTION_LOG_FILE)
        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[1]["action"], "SELL")
        self.assertEqual(transactions[1]["total_transaction_amount"], "1200.00")

        values = _read_rows(self.base / ASSET_VALUE_FILE)
        self.assertEqual(
            values[-1],
            {
                "date": "2026-02-15",
                "assets_held": "CASH",
                "asset_values": "CASH:10200.00",
                "portfolio_value": "10200.00",
            },
        )

    def test_rejects_buy_when_cash_is_insufficient(self):
        with self.assertRaisesRegex(ValueError, "Insufficient cash"):
            process_trade(
                action="BUY",
                symbol="AAPL",
                shares="200",
                price_per_share="100",
                trade_date="2026-02-14",
                base_dir=self.base,
            )

        assets = _read_rows(self.base / CURRENT_ASSETS_FILE)
        self.assertEqual(assets, [{"symbol": "CASH", "amount": "10000.00"}])

        transactions = _read_rows(self.base / TRANSACTION_LOG_FILE)
        self.assertEqual(transactions, [])

    def test_multiple_trades_same_day_upserts_asset_value_row(self):
        process_trade(
            action="BUY",
            symbol="AAPL",
            shares="10",
            price_per_share="100",
            trade_date="2026-02-14",
            base_dir=self.base,
        )
        process_trade(
            action="BUY",
            symbol="MSFT",
            shares="5",
            price_per_share="50",
            trade_date="2026-02-14",
            base_dir=self.base,
        )

        values = _read_rows(self.base / ASSET_VALUE_FILE)
        self.assertEqual(len(values), 2)
        self.assertEqual(
            values[-1],
            {
                "date": "2026-02-14",
                "assets_held": "CASH|AAPL|MSFT",
                "asset_values": "CASH:8750.00|AAPL:1000.00|MSFT:250.00",
                "portfolio_value": "10000.00",
            },
        )


if __name__ == "__main__":
    unittest.main()
