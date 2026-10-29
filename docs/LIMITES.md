# Limites non résolues et décision de recette

| Sujet | État honnête | Action avant d’annoncer une disponibilité |
|---|---|---|
| Clone/Docker vierge | Non exécuté ; sixconfig parsées et code testé | Construire images et exécuter recette sur nouvelle instance dédiée |
| Milvus/BGEneufs | Scripts/gardes testés avec vecteurs/SDKsynthétiques, pas physiques | Acquérir poids/dépendances vérifiés, inspecter puis autoriser indexation RELEASE, vérifier96 entités et recherche réelle |
| Mongo neuf | Config/guards/testsstoreavec doubles, pas DB/auth/volume neuf exécutés ici | Authentification, création/lecture/reprise/suppression d’une séance-test neuve et persistance à mesurer |
| Fournisseurs externes | Aucun appel réel dans la fabrication | Budgets/clefs privés/GO distincts, validation des provenances à chaque résultat |
| Qwen | Anciennes limites JSON/troncature et latence ; pas inférence de ce candidat | Essai physique du GGUF réellement choisi ; pas objectif<15sgaranti |
| Corpus et réponses |96 unités attribuées, revue humaine pending | Revue experte, qualité et abstention à évaluer sans jeux scellés |
| AncienretrieveV1/E5 | Contrats présents mais corpus/expériences exclus | Utiliser conversationV3/vector-search ; pas faux raccord ni données anciennes réintroduites |
| Échiquier | Alternative64boutons Angular, ngx absent | Justification à présenter au jury, pas conformité littérale inventée |
| Build/licences dépendances | Pins exacts/locknpm/BGEhashes ; pas auditCVEexhaustif | Revue de maintenance et résolution de digests des tags app/serveurs avant usage durable |
| Exposition publique | POC local, loopback et origine limitée, bases internes | Auth/TLS multi-utilisateur, DPO/retention/sauvegarde-restauration et isolation avant Internet |
| Sauvegarde et idempotence | Pas backup/restauration certifiés ni idempotence inter-requêtes | Relister après timeout ; procédure de sauvegarde/rotation à définir séparément |
| ArchitectureMCPvidéo | Étude et contrat proposés seulement | Droits+pilote+mesures, aucune collecte/extraction automatiquement autorisée |

Les preuves de fonctionnement obtenues auparavant sur un autre environnement ne sont pas des preuves de cette installation neuve. Les métriques de benchmark expérimentales et questions sont exclues ; aucune supériorité de BGE n’est déduite de sa taille. Les contraintes d’origine et le réseau ne sont pas une authentification Internet.

**Statut : POC local sous GPL-3.0-or-later, reproductibilité physique PARTIAL/non démontrée.** Les documents expliquent exactement les essais restant à exécuter ; le dépôt ne doit pas être présenté comme « clone et tout fonctionne » avant leur observation.
