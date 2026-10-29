# Architecture implémentée et contrats de confiance

[Architecture Docker éditable](diagrammes/DOCKER.mmd), [parent exact](diagrammes/GLOBAL.mmd), [parent développé](diagrammes/GLOBAL_EXPANDED.mmd). Les diagrammes sont des sources Mermaid ; un lecteur Markdown n’affiche pas nécessairement un .mmd sans outil de rendu. Pas d’image qui contiendrait l’unique explication.

## Frontend, positions et modes

Angular20.3/Vite, grille64boutons Unicode (alternative explicite àngx-chessboard, non une intégration de cette bibliothèque), services fetch typés. Le serveur python-chess rejoue l’historique UCI, produit SAN/FEN et refuse les coups illégaux. Le snapshot est un checksum de synchronisation, pas une authentification.

Positions/intentions/modes ont tickets et abort ; une réponse tardive ne remplace pas la position courante. Abort UI ne garantit pas l’annulation d’un coût déjà engagé. Les ouvertures sont identifiées depuis le catalogue Lichess chess-openings CC0 versionné, sans API au mouvement ; transpositions/ambiguïtés/variantes inconnues sont annoncées.

## Quatre vrais sous-graphes

FastAPI fixe19 intentions pour20 opérations métier/24 opérations API. Le parent compilé p13_global choisit un seul enfant, puis finit. Les4contrôles directs (santé, capabilities démo, capabilities legacy, status séances) ne sont pas des invocations métier. L’OpenAPI/framework n’est pas un outil supplémentaire.

| Branche | Export réel | Actions / composition |
|---|---|---|
| Analyse | [ANALYSE](diagrammes/ANALYSE.mmd) | analyses, coups, moteur, jeu, validation, classification ; [graphe technique délégué](diagrammes/ANALYSE_DETAIL.mmd) |
| RAG | [RAG](diagrammes/RAG.mmd) | conversationV3/vector-search, compatibilité retrieveV1 indisponible ; ConversationService garde le pipeline |
| Vidéos | [VIDEOS](diagrammes/VIDEOS.mmd) | search/GET/explore ; [mini-graphe trois intentions](diagrammes/VIDEOS_INTENTIONS.mmd) |
| Séances | [SEANCES](diagrammes/SEANCES.mmd) | créer/lister/lire/supprimer/préparer reprise, un appel métier par action |

Chaque enfant : admit_action→execute_action→check_result. État typé intention/contexte/payload fermé/résultat/erreurs/provenance ; services et exceptions internes en contexte non sérialisé. Aucun checkpointer, retry automatique, tracing hébergé ou mémoire Mongo du graphe. Le xray développe les4 enfants, pas le contenu arbitraire d’une méthode Python. Ne pas annoncer BM25 ou Groq comme nœuds distincts inexistants.

Les headers X-Workflow-Graph=p13_global_v1 et X-Workflow-Path ne contiennent que des noms d’étapes. Ils attestent le routage, pas une I/O réelle. Les erreurs avant admission FastAPI peuvent n’avoir aucun header. Pour afficher le graphe depuis l’image sans fournisseur : `./scripts/p13 graph`.

## RAG commun, génération séparée

[Flux de service pédagogique](diagrammes/RAG_SERVICE.mmd). Validation de question/injection/scope/FEN/historique ; admission exacte de position ou théorie d’une famille ; BM25 localk1=1,2/b=0,75 ; BGE optionnel, candidats denses ensuite filtrés par les mêmes contraintes et soutien lexical ; fusion RRF60, déduplication, max3 passages. Les scores BM25/IP ne sont pas des probabilités comparables.

BGE CPUFP32/CLS/L2/1024D/512 tokens, MilvusFLAT/IP. Révision/hash modèle/corpus et96 identités vérifiés, empreintes des vecteurs contrôlées avant/après recherche. Le bootstrap d’indexation est séparé et approuvé explicitement ; le worker HTTP n’expose aucune mutation. Défaut lexical offline_bm25_v3, hybride ready si vérifié, panne dense bm25_fallback_v3 clairement déclarée. `/vector-search` ne convertit jamais un résultat BM25 en réussite vectorielle.

Génération sur clic après preuves admises ; Simulation Qwen ou restitution déterministe, Réel APIconfigurée. Validation JSON/IDs/scope/UCI, pas garantie sémantique totale. Les documents peuvent contenir une erreur malgré une empreinte correcte. Revue humaine pending ; aucune supériorité BGE, seuil universel ou nouvelle métrique n’est annoncée sans mesure. Aucun benchmark ni jeu scellé distribué.

## Théorie, moteur et vidéos

Défaut analyse requested : statistiques et moteur si demandés/autorisés ; option theory_fallback : théorie présente⇒moteur skipped, théorie vide⇒moteur demandé ; panne Lichess⇒erreur conservée et éventuellement partial, jamais « sortie de théorie prouvée ». Score Stockfish cp ou mat blanc-centré et borné, coup légal, pas probabilité de victoire. Adversaire Réel utilise fréquence légale puis moteur sous bornes ; simulations annoncées indépendamment.

Vidéos : demande utilisateur et trois intentions bornées, pas recommandation automatique à chaque coup. Mode serveur indépendant, quotas locaux non distribués, erreurs sans repli fixture. Métadonnées!=vidéo visionnée ou timestamp FEN. L’étude MCP décrit une extension future seulement.

## Sessions et stockage

Mongo facultatif, compteappauthentifié/réseau interne, données minimisées ; reçus HMACvalables15min seulement pour réponses générées admises, pas jugements humains. Pas de checkpoint LangGraph, de réécriture de corpus ni de conversations privées copiées. Une écriture en timeout peut aboutir : relister avant toute répétition. Pas d’idempotence distribuée ou sauvegarde/restauration déjà certifiée.

## Packaging RELEASE

Les règles métier, corpus, classements, prompts et budgets sont conservés. Adaptations : namespace de collection neuf dans les validateurs, contrats BGE rendus autonomes à partir du seul corpus distribué, encodeur/store déplacés, stub explicite du chargeur legacyV1dont les archives sont exclues, chemins Docker/tests/cache et commandes de cycle de vie réécrits pour le nouveau projet. Aucun lien privé nécessaire ; aucune image/base historique utilisée. Les tests des nouveaux garde-fous et la recette restante figurent dans [VALIDATION](VALIDATION.md).
