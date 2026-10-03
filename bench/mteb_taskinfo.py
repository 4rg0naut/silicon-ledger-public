# /// script
# requires-python = ">=3.11"
# dependencies = ["mteb>=2.0"]
# ///
import mteb
for name in ("MultilingualNanoSciFactRetrieval", "WikipediaRetrievalMultilingual"):
    t = mteb.get_task(name)
    md = t.metadata
    print(f"{name}")
    print(f"    main={md.main_score} splits={md.eval_splits}")
    print(f"    languages={md.languages}")
    print(f"    n_samples={getattr(md,'n_samples',None)}")
