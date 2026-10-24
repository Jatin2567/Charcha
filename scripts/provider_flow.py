"""Local-only provider flow approval and manual balance evidence. Makes no API calls.

Review the printed resource limits with the human before `approve`. This tool is
an operator capability, deliberately absent from browser/HTTP routes. It opens
only the local ledger, even when the application remains in demo mode.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from pydantic import ValidationError

from artha_mesh.config import Settings
from artha_mesh.errors import ProviderError
from artha_mesh.services.approvals import BALANCE_UNITS, PURPOSES, RESOURCE_KEYS, validate_budgets
from artha_mesh.services.usage import UsageGuard


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("plan", "approve"):
        command = commands.add_parser(name)
        command.add_argument("--purpose", choices=PURPOSES, required=True)
        command.add_argument("--seconds", type=int, required=True, help="Expiry 1–300 seconds; not a billing estimate")
        for key in RESOURCE_KEYS:
            command.add_argument("--" + key.replace("_", "-"), type=int, default=0)
        if name == "approve":
            command.add_argument("--human-approved", action="store_true", required=True,
                                 help="Use only after the human explicitly approves this exact flow")
            command.add_argument("--before-balance", type=float)
            command.add_argument("--unit", choices=BALANCE_UNITS)
            command.add_argument("--before-observed-at")
    commands.add_parser("status")
    close = commands.add_parser("close")
    close.add_argument("--flow-id", required=True)
    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--flow-id", required=True)
    reconcile.add_argument("--after-balance", required=True, type=float)
    reconcile.add_argument("--unit", required=True, choices=BALANCE_UNITS)
    reconcile.add_argument("--after-observed-at", required=True)
    balance = commands.add_parser("balance")
    balance.add_argument("--balance", required=True, type=float)
    balance.add_argument("--unit", required=True, choices=BALANCE_UNITS)
    balance.add_argument("--observed-at", required=True)
    balance.add_argument("--source", choices=("manual_dashboard", "user_reported"), default="manual_dashboard")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    guard = None
    try:
        if args.command in ("plan", "approve"):
            budgets = validate_budgets({key: getattr(args, key) for key in RESOURCE_KEYS})
            if not 1 <= args.seconds <= 300:
                raise ValueError("Expiry must be from 1 to 300 seconds")
            if args.command == "plan":
                print(json.dumps({"purpose": args.purpose, "seconds": args.seconds, "budgets": budgets,
                                  "provider_credit_cost": None,
                                  "detail": "Plan only; no grant, ledger write or API call. Obtain human permission before approval. Vendor charges require dashboard evidence."}, indent=2))
                return 0
        # Mode is overridden for ledger commands only; .env and the running API mode
        # are never changed, and no app, HTTP client or speech adapter is imported.
        settings = Settings(mode="live", usage_require_flow_approval=True)
        guard = UsageGuard(settings)
        if args.command == "approve":
            output = guard.approve_flow(
                purpose=args.purpose, seconds=args.seconds, budgets=budgets,
                before_balance=args.before_balance, balance_unit=args.unit,
                before_observed_at=args.before_observed_at,
            )
        elif args.command == "close":
            output = guard.close_flow(args.flow_id)
        elif args.command == "reconcile":
            output = guard.reconcile_flow(flow_id=args.flow_id, after_balance=args.after_balance,
                                          balance_unit=args.unit, after_observed_at=args.after_observed_at)
        elif args.command == "balance":
            guard.record_programme_balance(balance=args.balance, unit=args.unit,
                                           observed_at=args.observed_at, source=args.source)
            output = guard.snapshot()["programme"]
        else:
            snapshot = guard.snapshot()
            output = {"approval": snapshot["approval"], "programme": snapshot["programme"],
                      "resources": snapshot["resources"]}
        print(json.dumps(output, indent=2, allow_nan=False))
        return 0
    except ValidationError:
        print("Configuration is invalid; values are redacted. No provider call was made.", file=sys.stderr)
        return 1
    except (ProviderError, ValueError) as exc:
        # These errors are authored by the local guard; no upstream payload exists.
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if guard:
            guard.close()


if __name__ == "__main__":
    raise SystemExit(main())
