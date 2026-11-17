"""Verify archived action labels, partitions, predictions and paired statistics."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from scripts import fresh_action as f


def audit(path):
    rows = {}
    seconds = 0
    for split in ("train", "test"):
        rows[split] = []
        for task in f.b.TASKS:
            for index, seed in enumerate(f.seeds(task, split)):
                row = json.loads((path / f"{split}-{seed}.json").read_text())
                assert (row["task"], row["window"], row["seed"]) == (task, f.WINDOWS[index % 3], seed)
                assert len(row["x"]) == 16 and np.isfinite(row["x"]).all()
                assert row["x"][0] == (8-row["window"])/8
                assert [branch["action"] for branch in row["terminal"]] == list(f.b.ACTIONS)
                for branch in row["terminal"]:
                    assert branch["score"] == f.b.check(task, branch["construction"])
                rows[split].append(row)
                seconds += row["seconds"]
    saved = json.loads((path / "models.json").read_text())
    refit = f.models(rows["train"])
    for row in rows["test"]:
        task, window = row["task"], str(row["window"])
        assert saved[task][window]["active"] == refit[task][window]["active"]
        np.testing.assert_allclose(f.predictions(saved[task][window],row["x"]),
                                   f.predictions(refit[task][window],row["x"]),atol=1e-12,rtol=0)
    result = f.analyze(rows["test"], saved)
    assert result == json.loads((path/"summary.json").read_text())
    return dict(training_states=len(rows["train"]),test_states=len(rows["test"]),
                exact_terminal_checks=3*sum(map(len,rows.values())),function_body_seconds=seconds,
                estimated_execution_USD=seconds*.00001754,
                models_sha256=hashlib.sha256((path/"models.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("path",type=Path)
    print(json.dumps(audit(parser.parse_args().path),indent=2))
