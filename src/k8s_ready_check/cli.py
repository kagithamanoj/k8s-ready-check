"""CLI: run readiness checks against YAML manifest files."""

from __future__ import annotations

import argparse
import sys

import yaml

from .checks import run_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="k8s-ready-check",
        description="Check Kubernetes manifests for production-readiness basics.",
    )
    parser.add_argument("files", nargs="+", help="YAML manifest files to check.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings as well as errors.",
    )
    args = parser.parse_args(argv)

    worst = 0
    for path in args.files:
        with open(path, encoding="utf-8") as fh:
            docs = [d for d in yaml.safe_load_all(fh) if d]
        for doc in docs:
            kind = doc.get("kind", "?")
            name = doc.get("metadata", {}).get("name", "?")
            findings = run_all(doc)
            if not findings:
                print(f"ok   {kind}/{name} ({path})")
                continue
            for finding in findings:
                level = finding["level"]
                print(
                    f"{level:<5} {kind}/{name} [{finding['check']}] "
                    f"({path}): {finding['message']}"
                )
                if level == "error":
                    worst = max(worst, 2)
                elif level == "warn":
                    worst = max(worst, 1)
    if args.strict and worst == 1:
        return 1
    return min(worst, 1) if not args.strict else worst


if __name__ == "__main__":
    sys.exit(main())
