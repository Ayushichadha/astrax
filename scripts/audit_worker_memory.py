"""Verify stored checkpoint decisions and exact terminal outcomes offline."""
import json
from pathlib import Path
import sys
from scripts import worker_memory as wm


def audit(path):
    def read(name):
        return json.loads((path / (name + ".json")).read_text())
    development = read("development")
    confirmation = read("confirmation")
    for rows, start, count in [(development, 2027400000, 48), (confirmation, 2027410000, 96)]:
        assert len(rows) == count
        for i, row in enumerate(rows):
            w = wm.WINDOWS[i % 3]
            assert (row["seed"], row["window"]) == (start + i, w)
            best = wm.autocheck(row["best"], exact=True)
            work = wm.autocheck(row["work"], exact=True)
            assert len(row["history"]) == 20 and abs(row["history"][-1] - work) < 1e-12
            speed = (row["history"][-6] - row["history"][-1]) / 5
            assert row["progress"] == int(speed > 0 and max(0, work-best) <= speed*20*(8-w))
            assert len(row["terminal"]) == 2 and all(score >= -best/2 for score in wm.score(row))
    rule = wm.time_rule(development)
    assert rule == read("time-rule") and wm.analyze(confirmation, rule) == read("summary")
    print("144 checkpoints and 288 terminal constructions verified")


if __name__ == "__main__":
    audit(Path(sys.argv[1]))
