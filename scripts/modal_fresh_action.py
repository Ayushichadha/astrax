import hashlib
import json
from pathlib import Path
import time
import modal
from scripts import fresh_action as f
from scripts.modal_benchmark_suite import image
app=modal.App("astrax-fresh-actions")
image=image.add_local_file(Path(f.__file__),"/root/scripts/fresh_action.py")


@app.function(image=image,cpu=(1,1),memory=(2048,2048),timeout=300,retries=0,max_containers=16,scaledown_window=2)
def run(task,seed,window,digest):
    from scripts import fresh_action as worker
    assert hashlib.sha256(Path(worker.__file__).read_bytes()).hexdigest()==digest
    start=time.monotonic()
    row=worker.collect(task,seed,window)
    row["seconds"]=time.monotonic()-start
    return row


@app.local_entrypoint()
def main():
    out=Path("outputs/fresh-action-v1")
    out.mkdir(parents=True,exist_ok=False)
    digest=hashlib.sha256(Path(f.__file__).read_bytes()).hexdigest()
    bundle=None
    for split in ("train","test"):
        jobs=[(t,seed,f.WINDOWS[i%3],digest) for t in f.b.TASKS for i,seed in enumerate(f.seeds(t,split))]
        rows=[]
        for args,row in zip(jobs,run.starmap(jobs,order_outputs=True)):
            assert (row["task"],row["seed"],row["window"])==args[:3]
            rows.append(row)
            (out/f'{split}-{row["seed"]}.json').write_text(json.dumps(row,allow_nan=False))
        assert len(rows)==len(jobs)
        if split=="train":
            bundle=f.models(rows)
            (out/"models.json").write_text(json.dumps(bundle,allow_nan=False))
            print("Models frozen",flush=True)
        else:
            result=f.analyze(rows,bundle)
            (out/"summary.json").write_text(json.dumps(result,indent=2))
            print(result)
