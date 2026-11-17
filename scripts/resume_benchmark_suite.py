"""Resume saved suite using observation-first local audit; remote treatment unchanged."""

import hashlib
import json
from pathlib import Path
from scripts import benchmark_suite as s
from scripts.modal_benchmark_suite import app, task, execute
from scripts.suite_portability import validate_rollout


@app.local_entrypoint()
def resume(output: str):
    p = Path(output)
    amendment = json.loads((p / "portability-amendment.json").read_text())
    for name, digest in amendment["audit_sources"].items():
        if (
            hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
            != digest
        ):
            raise ValueError("Changed observation-first audit source")
    receipt = json.loads((p / "linux-portability-audit.json").read_text())
    if (
        receipt["status"] != "passed"
        or receipt["rollouts"] != 288
        or not receipt["original_validator"]
        or receipt["optimization_repeated"]
    ):
        raise ValueError("Original Linux audit must pass before continuation")
    original = s.validate_rollout
    s.validate_rollout = validate_rollout
    try:
        result = execute(p, lambda jobs: task.starmap(jobs, order_outputs=True))
        print(json.dumps(result, indent=2))
    finally:
        s.validate_rollout = original
