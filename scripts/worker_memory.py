"""Single checkpoint intervention on the 64-bin first autoconvolution worker."""
import numpy as np
from scipy.optimize import linprog
from scripts.benchmark_suite import autocheck

WINDOWS = (2, 4, 6)

def advance(work, best):
    best_score = -autocheck(best, exact=True)
    failures = 0
    history = []
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
        history.append(-scores[k])
        if scores[k] > best_score:
            verified = -autocheck(work, exact=True)
            if verified > best_score:
                best = work.copy()
                best_score = verified
    return work, best, history, failures


def collect(seed, window):
    rng = np.random.default_rng(seed)
    best = rng.dirichlet(np.ones(64))
    for _ in range(window):
        work = rng.dirichlet(np.ones(64))
        work, best, history, _ = advance(work, best)
    checkpoint = autocheck(best, exact=True)
    gap = max(0., autocheck(work, exact=True)-checkpoint)
    speed = (history[-6]-history[-1])/5
    progress = int(speed>0 and gap<=speed*20*(8-window))
    terminals = []
    for initial in (best, work):
        candidate, incumbent = initial.copy(), best.copy()
        for _ in range(8-window):
            candidate, incumbent, _, _ = advance(candidate, incumbent)
        terminals.append(incumbent.tolist())
    return dict(seed=seed,window=window,best=best.tolist(),work=work.tolist(),history=history,
                progress=progress,terminal=terminals)


def score(row):
    return [-autocheck(x,exact=True)/2 for x in row['terminal']]


def time_rule(rows):
    return {str(w):int(np.mean([np.diff(score(r))[0] for r in rows if r['window']==w])>0) for w in WINDOWS}


def analyze(rows,rule):
    rng=np.random.default_rng(18451)
    result={}
    for a,b in [('resume','reset'),('progress','resume'),('progress','reset'),('progress','time')]:
        diffs=[]; samples=[]
        for w in WINDOWS:
            group=[]
            for r in rows:
                if r['window']!=w: continue
                u=score(r); actions=dict(reset=0,resume=1,time=rule[str(w)],progress=r['progress'])
                group.append(u[actions[a]]-u[actions[b]])
            diffs.extend(group)
            samples.append(rng.choice(group,(20000,len(group))).mean(axis=1))
        mean=float(np.mean(diffs));ci=np.quantile(np.mean(samples,axis=0),[.00625,.99375]).tolist()
        result[a+' minus '+b]=dict(mean=mean,ci=ci,passed=bool(mean>=.0002 and ci[0]>0))
    return result
