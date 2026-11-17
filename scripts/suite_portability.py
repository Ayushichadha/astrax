"""Audit the actual logged observation, then the frozen model on that observation.

No worker, feature generator, model, action or confirmation data is changed.
The original replay incorrectly assumed prediction stability under its permitted
1e-12 observation tolerance. Near-zero ridge scales violate that assumption.
"""

import numpy as np
from scripts import benchmark_suite as s


def validate_rollout(task, row, seed, name, bundle):
    if (
        row["task"] != task
        or row["seed"] != seed
        or row["policy"] != name
        or len(row["trace"]) != s.WINDOWS
        or len(row["decisions"]) != s.WINDOWS
    ):
        raise ValueError("Rollout identity")
    state, trace = s.initialize(task, seed), []
    for event, d in zip(row["trace"], row["decisions"]):
        expected = s.observations(task, state, trace)
        if not s.close(d["observation"], expected):
            raise ValueError("Noncausal observation")
        if name in s.LEARNED:
            q = [
                float(s.old.predict(m, d["observation"])[0])
                for m in bundle["models"][name][state.window]
            ]
            if (
                d["q_milliutility"] is None
                or not s.close(d["q_milliutility"], q)
                or event["action"] != s.ACTIONS[int(np.argmax(q))]
                or event["action"] != s.ACTIONS[int(np.argmax(d["q_milliutility"]))]
            ):
                raise ValueError("Frozen model/logged action mismatch")
        else:
            if (
                d["q_milliutility"] is not None
                or event["action"] != s.choose(task, name, state, trace, bundle)[0]
            ):
                raise ValueError("Static/reactive action mismatch")
        state = s.transition(task, state, event["action"], event, event["construction"])
        trace.append(event)
    if (
        row["score"] != state.score
        or row["evaluations"] != 640
        or row["switches"] != state.revisions
        or not s.close(row["utility"], state.score / s.scale(task))
        or not s.close(
            row["objective"],
            -state.score if task == "autoconvolution64" else state.score,
        )
    ):
        raise ValueError("Terminal mismatch")
