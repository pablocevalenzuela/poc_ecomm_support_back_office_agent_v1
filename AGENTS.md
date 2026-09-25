# AGENTS.md

Shopify back-office conversational agent (PoC). ReAct loop over LangGraph + FastAPI + Gradio, talking to the Shopify Admin GraphQL API, pgvector RAG on Supabase, and Gmail for HITL approvals. Deployed to GCP Cloud Run.

Docs here are Spanish; this file is English. **Code comments, docstrings, and log messages are Spanish, and all agent/user-facing output is Spanish — keep it that way.**

## Setup & run

```bash
source venv/bin/activate          # repo ships ./venv (Python 3.14)
pip install -r requirements.txt
make dev                          # http://localhost:8000  (UI at /ui)
```

- `make dev` is the only working run target. It sets `PYTHONPATH=.` and serves `api.main:app` via uvicorn with `--reload`.
- `PYTHONPATH` is mandatory — the app cross-imports top-level packages (`api/main.py` imports `ui.gradio_app` and `shopify_agent.*`). The Dockerfile bakes `PYTHONPATH=/app` for this reason.
- Python versions disagree across the repo: Dockerfile `python:3.11-slim`, CI `3.13`, local venv `3.14`. `requirements.txt:12` is marker-gated (`audioop-lts==0.2.2; python_version >= '3.13.7'`), so it silently skips on 3.11. Don't "fix" one of these without checking the other two.
- **`README.md` is wrong** — it says `npm install`, JavaScript, React. Trust `Makefile`, `Dockerfile`, and `.github/workflows/deploy.yml`. `notes.md` is a raw bootstrap scratchpad.
- Required env: `DATABASE_URL`, `HUGGINGFACE_API_TOKEN` (or an OpenAI/GitHub token), `SHOPIFY_STORE_NAME`, `SHOPIFY_ADMIN_ACCESS_TOKEN`. Live values live in the gitignored `.env.develop`, which `shopify_agent/settings.py:6` hardcodes via `load_dotenv(".env.develop")`.

## Testing

```bash
pytest tests/unit tests/integration/test_graph.py    # 10 tests, ~0.5s, fully hermetic
```

Use that subset for verification. **`pytest tests/` is not hermetic**: it also collects `tests/integration/test_hitl_cancellation.py`, which calls `init_graph()` against real Postgres, then drives a real LLM, real Shopify, and real SMTP. Without live services it burns 30s and fails with `psycopg_pool.PoolTimeout` (`1 failed, 10 passed`). CI runs it too (`deploy.yml:49`) with only mock env vars and no DB service — so a red `test` job on that file is pre-existing, not something you broke.

- `pytest.ini` sets `asyncio_mode = auto`, so `@pytest.mark.asyncio` is optional.
- `tests/integration/test_graph.py` parametrizes off `tests/data/golden_dataset.json` **at collection time** — editing that file changes test IDs. It patches `shopify_agent.graph.llm` and `httpx.AsyncClient.post`, and asserts the ReAct contract: exactly 2 LLM calls, and a `ToolMessage` present in the second call's history.
- Three datasets, different purposes: `golden_dataset.json` (test_graph.py), `golden_dataset_token_economy_test.json` (benchmark_agent.py), `golden_dataset_backup.json` (unused).
- **There is no lint, format, or typecheck config** — no ruff/black/mypy/pyproject/pre-commit, no lint CI job. Don't invent `make lint` or claim one exists.

## Architecture

One deployable. `api/main.py` is the single entrypoint: FastAPI with Gradio mounted at `/ui` via `gr.mount_gradio_app`, `POST /chat` taking `{message, session_id}`, and `GET /` returning `APP_VERSION`. Those three are the app's own routes (`/docs` and friends are FastAPI defaults). `thread_id` for the checkpointer is the client-supplied `session_id`.

`shopify_agent/graph.py` is the core: a two-node `agent` ⇄ `tools` ReAct loop over `AgentState` (messages only; the other TypedDict keys are unused).

- **Import-time side effect**: `graph.py:34` calls `get_llm(...)` at module scope, so merely importing `shopify_agent.graph` instantiates an LLM client from settings. Any script or test importing it needs a provider token set.
- **`graph` is a module-level `None` until `await init_graph()`**, which opens the `AsyncConnectionPool`, runs `checkpointer.setup()`, and compiles. The FastAPI lifespan calls it; `benchmark_agent.py`, `ui/gradio_app.py`, and the HITL test call it themselves. `/chat` returns 503 while it is `None`, and a DB failure at startup is only logged as a warning.
- `graph.py:39` trims history to `max_tokens=15` (`start_on="human"`, `token_counter=len`). Multi-turn flows needing more than 15 messages lose context.
- **DB URL handling is inconsistent.** `graph.py:97` and `db.py:6` read `os.getenv("DATABASE_URL")` with *different* fallback strings; `tools.py:263` and both ingest scripts use `settings.database_url`. The latter string-replace `postgresql+asyncpg://` → `postgresql://` because psycopg needs the sync scheme. Change one and you change behaviour everywhere.
- Add LLM providers in `shopify_agent/llm_factory.py:get_llm(purpose=...)`, never inline in `graph.py`. Selected by `LLM_PROVIDER`: `huggingface` (default → Qwen2.5-72B-Instruct), `openai` (gpt-4o-mini agent / gpt-4o judge), `github` (same models via `models.inference.ai.azure.com`).

**Dead code — don't build on it:**
- `shopify_agent/hitl.py` is a stub that always returns `False` and is **not wired into the graph**. HITL approval is enforced only by the system prompt and tool choice, not by code.
- `webhook/main.py` is a stub app, mounted nowhere.
- `shopify_agent/models.py` / `db.py` (`AgentLog`) are defined but never used by the app.

## The transparency-marker contract

Every tool docstring in `tools.py` tells the model to prefix its reply with one of three exact strings, `prompts.py:35-38` repeats them, and the LLM-as-a-Judge prompt caps any answer missing them at score 3 (`benchmark_agent.py:54`):

- `He verificado en el Sistema Shopify:` — orders, stock, inventory
- `He consultado el Catálogo De Proveedores:` — RAG, SAP codes, wholesale pricing
- `Consultando el Sistema de Correos:` — emails and approvals

Changing any of these strings requires updating the tool docstring, `prompts.py`, and the judge rubric together. Missing one silently tanks the eval score rather than raising an error.

## RAG & data

- pgvector table `product_catalog_embeddings (content, embedding, metadata)` in Supabase; embeddings via `HuggingFaceEndpointEmbeddings` / `sentence-transformers/all-MiniLM-L6-v2`.
- Retrieval (`tools.py:270`) is `ORDER BY embedding <=> %s LIMIT 6`, with an unfiltered `LIMIT 3` fallback when nothing matches — results degrade to arbitrary rows rather than admitting no match.
- Ingest from repo root; source files are in `products_catalog/`:
  - `python ingest_catalog.py catalogo_2026_lech_rio_claro.pdf`
  - `python ingest_catalog_excel.py lista_precios_rio_claro_12062026.xlsx --sheet <name>` (`--sheet` optional, defaults to first)
- `openpyxl` is **not** in `requirements.txt`, so `.xlsx` ingest fails until you `pip install openpyxl`.

## Evals

`python benchmark_agent.py` — LLM-as-a-Judge over the golden dataset, printing task success rate, real token cost, and per-tool frequency. Requires live Postgres + a live LLM. The active dataset path is `golden_dataset_token_economy_test.json`; the general `golden_dataset.json` line is commented out at `benchmark_agent.py:82-86` — switch there to run the full 7-case set.

`python script_visualizer_graph.py` regenerates `mi_grafo_langgraph.png` from `workflow.compile()` (no DB needed).

## Deploy

`.github/workflows/deploy.yml`, single workflow, two jobs:

- `develop` → runs tests and creates a git tag (`-dev` prerelease). **No deploy.**
- `main` → auth to GCP via Workload Identity Federation, `gcloud builds submit`, then `gcloud run deploy` (`--allow-unauthenticated`).
- `fetch-depth: 0` is required by `anothrNick/github-tag-action` — don't drop it.
- Cloud Run env vars come from `gcloud run deploy --set-env-vars` (`^~^` = clear-all-then-set). Real OS env wins over the dotenv file because `load_dotenv` doesn't override by default, so the local `.env.develop` does not leak into prod.
- The image starts with `CMD ["python", "-m", "api.main"]` and reads `$PORT` from the environment (Cloud Run injects it; local default 8000).
- PR validation only triggers on `api/`, `ui/`, `shopify_agent/`, `requirements.txt`, `Dockerfile`, `.github/workflows/`.

## Known gaps

All four verified — pre-existing, don't assume you introduced them:

- **`make run` is broken.** It runs `python api/main.py` without `PYTHONPATH`, which fails with `ModuleNotFoundError: No module named 'ui'`. Use `make dev`, or `PYTHONPATH=. python -m api.main`.
- **`alembic/` is a stub** — only `.gitkeep` and `__init__.py`, no `env.py` and no versions. `alembic upgrade head` cannot work; the Supabase schema is managed directly in the dashboard. `alembic.ini`'s URL is a dummy.
- **`SHOPIFY_API_VERSION` is ignored.** It is set in `.env.develop` and passed by CI, but it is not a field on `Settings`; `settings.shopify_url` (`settings.py:41`) hardcodes `2024-01`. Editing the env var has no effect.
- **`.env.develop` is gitignored but present locally** with live Supabase/HF/Shopify credentials and a plaintext DB password in a comment. Never commit it, never print it, and don't echo its values into logs, commits, or PR descriptions.

## Conventions

- Logger names: `SHOPIFY-AGENT` (graph), `SHOPIFY-TOOLS` (tools), `LLM-FACTORY`. `logging.basicConfig` is configured in `ui/gradio_app.py`.
- **Superseded implementations are intentionally preserved** as commented blocks marked "IMPLEMENTACIÓN ANTERIOR (Comentado para registro)" in `prompts.py`, `graph.py`, `tools.py`, `ingest_catalog.py`, and `benchmark_agent.py`. This is a deliberate convention — don't mistake them for live code, and don't delete them during refactors.
- Design context lives in `ARCHITECTURE_AGENTIC_EVALS.md` and `METRICS_REPORT.md` (the latter's 100% metrics are from a specific 4-case run, not a regression gate).
