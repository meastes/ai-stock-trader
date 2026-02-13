#!/usr/bin/env python3
"""Validate consistency across portfolio CSV files."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from update_trades import (
    ASSET_VALUE_FILE,
    ASSET_VALUE_HEADERS,
    CURRENT_ASSETS_FILE,
    CURRENT_ASSETS_HEADERS,
    TRANSACTION_LOG_FILE,
    TRANSACTION_LOG_HEADERS,
)

TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class Transaction:
    trade_date: str
    action: str
    symbol: str
    shares: Decimal
    total: Decimal


@dataclass(frozen=True)
class Snapshot:
    snapshot_date: str
    symbols: List[str]
    value_by_symbol: Dict[str, Decimal]


def _ordered_symbols(assets: Dict[str, Decimal]) -> List[str]:
    symbols = sorted([sym for sym, amount in assets.items() if sym != "CASH" and amount > 0])
    if assets.get("CASH", Decimal("0")) > 0:
        return ["CASH", *symbols]
    return symbols


def _parse_decimal(value: str, label: str, errors: List[str]) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        errors.append(f"{label}: invalid decimal value '{value}'.")
        return None


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _read_csv_rows(path: Path, expected_headers: Sequence[str], errors: List[str]) -> List[dict]:
    if not path.exists():
        errors.append(f"Missing file: {path.name}.")
        return []

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(expected_headers):
            errors.append(
                f"{path.name}: unexpected headers {reader.fieldnames}; expected {list(expected_headers)}."
            )
            return []
        return list(reader)


def _parse_assets(rows: Iterable[dict], errors: List[str]) -> Dict[str, Decimal]:
    assets: Dict[str, Decimal] = {}
    for row_index, row in enumerate(rows, start=2):
        symbol = row["symbol"].strip().upper()
        if not symbol:
            errors.append(f"{CURRENT_ASSETS_FILE} row {row_index}: symbol is empty.")
            continue
        if symbol in assets:
            errors.append(f"{CURRENT_ASSETS_FILE} row {row_index}: duplicate symbol '{symbol}'.")
            continue

        amount = _parse_decimal(row["amount"], f"{CURRENT_ASSETS_FILE} row {row_index} amount", errors)
        if amount is None:
            continue
        if amount <= 0:
            errors.append(f"{CURRENT_ASSETS_FILE} row {row_index}: amount for '{symbol}' must be greater than 0.")
            continue

        assets[symbol] = amount

    if "CASH" not in assets:
        errors.append(f"{CURRENT_ASSETS_FILE}: CASH position is missing.")

    return assets


def _parse_transactions(rows: Iterable[dict], errors: List[str]) -> List[Transaction]:
    transactions: List[Transaction] = []
    running_shares: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for row_index, row in enumerate(rows, start=2):
        tx_date = row["date"].strip()
        if not _is_iso_date(tx_date):
            errors.append(f"{TRANSACTION_LOG_FILE} row {row_index}: invalid date '{tx_date}'.")

        action = row["action"].strip().upper()
        if action not in {"BUY", "SELL"}:
            errors.append(f"{TRANSACTION_LOG_FILE} row {row_index}: action must be BUY or SELL.")
            continue

        symbol = row["symbol"].strip().upper()
        if not symbol or symbol == "CASH":
            errors.append(f"{TRANSACTION_LOG_FILE} row {row_index}: symbol must be a non-CASH ticker.")
            continue

        shares = _parse_decimal(row["shares"], f"{TRANSACTION_LOG_FILE} row {row_index} shares", errors)
        price = _parse_decimal(row["price_per_share"], f"{TRANSACTION_LOG_FILE} row {row_index} price", errors)
        total = _parse_decimal(
            row["total_transaction_amount"],
            f"{TRANSACTION_LOG_FILE} row {row_index} total_transaction_amount",
            errors,
        )
        if shares is None or price is None or total is None:
            continue
        if shares <= 0:
            errors.append(f"{TRANSACTION_LOG_FILE} row {row_index}: shares must be greater than 0.")
            continue
        if price <= 0:
            errors.append(f"{TRANSACTION_LOG_FILE} row {row_index}: price_per_share must be greater than 0.")
            continue

        expected_total = (shares * price).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        if total != expected_total:
            errors.append(
                f"{TRANSACTION_LOG_FILE} row {row_index}: total_transaction_amount is {total} "
                f"but expected {expected_total}."
            )
            continue

        if action == "BUY":
            running_shares[symbol] += shares
        else:
            running_shares[symbol] -= shares
            if running_shares[symbol] < 0:
                errors.append(
                    f"{TRANSACTION_LOG_FILE} row {row_index}: SELL for '{symbol}' exceeds previously purchased shares."
                )

        transactions.append(
            Transaction(
                trade_date=tx_date,
                action=action,
                symbol=symbol,
                shares=shares,
                total=total,
            )
        )

    return transactions


def _parse_asset_values(rows: Iterable[dict], errors: List[str]) -> List[Snapshot]:
    snapshots: List[Snapshot] = []
    seen_dates = set()
    previous_date: str | None = None

    for row_index, row in enumerate(rows, start=2):
        snapshot_date = row["date"].strip()
        if not _is_iso_date(snapshot_date):
            errors.append(f"{ASSET_VALUE_FILE} row {row_index}: invalid date '{snapshot_date}'.")
            continue
        if snapshot_date in seen_dates:
            errors.append(f"{ASSET_VALUE_FILE} row {row_index}: duplicate date '{snapshot_date}'.")
            continue
        if previous_date is not None and snapshot_date < previous_date:
            errors.append(f"{ASSET_VALUE_FILE} row {row_index}: rows are not sorted by ascending date.")
        previous_date = snapshot_date
        seen_dates.add(snapshot_date)

        raw_symbols = [token.strip().upper() for token in row["assets_held"].split("|") if token.strip()]
        if len(set(raw_symbols)) != len(raw_symbols):
            errors.append(f"{ASSET_VALUE_FILE} row {row_index}: assets_held has duplicate symbols.")
            continue

        value_by_symbol: Dict[str, Decimal] = {}
        parsed_symbols: List[str] = []
        if row["asset_values"].strip():
            for token in row["asset_values"].split("|"):
                pair = token.strip()
                if not pair:
                    continue
                if ":" not in pair:
                    errors.append(f"{ASSET_VALUE_FILE} row {row_index}: invalid asset_values entry '{pair}'.")
                    continue
                symbol_part, value_part = pair.split(":", 1)
                symbol = symbol_part.strip().upper()
                if not symbol:
                    errors.append(f"{ASSET_VALUE_FILE} row {row_index}: asset_values has an empty symbol.")
                    continue
                if symbol in value_by_symbol:
                    errors.append(f"{ASSET_VALUE_FILE} row {row_index}: duplicate symbol '{symbol}' in asset_values.")
                    continue

                value = _parse_decimal(
                    value_part.strip(),
                    f"{ASSET_VALUE_FILE} row {row_index} value for {symbol}",
                    errors,
                )
                if value is None:
                    continue
                if value < 0:
                    errors.append(f"{ASSET_VALUE_FILE} row {row_index}: value for '{symbol}' cannot be negative.")
                    continue

                parsed_symbols.append(symbol)
                value_by_symbol[symbol] = value

        if raw_symbols != parsed_symbols:
            errors.append(
                f"{ASSET_VALUE_FILE} row {row_index}: assets_held symbols do not match asset_values symbols/order."
            )
            continue

        portfolio_value = _parse_decimal(
            row["portfolio_value"],
            f"{ASSET_VALUE_FILE} row {row_index} portfolio_value",
            errors,
        )
        if portfolio_value is None:
            continue

        computed_value = sum(value_by_symbol.values(), Decimal("0")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        if portfolio_value != computed_value:
            errors.append(
                f"{ASSET_VALUE_FILE} row {row_index}: portfolio_value is {portfolio_value} "
                f"but sum(asset_values) is {computed_value}."
            )
            continue

        snapshots.append(
            Snapshot(
                snapshot_date=snapshot_date,
                symbols=raw_symbols,
                value_by_symbol=value_by_symbol,
            )
        )

    return snapshots


def _apply_transaction(assets: Dict[str, Decimal], transaction: Transaction) -> None:
    shares = assets.get(transaction.symbol, Decimal("0"))
    cash = assets.get("CASH", Decimal("0"))

    if transaction.action == "BUY":
        assets["CASH"] = cash - transaction.total
        assets[transaction.symbol] = shares + transaction.shares
        return

    assets["CASH"] = cash + transaction.total
    remaining = shares - transaction.shares
    if remaining > 0:
        assets[transaction.symbol] = remaining
    else:
        assets.pop(transaction.symbol, None)


def _reverse_transaction(assets: Dict[str, Decimal], transaction: Transaction, errors: List[str]) -> None:
    shares = assets.get(transaction.symbol, Decimal("0"))
    cash = assets.get("CASH", Decimal("0"))

    if transaction.action == "BUY":
        assets["CASH"] = cash + transaction.total
        remaining = shares - transaction.shares
        if remaining < 0:
            errors.append(
                f"{CURRENT_ASSETS_FILE}: cannot reverse BUY for '{transaction.symbol}' on {transaction.trade_date}; "
                "share count is inconsistent with transaction_log."
            )
            return
        if remaining > 0:
            assets[transaction.symbol] = remaining
        else:
            assets.pop(transaction.symbol, None)
        return

    assets["CASH"] = cash - transaction.total
    assets[transaction.symbol] = shares + transaction.shares


def _infer_first_snapshot_assets(
    assets: Dict[str, Decimal],
    transactions: List[Transaction],
    snapshots: List[Snapshot],
    errors: List[str],
) -> Dict[str, Decimal] | None:
    if not snapshots:
        errors.append(f"{ASSET_VALUE_FILE}: expected at least one row to validate snapshots.")
        return None

    first_snapshot_date = snapshots[0].snapshot_date
    inferred_assets = dict(assets)
    later_transactions = [tx for tx in transactions if tx.trade_date > first_snapshot_date]

    for transaction in reversed(later_transactions):
        _reverse_transaction(inferred_assets, transaction, errors)

    if "CASH" not in inferred_assets:
        errors.append(
            f"{CURRENT_ASSETS_FILE}: cannot infer first snapshot holdings because CASH is missing after reverse replay."
        )
        return None

    return inferred_assets


def _validate_cross_file_consistency(
    assets: Dict[str, Decimal],
    transactions: List[Transaction],
    snapshots: List[Snapshot],
    errors: List[str],
) -> None:
    first_snapshot_assets = _infer_first_snapshot_assets(assets, transactions, snapshots, errors)
    if first_snapshot_assets is None:
        return

    sorted_transactions = sorted(transactions, key=lambda item: item.trade_date)
    first_snapshot = snapshots[0]
    first_snapshot_symbols = _ordered_symbols(first_snapshot_assets)
    if first_snapshot.symbols != first_snapshot_symbols:
        errors.append(
            f"{ASSET_VALUE_FILE} row for {first_snapshot.snapshot_date}: assets_held is {first_snapshot.symbols} "
            f"but expected {first_snapshot_symbols} from current_assets and transaction_log."
        )

    if "CASH" in first_snapshot.value_by_symbol:
        first_snapshot_cash = first_snapshot.value_by_symbol["CASH"].quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        inferred_cash = first_snapshot_assets["CASH"].quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        if first_snapshot_cash != inferred_cash:
            errors.append(
                f"{ASSET_VALUE_FILE} row for {first_snapshot.snapshot_date}: CASH value {first_snapshot_cash} "
                f"does not match inferred CASH amount {inferred_cash}."
            )

    expected_assets = dict(first_snapshot_assets)
    tx_index = 0
    while tx_index < len(sorted_transactions) and sorted_transactions[tx_index].trade_date <= first_snapshot.snapshot_date:
        tx_index += 1

    for snapshot in snapshots[1:]:
        while tx_index < len(sorted_transactions) and sorted_transactions[tx_index].trade_date <= snapshot.snapshot_date:
            _apply_transaction(expected_assets, sorted_transactions[tx_index])
            tx_index += 1
        expected_symbols = _ordered_symbols(expected_assets)
        if snapshot.symbols != expected_symbols:
            errors.append(
                f"{ASSET_VALUE_FILE} row for {snapshot.snapshot_date}: assets_held is {snapshot.symbols} "
                f"but expected {expected_symbols} from transaction_log."
            )

    for transaction in sorted_transactions[tx_index:]:
        if transaction.trade_date > snapshots[-1].snapshot_date:
            errors.append(
                f"{TRANSACTION_LOG_FILE}: contains trade date {transaction.trade_date} after the latest valuation "
                f"date {snapshots[-1].snapshot_date}."
            )

    current_symbols = _ordered_symbols(assets)
    latest_snapshot = snapshots[-1]
    if latest_snapshot.symbols != current_symbols:
        errors.append(
            f"{ASSET_VALUE_FILE}: latest row symbols {latest_snapshot.symbols} do not match "
            f"{CURRENT_ASSETS_FILE} symbols {current_symbols}."
        )

    if "CASH" in latest_snapshot.value_by_symbol and "CASH" in assets:
        snapshot_cash = latest_snapshot.value_by_symbol["CASH"].quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        current_cash = assets["CASH"].quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        if snapshot_cash != current_cash:
            errors.append(
                f"{ASSET_VALUE_FILE}: latest CASH value {snapshot_cash} does not match "
                f"{CURRENT_ASSETS_FILE} CASH amount {current_cash}."
            )


def validate_csv_files(base_dir: str | Path = ".") -> List[str]:
    """Return a list of validation errors. Empty list means validation passed."""
    base = Path(base_dir)
    errors: List[str] = []

    current_assets_rows = _read_csv_rows(base / CURRENT_ASSETS_FILE, CURRENT_ASSETS_HEADERS, errors)
    transaction_rows = _read_csv_rows(base / TRANSACTION_LOG_FILE, TRANSACTION_LOG_HEADERS, errors)
    asset_value_rows = _read_csv_rows(base / ASSET_VALUE_FILE, ASSET_VALUE_HEADERS, errors)

    assets = _parse_assets(current_assets_rows, errors)
    transactions = _parse_transactions(transaction_rows, errors)
    snapshots = _parse_asset_values(asset_value_rows, errors)

    if assets and snapshots:
        _validate_cross_file_consistency(assets, transactions, snapshots, errors)

    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate consistency across current_assets.csv, transaction_log.csv, and asset_value_tracker.csv."
    )
    parser.add_argument("--base-dir", default=".", help="Directory containing CSV files")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    errors = validate_csv_files(base_dir=args.base_dir)

    if errors:
        print(f"Validation failed with {len(errors)} issue(s):")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("Validation passed: no inconsistencies found across the three CSV files.")


if __name__ == "__main__":
    main()
