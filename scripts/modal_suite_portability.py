"""One bounded Linux validation call, with the original frozen audit unchanged."""

import hashlib
import json
from pathlib import Path
import time
import modal
from scripts.modal_benchmark_suite import image
from scripts import benchmark_suite as s

app = modal.App("astrax-suite-portability-audit")


@app.function(
    image=image,
    cpu=(1, 1),
    memory=(2048, 2048),
    timeout=600,
    max_containers=1,
    retries=0,
    scaledown_window=2,
)
def verify_existing(rows, bundle, expected):
    from scripts import benchmark_suite as b

    if b.hashes() != expected:
        raise ValueError("Source mismatch")
    start = time.perf_counter()
    count = 0
    for row in rows:
        for name, data in row["policies"].items():
            b.validate_rollout("packing26", data, row["seed"], name, bundle)
            count += 1
    return dict(
        status="passed",
        rollouts=count,
        function_seconds=time.perf_counter() - start,
        original_validator=True,
        optimization_repeated=False,
    )


@app.local_entrypoint()
def main(output: str):
    p = Path(output)
    receipt = p / "linux-portability-audit.json"
    pending = p / "linux-portability-audit.pending"
    if receipt.exists() or pending.exists():
        raise RuntimeError("No automatic retry")
    m = json.loads((p / "manifest.json").read_text())
    if m != s.specification():
        raise ValueError("Changed frozen specification")
    rows = [
        json.loads((p / f"packing26-confirmation-{seed}.json").read_text())["response"][
            "result"
        ]
        for seed in m["splits"]["packing26"]["confirmation"]
    ]
    bundle = json.loads((p / "packing26-models.json").read_text())["response"]["result"]
    pending.write_text(
        "One additional audit call, max $0.010524, no optimization or retries\n"
    )
    result = verify_existing.remote(rows, bundle, m["sources"])
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    pending.unlink()
    print(json.dumps(result))
