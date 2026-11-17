"""Offline replay of suite identities, exact geometry, observations and frozen Q values."""

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from scripts import benchmark_suite as s
from scripts.suite_portability import validate_rollout


def audit(output):
    raw = (output / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    expected = s.specification()
    original_auditor = (
        "62d6b280897b52fb07f7410c65a979525f8736e45b1b7d6fbd55b3ea53c9aa3f"
    )
    amended = manifest["sources"].get("audit_benchmark_suite.py") == original_auditor
    if amended:
        # This one known audit-only amendment changes no worker/model/statistics source.
        expected["sources"]["audit_benchmark_suite.py"] = original_auditor
        amendment = json.loads((output / "audit-amendment.json").read_text())
        if (
            amendment["original_auditor_sha256"] != original_auditor
            or amendment["corrected_expected_calls"] != 487
            or amendment["treatment_changes"]
            or amendment["seed_changes"]
            or amendment["recollection"]
        ):
            raise ValueError("Invalid audit amendment")
    if manifest != expected:
        raise ValueError("Manifest/source changed")
    if amended or (output / "frozen-sources").exists():
        for name, digest in manifest["sources"].items():
            if (
                hashlib.sha256(
                    (output / "frozen-sources" / name).read_bytes()
                ).hexdigest()
                != digest
            ):
                raise ValueError("Frozen source archive changed")
    supplementary_seconds = 0.0
    supplementary_calls = 0
    if (output / "portability-amendment.json").exists():
        portability = json.loads((output / "portability-amendment.json").read_text())
        if (
            portability["worker_changed"]
            or portability["model_changed"]
            or portability["confirmation_replaced"]
            or portability["observations_atol"] != 1e-12
            or portability["predictions_atol"] != 1e-12
        ):
            raise ValueError("Changed scientific protocol")
        for name, digest in portability["audit_sources"].items():
            if (
                hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                != digest
            ):
                raise ValueError("Changed portability audit source")
        linux = json.loads((output / "linux-portability-audit.json").read_text())
        if (
            linux["status"] != "passed"
            or linux["rollouts"] != 288
            or not linux["original_validator"]
            or linux["optimization_repeated"]
        ):
            raise ValueError("Original Linux audit failed")
        supplementary_seconds = linux["function_seconds"]
        supplementary_calls = 1
    identity = hashlib.sha256(raw).hexdigest()
    if list(output.glob("*.pending")):
        raise ValueError("Unresolved calls")
    ledger = [
        json.loads(line)
        for line in (output / "dispatch.jsonl").read_text().splitlines()
    ]
    expected_jobs = {"summary"}
    for task, split in manifest["splits"].items():
        expected_jobs.update({task + "-models", task + "-frozen"})
        expected_jobs.update(
            f"{task}-{phase}-{seed}" for phase, seeds in split.items() for seed in seeds
        )
    if (
        len(ledger) != len(expected_jobs)
        or {x["name"] for x in ledger} != expected_jobs
        or any(x["manifest_sha256"] != identity for x in ledger)
    ):
        raise ValueError("Dispatch accounting")
    first_confirm = next(
        i for i, x in enumerate(ledger) if "-confirmation-" in x["name"]
    )
    if not all(
        any(x["name"] == t + "-frozen" for x in ledger[:first_confirm]) for t in s.TASKS
    ):
        raise ValueError("Confirmation before freeze")
    seconds = 0
    for entry in ledger:
        item = json.loads((output / (entry["name"] + ".json")).read_text())
        if item["manifest_sha256"] != identity:
            raise ValueError("Artifact identity")
        seconds += item["response"]["function_seconds"]

    def read(n):
        return json.loads((output / (n + ".json")).read_text())["response"]["result"]

    receipt = json.loads((output / "freeze-receipt.json").read_text())
    if set(receipt["files"]) != {
        t + suffix for t in s.TASKS for suffix in ("-models", "-frozen")
    }:
        raise ValueError("Incomplete freeze receipt")
    if receipt["manifest_sha256"] != identity or any(
        hashlib.sha256((output / (n + ".json")).read_bytes()).hexdigest() != h
        for n, h in receipt["files"].items()
    ):
        raise ValueError("Frozen artifacts changed")
    all_rows = {}
    frozen = {}
    opportunity = {}
    failures = {}
    for task in s.TASKS:
        split = manifest["splits"][task]
        training = [read(f"{task}-training-{seed}") for seed in split["training"]]
        for seed, row in zip(split["training"], training):
            s.validate_training(task, row, seed)
        # Development-only, immediate action opportunity. No controller performance claim.
        gains = np.array(
            [
                [[b["reward"] for b in w["branches"]] for w in d["windows"]]
                for d in training
            ]
        )
        opportunity[task] = dict(
            mean_oracle_minus_best_constant=float(
                gains.max(axis=2).mean() - gains.mean(axis=(0, 1)).max()
            ),
            mean_branch_gain={
                a: float(gains[:, :, i].mean()) for i, a in enumerate(s.ACTIONS)
            },
        )
        bundle = read(task + "-models")
        if (
            bundle["training_seeds"] != split["training"]
            or bundle["task"] != task
            or bundle["config"] != s.old.CONFIG
        ):
            raise ValueError("Model identity")
        val = []
        for seed in split["validation"]:
            row = read(f"{task}-validation-{seed}")
            if row["seed"] != seed or set(row["policies"]) != set(s.STATIC):
                raise ValueError("Validation identity")
            for n in s.STATIC:
                validate_rollout(task, row["policies"][n], seed, n, bundle)
            val.append(row)
        frozen[task] = read(task + "-frozen")
        if frozen[task] != s.select(val):
            raise ValueError("Comparator selection")
        names = [*s.LEARNED, frozen[task]["static"], "reactive"]
        rows = []
        for seed in split["confirmation"]:
            row = read(f"{task}-confirmation-{seed}")
            if row["seed"] != seed or set(row["policies"]) != set(names):
                raise ValueError("Confirmation identity")
            for n in names:
                validate_rollout(task, row["policies"][n], seed, n, bundle)
            rows.append(row)
        all_rows[task] = rows
        failures[task] = sum(
            c.get("lp_failures", 0)
            for d in training
            for w in d["windows"]
            for b in w["branches"]
            for c in b["event"]["calls"]
        )
    expected = s.summarize(all_rows, frozen)
    if read("summary") != expected:
        raise ValueError("Summary mismatch")
    return dict(
        status="passed",
        audit_only_amendment=amended,
        training_transitions=6912,
        rollouts=1056,
        calls=len(ledger),
        total_cloud_calls=len(ledger) + supplementary_calls,
        study_function_seconds=seconds,
        supplementary_audit_seconds=supplementary_seconds,
        function_seconds=seconds + supplementary_seconds,
        estimated_function_USD=(seconds + supplementary_seconds) * 0.00001754,
        development_opportunity=opportunity,
        training_lp_failures=failures,
        pilot_gate_met=bool(
            not any(v["passed"] for v in expected["comparisons"].values())
            and any(
                d["mean_oracle_minus_best_constant"] < 0.0002
                for d in opportunity.values()
            )
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = audit(a.output)
    (a.output / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
