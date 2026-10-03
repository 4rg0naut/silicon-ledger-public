# /// script
# requires-python = ">=3.11"
# dependencies = ["mteb>=2.0"]
# ///
"""Which French retrieval tasks does MTEB/MMTEB offer, and how big are they?"""
import mteb
print("=== French (fra) retrieval tasks ===")
tasks = mteb.get_tasks(task_types=["Retrieval"], languages=["fra"])
for t in tasks:
    md = t.metadata
    print(f"  {md.name:<40} main={getattr(md,'main_score',None)} splits={md.eval_splits}")
print(f"  total: {len(tasks)}")
print("\n=== French STS (semantic similarity) ===")
for t in mteb.get_tasks(task_types=["STS"], languages=["fra"])[:8]:
    print(f"  {t.metadata.name:<40} main={getattr(t.metadata,'main_score',None)}")
print("\n=== how many languages does MMTEB cover overall? ===")
allr = mteb.get_tasks(task_types=["Retrieval"])
langs = set()
for t in allr:
    langs.update(t.metadata.languages or [])
print(f"  {len(allr)} retrieval tasks across {len(langs)} languages")
