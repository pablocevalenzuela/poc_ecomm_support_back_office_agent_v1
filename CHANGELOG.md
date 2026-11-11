# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!--
Rules
-----
- Add entries under [Unreleased] in the same PR as the change. Never document unmerged work.
- Use the standard categories, in this order: Added, Changed, Deprecated, Removed, Fixed, Security.
- Write for humans: what changed and why. No commit hashes.
- Do NOT bump versions by hand. The release version comes from the CI tag job
  (.github/workflows/deploy.yml, anothrNick/github-tag-action). When a tag is cut, move the
  [Unreleased] content into a new version section with its release date.
-->

## [Unreleased]

### Added

- `shopify_agent/embeddings.py` — embeddings locales con `fastembed` + ONNX Runtime
  (`sentence-transformers/all-MiniLM-L6-v2`, 384 dims): el mismo modelo que usaba la API de
  inferencia de Hugging Face, pero sin token, sin cuota y sin coste.
- `fastembed==0.9.1` y `openpyxl==3.1.5` en `requirements.txt` (el segundo faltaba y rompía la
  ingesta de `.xlsx`).

### Changed

- `shopify_agent/tools.py::search_product_catalog`, `ingest_catalog.py` e
  `ingest_catalog_excel.py` calculan los vectores en local; ya no llaman a
  `HuggingFaceEndpointEmbeddings`.
- `AGENTS.md`: sección RAG actualizada con el DDL de `product_catalog_embeddings` y el nuevo
  logger `SHOPIFY-EMBEDDINGS`.

### Fixed

- Flujo RAG bloqueado por el 402 de Hugging Face Inference Providers: se habilitó `pgvector`, se
  creó `product_catalog_embeddings` y se reingestó el catálogo (PDF + Excel).

<!--
Add entries below, for example:

### Added
- Feature-level specification template for `specs/`.

### Changed
- `AGENTS.md` restructured around the spec-driven workflow.

### Fixed
- Corrected stale provider defaults in `AGENTS.md`.

Other categories: Deprecated, Removed, Security.
-->
