# Fournisseurs et générateurs — configuration privée, opt-in explicite

Aucun appel API métier ni acquisition de poids n’a été exécuté pour fabriquer le candidat. Les sélecteurs ci-dessous sont des paramètres publics ; leurs valeurs secrètes ne doivent jamais figurer dans Git, Angular, logs, URLs ou commandes.

## Simulation / Réel : responsabilités différentes

Simulation par défaut : coups et analyses simulés annoncés, ouverture reconnue localement, corpus/BM25 authentiques ; BGE peut être réel s’il est installé. Génération sur clic seulement : Qwen local si disponible, sinon extraits déterministes explicitement étiquetés. Cette restitution n’est pas une réponse LLM fictive.

Pour rendre Réel disponible, éditer privément les plafonds EXPLORER_MODE=live, STOCKFISH_ENABLED=true, DEMO_ALLOW_LIVE=true et GAME_ALLOW_TOOLS=true puis reload-api. EXPLORER_DEFAULT_MODE et ANALYSIS_DEFAULT_ENGINE restent des préférences par défaut, pas des permissions. Toute requête reste bornée par les plafonds serveur. Réel n’exige pas que toutes les sources soient disponibles : erreurs/partial annoncés, jamais fixture silencieuse. La bascule Réel réinitialise la partie et peut analyser la position initiale.

Lichess lit LICHESS_API_TOKEN en environnement backend ou le mécanisme fichier compatible en Python. Clé minimale obtenue par l’opérateur, jamais demandée dans un chat. Pas de retry automatique ; respecter limites et cache. Stockfish ne nécessite pas de jeton : binaire local dans l’image,1thread/hash16 Mo/profondeur≤20 et temps configuré≤1s. Une version/binary_present_not_probed ne prouve pas un calcul exécuté.

## Réel : Mistral par défaut ou Groq alternatif

Le code n’offre pas d’URL/API arbitraire depuis le navigateur. Modifier les quatre paramètres ensemble, dans le fichier privé, puis :

```sh
./scripts/p13 reload-api
```

| Paramètre | Mistral, défaut | Groq, alternative explicite |
|---|---|---|
| ADVISOR_API_PROVIDER | mistral | groq |
| ADVISOR_API_MODEL | mistral-small-latest | openai/gpt-oss-120b |
| ADVISOR_API_ENDPOINT | https://api.mistral.ai/v1/chat/completions | https://api.groq.com/openai/v1/chat/completions |
| ADVISOR_API_SECRET_ENV | MISTRAL_API_KEY | GROQ_API_KEY |
| Budget de sortie | MISTRAL_MAX_TOKENS=512 | GROQ_MAX_TOKENS=2048 |
| Effort spécifique | — | GROQ_REASONING_EFFORT=low |

Définir uniquement la clé réelle côté backend via mécanisme privé. Priorité budget spécifique>GENERATION_MAX_TOKENS hérité>défaut, dans bornes : local64–128, Mistral64–512, Groq64–2048. Aucun mode gratuit/crédit/quota n’est présumé. Fixer un max_calls et une enveloppe financière opérateur avant essai. Une soumission, pas de retry/fallback automatique entre API et Qwen.

API timeout15s par opération (config1–20), corps/prompt/sortie bornés, JSON/scope/citations et suites UCI validés. Les IDs existants ne garantissent pas la fidélité sémantique de chaque phrase. Une sortie tronquée/rejetée reste un refus avec les sources, sans appel réparateur. Conserver usage/modèle réellement renvoyés et temps mesurés ; ne jamais inventer coût ou réponse. Le modèle Mistral latest peut évoluer ; noter requested_model/actual_model.

Pour un autre fournisseur compatible, une simple URL privée ne suffit pas : adapter l’allowlist centralisée, authentification, modèle/format et tests. Changer un modèle du même fournisseur doit respecter les contraintes du validateur ; pas de compatibilité universelle promise.

## Qwen facultatif en Simulation

Image llama.cpp publique épinglée dans compose.local.yaml, pull_policynever. Acquérir explicitement cette image sur la machine d’installation, puis un GGUF sous licence et hash vérifiés **hors Git**. Référence documentée : Qwen2.5-1.5B-Instruct-GGUF, révision91cad51170dc346986eccefdc2dd33a9da36ead9, fichier qwen2.5-1.5b-instruct-q4_k_m.gguf, SHA2566a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e,1 117 320 736 octets, licence déclarée Apache2.0. Vérifier la provenance avant choix ; aucun fichier n’est acquis par start.

Configurer LOCAL_LLM_MODEL_DIR/FILE (répertoire absolu détenu par l’opérateur, bindRO), contexte2048et2threads, puis `./scripts/p13 local-start`. Pour un changement de fichier, recréer explicitement le seul service advisor-local avec l’overlay local ; ne pas reconstruire Milvus ou les embeddings. L’alias public suit le basename du GGUF ; conserver séparément le SHA opérateur des poids. Pas de secret API dans le serveur local.

Le prompt compact limite les sources/phrases et la sortie128 tokens ; les validations restent strictes. CPU2/RAM4 Gio, timeout45s et latence cible<15s **non certifiée**. Les premiers essais historiques avaient produit rejet/troncature : cela interdit d’annoncer une réussite ou un gain de latence sur ce candidat sans mesure physique.

## YouTube opt-in indépendant du mode global

YOUTUBE_MODE=disabled par défaut ; synthetic_fixture n’utilise ni clé ni lien réel. Pour live, activer YouTubeDataAPIv3, configurer une clé serveur restreinte et YOUTUBE_MODE=live puis reload-api. **Un clic vidéo peut consommer du quota même en Simulation.** Aucun appel au changement de position/mode ou à la génération d’un conseil.

L’UI utilise POST `/api/v1/videos/explore`, trois intentions contexte/historique/thème vérifiés, max3recherches et3 vidéos distinctes. Le GETcompatibilité `/api/v1/videos/{opening}` exige confirm_live=true en live et partage la garde : ne pas lancer GET+UI pour la même recette. Garde3 départs/60s,1en vol ; erreurs comptées, arrêt des intentions restantes en quota/auth/429, pas de contournement par reload/retry.

Clé en header backend vers l’endpoint approuvé, pas dans l’URL. Lien canonique seulement, pas de chargement automatique d’image/iframe/transcription. Le résultat peut être vide/partial ; un titre pertinent ne certifie ni qualité pédagogique, ni français, ni contenu adapté aux mineurs, ni droit d’extraire la vidéo. Fixer max_search_calls avec l’opérateur et regarder l’allocation actuelle du compte Google : aucun quota gratuit n’est garanti par ce guide.
