# AGENTS.md

## Project Overview

This project is a Proof of Concept (PoC) for an agentic conversational AI system designed to support the daily operations of an e-commerce business.

## Session Start Protocol

When starting a new session, **ALWAYS** do these 4 things first:

1. **Read `TODO.md`** — know what's done, in progress, and pending
2. **Check current git branch** — `git branch --show-current`
3. **Check `specs/roadmap.md`** — know what phase comes next
4. **If working on a feature** — read its spec in `specs/features/YYYY-MM-DD-entity/` (requirements.md, plan.md, validation.md)

## Constitution (DO NOT MODIFY)

The project's SDD (Spec-Driven Development) constitution lives in `specs/`:
- `specs/mission.md` — Product requirements & stakeholders
- `specs/tech-stack.md` — Allowed dependencies, directory conventions and definitions of tech-stack
- `specs/roadmap.md` — Sequence of phases ordering, including their tasks and dependencies. `specs/roadmap.md` is the single source of truth; it contains the requirements defined by the user (Product Owner).


## Spec-Driven Development Workflow

1. Check `specs/roadmap.md` for next phase
2. If spec exists in `specs/features/YYYY-MM-DD-entity/` → read requirements.md, plan.md, validation.md
3. If NO spec exists → **ask user to create it BEFORE coding**
4. Implement per `plan.md` task groups (one at a time)
5. Validate per `validation.md` merge gate
6. Run `npm run type-check` + `npm test` before committing


## Non-Negotiables
1. **NEVER** make changes to the source code in the current repository, and do not make independent decisions regarding requirements or features specified in `specs/roadmap.md`.

1. `specs/roadmap.md` is the single source of truth; it contains the requirements defined by the user (Product Owner).










## Set up & Commands

```bash
source venv/bin/activate                  # repo ships ./venv (Python 3.14)
pip install -r requirements.txt
make dev                                  # http://localhost:8000  (UI at /ui)

pytest tests/unit tests/integration/test_graph.py   # hermetic — use for every change
pytest tests/                             # NOT hermetic: live Postgres/LLM/Shopify/SMTP

python benchmark_agent.py                 # LLM-as-a-Judge eval, live services required
python script_visualizer_graph.py         # regenerates mi_grafo_langgraph.png, no DB needed
```

## TODO.md conventions

Format and lifecycle rules live in the file's header; the short version:

- One item = one verifiable unit of work: `- [ ] T-001 — <imperative verb> (<spec or module>)`.
- Max 3 items under **In progress**. Every item traces to `specs/` or an explicit human request.
- Closing: tick it, write the changelog entry, move it to **Done**. **Done** is pruned each release.

## CHANGELOG.md conventions

[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + [SemVer](https://semver.org/).
Rules live in the file's header; the short version:

- Add entries under `[Unreleased]` **in the same PR** as the change, for humans, no commit hashes.
- **Do not bump versions by hand.** CI cuts tags (`anothrNick/github-tag-action`); when a tag is
  cut, move `[Unreleased]` into a new version section.

## Git, branches, PRs, CI

- `main` = production, `develop` = integration, branches `feat/…`, `fix/…`, `chore/…`, `docs/…`.
  Open PRs against `develop`; `main` receives release merges only.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`), English and
  imperative. Tagging is automated: `develop` → `-dev` prerelease, `main` → deploy, default bump
  `patch` (`#major` / `#minor` in a commit message overrides it).
- PR checks only trigger on `api/`, `ui/`, `shopify_agent/`, `requirements.txt`, `Dockerfile`, and
  `.github/workflows/`. A docs-only PR runs no checks — expected, not a failure.
- Never force-push `main` or `develop`.


- `make dev` is the only working run target: it sets `PYTHONPATH=.` and serves `api.main:app` with
  `--reload`. `PYTHONPATH` is mandatory because `api/main.py` imports `ui.*` and `shopify_agent.*`
  as top-level packages; the `Dockerfile` bakes `PYTHONPATH=/app`.
- `make run` is broken (`python api/main.py` without `PYTHONPATH`). Use `make dev` or
  `PYTHONPATH=. python -m api.main`.
- Python versions disagree: `Dockerfile` `3.11-slim`, CI `3.13`, local venv `3.14`.
  `requirements.txt` marker-gates `audioop-lts` to `>= 3.13.7`, so it silently skips on 3.11.
  Don't "fix" one without checking the other two.

## Definition of Done

- [ ] The change traces to a `specs/` statement or a `TODO.md` item and does not alter the stack.
- [ ] `pytest tests/unit tests/integration/test_graph.py` passes.
- [ ] If prompts, tool docstrings, or tool behavior changed: marker contract intact and
      `python benchmark_agent.py` run when live services are available.
- [ ] `CHANGELOG.md` has an `[Unreleased]` entry; the `TODO.md` item is closed.
- [ ] No secrets or `.env.develop` values in code, logs, commits, or PR text.
- [ ] `AGENTS.md` updated in the same PR if commands, invariants, or contracts changed.

There is **no lint, format, or typecheck config** — no ruff/black/mypy/pyproject/pre-commit, no lint
CI job. Do not invent `make lint` or claim one exists.

## Testing

**`pytest tests/` is not hermetic.** It also collects `tests/integration/test_hitl_cancellation.py`,
which calls `init_graph()` against real Postgres, then drives a real LLM, Shopify, and SMTP. Without
live services it burns ~30s and fails with `psycopg_pool.PoolTimeout` (`1 failed, 10 passed`). CI
runs it with mock env vars and no DB, so a red `test` job on that file is pre-existing.

- `pytest.ini` sets `asyncio_mode = auto`, so `@pytest.mark.asyncio` is optional.
- `tests/integration/test_graph.py` parametrizes off `tests/data/golden_dataset.json` **at
  collection time**, so editing that file changes test IDs. It patches `shopify_agent.graph.llm` and
  `httpx.AsyncClient.post` and asserts the ReAct contract: exactly 2 LLM calls, and a `ToolMessage`
  in the second call's history.
- Datasets: `golden_dataset.json` (test_graph.py), `golden_dataset_token_economy_test.json`
  (benchmark_agent.py), `golden_dataset_backup.json` (unused).

## Architecture invariants

`api/main.py` is the single entrypoint: FastAPI with Gradio mounted at `/ui`, `POST /chat` taking
`{message, session_id}`, `GET /` returning `APP_VERSION`. Those three are the app's own routes.
`thread_id` for the checkpointer is the client-supplied `session_id`.

`shopify_agent/graph.py` is a two-node `agent` ⇄ `tools` ReAct loop over `AgentState` (messages
only; the other TypedDict keys are unused).

- **Import-time side effect**: importing `shopify_agent.graph` calls `get_llm(...)` at module scope,
  so any script or test importing it needs a provider token set.
- **`graph` is module-level `None` until `await init_graph()`**, which opens the
  `AsyncConnectionPool`, runs `checkpointer.setup()`, and compiles. The lifespan calls it;
  `benchmark_agent.py`, `ui/gradio_app.py`, and the HITL test call it themselves. `/chat` returns
  503 while it is `None`; a DB failure at startup is only logged as a warning.
- The trimmer keeps the last 15 messages (`start_on="human"`, `token_counter=len`), so multi-turn
  flows needing more lose context.
- **DB URL handling is inconsistent.** `graph.py` and `db.py` read `os.getenv("DATABASE_URL")` with
  *different* fallbacks; `tools.py` and both ingest scripts use `settings.database_url`. The latter
  replace `postgresql+asyncpg://` → `postgresql://` because psycopg needs the sync scheme.
- Add providers only in `shopify_agent/llm_factory.py::get_llm(purpose=...)`. `LLM_PROVIDER`:
  `openrouter` (default → `qwen/qwen-2.5-72b-instruct`), `huggingface` (Qwen2.5-72B-Instruct),
  `openai` (gpt-4o-mini agent / gpt-4o judge), `github` (same models via
  `models.inference.ai.azure.com`).

## Transparency-marker contract

Canonical strings live in the `SYSTEM_PROMPT` block of `shopify_agent/prompts.py`, are repeated in
every tool docstring in `shopify_agent/tools.py`, and the judge rubric in `benchmark_agent.py` caps
any answer missing them at score 3:

- `He verificado en el Sistema Shopify:` — orders, stock, inventory
- `He consultado el Catálogo De Proveedores:` — RAG, SAP codes, wholesale pricing
- `Consultando el Sistema de Correos:` — emails and approvals

Change them only by updating the tool docstring, `prompts.py`, and the judge rubric together.
Missing one silently tanks the eval score instead of raising an error. The comments at the top of
`prompts.py` still mention an older `Catálogo Técnico` variant — `SYSTEM_PROMPT` is authoritative.

## RAG & data

- pgvector table `product_catalog_embeddings (id, content, embedding vector(384), metadata jsonb)` in
  Supabase. No script creates it — the DDL below is applied by hand (dashboard or `psql`).
- Embeddings run **locally** via `shopify_agent/embeddings.py`: `fastembed` + ONNX Runtime with
  `sentence-transformers/all-MiniLM-L6-v2` (384 dims). No token, no quota, no cost, works offline.
  Do **not** reintroduce `HuggingFaceEndpointEmbeddings`: HF Inference Providers are prepaid since
  2025 and return 402 without credits, which kills both chat and RAG.
- `tools.py::search_product_catalog` runs `ORDER BY embedding <=> %s LIMIT 6`, with an unfiltered
  `LIMIT 3` fallback when nothing matches — results degrade to arbitrary rows instead of admitting
  no match.
- Ingest from the repo root (`products_catalog/` holds the sources):
  `python ingest_catalog.py catalogo_2026_lech_rio_claro.pdf` and
  `python ingest_catalog_excel.py lista_precios_rio_claro_12062026.xlsx [--sheet <name>]`.
  Re-running an ingest **appends duplicates**; truncate the table first.
- DDL (Supabase SQL editor or `psql`):

  ```sql
  create extension if not exists vector;
  create table if not exists product_catalog_embeddings (
    id bigserial primary key,
    content text not null,
    embedding vector(384) not null,
    metadata jsonb not null default '{}'::jsonb
  );
  create index if not exists product_catalog_embeddings_embedding_idx
    on product_catalog_embeddings using hnsw (embedding vector_cosine_ops);
  ```

## Evals

`python benchmark_agent.py` — LLM-as-a-Judge over the golden dataset (success rate, real token cost,
per-tool frequency). Requires live Postgres + LLM. The active dataset is
`tests/data/golden_dataset_token_economy_test.json`; the full 7-case `golden_dataset.json` line is
commented out in `run_senior_benchmark()`.

`python script_visualizer_graph.py` regenerates `mi_grafo_langgraph.png` from `workflow.compile()`,
no DB needed.

## Deploy

`.github/workflows/deploy.yml`, one workflow, two jobs:

- `develop` → runs tests and creates a `-dev` prerelease tag. **No deploy.**
- `main` → auth to GCP via Workload Identity Federation, `gcloud builds submit`, then
  `gcloud run deploy --allow-unauthenticated`.
- `fetch-depth: 0` is required by the tag action — don't drop it.
- Env vars come from `gcloud run deploy --set-env-vars` (`^~^` = clear-all-then-set). Real OS env
  wins over the dotenv file because `load_dotenv` doesn't override, so `.env.develop` never leaks
  into prod. The image runs `python -m api.main` and reads `$PORT` (local default 8000).

## Known gaps

Pre-existing and verified — don't assume you introduced them:

- **`make run` is broken** (see Commands).
- **`alembic/` is a stub**: only `.gitkeep` and `__init__.py`, no `env.py`, no versions. The
  Supabase schema is managed in the dashboard and `alembic.ini`'s URL is a dummy.
- **`SHOPIFY_API_VERSION` is ignored**: it is not a field on `Settings`, and `Settings.shopify_url`
  hardcodes `2024-01`.
- **`.env.develop` is gitignored but present locally** with live credentials and a plaintext DB
  password in a comment. Never commit, print, or echo its values.
- **Deployment/provider drift to verify**: `Settings.llm_provider` defaults to `openrouter`, but the
  deploy workflow sets neither `LLM_PROVIDER` nor `OPEN_ROUTER_API_KEY`, only `OPENAI_API_KEY`.
- **HF Inference Providers are paid**: `HuggingFaceEndpointEmbeddings` / `HuggingFaceEndpoint` return
  402 without prepaid credits. That is why the chat provider is OpenRouter and RAG uses local
  `fastembed`. The `huggingface` branch in `llm_factory.py::get_llm` is only a legacy fallback.
- **`catalogo_2026_lech_rio_claro.pdf` extracts only ~1.5k chars (3 chunks)**: it is mostly scanned
  images, so `pypdf` gets almost no text. RAG answers on PDF content are thin; the Excel price list
  carries most of the catalog.

## Guardrails

- **Dead code — don't build on it:** `shopify_agent/hitl.py` always returns `False` and is not
  wired into the graph (HITL lives only in the prompt and tool choice); `webhook/main.py` is mounted
  nowhere; `models.py` / `db.py` (`AgentLog`) are unused.
- **Superseded implementations are intentional.** Blocks marked "IMPLEMENTACIÓN ANTERIOR (Comentado
  para registro)" in `prompts.py`, `graph.py`, `tools.py`, `ingest_catalog.py`, and
  `benchmark_agent.py` are kept for the record — don't treat them as live code or delete them.
- **Logger names:** `SHOPIFY-AGENT` (graph), `SHOPIFY-TOOLS` (tools), `LLM-FACTORY`,
  `SHOPIFY-EMBEDDINGS` (embeddings). `logging.basicConfig` is configured in `ui/gradio_app.py`.
- No secrets in commits, no telemetry or external services added without approval.

## Maintenance

This file rots if left alone: if a command, path, symbol, or invariant here no longer matches the
repo, update it in the same PR that broke it. Prefer symbol references (`module.py::function`) over
line numbers, which drift on every refactor. Bump `Last reviewed` after a full pass.
