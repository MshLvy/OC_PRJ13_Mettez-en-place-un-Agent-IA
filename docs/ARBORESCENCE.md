# Arborescence finale du candidat

Fichiers publiables uniquement, sans .git, dépendances, poids ou work. Voir [inventaire](INVENTAIRE_RELEASE.md) et [empreintes](../validation/files.json).

```text
OC_PRJ13_RELEASE_CANDIDATE/
├── .dockerignore
├── .env.example
├── .gitignore
├── LICENSE.md
├── LICENSES/
│   └── GPL-3.0-or-later.txt
├── README.md
├── backend/
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── app/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── advisor.py
│   │   ├── advisor_data.py
│   │   ├── advisor_dense.py
│   │   ├── advisor_dense_worker.py
│   │   ├── advisor_routes.py
│   │   ├── analysis_preferences.py
│   │   ├── analysis_routes.py
│   │   ├── cli.py
│   │   ├── config.py
│   │   ├── conversation.py
│   │   ├── conversation_bge.py
│   │   ├── conversation_data.py
│   │   ├── conversation_generators.py
│   │   ├── conversation_local.py
│   │   ├── conversation_mistral.py
│   │   ├── conversation_retrieval.py
│   │   ├── conversation_routes.py
│   │   ├── data/
│   │   │   ├── advisor_v3/
│   │   │   │   ├── README.md
│   │   │   │   └── chunks.json
│   │   │   └── openings/
│   │   │       ├── catalog.json
│   │   │       ├── manifest.json
│   │   │       ├── translations.fr.json
│   │   │       └── upstream/
│   │   │           ├── COPYING.txt
│   │   │           ├── README.md
│   │   │           ├── a.tsv
│   │   │           ├── b.tsv
│   │   │           ├── c.tsv
│   │   │           ├── d.tsv
│   │   │           └── e.tsv
│   │   ├── demo.py
│   │   ├── evaluate_routes.py
│   │   ├── explorer.py
│   │   ├── explorer_fixtures.py
│   │   ├── explorer_live.py
│   │   ├── explorer_registry.py
│   │   ├── game.py
│   │   ├── game_routes.py
│   │   ├── main.py
│   │   ├── moves_routes.py
│   │   ├── openings.py
│   │   ├── openings_routes.py
│   │   ├── orchestration.py
│   │   ├── position_routes.py
│   │   ├── positions.py
│   │   ├── sessions.py
│   │   ├── sessions_routes.py
│   │   ├── stockfish.py
│   │   ├── vector_routes.py
│   │   ├── vector_search.py
│   │   ├── video_exploration.py
│   │   ├── videos.py
│   │   ├── videos_routes.py
│   │   ├── workflow.py
│   │   └── workflow_dispatch.py
│   ├── pytest.ini
│   ├── requirements-dev.txt
│   ├── requirements.txt
│   └── tests/
│       ├── conftest.py
│       ├── graph_smoke_app.py
│       ├── test_analysis_preferences.py
│       ├── test_api.py
│       ├── test_conversation.py
│       ├── test_conversation_bge.py
│       ├── test_demo_docker_peer.py
│       ├── test_demo_modes.py
│       ├── test_demo_modes_i07a.py
│       ├── test_env_config.py
│       ├── test_explorer.py
│       ├── test_explorer_live.py
│       ├── test_game.py
│       ├── test_generation_api.py
│       ├── test_generation_budgets.py
│       ├── test_generation_compact.py
│       ├── test_generation_contract.py
│       ├── test_generation_groq.py
│       ├── test_generation_local.py
│       ├── test_global_workflow.py
│       ├── test_openings.py
│       ├── test_orchestration.py
│       ├── test_positions.py
│       ├── test_release_packaging.py
│       ├── test_sessions.py
│       ├── test_stockfish.py
│       ├── test_video_exploration.py
│       ├── test_videos.py
│       └── test_youtube_live.py
├── compose.bge.yaml
├── compose.local.yaml
├── compose.milvus.yaml
├── compose.mongodb.yaml
├── compose.yaml
├── docs/
│   ├── API.md
│   ├── ARBORESCENCE.md
│   ├── ARCHITECTURE.md
│   ├── AUDIT_RELEASE.md
│   ├── BGE_MILVUS.md
│   ├── CORPUS.md
│   ├── DEMONSTRATION.md
│   ├── FOURNISSEURS.md
│   ├── INSTALLATION.md
│   ├── INVENTAIRE_RELEASE.md
│   ├── LICENCES.md
│   ├── LIMITES.md
│   ├── MONGODB.md
│   ├── OPERATIONS.md
│   ├── PUBLICATION.md
│   ├── VALIDATION.md
│   ├── assets/
│   │   └── interface-simulation.png
│   ├── diagrammes/
│   │   ├── ANALYSE.mmd
│   │   ├── ANALYSE_DETAIL.mmd
│   │   ├── DOCKER.mmd
│   │   ├── GLOBAL.mmd
│   │   ├── GLOBAL_EXPANDED.mmd
│   │   ├── PARCOURS.mmd
│   │   ├── RAG.mmd
│   │   ├── RAG_SERVICE.mmd
│   │   ├── SEANCES.mmd
│   │   ├── VIDEOS.mmd
│   │   └── VIDEOS_INTENTIONS.mmd
│   └── mcp/
│       ├── ARCHITECTURE_MCP_VIDEO.mmd
│       ├── CONTRAT.md
│       ├── ETUDE.md
│       ├── costs.csv
│       ├── costs.json
│       ├── costs.py
│       └── sources.json
├── frontend/
│   ├── .dockerignore
│   ├── .gitignore
│   ├── Dockerfile
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── src/
│   │   ├── analysis-ui.spec.ts
│   │   ├── analysis.spec.ts
│   │   ├── analysis.ts
│   │   ├── app.spec.ts
│   │   ├── app.ts
│   │   ├── conversation-ui.spec.ts
│   │   ├── conversation.spec.ts
│   │   ├── conversation.ts
│   │   ├── demo-modes-i07a.spec.ts
│   │   ├── demo-ui.spec.ts
│   │   ├── demo-validation.spec.ts
│   │   ├── demo.spec.ts
│   │   ├── demo.ts
│   │   ├── environment-config.spec.ts
│   │   ├── game.spec.ts
│   │   ├── game.ts
│   │   ├── main.ts
│   │   ├── openings-ui.spec.ts
│   │   ├── openings.spec.ts
│   │   ├── openings.ts
│   │   ├── sessions-fixtures.ts
│   │   ├── sessions-ui.spec.ts
│   │   ├── sessions.spec.ts
│   │   ├── sessions.ts
│   │   ├── style.css
│   │   ├── videos-fixtures.ts
│   │   ├── videos-ui.spec.ts
│   │   ├── videos.spec.ts
│   │   └── videos.ts
│   ├── tests/
│   │   └── fixtures/
│   │       └── analysis-synthetic.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── infra/
│   ├── milvus/
│   │   ├── embedEtcd.yaml
│   │   └── user.yaml
│   └── mongodb/
│       ├── 10-sessions.js
│       └── entrypoint.sh
├── retrieval/
│   ├── Dockerfile
│   ├── __init__.py
│   ├── acquire.py
│   ├── artifacts.json
│   ├── contract.py
│   ├── encoder.py
│   ├── index.py
│   ├── model-files.json
│   ├── policy.json
│   ├── preflight.py
│   ├── requirements.lock
│   ├── server.py
│   └── store.py
├── scripts/
│   ├── audit-release.py
│   ├── export-graph.py
│   ├── mongo-config.py
│   ├── p13
│   └── test-backend.py
├── tools/
│   └── openings/
│       └── build_catalog.py
└── validation/
    ├── audit.json
    ├── browser.json
    ├── compose.json
    ├── dependencies.json
    ├── files.json
    ├── graphs.json
    ├── integrity.json
    ├── publication.json
    └── tests.json
```
