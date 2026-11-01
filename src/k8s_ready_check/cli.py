"""CLI: run readiness checks against YAML manifest files."""

from __future__ import annotations

import argparse
import json
import sys

import yaml

from .checks import CHECK_NAMES, run_all


def _parse_ignore(values: list[str]) -> set[str]:
    """Split --ignore values on commas and drop blanks."""
    names = set()
    for value in values:
        for name in value.split(","):
            name = name.strip()
            if name:
                names.add(name)
    return names


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
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format: human-readable text (default) or JSON.",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="CHECK",
        help=(
            "Skip a check by name; repeatable and comma-separated, "
            "e.g. --ignore replicas --ignore probes,resources. "
            f"Valid names: {', '.join(CHECK_NAMES)}."
        ),
    )
    args = parser.parse_args(argv)
    ignored = _parse_ignore(args.ignore)
    unknown = sorted(ignored - set(CHECK_NAMES))
    if unknown:
        parser.error(
            f"unknown check(s): {', '.join(unknown)}; "
            f"valid names: {', '.join(CHECK_NAMES)}"
        )

    # Load every document first: the PodDisruptionBudget check needs
    # the full set of budgets, which may live in another file or
    # another document in the same file as the workload.
    all_docs = []
    for path in args.files:
        with open(path, encoding="utf-8") as fh:
            docs = [d for d in yaml.safe_load_all(fh) if d]
        for doc in docs:
            all_docs.append((path, doc))
    pdb_docs = [
        doc for _, doc in all_docs if doc.get("kind") == "PodDisruptionBudget"
    ]

    worst = 0
    results = []
    for path, doc in all_docs:
        kind = doc.get("kind", "?")
        name = doc.get("metadata", {}).get("name", "?")
        findings = run_all(doc, pdbs=pdb_docs, ignore=ignored)
        results.append(
            {
                "file": path,
                "kind": kind,
                "name": name,
                "findings": findings,
            }
        )
        if args.output == "json":
            for finding in findings:
                if finding["level"] == "error":
                    worst = max(worst, 2)
                elif finding["level"] == "warn":
                    worst = max(worst, 1)
            continue
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
    if args.output == "json":
        all_findings = [
            finding for result in results for finding in result["findings"]
        ]
        report = {
            "results": results,
            "summary": {
                "files": len(args.files),
                "resources": len(results),
                "findings": len(all_findings),
                "errors": sum(
                    1 for f in all_findings if f["level"] == "error"
                ),
                "warnings": sum(
                    1 for f in all_findings if f["level"] == "warn"
                ),
            },
        }
        print(json.dumps(report, indent=2))
    if args.strict and worst == 1:
        return 1
    return min(worst, 1) if not args.strict else worst


if __name__ == "__main__":
    sys.exit(main())
