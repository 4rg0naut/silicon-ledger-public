# /// script
# requires-python = ">=3.11"
# dependencies = ["mteb>=2.0"]
# ///
import mteb
MODELS = ["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-small-en-v1.5",
          "BAAI/bge-base-en-v1.5", "sentence-transformers/all-mpnet-base-v2"]
TASKS = ["SciFact", "NFCorpus", "ArguAna"]
res = mteb.load_results(models=MODELS, tasks=TASKS)
df = res.to_dataframe()
pd_cols = ["task_name"] + [m for m in MODELS if m in df.columns]
print(df[pd_cols].to_string(index=False))
