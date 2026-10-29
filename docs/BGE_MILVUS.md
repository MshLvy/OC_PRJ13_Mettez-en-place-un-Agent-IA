# Milvus neuf et BGE-M3 — procédure opérateur explicite

**Cette procédure n’a pas été exécutée physiquement pour RELEASE.** Aucun accès, copie ou réingestion des bases existantes n’a lieu lors de la fabrication du candidat.

## 1. Définir une nouvelle instance

```sh
./scripts/p13 milvus-start
./scripts/p13 doctor
```

Compose provisionne Milvus2.5.26 standalone avec etcd embarqué et stockage local. Volume **p13-release_milvus-data** et réseau interne propres à RELEASE. Le petit init BusyBox change seulement le propriétaire de la racine du nouveau volume ; pas de chown récursif ni effacement. Le contrôleur refuse un volume préexistant sans labels de propriété RELEASE. Aucun port19530/9091 n’est publié.

Ne pas relier ce service à une base d’un autre projet, ne pas remplacer les volumes par external:true. Le nom de collection **p13_openings_bge_1024_v1** n’est admis que dans cette instance. Une collection inconnue dans l’instance bloque le bootstrap plutôt qu’être ignorée/effacée. Le nom fixe garde les validateurs frontend/backend cohérents ; changer arbitrairement de cible n’est pas une configuration approuvée.

## 2. Acquérir des dépendances et poids vérifiés

Exécuter uniquement sur la machine de recette avec réseau et disque suffisants, jamais pour lancer les tests simulés :

```sh
python3 -m retrieval.acquire --kind dependencies --directory ./wheelhouse --approve-public-downloads
python3 -m retrieval.acquire --kind model --directory ./models/bge --approve-public-downloads
./scripts/p13 bge-build
```

Acquisition explicite publique, pas clé API. Linux amd64CPython3.12 ;48 artefacts épinglés avec SHA256, vérification de l’ensemble avant installation offline/no-deps/no-index/require-hashes et pip check. Les roues/archives ne sont pas dans Git. Les fichiers existants de même hash sont réutilisés ; un conflit ou `.part` préexistant bloque sans écrasement. Débit/temps/octets bornés, aucun retry automatique. Une panne conserve la trace partielle locale pour décision opérateur, pas de nettoyage global.

BGE : **BAAI/bge-m3**, révision immuable **5617a9f61b028005a4858fdac845db406aefb181**, licence déclarée MIT.6 fichiers/2,293 Go, hashes et tailles dans [model-files.json](../retrieval/model-files.json). Chargement local-only, CPUFP32, CLS/L2,1024D, seed0, batch1, thread1,512 tokens maximum sans troncature. Aucune variante quantifiée/sparse/multi-vector ou substitution silencieuse. [Politique complète](../retrieval/policy.json).

Le format historique pytorch_model.bin et les versions torch2.5.1+cpu/transformers4.44.2 sont conservés pour comparabilité ; ils ne sont pas une attestation d’absence de vulnérabilité. Poids uniquement de la révision/hash admis, aucune désérialisation d’un fichier choisi par le navigateur. Revue de maintenance/sécurité des versions requise avant usage public au-delà du POC.

L’image **p13-release-bge:local** est construite par son Dockerfile, pas récupérée d’un poste privé. Les poids sont montés RO dans le worker, pas incorporés dans l’image. Exécuter sous l’UID de leur propriétaire si le cache est privé ; BGE_UID/BGE_GID permettent l’identité non root. Aucun modèle local de développement ne doit être bindé implicitement.

## 3. Autoriser une seule indexation dans l’instance RELEASE

Après inspection de l’hôte, volumes, réseau et collections, sous une fenêtre opérateur exclusive :

```sh
./scripts/p13 bge-index --approve-new-release-collection
```

Cette option est une **approbation d’écriture à donner pour cette nouvelle installation** ; sa présence dans le guide n’autorise aucune opération sur l’ancienne instance. Sans le drapeau, aucun encodage/connexion d’indexation n’est lancé.

Le processus d’indexation impose1800sde temps mur,1700 sCPU,8 Gio d’espace d’adressage et8 Mio de sortie, en plus des cgroups Docker1 CPU/8 Gio. Ces plafonds sont testés avec doubles, pas une performance physique mesurée. Le bootstrap vérifie serveur2.5.26, absence de collections étrangères, corpus/hash/96 identités, métadonnées/licences ; encode96textes, recompare l’inventaire avant écriture puis crée le schéma1024D FLAT/IP et insère en une fois les96vecteurs. Aucun delete/drop/upsert/reset accessible. Si une collection complète existe déjà et est strictement conforme, il vérifie sans réencoder/réécrire. Si elle est partielle, non conforme ou modifiée concurremment, il refuse ; aucune réparation destructive automatique.

Ne pas supprimer/recréer une collection pour résoudre un conflit. Conserver les diagnostics courts et l’inventaire, demander une revue. Un résultat non confirmé n’est jamais annoncé comme ingestion réussie.

## 4. Rechercher en lecture seule

```sh
./scripts/p13 bge-start
./scripts/p13 doctor
```

Le worker advisor-bge charge le snapshot vérifié, contrôle96 identités et empreintes de vecteurs. Il n’expose que /health et /search internes, jamais d’ingestion HTTP. Le backend n’importe pas torch/PyMilvus. Un changement de collection pendant une requête est refusé. Aucun port hôte du worker/Milvus.

Dans Angular Simulation, e2e4/c7c5, question de la Sicilienne, bouton explicite de conseil. Attendu si prêts : hybrid_bm25_bge_v3, dense ready, BGE_READ_ONLY_SEARCH_VERIFIED ; pas de réussite dense annoncée en repli BM25. La génération locale reste indépendante ; absence de Qwen⇒extraits déterministes. Pour prouver uniquement la recherche vectorielle, POST `/vector-search` avec request_generation=false et même FEN/historique, sous autorisation de calcul read-only.

Relever réellement : version serveur, schéma,96 entités, identité modèle/corpus/collection, statut/requête dense, provenance, latence et ressources. Le hash du vecteur stocké ne prouve pas une nouvelle inférence indépendante. Les tests de ce candidat utilisent des vecteurs synthétiques et un SDKdouble, pas ces preuves physiques.
