#!/usr/bin/env python3
"""Update stock trade tracking CSV files."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Iterable, List
from zoneinfo import ZoneInfo

CURRENT_ASSETS_HEADERS = ["symbol", "amount"]
TRANSACTION_LOG_HEADERS = [
    "date",
    "action",
    "symbol",
    "shares",
    "price_per_share",
    "total_transaction_amount",
]
ASSET_VALUE_HEADERS = ["date", "assets_held", "asset_values", "portfolio_value"]

CURRENT_ASSETS_FILE = "current_assets.csv"
TRANSACTION_LOG_FILE = "transaction_log.csv"
ASSET_VALUE_FILE = "asset_value_tracker.csv"

TRACKING_TIMEZONE_NAME = "America/New_York"
TRACKING_TIMEZONE = ZoneInfo(TRACKING_TIMEZONE_NAME)

TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class Trade:
    action: str
    symbol: str
    shares: Decimal
    price_per_share: Decimal
    trade_date: str

    @property
    def total(self) -> Decimal:
        return (self.shares * self.price_per_share).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _parse_decimal(value: str, label: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Invalid {label}: {value}") from exc


def _to_money(value: Decimal) -> str:
    return str(value.quantize(TWOPLACES, rounding=ROUND_HALF_UP))


def _to_quantity(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return text or "0"


def _ordered_symbols(assets: Dict[str, Decimal]) -> List[str]:
    symbols = sorted([sym for sym in assets.keys() if sym != "CASH"])
    if "CASH" in assets:
        return ["CASH", *symbols]
    return symbols


def _today_iso_in_tracking_tz() -> str:
    return datetime.now(TRACKING_TIMEZONE).date().isoformat()


def initialize_files(base_dir: str | Path = ".", initial_cash: str = "10000.00", initial_date: str | None = None) -> None:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    start_date = initial_date or _today_iso_in_tracking_tz()
    cash = _parse_decimal(initial_cash, "initial cash")
    if cash < 0:
        raise ValueError("Initial cash cannot be negative.")

    current_assets_path = base / CURRENT_ASSETS_FILE
    if not current_assets_path.exists():
        _write_csv(current_assets_path, CURRENT_ASSETS_HEADERS, [{"symbol": "CASH", "amount": _to_money(cash)}])

    transaction_log_path = base / TRANSACTION_LOG_FILE
    if not transaction_log_path.exists():
        _write_csv(transaction_log_path, TRANSACTION_LOG_HEADERS, [])

    asset_value_path = base / ASSET_VALUE_FILE
    if not asset_value_path.exists():
        row = {
            "date": start_date,
            "assets_held": "CASH",
            "asset_values": f"CASH:{_to_money(cash)}",
            "portfolio_value": _to_money(cash),
        }
        _write_csv(asset_value_path, ASSET_VALUE_HEADERS, [row])


def _read_csv_rows(path: Path, headers: Iterable[str]) -> List[dict]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = list(headers)
        if reader.fieldnames != expected:
            raise ValueError(f"Unexpected headers in {path.name}: {reader.fieldnames}; expected: {expected}")
        return list(reader)


def _write_csv(path: Path, headers: Iterable[str], rows: Iterable[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers))
        writer.writeheader()
        writer.writerows(rows)


def _read_assets(path: Path) -> Dict[str, Decimal]:
    rows = _read_csv_rows(path, CURRENT_ASSETS_HEADERS)
    assets: Dict[str, Decimal] = {}
    for row in rows:
        symbol = row["symbol"].strip().upper()
        if not symbol:
            continue
        amount = _parse_decimal(row["amount"], f"amount for {symbol}")
        if amount <= 0:
            continue
        assets[symbol] = amount
    if "CASH" not in assets:
        assets["CASH"] = Decimal("0")
    return assets


def _write_assets(path: Path, assets: Dict[str, Decimal]) -> None:
    rows = []
    for symbol in _ordered_symbols(assets):
        amount = assets[symbol]
        if amount <= 0:
            continue
        rows.append({"symbol": symbol, "amount": _to_money(amount) if symbol == "CASH" else _to_quantity(amount)})
    _write_csv(path, CURRENT_ASSETS_HEADERS, rows)


def _parse_prices(prices: str | None) -> Dict[str, Decimal]:
    if not prices:
        return {}
    parsed: Dict[str, Decimal] = {}
    for pair in prices.split(","):
        token = pair.strip()
        if not token:
            continue
        if "=" not in token:
            raise ValueError(f"Invalid --prices entry: {token}. Expected SYMBOL=PRICE.")
        symbol, value = token.split("=", 1)
        parsed[symbol.strip().upper()] = _parse_decimal(value.strip(), f"price for {symbol.strip().upper()}")
    return parsed


def _last_known_prices(transaction_rows: List[dict]) -> Dict[str, Decimal]:
    prices: Dict[str, Decimal] = {}
    for row in transaction_rows:
        symbol = row["symbol"].strip().upper()
        if symbol and symbol != "CASH":
            prices[symbol] = _parse_decimal(row["price_per_share"], f"price for {symbol}")
    return prices


def _build_snapshot(assets: Dict[str, Decimal], prices: Dict[str, Decimal]) -> tuple[str, str, str]:
    symbols = _ordered_symbols(assets)
    held_symbols = []
    values = []
    portfolio_total = Decimal("0")

    for symbol in symbols:
        qty = assets[symbol]
        if qty <= 0:
            continue
        if symbol == "CASH":
            value = qty.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        else:
            if symbol not in prices:
                raise ValueError(f"Missing valuation price for held symbol {symbol}. Pass --prices {symbol}=PRICE.")
            value = (qty * prices[symbol]).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        held_symbols.append(symbol)
        values.append(f"{symbol}:{_to_money(value)}")
        portfolio_total += value

    return "|".join(held_symbols), "|".join(values), _to_money(portfolio_total)


def _upsert_asset_value_row(path: Path, trade_date: str, assets: Dict[str, Decimal], prices: Dict[str, Decimal]) -> None:
    rows = _read_csv_rows(path, ASSET_VALUE_HEADERS)
    assets_held, asset_values, portfolio_value = _build_snapshot(assets, prices)
    new_row = {
        "date": trade_date,
        "assets_held": assets_held,
        "asset_values": asset_values,
        "portfolio_value": portfolio_value,
    }

    replaced = False
    for index, row in enumerate(rows):
        if row["date"] == trade_date:
            rows[index] = new_row
            replaced = True
            break
    if not replaced:
        rows.append(new_row)

    rows.sort(key=lambda item: item["date"])
    _write_csv(path, ASSET_VALUE_HEADERS, rows)


def process_trade(
    action: str,
    symbol: str,
    shares: str,
    price_per_share: str,
    trade_date: str | None = None,
    prices: str | None = None,
    base_dir: str | Path = ".",
) -> None:
    base = Path(base_dir)
    initialize_files(base_dir=base)

    current_assets_path = base / CURRENT_ASSETS_FILE
    transaction_log_path = base / TRANSACTION_LOG_FILE
    asset_value_path = base / ASSET_VALUE_FILE

    action_normalized = action.strip().upper()
    if action_normalized not in {"BUY", "SELL"}:
        raise ValueError("Action must be BUY or SELL.")

    symbol_normalized = symbol.strip().upper()
    if not symbol_normalized or symbol_normalized == "CASH":
        raise ValueError("Symbol must be a stock ticker and cannot be CASH.")

    share_qty = _parse_decimal(shares, "shares")
    if share_qty <= 0:
        raise ValueError("Shares must be greater than 0.")

    share_price = _parse_decimal(price_per_share, "price per share")
    if share_price <= 0:
        raise ValueError("Price per share must be greater than 0.")

    tx_date = trade_date or _today_iso_in_tracking_tz()
    trade = Trade(
        action=action_normalized,
        symbol=symbol_normalized,
        shares=share_qty,
        price_per_share=share_price,
        trade_date=tx_date,
    )

    assets = _read_assets(current_assets_path)
    current_shares = assets.get(trade.symbol, Decimal("0"))
    current_cash = assets.get("CASH", Decimal("0"))

    if trade.action == "BUY":
        if current_cash < trade.total:
            raise ValueError(f"Insufficient cash. Available: {_to_money(current_cash)}, needed: {_to_money(trade.total)}.")
        assets["CASH"] = current_cash - trade.total
        assets[trade.symbol] = current_shares + trade.shares
    else:
        if current_shares < trade.shares:
            raise ValueError(
                f"Insufficient shares to sell. Available: {_to_quantity(current_shares)}, requested: {_to_quantity(trade.shares)}."
            )
        remaining = current_shares - trade.shares
        assets["CASH"] = current_cash + trade.total
        if remaining > 0:
            assets[trade.symbol] = remaining
        elif trade.symbol in assets:
            del assets[trade.symbol]

    tx_rows = _read_csv_rows(transaction_log_path, TRANSACTION_LOG_HEADERS)
    new_tx_row = {
        "date": trade.trade_date,
        "action": trade.action,
        "symbol": trade.symbol,
        "shares": _to_quantity(trade.shares),
        "price_per_share": _to_money(trade.price_per_share),
        "total_transaction_amount": _to_money(trade.total),
    }
    tx_rows.append(new_tx_row)

    valuation_prices = _last_known_prices(tx_rows)
    valuation_prices.update(_parse_prices(prices))
    valuation_prices[trade.symbol] = trade.price_per_share

    _write_assets(current_assets_path, assets)
    _write_csv(transaction_log_path, TRANSACTION_LOG_HEADERS, tx_rows)
    _upsert_asset_value_row(asset_value_path, trade.trade_date, assets, valuation_prices)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update stock tracking CSV files with a trade.")
    parser.add_argument("--action", required=True, choices=["BUY", "SELL", "buy", "sell"])
    parser.add_argument("--symbol", required=True, help="Ticker symbol, e.g. AAPL")
    parser.add_argument("--shares", required=True, help="Number of shares traded")
    parser.add_argument("--price", required=True, help="Price paid/received per share")
    parser.add_argument("--date", dest="trade_date", default=None, help="Trade date in YYYY-MM-DD format")
    parser.add_argument(
        "--prices",
        default=None,
        help="Optional valuation prices for held assets, e.g. AAPL=192.12,MSFT=425.50",
    )
    parser.add_argument("--base-dir", default=".", help="Directory containing CSV files")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    process_trade(
        action=args.action,
        symbol=args.symbol,
        shares=args.shares,
        price_per_share=args.price,
        trade_date=args.trade_date,
        prices=args.prices,
        base_dir=args.base_dir,
    )


if __name__ == "__main__":
    main()
