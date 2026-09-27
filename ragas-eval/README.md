# Optional RAGAS environment

This environment keeps RAGAS separate from the backend's LangChain packages.
RAGAS 0.3.9 imports with `langchain-community<0.4`; RAGAS 0.4.3 failed to
import with the backend's resolved LangChain Community version.

From this directory, install the locked dependencies and check the import:

```bash
uv sync
uv run python -c 'import ragas; print(ragas.__version__)'
```

This only prepares the evaluator. The ground-truth results in `../eval/summary.md`
do not include RAGAS scores. Running LLM-based RAGAS metrics requires a
configured judge model and may incur inference charges.
