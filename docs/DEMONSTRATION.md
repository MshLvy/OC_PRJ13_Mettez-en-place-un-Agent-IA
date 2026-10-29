# Démonstration reproductible — Sicilienne

## Sans clé et sans fournisseur

Démarrer le socle selon [installation](INSTALLATION.md), rester **Simulation**. Le dossier ne fournit pas de réponse LLM ou score physique préenregistré comme résultat du jour.

1. **Votre activité** : **Étudier une ouverture**. Le mode **Jouer contre l’ordinateur** est disponible pour un autre essai synthétique légal, borné à24 demi-coups.
2. Cliquer e2 puis e4, attendre validation ; c7 puis c5. Le panneau **Ouverture actuelle** reconnaît la famille Sicilienne depuis l’historique. Une variante inconnue reste inconnue.
3. **Conseiller pédagogique** : **Conseiller ma position actuelle**, question « Pourquoi le pion c5 contrôle d4 dans la Sicilienne ? », bouton **Chercher des sources et demander un conseil**.
4. Lire les passages authentiques du corpus local et leurs attributions. Sans BGE : offline_bm25_v3 ; sans Qwen : restitution documentaire déterministe déclarée. Un score/compte simulé ne devient pas une consultation réelle.
5. Vidéos disabled et séances indisponibles sont des résultats prévus sans installation optionnelle ; ne pas les présenter comme un défaut masqué par fixtures.

| Étape | UCI | FEN complète attendue |
|---|---|---|
| Initiale | `[]` | `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` |
| Après1.e4 | `["e2e4"]` | `rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1` |
| Après1.e4 c5 | `["e2e4","c7c5"]` | `rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2` |

Intention position, thème vidéo optionnel central_control. La FEN sérialise l’en passant selon fen, même sans capture légale disponible. FEN≠simple disposition ; snapshot anti-réponse périmée≠identité d’utilisateur.

## Parcours réel optionnel, après recette et budget opérateur

Sur la nouvelle installation, activer/configurer Lichess/Stockfish, BGE/Milvus, APIgénérative, YouTube et Mongo séparément. Accepter avant la bascule Réel les appels d’analyse aux positions initiale/e4/e4c5 ; prévoir max1soumissionAPI et max1explorationYouTube/3recherches, coût/plafondLichess à fixer par opérateur. Pas d’appel de préparation supplémentaire non compté.

Sélectionner Réel **avant** les coups, confirmer le nouveau départ ; rejouer e4c5. Lire statistique live et version/score moteur de cette FEN, pas d’une ancienne réponse. Demander le conseil une fois ; confirmer dense ready/BGE_READ_ONLY_SEARCH_VERIFIED et provider/modèle réellement configuré. Groq peut être choisi selon le guide ; Mistral demeure défaut de code. Qwen n’est pas le générateur Réel.

Dans Vidéos, choisir Sicilienne puis **Contrôle du centre**, cliquer **Explorer les vidéos** une fois. Résultat0..3 vidéos distinctes ; source_modelive/syntheticfalse/test_transportfalse si authentique. Le thème choisi n’est pas une preuve issue du conseil LLM. Les vidéos ne sont pas visionnées par l’agent.

Dans Mes séances locales, choisir Sicilienne, inclure la réponse seulement si reçu valide, puis **Sauvegarder la séance**. Attendre201/confirmation, relever nouvel UUID/date. **Afficher les séances**, **Consulter**, **Reprendre en Étudier / Simulation** : position revalidée, archives annoncées, aucun nouveau fournisseur. Tester suppression seulement sur cette séance-test neuve avec accord distinct. Pas de champ « nom de séance ».

## Prouver les quatre branches sans falsifier la provenance

| Réponse | X-Workflow-Graph | Branche attendue dans X-Workflow-Path |
|---|---|---|
| analyse démo | p13_global_v1 | analysis.admit_action / execute_action / check_result |
| conversation | p13_global_v1 | rag.admit_action / execute_action / check_result |
| exploration vidéos | p13_global_v1 | videos.admit_action / execute_action / check_result |
| sauvegarde/liste séance | p13_global_v1 | sessions.admit_action / execute_action / check_result |

Chemin complet : root.route_action puis les3étapes préfixées de la branche, root.finish_action. Lire ResponseHeaders seulement, jamais copier clé, requête d’authentification, reçu ou HAR. Les headers prouvent le routage ; provenance métier distincte nécessaire pour affirmer source réelle. Les tests offline couvrent ces branches avec doubles ; aucun test physique neuf n’est revendiqué ici.

## Plan de repli

Lichess/moteur absent : montrer partial/unavailable, pas fixture en Réel. BGE absent : BM25annoncé ou vector-search503 ; aucune réingestion. APItronquée/invalide : sources conservées/refus, aucun nouvel appel caché ni passage Mistral↔Groq. Vidéoquota : arrêt, pas retry/reloadpourcontournement. Mongo timeout : relister avant de sauver de nouveau ; reçu absent : position seule si autorisée. Docker indisponible : présenter la documentation comme preuve documentaire, pas comme une exécution.

La recette intégrale et son chrono sont à réaliser sur l’installation RELEASE. Aucune durée de dix minutes ou génération<15s n’est certifiée par les tests de packaging.
