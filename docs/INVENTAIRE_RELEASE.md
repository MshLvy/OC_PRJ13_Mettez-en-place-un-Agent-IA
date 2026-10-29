# Inventaire RELEASE — sélection et exclusions

La sélection est une extraction de fichiers nécessaires, pas un clone Git ni une copie intégrale du dépôt source. Les droits et limites sont dans [l’audit](AUDIT_RELEASE.md) et [les licences](LICENCES.md). Le manifeste exact avec tailles/SHA256 est [files.json](../validation/files.json). Cette table décrit les raisons de conservation ; elle ne signifie pas que toutes les fonctionnalités optionnelles ont été physiquement exécutées.

## Exclusions

| Groupe exclu | Justification / remplacement |
|---|---|
| Historique Git, branches source, tags et remotes privés | Nouveau .git local main sans commit, aucun partage d’objets |
| Handoffs, journaux, rapports d’exécution internes et preuves intermédiaires | Guides finaux et nouvelles synthèses expurgées uniquement |
| CorpusV1/V2, brouillons/précurseurs V3, évaluations/dev/questions réservées | Uniquement la copie d’exécution96 unités avec provenance ; aucune question de benchmark distribuée |
| Outils d’expérimentation E5/BM25comparatif/ingestions anciennes | Runtime BM25 actuel et outillage BGE autonome seulement ; pas de benchmark |
| AnciennepolicyV1ettestsV1/E5 | Source legacy refusée explicitement, contrats HTTP conservés comme unavailable |
| Tests de l’ancien contrôleur de services et application de démo interne | Nouveau contrôleur RELEASE, nouveaux tests de propriété/approbation |
| Capture réseau Lichess intermédiaire | Test de replay remplacé par échantillon synthétique déclaré |
| Modèles BGE/Qwen et caches/dépendances installées | Manifeste d’acquisition, hashes, locks et Dockerfiles seulement |
| Données Mongo, collections/volumes Milvus, fichiers privés .env/clefs | Aucune copie, nouveaux volumes/collection exclusivement après autorisation opérateur |
| ImagesDockerprivées, chemins de poste personnel et liens indispensables privés | Builds depuis sources publiques et ressources propres au projet |

Les modules de compatibilité legacy qui restent importés par les DTO/routeurs ne constituent pas un retour des corpus expérimentaux : le chargeur refuse et le guide les annonce indisponibles. Les tests de runtime conservés sont nécessaires à la maintenance des contrats, pas des benchmarks publiés.

## Fichiers conservés

| Chemin | Raison |
|---|---|
| `.dockerignore` | Entrée, notice légale, exemple public ou configuration du packaging |
| `.env.example` | Entrée, notice légale, exemple public ou configuration du packaging |
| `.gitignore` | Entrée, notice légale, exemple public ou configuration du packaging |
| `LICENSE.md` | Entrée, notice légale, exemple public ou configuration du packaging |
| `LICENSES/GPL-3.0-or-later.txt` | Entrée, notice légale, exemple public ou configuration du packaging |
| `README.md` | Entrée, notice légale, exemple public ou configuration du packaging |
| `backend/.dockerignore` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/Dockerfile` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/__init__.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/__main__.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/advisor.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/advisor_data.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/advisor_dense.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/advisor_dense_worker.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/advisor_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/analysis_preferences.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/analysis_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/cli.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/config.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/conversation.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/conversation_bge.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/conversation_data.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/conversation_generators.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/conversation_local.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/conversation_mistral.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/conversation_retrieval.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/conversation_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/data/advisor_v3/README.md` | Corpus96unités exécutables et notice, licences/empreintes conservées |
| `backend/app/data/advisor_v3/chunks.json` | Corpus96unités exécutables et notice, licences/empreintes conservées |
| `backend/app/data/openings/catalog.json` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/data/openings/manifest.json` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/data/openings/translations.fr.json` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/data/openings/upstream/COPYING.txt` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/data/openings/upstream/README.md` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/data/openings/upstream/a.tsv` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/data/openings/upstream/b.tsv` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/data/openings/upstream/c.tsv` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/data/openings/upstream/d.tsv` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/data/openings/upstream/e.tsv` | Référentiel factuel localCC0avec sa provenance et notices |
| `backend/app/demo.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/evaluate_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/explorer.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/explorer_fixtures.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/explorer_live.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/explorer_registry.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/game.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/game_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/main.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/moves_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/openings.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/openings_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/orchestration.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/position_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/positions.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/sessions.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/sessions_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/stockfish.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/vector_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/vector_search.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/video_exploration.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/videos.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/videos_routes.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/workflow.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/app/workflow_dispatch.py` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/pytest.ini` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/requirements-dev.txt` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/requirements.txt` | Runtime FastAPI/LangGraph et dépendances nécessaires |
| `backend/tests/conftest.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/graph_smoke_app.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_analysis_preferences.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_api.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_conversation.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_conversation_bge.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_demo_docker_peer.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_demo_modes.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_demo_modes_i07a.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_env_config.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_explorer.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_explorer_live.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_game.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_generation_api.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_generation_budgets.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_generation_compact.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_generation_contract.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_generation_groq.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_generation_local.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_global_workflow.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_openings.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_orchestration.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_positions.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_release_packaging.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_sessions.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_stockfish.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_video_exploration.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_videos.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `backend/tests/test_youtube_live.py` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `compose.bge.yaml` | Entrée, notice légale, exemple public ou configuration du packaging |
| `compose.local.yaml` | Entrée, notice légale, exemple public ou configuration du packaging |
| `compose.milvus.yaml` | Entrée, notice légale, exemple public ou configuration du packaging |
| `compose.mongodb.yaml` | Entrée, notice légale, exemple public ou configuration du packaging |
| `compose.yaml` | Entrée, notice légale, exemple public ou configuration du packaging |
| `docs/API.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/ARBORESCENCE.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/ARCHITECTURE.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/AUDIT_RELEASE.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/BGE_MILVUS.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/CORPUS.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/DEMONSTRATION.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/FOURNISSEURS.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/INSTALLATION.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/INVENTAIRE_RELEASE.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/LICENCES.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/LIMITES.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/MONGODB.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/OPERATIONS.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/PUBLICATION.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/VALIDATION.md` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/assets/interface-simulation.png` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/ANALYSE.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/ANALYSE_DETAIL.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/DOCKER.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/GLOBAL.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/GLOBAL_EXPANDED.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/PARCOURS.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/RAG.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/RAG_SERVICE.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/SEANCES.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/VIDEOS.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/diagrammes/VIDEOS_INTENTIONS.mmd` | Documentation finale, schéma ou capture authentique du candidat |
| `docs/mcp/ARCHITECTURE_MCP_VIDEO.mmd` | Étude de conception requise : source éditable, coûts ou références publiques |
| `docs/mcp/CONTRAT.md` | Étude de conception requise : source éditable, coûts ou références publiques |
| `docs/mcp/ETUDE.md` | Étude de conception requise : source éditable, coûts ou références publiques |
| `docs/mcp/costs.csv` | Étude de conception requise : source éditable, coûts ou références publiques |
| `docs/mcp/costs.json` | Étude de conception requise : source éditable, coûts ou références publiques |
| `docs/mcp/costs.py` | Étude de conception requise : source éditable, coûts ou références publiques |
| `docs/mcp/sources.json` | Étude de conception requise : source éditable, coûts ou références publiques |
| `frontend/.dockerignore` | Interface Angular, sources et build verrouillé |
| `frontend/.gitignore` | Interface Angular, sources et build verrouillé |
| `frontend/Dockerfile` | Interface Angular, sources et build verrouillé |
| `frontend/index.html` | Interface Angular, sources et build verrouillé |
| `frontend/package-lock.json` | Interface Angular, sources et build verrouillé |
| `frontend/package.json` | Interface Angular, sources et build verrouillé |
| `frontend/src/analysis-ui.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/analysis.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/analysis.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/app.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/app.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/conversation-ui.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/conversation.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/conversation.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/demo-modes-i07a.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/demo-ui.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/demo-validation.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/demo.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/demo.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/environment-config.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/game.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/game.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/main.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/openings-ui.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/openings.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/openings.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/sessions-fixtures.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/sessions-ui.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/sessions.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/sessions.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/style.css` | Interface Angular, sources et build verrouillé |
| `frontend/src/videos-fixtures.ts` | Interface Angular, sources et build verrouillé |
| `frontend/src/videos-ui.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/videos.spec.ts` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/src/videos.ts` | Interface Angular, sources et build verrouillé |
| `frontend/tests/fixtures/analysis-synthetic.json` | Test maintenu de contrat, de sécurité ou non-régression avec données synthétiques |
| `frontend/tsconfig.json` | Interface Angular, sources et build verrouillé |
| `frontend/vite.config.ts` | Interface Angular, sources et build verrouillé |
| `infra/milvus/embedEtcd.yaml` | Configuration des nouvelles bases internes |
| `infra/milvus/user.yaml` | Configuration des nouvelles bases internes |
| `infra/mongodb/10-sessions.js` | Configuration des nouvelles bases internes |
| `infra/mongodb/entrypoint.sh` | Configuration des nouvelles bases internes |
| `retrieval/Dockerfile` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/__init__.py` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/acquire.py` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/artifacts.json` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/contract.py` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/encoder.py` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/index.py` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/model-files.json` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/policy.json` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/preflight.py` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/requirements.lock` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/server.py` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `retrieval/store.py` | Acquisition, bootstrap et recherche BGE autonomes sans poids/benchmark |
| `scripts/audit-release.py` | Installation, opérations bornées, test ou audit du candidat |
| `scripts/export-graph.py` | Installation, opérations bornées, test ou audit du candidat |
| `scripts/mongo-config.py` | Installation, opérations bornées, test ou audit du candidat |
| `scripts/p13` | Installation, opérations bornées, test ou audit du candidat |
| `scripts/test-backend.py` | Installation, opérations bornées, test ou audit du candidat |
| `tools/openings/build_catalog.py` | Reconstruction déterministe du catalogue distribué |
| `validation/audit.json` | Contrôle expurgé de ce candidat, sans preuve historique privée |
| `validation/browser.json` | Contrôle expurgé de ce candidat, sans preuve historique privée |
| `validation/compose.json` | Contrôle expurgé de ce candidat, sans preuve historique privée |
| `validation/dependencies.json` | Contrôle expurgé de ce candidat, sans preuve historique privée |
| `validation/files.json` | Contrôle expurgé de ce candidat, sans preuve historique privée |
| `validation/graphs.json` | Contrôle expurgé de ce candidat, sans preuve historique privée |
| `validation/integrity.json` | Contrôle expurgé de ce candidat, sans preuve historique privée |
| `validation/tests.json` | Contrôle expurgé de ce candidat, sans preuve historique privée |

| `validation/publication.json` | Contrôles de finalisation, licence définitive et limites d’exécution ; aucune preuve privée |
