"""CPU collection; all tasks freeze before any confirmation; no automatic retries."""

import hashlib
import json
from pathlib import Path
import time
import modal
from scripts import benchmark_suite as s

ROOT = Path(__file__).parent
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("numpy==2.2.6", "scipy==1.15.3", "scikit-learn==1.8.0")
    .env({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
)
for name in s.hashes():
    image = image.add_local_file(ROOT / name, "/root/scripts/" + name)
app = modal.App("astrax-benchmark-suite")


@app.function(
    image=image,
    cpu=(1, 1),
    memory=(2048, 2048),
    timeout=600,
    max_containers=4,
    retries=0,
    scaledown_window=2,
)
def task(mode, payload, expected):
    import platform
    import numpy, scipy, sklearn
    from scripts import benchmark_suite as b

    if b.hashes() != expected:
        raise RuntimeError("Remote source mismatch")
    start = time.perf_counter()
    name, body = payload
    if mode == "collect":
        result = b.collect(name, body)
    elif mode == "fit":
        result = b.fit(name, body)
    elif mode == "rollout":
        seed, names, bundle = body
        result = dict(
            seed=seed, policies={n: b.rollout(name, seed, n, bundle) for n in names}
        )
    elif mode == "freeze":
        result = b.select(body)
    elif mode == "summary":
        result = b.summarize(*body)
    else:
        raise ValueError("Unknown operation")
    return dict(
        result=result,
        function_seconds=time.perf_counter() - start,
        environment=dict(
            python=platform.python_version(),
            numpy=numpy.__version__,
            scipy=scipy.__version__,
            sklearn=sklearn.__version__,
        ),
    )


def execute(output, remote):
    raw = (output / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    if manifest != s.specification():
        raise ValueError("Changed specification")
    identity = hashlib.sha256(raw).hexdigest()
    if list(output.glob("*.pending")):
        raise RuntimeError("Inspect unresolved calls; no automatic retry")
    lock = output / "dispatch.lock"
    with lock.open("x") as f:
        f.write(identity)
    ledger = output / "dispatch.jsonl"

    def batch(jobs):
        saved = {}
        missing = []
        for name, mode, payload in jobs:
            path = output / (name + ".json")
            if path.exists():
                data = json.loads(path.read_text())
                if data["manifest_sha256"] != identity:
                    raise ValueError("Artifact identity")
                saved[name] = data["response"]["result"]
            else:
                missing.append((name, mode, payload))
        for offset in range(0, len(missing), 4):
            chunk = missing[offset : offset + 4]
            prior = (
                [json.loads(line) for line in ledger.read_text().splitlines()]
                if ledger.exists()
                else []
            )
            if len(prior) + len(chunk) > manifest["cost"]["max_calls"] or any(
                j[0] in {r["name"] for r in prior} for j in chunk
            ):
                raise RuntimeError("Call cap or attempted duplicate dispatch")
            for name, mode, _ in chunk:
                with (output / (name + ".pending")).open("x") as f:
                    f.write(identity)
                with ledger.open("a") as f:
                    f.write(
                        json.dumps(dict(name=name, mode=mode, manifest_sha256=identity))
                        + "\n"
                    )
            responses = list(
                remote(
                    [(mode, payload, manifest["sources"]) for _, mode, payload in chunk]
                )
            )
            if len(responses) != len(chunk):
                raise RuntimeError("Missing response")
            for (name, _, _), response in zip(chunk, responses):
                path = output / (name + ".json")
                temp = path.with_suffix(".tmp")
                temp.write_text(
                    json.dumps(
                        dict(manifest_sha256=identity, response=response),
                        allow_nan=False,
                    )
                    + "\n"
                )
                temp.replace(path)
                (output / (name + ".pending")).unlink()
                saved[name] = response["result"]
                print("Saved " + name, flush=True)
        return [saved[n] for n, _, _ in jobs]

    try:
        bundles = {}
        frozen = {}
        # Training, models and validation for every task precede all confirmation.
        for name in s.TASKS:
            split = manifest["splits"][name]
            training = batch(
                [
                    (f"{name}-training-{seed}", "collect", (name, seed))
                    for seed in split["training"]
                ]
            )
            for d, seed in zip(training, split["training"]):
                s.validate_training(name, d, seed)
            bundle = batch([(name + "-models", "fit", (name, training))])[0]
            bundles[name] = bundle
            if bundle["training_seeds"] != split["training"] or bundle["task"] != name:
                raise ValueError("Model identity")
            validation = batch(
                [
                    (
                        f"{name}-validation-{seed}",
                        "rollout",
                        (name, (seed, list(s.STATIC), bundle)),
                    )
                    for seed in split["validation"]
                ]
            )
            for row, seed in zip(validation, split["validation"]):
                if row["seed"] != seed or set(row["policies"]) != set(s.STATIC):
                    raise ValueError("Validation identity")
                for policy in s.STATIC:
                    s.validate_rollout(
                        name, row["policies"][policy], seed, policy, bundle
                    )
            frozen[name] = batch([(name + "-frozen", "freeze", (name, validation))])[0]
            if frozen[name] != s.select(validation):
                raise ValueError("Comparator mismatch")
        receipt = dict(
            manifest_sha256=identity,
            files={
                n
                + suffix: hashlib.sha256(
                    (output / (n + suffix + ".json")).read_bytes()
                ).hexdigest()
                for n in s.TASKS
                for suffix in ("-models", "-frozen")
            },
        )
        path = output / "freeze-receipt.json"
        if path.exists():
            if json.loads(path.read_text()) != receipt:
                raise ValueError("Frozen receipt changed")
        else:
            path.write_text(json.dumps(receipt, indent=2) + "\n")
        all_rows = {}
        for name in s.TASKS:
            names = [*s.LEARNED, frozen[name]["static"], "reactive"]
            seeds = manifest["splits"][name]["confirmation"]
            rows = batch(
                [
                    (
                        f"{name}-confirmation-{seed}",
                        "rollout",
                        (name, (seed, names, bundles[name])),
                    )
                    for seed in seeds
                ]
            )
            for row, seed in zip(rows, seeds):
                if row["seed"] != seed or set(row["policies"]) != set(names):
                    raise ValueError("Confirmation identity")
                for policy in names:
                    s.validate_rollout(
                        name, row["policies"][policy], seed, policy, bundles[name]
                    )
            all_rows[name] = rows
        return batch([("summary", "summary", ("suite", (all_rows, frozen)))])[0]
    finally:
        lock.unlink()


@app.local_entrypoint()
def main(output: str):
    print(
        json.dumps(
            execute(Path(output), lambda jobs: task.starmap(jobs, order_outputs=True)),
            indent=2,
        )
    )
