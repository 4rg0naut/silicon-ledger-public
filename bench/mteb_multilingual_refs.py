# /// script
# requires-python = ">=3.11"
# dependencies = ["mteb>=2.0"]
# ///
"""Multilingual-retrieval reference scores, and which tasks have the widest model coverage."""
import mteb
MODELS = [
    "intfloat/multilingual-e5-small",
    "intfloat/multilingual-e5-base",
    "intfloat/multilingual-e5-large",
    "jhu-clsp/mmBERT-base",
    "jhu-clsp/mmBERT-small",
    "BAAI/bge-m3",
]
res = mteb.load_results(models=MODELS)
df = res.to_dataframe()
print("columns:", list(df.columns)[:10])
print("index name:", df.index.name, "| n rows:", len(df))
key = "task_name" if "task_name" in df.columns else df.index.name
multi = df[df[key].astype(str).str.contains("Multilingual", case=False, na=False)]
model_cols = [c for c in df.columns if "/" in str(c)]
print(f"\nmultilingual rows: {len(multi)}  model columns: {model_cols}")
cov = multi[model_cols].notna().sum(axis=1).sort_values(ascending=False)
print("\n=== widest model coverage ===")
for i in cov.head(10).index:
    name = multi.loc[i, key] if key in multi.columns else i
    print(f"  {str(name):<44} models={cov[i]}")
if len(cov):
    top = cov.index[0]
    print(f"\n=== scores for {multi.loc[top, key] if key in multi.columns else top} ===")
    row = multi.loc[top, model_cols].dropna()
    for m, v in row.items():
        print(f"  {m:<52} {v}")
