"""Paired terminal action prediction at fresh polishing checkpoints."""
from pathlib import Path
import hashlib
import json
import numpy as np
from scripts import benchmark_suite as b

WINDOWS = (4, 6, 7)
FIXED = dict(packing26="moderate", packing32="moderate", autoconvolution64="restart")
ROOT = Path(__file__).parent


def collect(task, seed, window):
    action = FIXED[task]
    state, trace = b.initialize(task, seed), []
    for _ in range(window):
        state, event = b.step(task, state, action)
        trace.append(event)
    x = b.observations(task, state, trace)
    terminal = []
    for first in b.ACTIONS:
        child = state.clone()
        for t in range(window, 8):
            child, _ = b.step(task, child, first if t == window else action)
        exact = b.check(task, child.incumbent)
        assert abs(exact-child.score) < 1e-12 and child.evaluations == 640
        terminal.append(dict(action=first, construction=child.incumbent.tolist(), score=exact))
    return dict(task=task, seed=seed, window=window, x=x, terminal=terminal)


def utility(row):
    values = np.array([r["score"] for r in row["terminal"]])/b.scale(row["task"])
    return values-values.mean()


def fit(rows):
    x = np.array([r["x"] for r in rows])
    y = np.array([utility(r) for r in rows])
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    active = std > 1e-10*np.maximum(1, abs(mean))
    z = (x[:,active]-mean[active])/std[active]
    intercept = y.mean(axis=0)
    coef = np.linalg.solve(z.T@z + 10*np.eye(z.shape[1]), z.T@(y-intercept))
    return dict(active=active.tolist(), mean=mean[active].tolist(), scale=std[active].tolist(),
                coef=coef.tolist(), intercept=intercept.tolist())


def predictions(model,x):
    active=np.array(model["active"])
    z=(np.asarray(x)[active]-model["mean"])/model["scale"]
    coef=np.asarray(model["coef"]).reshape(len(z),3)
    return model["intercept"]+z@coef


def seeds(task, split):
    start=2027000000+10000*b.TASKS.index(task)+(1000 if split=="test" else 0)
    return range(start,start+(24 if split=="test" else 48))


def models(rows):
    return {t:{str(w):fit([r for r in rows if r["task"]==t and r["window"]==w]) for w in WINDOWS} for t in b.TASKS}


def analyze(rows, bundle):
    rng=np.random.default_rng(7351)
    result={}; boots=[]
    for task in b.TASKS:
        groups=[]; differences=[];changed=0
        for w in WINDOWS:
            model=bundle[task][str(w)]
            fixed=int(np.argmax(model["intercept"]))
            group=[]
            for row in rows:
                if (row["task"],row["window"])!=(task,w):continue
                chosen=int(np.argmax(predictions(model,row["x"])))
                u=utility(row)
                group.append(u[chosen]-u[fixed]);changed+=int(chosen!=fixed)
            assert len(group)==8
            differences.extend(group)
            groups.append(rng.choice(group,(20000,len(group))).mean(axis=1))
        boots.append(np.mean(groups,axis=0))
        result[task]=dict(mean=float(np.mean(differences)),changed=changed)
    mean=float(np.mean([v["mean"] for v in result.values()]))
    ci=np.quantile(np.mean(boots,axis=0),[.025,.975]).tolist()
    return dict(tasks=result,mean=mean,ci95=ci,passed=bool(mean>=.0002 and ci[0]>0))
