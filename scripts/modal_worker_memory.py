import json
import hashlib
from pathlib import Path
import time
import modal
from scripts import worker_memory as wm
from scripts.modal_benchmark_suite import image
app=modal.App('astrax-problem2-memory')
image=image.add_local_file(Path(wm.__file__),'/root/scripts/worker_memory.py')

@app.function(image=image,cpu=(1,1),memory=(2048,2048),timeout=180,max_containers=12,retries=0,scaledown_window=2)
def run(seed,w,digest):
    from scripts import worker_memory as worker
    assert hashlib.sha256(Path(worker.__file__).read_bytes()).hexdigest()==digest
    start=time.monotonic()
    row=worker.collect(seed,w)
    row['seconds']=time.monotonic()-start
    return row

@app.local_entrypoint()
def main():
    out=Path('outputs/worker-memory-v1');out.mkdir(parents=True,exist_ok=False)
    digest=hashlib.sha256(Path(wm.__file__).read_bytes()).hexdigest()
    for split,start,n in [('development',2027400000,48),('confirmation',2027410000,96)]:
        jobs=[(start+i,wm.WINDOWS[i%3],digest) for i in range(n)]
        rows=list(run.starmap(jobs,order_outputs=True))
        assert [(r['seed'],r['window']) for r in rows]==[j[:2] for j in jobs]
        (out/(split+'.json')).write_text(json.dumps(rows,allow_nan=False))
        if split=='development':
            rule=wm.time_rule(rows)
            (out/'time-rule.json').write_text(json.dumps(rule))
        else:
            result=wm.analyze(rows,rule)
            (out/'summary.json').write_text(json.dumps(result,indent=2))
            print(result)
