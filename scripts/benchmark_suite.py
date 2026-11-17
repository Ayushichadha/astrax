"""Frozen two-family, three-task metacontrol study. No cloud work on import."""

import argparse
from dataclasses import asdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.optimize import linprog
from scripts import sequential_controller as old
from scripts.matched_revision import (
    Protocol,
    State,
    Commitment,
    initialize as packing_init,
)

TASKS = ("packing26", "packing32", "autoconvolution64")
ACTIONS = old.ACTIONS
LEARNED = old.LEARNED
STATIC = ("always_local", "always_moderate", "always_restart", "fixed4")
WINDOWS = 8
CALLS = 80


def protocol(task):
    if task not in TASKS:
        raise ValueError("Unknown task")
    return Protocol(circles=32 if task == "packing32" else 26)


def scale(task):
    return (
        2.0 if task == "autoconvolution64" else np.sqrt(protocol(task).circles / np.pi)
    )


def autocheck(values, exact=False):
    if any(isinstance(x, (bool, np.bool_)) for x in values):
        raise ValueError("Boolean coefficient")
    a = np.asarray(values)
    if (
        a.ndim != 1
        or not len(a)
        or a.dtype.kind not in "fiu"
        or not np.isfinite(a).all()
        or (a < 0).any()
        or not (a > 0).any()
    ):
        raise ValueError("Expected finite nonnegative real coefficients, positive mass")
    if exact:
        ratios = [float(x).as_integer_ratio() for x in a]
        d = max(q for _, q in ratios)
        v = [p * (d // q) for p, q in ratios]
        c = [0] * (2 * len(v) - 1)
        for i, x in enumerate(v):
            for j, y in enumerate(v):
                c[i + j] += x * y
        return float(Fraction(2 * len(v) * max(c), sum(v) ** 2))
    # Scale before summation to avoid overflow and underflow exploits.
    a = a.astype(float) / a.max()
    a /= a.sum()
    return float(2 * len(a) * np.max(np.convolve(a, a)))


def packing_exact(values):
    a = np.asarray(values, dtype=float).reshape(-1, 3)
    if not np.isfinite(a).all():
        raise ValueError("Nonfinite packing")
    z = [[Fraction(float(v)) for v in row] for row in a]
    for x, y, r in z:
        if r < 0 or min(x, y, 1 - x, 1 - y) < r:
            raise ValueError("Exact boundary violation")
    for i, (x, y, r) in enumerate(z):
        for u, v, s in z[:i]:
            if (x - u) ** 2 + (y - v) ** 2 < (r + s) ** 2:
                raise ValueError("Exact overlap")
    return float(sum(row[2] for row in z))


def check(task, values):
    a = np.asarray(values, dtype=float)
    if task == "autoconvolution64":
        if a.shape != (64,):
            raise ValueError("Expected 64 coefficients")
        return -autocheck(a, exact=True)
    if a.shape != (protocol(task).circles * 3,):
        raise ValueError("Wrong packing shape")
    return packing_exact(a)


def initialize(task, seed):
    if task != "autoconvolution64":
        return packing_init(seed, protocol(task))
    rng = np.random.default_rng(np.random.SeedSequence([seed, 731]))
    a = rng.exponential(size=64)
    a /= a.sum()
    return State(seed, a, -autocheck(a, exact=True))


def observations(task, state, trace):
    if task != "autoconvolution64":
        x = old.observations(state, trace, protocol(task))
    else:
        gains = [e["score_after"] - e["score_before"] for e in trace]
        stagnant = 0
        for g in reversed(gains):
            if g > 1e-10:
                break
            stagnant += 1
        age = 0
        for e in reversed(trace):
            if e["action"] != state.commitment.recipe:
                break
            age += 1
        a = state.incumbent / state.incumbent.sum()
        positive = a[a > 0]
        conv = np.convolve(a, a)
        shape = [
            float(a.std() / a.mean()),
            float(a.min() / a.mean()),
            float(np.mean(a < 1e-8)),
            float(np.abs(np.diff(a)).sum()),
            float(-np.sum(positive * np.log(positive)) / np.log(len(a))),
            float(np.argmax(conv) / (len(conv) - 1)),
            float(np.mean(conv >= 0.99 * conv.max())),
        ]
        x = [
            (WINDOWS - state.window) / WINDOWS,
            state.score,
            gains[-1] if gains else 0.0,
            gains[-2] if len(gains) > 1 else 0.0,
            stagnant / WINDOWS,
            age / WINDOWS,
            *[float(bool(trace) and state.commitment.recipe == a) for a in ACTIONS],
            *shape,
        ]
    x = list(x)
    for i in (1, 2, 3):
        x[i] /= scale(task)
    if len(x) != 16 or not np.isfinite(x).all():
        raise ValueError("Invalid observations")
    return x


def step(task, state, action):
    if action not in ACTIONS or state.window >= WINDOWS:
        raise ValueError("Invalid action/window")
    if task != "autoconvolution64":
        nxt, event = old.step(state, action, protocol(task))
        check(task, nxt.incumbent)
        return nxt, event
    start = time.perf_counter()
    rng = np.random.default_rng(np.random.SeedSequence([state.seed, state.window, 913]))
    if action == "restart":
        work = rng.exponential(size=64)
    else:
        work = np.maximum(
            0.0,
            state.incumbent
            + rng.normal(size=64) * (0.15 if action == "local" else 0.6) / 64,
        )
    if not work.sum():
        work = np.ones(64)
    work /= work.sum()
    nxt = state.clone()
    failures = 0
    # Exactly 20 LP direction computations and 4 objective calls per direction.
    # The LP RHS is fixed; direction normalization removes its arbitrary scale.
    for _ in range(20):
        mat = np.zeros((127, 64))
        for j in range(64):
            mat[j : j + 64, j] = work
        result = linprog(
            -np.ones(64),
            A_ub=mat,
            b_ub=np.ones(127),
            bounds=(0, None),
            method="highs",
            options={"maxiter": 1000, "time_limit": 2.0},
        )
        if result.success and np.isfinite(result.x).all() and result.x.sum() > 0:
            direction = np.maximum(result.x, 0.0)
            direction /= direction.sum()
        else:
            failures += 1
            direction = work.copy()
        candidates = [(1 - t) * work + t * direction for t in (0.01, 0.05, 0.15, 0.35)]
        scores = [-autocheck(a) for a in candidates]
        k = int(np.argmax(scores))
        work = candidates[k]
        if scores[k] > nxt.score:
            verified = -autocheck(work, exact=True)
            if verified > nxt.score:
                nxt.incumbent = work.copy()
                nxt.score = verified
    changed = state.window == 0 or state.commitment.recipe != action
    nxt.commitment = Commitment(
        action, state.window if changed else state.commitment.emitted_at
    )
    nxt.revisions += int(state.window > 0 and changed)
    nxt.window += 1
    nxt.evaluations += CALLS
    event = dict(
        window=state.window,
        action=action,
        score_before=state.score,
        score_after=nxt.score,
        evaluations=nxt.evaluations,
        worker_seconds=time.perf_counter() - start,
        calls=[dict(function_evaluations=CALLS, lp_calls=20, lp_failures=failures)],
    )
    return nxt, event


def transition(task, state, action, event, construction):
    a = np.asarray(construction, dtype=float)
    score = check(task, a)
    if not np.isfinite([event["score_before"], event["score_after"]]).all():
        raise ValueError("Nonfinite event")
    if (
        event["window"] != state.window
        or event["action"] != action
        or abs(event["score_before"] - state.score) > 1e-12
        or abs(score - event["score_after"]) > 1e-12
        or event["score_after"] < state.score
        or event["evaluations"] != state.evaluations + CALLS
        or sum(c["function_evaluations"] for c in event["calls"]) != CALLS
        or any(c["function_evaluations"] <= 0 for c in event["calls"])
    ):
        raise ValueError("Invalid transition/accounting")
    if task == "autoconvolution64" and (
        len(event["calls"]) != 1 or event["calls"][0]["lp_calls"] != 20
    ):
        raise ValueError("LP accounting")
    nxt = state.clone()
    changed = state.window == 0 or state.commitment.recipe != action
    nxt.commitment = Commitment(
        action, state.window if changed else state.commitment.emitted_at
    )
    nxt.revisions += int(state.window > 0 and changed)
    nxt.window += 1
    nxt.evaluations += CALLS
    nxt.incumbent = a.copy()
    nxt.score = event["score_after"]
    return nxt


def collect(task, seed):
    state, trace, rows = initialize(task, seed), [], []
    rng = np.random.default_rng(np.random.SeedSequence([seed, 202640]))
    for t in range(WINDOWS):
        branches, states = [], []
        for action in ACTIONS:
            nxt, event = step(task, state, action)
            states.append(nxt)
            branches.append(
                dict(
                    action=action,
                    x=observations(task, state, trace),
                    reward=(nxt.score - state.score) / scale(task),
                    next_x=observations(task, nxt, trace + [event]),
                    event=event,
                    construction=nxt.incumbent.tolist(),
                )
            )
        k = int(rng.integers(3))
        rows.append(dict(window=t, behavior_action=ACTIONS[k], branches=branches))
        state = states[k]
        trace.append(branches[k]["event"])
    return dict(task=task, seed=seed, windows=rows, objective_evaluations=1920)


def close(a, b):
    return np.shape(a) == np.shape(b) and np.allclose(a, b, atol=1e-12, rtol=0)


def validate_training(task, data, seed):
    if (
        data["task"] != task
        or data["seed"] != seed
        or len(data["windows"]) != WINDOWS
        or data["objective_evaluations"] != 1920
    ):
        raise ValueError("Training identity")
    state, trace = initialize(task, seed), []
    rng = np.random.default_rng(np.random.SeedSequence([seed, 202640]))
    for t, row in enumerate(data["windows"]):
        chosen = ACTIONS[int(rng.integers(3))]
        if (
            row["window"] != t
            or row["behavior_action"] != chosen
            or [b["action"] for b in row["branches"]] != list(ACTIONS)
        ):
            raise ValueError("Training behavior")
        successors = {}
        for b in row["branches"]:
            nxt = transition(task, state, b["action"], b["event"], b["construction"])
            if (
                not close(b["x"], observations(task, state, trace))
                or not close(b["next_x"], observations(task, nxt, trace + [b["event"]]))
                or not close(b["reward"], (nxt.score - state.score) / scale(task))
            ):
                raise ValueError("Noncausal training row")
            successors[b["action"]] = (nxt, b["event"])
        state, event = successors[chosen]
        trace.append(event)


def fit(task, training):
    seeds = [d["seed"] for d in training]
    if len(set(seeds)) != len(seeds):
        raise ValueError("Duplicate seeds")
    for data in training:
        validate_training(task, data, data["seed"])
    models = {}
    for name in LEARNED:
        kind, horizon = name.split("_")
        heads = [None] * WINDOWS
        for t in reversed(range(WINDOWS)):
            heads[t] = []
            for a in range(3):
                rows = [d["windows"][t]["branches"][a] for d in training]
                y = np.array([1000 * r["reward"] for r in rows])
                if horizon == "sequential" and t + 1 < WINDOWS:
                    y += np.max(
                        [
                            old.predict(m, [r["next_x"] for r in rows])
                            for m in heads[t + 1]
                        ],
                        axis=0,
                    )
                heads[t].append(old.regress(np.array([r["x"] for r in rows]), y, kind))
        models[name] = heads
    return dict(task=task, training_seeds=seeds, models=models, config=old.CONFIG)


def choose(task, name, state, trace, bundle):
    x = observations(task, state, trace)
    q = None
    if name in LEARNED:
        q = [float(old.predict(m, x)[0]) for m in bundle["models"][name][state.window]]
        a = ACTIONS[int(np.argmax(q))]
    elif name.startswith("always_") and name[7:] in ACTIONS:
        a = name[7:]
    elif name == "fixed4":
        a = "local" if state.window < 4 else "moderate"
    elif name == "reactive":
        a = "moderate" if x[4] * WINDOWS >= 2 else "local"
    else:
        raise ValueError("Unknown policy")
    return a, dict(observation=x, q_milliutility=q)


def rollout(task, seed, name, bundle):
    if seed in bundle["training_seeds"] or bundle["task"] != task:
        raise ValueError("Evaluation overlap or model mismatch")
    start = time.perf_counter()
    state, trace, decisions = initialize(task, seed), [], []
    for _ in range(WINDOWS):
        t = time.perf_counter()
        action, decision = choose(task, name, state, trace, bundle)
        decision["controller_seconds"] = time.perf_counter() - t
        state, event = step(task, state, action)
        event["construction"] = state.incumbent.tolist()
        trace.append(event)
        decisions.append(decision)
    return dict(
        task=task,
        seed=seed,
        policy=name,
        score=state.score,
        objective=-state.score if task == "autoconvolution64" else state.score,
        utility=state.score / scale(task),
        evaluations=state.evaluations,
        switches=state.revisions,
        trace=trace,
        decisions=decisions,
        episode_seconds=time.perf_counter() - start,
    )


def validate_rollout(task, row, seed, name, bundle):
    if (
        row["task"] != task
        or row["seed"] != seed
        or row["policy"] != name
        or len(row["trace"]) != WINDOWS
        or len(row["decisions"]) != WINDOWS
    ):
        raise ValueError("Rollout identity")
    state, trace = initialize(task, seed), []
    for event, d in zip(row["trace"], row["decisions"]):
        action, expected = choose(task, name, state, trace, bundle)
        if (
            event["action"] != action
            or not close(d["observation"], expected["observation"])
            or ((d["q_milliutility"] is None) != (expected["q_milliutility"] is None))
            or (
                d["q_milliutility"] is not None
                and not close(d["q_milliutility"], expected["q_milliutility"])
            )
        ):
            raise ValueError("Policy/observation mismatch")
        state = transition(task, state, action, event, event["construction"])
        trace.append(event)
    if (
        row["score"] != state.score
        or row["evaluations"] != 640
        or row["switches"] != state.revisions
        or not close(row["utility"], state.score / scale(task))
        or not close(
            row["objective"],
            -state.score if task == "autoconvolution64" else state.score,
        )
    ):
        raise ValueError("Terminal mismatch")


def select(validation):
    means = {
        n: float(np.mean([r["policies"][n]["utility"] for r in validation]))
        for n in STATIC
    }
    return dict(
        static=max(STATIC, key=lambda n: means[n]),
        validation_means=means,
        validation_seeds=[r["seed"] for r in validation],
    )


def summarize(all_rows, frozen):
    rng = np.random.default_rng(6811)
    comparisons = {}
    for label, other in [
        ("H1_deployability", "selected"),
        ("H2_capacity", "ridge_sequential"),
        ("H3_credit", "tree_myopic"),
    ]:
        task_results = {}
        boot = []
        means = []
        for task in TASKS:
            name = frozen[task]["static"] if other == "selected" else other
            rows = all_rows[task]
            diff = np.array(
                [
                    r["policies"]["tree_sequential"]["utility"]
                    - r["policies"][name]["utility"]
                    for r in rows
                ]
            )
            sampled = diff[rng.integers(len(diff), size=(20000, len(diff)))].mean(
                axis=1
            )
            ci = np.quantile(sampled, [0.025, 0.975]).tolist()
            task_results[task] = dict(
                mean=float(diff.mean()),
                ci95_descriptive=ci,
                wins=int(sum(diff > 1e-12)),
                losses=int(sum(diff < -1e-12)),
                ties=int(sum(abs(diff) <= 1e-12)),
            )
            boot.append(sampled)
            means.append(float(diff.mean()))
        ci = np.quantile(np.mean(boot, axis=0), [0.05 / 6, 1 - 0.05 / 6]).tolist()
        mean = float(np.mean(means))
        comparisons[label] = dict(
            equal_task_mean=mean,
            ci98_333=ci,
            passed=bool(mean >= 0.0002 and ci[0] > 0),
            tasks=task_results,
        )
    return dict(
        comparisons=comparisons,
        tasks={
            t: dict(
                selected_static=frozen[t]["static"],
                mean_objective={
                    n: float(
                        np.mean([r["policies"][n]["objective"] for r in all_rows[t]])
                    )
                    for n in all_rows[t][0]["policies"]
                },
                mean_seconds={
                    n: float(
                        np.mean(
                            [r["policies"][n]["episode_seconds"] for r in all_rows[t]]
                        )
                    )
                    for n in all_rows[t][0]["policies"]
                },
            )
            for t in TASKS
        },
    )


def hashes():
    root = Path(__file__).parent
    return dict(
        old.hashes(),
        **{
            n: hashlib.sha256((root / n).read_bytes()).hexdigest()
            for n in (
                "benchmark_suite.py",
                "modal_benchmark_suite.py",
                "audit_benchmark_suite.py",
            )
        }
    )


def specification():
    return dict(
        schema=1,
        tasks=list(TASKS),
        sources=hashes(),
        splits={
            t: {
                split: list(
                    range(
                        2026400000 + i * 30000 + j * 10000,
                        2026400000 + i * 30000 + j * 10000 + n,
                    )
                )
                for j, (split, n) in enumerate(
                    [("training", 96), ("validation", 16), ("confirmation", 48)]
                )
            }
            for i, t in enumerate(TASKS)
        },
        windows=WINDOWS,
        objective_calls_per_window=CALLS,
        actions=list(ACTIONS),
        learned=list(LEARNED),
        static=list(STATIC),
        config=old.CONFIG,
        utility="packing score/sqrt(n/pi); autoconvolution -C/2; task-specific models",
        auto_worker=dict(
            bins=64,
            lp_steps=20,
            mix=[0.01, 0.05, 0.15, 0.35],
            perturbation=[0.15 / 64, 0.6 / 64],
            lp_rhs=1,
            lp_maxiter=1000,
            lp_time_limit=2,
        ),
        features="9 generic normalized features; packing geometry7 or coefficient CV,min/mean,zero fraction,total variation,entropy,peak position,peak plateau fraction",
        hypotheses=[
            "H1 tree-sequential > validation-selected static",
            "H2 tree-sequential > ridge-sequential",
            "H3 tree-sequential > tree-myopic",
        ],
        success="equal-task mean normalized gain >=.0002 and positive 98.333% paired bootstrap lower endpoint; 20000 resamples within each task; 3 Bonferroni-adjusted primary contrasts",
        limitations="two families, three tasks; fixed 64-bin restriction not record reproduction; separate training not zero-shot transfer; equal objective counts not equal total compute; taskwise intervals descriptive",
        pilot_gate="Only consider development-only code-editing pilot if all 3 primary gates fail and training reveals weak fixed-action opportunity: mean max immediate branch gain minus best constant-action mean <.0002 normalized per window on at least one task. Otherwise prioritize interpreting confirmed controller evidence or model/support diagnostics. No confirmation reuse.",
        cost=dict(
            max_calls=490,
            timeout=600,
            cores=1,
            memory_GiB=2,
            rate_per_second=0.00001754,
            max_function_USD=5.15676,
            prior_usage_allowance_USD=2,
            overhead_reserve_USD=1,
            total_limit_USD=10,
            retries=0,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", type=Path, required=True)
    a = p.parse_args()
    a.prepare.mkdir(parents=True, exist_ok=False)
    (a.prepare / "manifest.json").write_text(
        json.dumps(specification(), indent=2) + "\n"
    )
