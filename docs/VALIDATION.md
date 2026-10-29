# Tests et reproductibilité

29 octobre 2026. Résultats de ce packaging, distincts des comptes historiques. Les dépendances déjà présentes ont été utilisées en lecture seule ; aucun venv, node_modules ou image privée n’est livré. Aucun modèle ni API métier exécuté.

## Contrôles réellement exécutés

| Contrôle | Résultat | Nature et portée |
|---|---|---|
| Backend maintenu, avant nouveaux cas de packaging |892 réussis | Sources du candidat, ASGI et doubles, corpus local authentique ; zéro réseau/processus/écriture source/lecture de données historiques interdite |
| Backend complet final du candidat | **916 réussis /0 échec**,55,04s | Inclut les nouveaux garde-fous RELEASE et scénario par défaut sans clé ; [synthèse](../validation/tests.json) |
| Frontend |169 réussis/0 échec | Tous les tests maintenus, collection cible mise à jour, jsdom et transports synthétiques |
| Navigateur Chromium local | **PASS**,1scénario1920×1080 | Véritable frontend compilé et backend local stérile : e4c5, ouverture B20,3 passages BM25, restitution déterministe ;11 réponses APIlocales,0fournisseur/modèle/base |
| Build frontend | PASS | TypeScript et Vite, sortie temporaire hors sources, aucun fournisseur ; bundleJS≈1,11 Mo avant gzip, avertissement>500 Ko conservé |
| Compose |6 variantesPASS | Socle /Milvus /Mongo /BGE+Milvus /local /ensemble ; variables fictives, aucun .envréel lu, aucun conteneur lancé |
| Exports LangGraph | **PASS**,6exports | Parent compilé+4enfants, xray/graphes identiques aux sources Mermaid, aucun service exécuté ; [preuve](../validation/graphs.json) |
| Pins backend |49/49versions correspondantes | Contrôle des métadonnées installées utilisées pour les tests, pas téléchargement/build neuf |
| Syntaxe/liens/corpus/sécurité/Git | [auditlocal](../validation/audit.json) | Contrôles des seules sources sélectionnées ; aucune garantie de sécurité universelle |

Ces résultats concernent uniquement les suites distribuées. Quatre modules dépendant d’archivesV1/E5, d’anciens outils de cycle de vie ou d’une application de démonstration interne ont été exclus. Les autres validations de légalité, synchronisation, budgets, citations, erreurs, graphes et non-invocations sont conservées. Les24questionsdev ne sont pas redistribuées : seuls des cas unitaires synthétiques distincts subsistent.

Premier passage backend :891 réussis/1 échec parce qu’un replay attendait une capture historique volontairement exclue. Le cas a été remplacé par une fixture unitaire synthétique annoncée ; aucun résultat fournisseur réel n’a été fabriqué. La suite maintenue est ensuite passée à892/892. Le nouveau cas d’intégration par défaut a confirmé le refus de l’origine fictive TestClient ; son client a été corrigé en loopback, sans assouplir la garde de production. La suite complète finale est passée à916/916. Les 24 nouveaux tests couvrent collectionvide/incompatible/étrangère/partielle/concurrente, refus sans approbation, vecteurs/identités, non-écriture en rerun, cachehashconflit/symlink, façades non destructives, volumes étrangers, configurationMongoetparcourslimité.

## Reproduire sans services réels

Depuis un venvPython3.12 préparé par le lecteur avec backend/requirements-dev.txt :

```sh
python scripts/test-backend.py
python3 scripts/audit-release.py
# Depuis frontend/ avec npm ci effectué dans cette installation :
npm test
npm run build
```

Le lanceur backend retire les variables héritées avant import et bloque socket.connect/subprocess.Popen réels pendant pytest. Logs de test sous work/validation, ignorés par Git. Les tests emploient des clés/embeddings/clients factices explicitement synthétiques. Un flag de preuve posé dans un double vérifie le contrat de validation, pas une inférence physique.

Les tests frontend ont été exécutés avec `--configLoader runner` et un cache de vérification externe pour préserver les dépendances empruntées ; le code et les locks restent dans le candidat. Le lien temporaire a été retiré. Le lecteur doit faire npm ci dans son propre clone ; aucun chemin du poste d’audit n’est requis.

Pour vérifier le schéma Compose sans valeur privée : utiliser `--env-file /dev/null`, des placeholders Mongo64hex distincts et des cheminsGGUFfictifs, puis config. **Ne pas imprimer config résolu avec un vrai .env.** Les6 variantes ont été comparées pour confirmer nomsproject-scoped, aucun volumeexternal et aucun port des bases/modèles.

## Non exécuté — à ne pas annoncer comme réussi

- Build Docker backend/frontend/BGE dans un clone vierge ; installation effective des locks sur nouvelle machine.
- Acquisition des48 artefacts et sixfichiersBGE, chargement CPU,96embeddings réels, création/indexation/requête Milvus RELEASE.
- MongoDB neuf : bootstrap/authentication, CRUD/résumés/reprise, persistance après recréation/restauration.
- Qwen réel, appels Mistral/Groq/YouTube/Lichess et calcul Stockfish physique du candidat.
- Chromium dans une installation Docker vierge, services réels et tous les modes ; le scénario navigateur local limité exécuté dans Codex ne les remplace pas.
- Performance matérielle/latence≤15s, démonstration chronométrée≤10min, qualité experte humaine et déploiementVPSsécurisé.

L’espace libre≈260 Mio dans Codex est insuffisant pour la pile lourde ; aucun nettoyage ou téléchargement n’a été tenté pour en masquer la limite. Les preuves physiques d’une autre installation ne valent pas recette du clone neuf.

## Recette vierge proposée, à consigner par l’opérateur

| Étape | Critère observable | Résultat effectif |
|---|---|---|
| Socle neuf | Build app, health200, Simulationjouable et aucun fournisseur | Non exécuté |
| Quatrebranches | Headers/provenance des4 parcours, erreurs sans action annexe | Testés avec doubles, physiqueàconsigner |
| Corpus/BM25 | Hash96 unités, questionSicilienne sourcée et horsscopeabstention | Code/corpus testé, recette UIneuveàconsigner |
| Milvus/BGE | Nouvelle instance/volume, schéma1024FLAT/IP,96 identités+hashvecteurs, vraie requête | Non exécuté |
| Mongo | Nouvelle base authentifiée, séance-test sauvée/lue/reprise et persistance | Non exécuté |
| Réel | Budgets autorisés, provenances et usages réels, erreurs/quotas transparents | Non exécuté |
| Relecture | Licence, attributs, qualitéhumaine, docs sans lienprivé, contenu du commit | Revue requise |

Conserver codes/compteurs/versions/timings sans contenu privé. Aucun retry caché. Après recette/revue, documenter les observations effectives et les limites restantes avant publication éventuelle de ces preuves.


## Finalisation publique du 29 octobre 2026

La licence et la documentation sont finalisées ; le scanner vérifie désormais GPL-3.0-or-later. Code applicatif, tests, corpus, locks et capture sont inchangés par rapport aux validations ci-dessus. Les 916 tests backend, 169 frontend, build et Chromium sont des résultats antérieurs sur ces mêmes sources applicatives, **pas des suites relancées pendant la finalisation**. Les contrôles statiques, l’intégrité des fichiers et les six configurations Compose ont été répétés. Voir [preuve de finalisation](../validation/publication.json). Aucun test physique supplémentaire ni fournisseur réel n’est revendiqué.
