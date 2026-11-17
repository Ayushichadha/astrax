import copy
import numpy as np
import pytest
from scripts import benchmark_suite as s


@pytest.mark.parametrize(
    "values", [[0, 0], [-1, 2], [float("nan"), 1], [float("inf"), 1], [True, False], []]
)
def test_invalid_coefficients(values):
    with pytest.raises(ValueError):
        s.autocheck(values)


def test_exact_convolution_and_scale():
    for a in ([1, 1], [1, 2, 3], [1e-200, 2e-200], [1e200, 2e200]):
        assert s.autocheck(a) == pytest.approx(s.autocheck(a, exact=True), abs=1e-14)
    assert s.autocheck([1] * 64, exact=True) == 2
    assert s.autocheck([1, 2, 3]) == pytest.approx(s.autocheck([3, 2, 1]))


def test_exact_packing_rejects_rounding_overlap():
    s.packing_exact([0.25, 0.5, 0.25, 0.75, 0.5, 0.25])
    with pytest.raises(ValueError):
        s.packing_exact([0.25, 0.5, 0.25, np.nextafter(0.75, 0), 0.5, 0.25])


def test_manifest_disjoint_and_budget():
    m = s.specification()
    sets = [set(v) for d in m["splits"].values() for v in d.values()]
    assert sum(map(len, sets)) == len(set.union(*sets))
    assert m["cost"]["max_calls"] * 600 * m["cost"]["rate_per_second"] + 3 < 10


def test_auto_step_accounting_and_tampering():
    task = "autoconvolution64"
    state = s.initialize(task, 991)
    nxt, event = s.step(task, state, "moderate")
    assert nxt.evaluations == 80 and nxt.score >= state.score
    assert state.window == 0 and state.evaluations == 0
    audited = s.transition(task, state, "moderate", event, nxt.incumbent.tolist())
    assert audited.score == nxt.score
    bad = copy.deepcopy(event)
    bad["calls"][0]["function_evaluations"] = 79
    with pytest.raises(ValueError):
        s.transition(task, state, "moderate", bad, nxt.incumbent.tolist())


def test_policy_freeze_and_direction():
    rows = [
        dict(seed=1, policies={n: dict(utility=-i) for i, n in enumerate(s.STATIC)})
    ]
    assert s.select(rows)["static"] == "always_local"
    state = s.initialize("autoconvolution64", 1)
    assert state.score < 0 and len(s.observations("autoconvolution64", state, [])) == 16


def test_complete_auto_training_model_and_policy_audit():
    task = "autoconvolution64"
    data = s.collect(task, 881)
    s.validate_training(task, data, 881)
    bundle = s.fit(task, [data])
    row = s.rollout(task, 882, "tree_sequential", bundle)
    s.validate_rollout(task, row, 882, "tree_sequential", bundle)
    bad = copy.deepcopy(row)
    bad["decisions"][0]["q_milliutility"][0] += 1
    with pytest.raises(ValueError):
        s.validate_rollout(task, bad, 882, "tree_sequential", bundle)
    bad = copy.deepcopy(data)
    bad["windows"][1]["branches"][0]["x"][2] += 1
    with pytest.raises(ValueError):
        s.validate_training(task, bad, 881)


def test_archived_reference_constructions_with_exact_checks():
    import json
    from pathlib import Path

    reference = json.loads(
        (
            Path(__file__).parents[1]
            / "papers/metacontrol/artifacts/benchmark-reference-audit.json"
        ).read_text()
    )
    a = reference["autocorrelation_problems.ipynb"]["construction"]["best_sequence"]
    assert s.autocheck(a, exact=True) == pytest.approx(1.5052939684401607, abs=1e-14)
    p = reference["packing_circles_max_sum_of_radii.ipynb"]["construction"]
    z = np.column_stack([p["centers_32"], p["radii_32"]])
    with pytest.raises(ValueError):
        s.packing_exact(z.ravel())
    z[:, 2] *= 1 - 1e-9
    assert s.packing_exact(z.ravel()) == pytest.approx(2.9395727682667503, abs=1e-14)


def test_failed_dispatch_cannot_silently_retry(tmp_path):
    import json
    from scripts.modal_benchmark_suite import execute

    (tmp_path / "manifest.json").write_text(json.dumps(s.specification()))
    calls = []

    def failed_backend(jobs):
        calls.extend(jobs)
        raise RuntimeError("Injected transport failure")

    with pytest.raises(RuntimeError, match="Injected"):
        execute(tmp_path, failed_backend)
    assert len(calls) == 4
    assert len(list(tmp_path.glob("*.pending"))) == 4
    assert not (tmp_path / "dispatch.lock").exists()
    with pytest.raises(RuntimeError, match="unresolved"):
        execute(tmp_path, failed_backend)
    assert len(calls) == 4


def test_auto_fast_evaluations_are_separate_from_exact_verification(monkeypatch):
    state = s.initialize("autoconvolution64", 991)
    original = s.autocheck
    calls = []

    def counted(values, exact=False):
        calls.append(exact)
        return original(values, exact)

    monkeypatch.setattr(s, "autocheck", counted)
    s.step("autoconvolution64", state, "moderate")
    assert calls.count(False) == 80
    assert 0 < calls.count(True) <= 20


def test_observation_first_audit_preserves_frozen_predictions():
    from scripts.suite_portability import validate_rollout

    task = "autoconvolution64"
    seed = 515
    name = "ridge_myopic"
    state = s.initialize(task, seed)
    initial = s.observations(task, state, [])
    heads = []
    for i in range(3):
        coef = [0.0] * 16
        coef[9] = 1.0 if i == 0 else 0.0
        scale = [1.0] * 16
        scale[9] = 1e-17
        heads.append(
            dict(kind="ridge", mean=initial, scale=scale, coef=coef, intercept=float(i))
        )
    bundle = dict(models={name: [heads] * 8})
    trace = []
    decisions = []
    for window in range(8):
        x = s.observations(task, state, trace)
        x[9] = float(np.nextafter(x[9], np.inf))
        q = [float(s.old.predict(m, x)[0]) for m in heads]
        action = s.ACTIONS[int(np.argmax(q))]
        assert action == "local"
        event = dict(
            window=window,
            action=action,
            score_before=state.score,
            score_after=state.score,
            evaluations=state.evaluations + 80,
            calls=[dict(function_evaluations=80, lp_calls=20, lp_failures=0)],
            construction=state.incumbent.tolist(),
        )
        state = s.transition(task, state, action, event, event["construction"])
        trace.append(event)
        decisions.append(dict(observation=x, q_milliutility=q))
    row = dict(
        task=task,
        seed=seed,
        policy=name,
        trace=trace,
        decisions=decisions,
        score=state.score,
        utility=state.score / 2,
        objective=-state.score,
        evaluations=640,
        switches=state.revisions,
    )
    with pytest.raises(ValueError, match="Policy/observation"):
        s.validate_rollout(task, row, seed, name, bundle)
    validate_rollout(task, row, seed, name, bundle)
    bad = copy.deepcopy(row)
    bad["decisions"][0]["q_milliutility"][0] += 1
    with pytest.raises(ValueError, match="Frozen model"):
        validate_rollout(task, bad, seed, name, bundle)
    bad = copy.deepcopy(row)
    bad["decisions"][0]["observation"][9] += 1e-8
    with pytest.raises(ValueError, match="Noncausal"):
        validate_rollout(task, bad, seed, name, bundle)
