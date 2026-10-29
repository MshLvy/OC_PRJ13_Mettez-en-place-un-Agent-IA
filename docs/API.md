# Contrats API — version RELEASE

24 opérations déclarées,20routées par le parent,4contrôles directs. Les DTO/FEN/historique/budgets et codes d’erreur restent ceux des sources ci-dessous. [OpenAPI](http://127.0.0.1:8001/docs) disponible seulement quand le backend local est lancé ; ce lien n’est pas un service public.

| Méthode | Route | Schéma entrée | Source |
|---|---|---|---|
| GET | `/api/v1/sessions/status` | Aucune | [source](../backend/app/sessions_routes.py#L27) |
| POST | `/api/v1/sessions` | SessionDraft | [source](../backend/app/sessions_routes.py#L29) |
| GET | `/api/v1/sessions` | limit, after | [source](../backend/app/sessions_routes.py#L31) |
| GET | `/api/v1/sessions/{ident}` | ident | [source](../backend/app/sessions_routes.py#L34) |
| DELETE | `/api/v1/sessions/{ident}` | ident | [source](../backend/app/sessions_routes.py#L37) |
| POST | `/api/v1/sessions/{ident}/resume` | ident | [source](../backend/app/sessions_routes.py#L41) |
| POST | `/api/v1/videos/search` | VideoRequest | [source](../backend/app/videos_routes.py#L27) |
| POST | `/api/v1/videos/explore` | ExploreRequest | [source](../backend/app/videos_routes.py#L32) |
| GET | `/api/v1/videos/{opening}` | opening, confirm_live | [source](../backend/app/videos_routes.py#L39) |
| POST | `/api/v1/game/state` | HistoryRequest | [source](../backend/app/game_routes.py#L24) |
| POST | `/api/v1/game/turn` | TurnRequest | [source](../backend/app/game_routes.py#L27) |
| POST | `/api/v1/openings/identify` | HistoryRequest | [source](../backend/app/openings_routes.py#L13) |
| GET | `/api/v1/advisor/capabilities` | Aucune | [source](../backend/app/advisor_routes.py#L35) |
| POST | `/api/v1/advisor/retrieve` | RetrieveRequest | [source](../backend/app/advisor_routes.py#L40) |
| POST | `/api/v1/advisor/conversation` | ConversationRequest | [source](../backend/app/conversation_routes.py#L7) |
| POST | `/api/v1/analysis/orchestrate` | AnalysisRequest | [source](../backend/app/analysis_routes.py#L38) |
| GET | `/api/v1/demo/capabilities` | Aucune | [source](../backend/app/demo.py#L344) |
| POST | `/api/v1/demo/turn` | DemoTurnRequest | [source](../backend/app/demo.py#L349) |
| POST | `/api/v1/demo/analysis` | DemoAnalysisRequest | [source](../backend/app/demo.py#L354) |
| GET | `/api/v1/moves/{fen}` | fen | [source](../backend/app/moves_routes.py#L42) |
| POST | `/api/v1/positions/validate` | PositionRequest | [source](../backend/app/position_routes.py#L44) |
| GET | `/api/v1/evaluate/{fen}` | fen | [source](../backend/app/evaluate_routes.py#L33) |
| GET | `/api/v1/healthcheck` | Aucune | [source](../backend/app/main.py#L124) |
| POST | `/vector-search` | VectorRequest | [source](../backend/app/vector_routes.py#L11) |


## Parcours recommandé

Le frontend utilise `/api/v1/demo/analysis`, `/api/v1/demo/turn`, `/api/v1/advisor/conversation`, `/api/v1/videos/explore` et les routes séances. POST `/vector-search` prend une question/FEN/historique, request_generation=false : uniquement passages denses admis ou indisponibilité503/passages vides, pas BM25 seul annoncé vectoriel.

GET `/api/v1/videos/{opening}` nécessite confirm_live=true si serveur live, avant toute consultation de clé/transport ; ne pas l’appeler pour un simple healthcheck. Les requêtes invalides peuvent être rejetées avant graphe et ne portent pas forcément de headerX-Workflow.

**Compatibilité conservée, ressource exclue :** `/api/v1/advisor/retrieve` et `/api/v1/advisor/capabilities` sont les contrats historiquesV1/E5, pas le conseiller V3. Leurs corpus expérimentaux ne sont pas redistribués : résultat unavailable explicite, sans chargement de modèle ni connexion E5. Ne pas utiliser ces routes pour diagnostiquer la disponibilité BGE du conseiller ; aucune fausse conformité V1 annoncée. Les24 opérations sont des contrats existants, pas24fonctions toutes opérationnelles en mode limité.

Création séances201sur acquittement ; liste/détail200 ; suppression explicite et acquittée ; resume prépare une lecture/revalidation, ne déplace pas le navigateur. L’UI conserve GETdétail puis game/state et force Étudier/Simulation sans analyse/génération/vidéo.
