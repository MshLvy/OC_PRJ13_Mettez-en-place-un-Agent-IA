# Commandes opérateur et effets

Le projet est fixé p13-release et le daemon au socket local. Pas de sélection silencieuse d’un environnement d’un autre poste. Les noms de volumes ne sont jamais configurables vers une installation antérieure. Le contrôleur vérifie les labels de propriété des volumes RELEASE déjà présents.

| Commande | Effet | Précondition / limite |
|---|---|---|
| `./scripts/p13 setup` | Crée un nouveau .env privé sans clé | Refuse tout écrasement, ne pas exécuter si déjà configuré |
| `./scripts/p13 doctor` | État Compose du seul projet | Pas preuve de fournisseur, d’inférence ou de connexion DB réussie |
| `./scripts/p13 start` | Build et démarrage frontend/backend | Réseau de build public ; ports libres ou détenus par ce projet, pas de checkpoint acquis |
| `./scripts/p13 stop` | Stop frontend/backend seulement | Les bases et leurs volumes restent en place |
| `./scripts/p13 reload-api` | Recrée seulement backend sans build | Conserve overlays auxiliaires actifs ; invalide reçus non sauvegardés |
| `./scripts/p13 smoke` | Santé et game/state légal +header global | Pas de génération, vidéo, embedding, moteur ou écriture |
| `./scripts/p13 graph` | Export pur du parent/xray depuis le backend | Pas import app.main ou appel service |
| `./scripts/p13 milvus-start` | Initialise/démarre la nouvelle instance Milvus | Nouveau volume dédié ou volume RELEASE identifié, jamais base étrangère |
| `python3 scripts/mongo-config.py` | Génère deux nouveaux secrets privés sans affichage | Refuse si paramètres ou volume Mongo déjà présents |
| `./scripts/p13 mongo-start` | Initialise/démarre Mongo et rattache backend | Credentials privés cohérents, MONGO_ENABLED explicitementtrue |
| `./scripts/p13 bge-build` | Construit l’image autonome sur bundle vérifié | Les48 artefacts doivent avoir été acquis explicitement |
| `./scripts/p13 bge-index --approve-new-release-collection` | Vérifie puis indexe96 unités dans la seule nouvelle cible | Approbation d’écriture explicite +instance exclusive ; ne touche jamais autre collection |
| `./scripts/p13 bge-start` | Démarre workerRO, backend/frontend sans build | Indexation achevée, poids vérifiés présents |
| `./scripts/p13 local-start` | Démarre llama.cpp seulement | Image/GGUF acquis explicitement avant, pas de téléchargement au démarrage |

Pour arrêter un auxiliaire de **cette** installation après autorisation : utiliser Compose avec projet p13-release et le bon overlay, commande `stop nom-du-service`, jamais down-v/prune/suppression de volume. Exemple Mongo : `docker compose -p p13-release -f compose.yaml -f compose.mongodb.yaml stop mongodb`. Ne pas appliquer ces commandes à un daemon ou projet du POC validé pour « tester » la release.

## Diagnostic sans exposition de secrets

Ne pas imprimer `.env`, environnement complet, Config.Env, requêtes privées ou HAR. Conserver code d’erreur court, état/service/version, ID public de passage, statut et durée ; ne pas conserver question privée, prompt, réponse brute rejetée, reçu HMAC ou clé. Les logs de scripts BGE distinguent refus de permission, manque de fichier/dépendance, empreinte incorrecte, mémoire et conflit d’identité sans exposer chemin privé.

Milvus indisponible⇒pas de réingestion-réparation. Conflit de corpus/collection⇒arrêt et revue. Clé/API/quota⇒arrêt sans retry ni changement fournisseur automatique. Mongo timeout⇒relister avant une nouvelle soumission. Réponse tardive⇒ne pas la considérer valable pour une autre FEN.

## Maintenance raisonnable

Modifier les versions/locks via une révision testée, pas un pip/npm upgrade global avant démonstration. Mettre à jour la provenance d’un modèle exige nouveaux hashes et revue ; le nom du dossier ou du modèle ne suffit pas. Toute nouvelle version de corpus/index doit conserver attribution/revue humaine et utiliser un namespace distinct, sans effacement d’archive.

Sauvegardes, restauration, rotation de credentials, TLS/auth multi-utilisateur et déploiement Internet exigent leur propre procédure. Aucune restauration ou recette VPS n’a été exécutée pour ce candidat. Les images de base app utilisent des tags de version, non tous des digests : risque de dérive résiduel documenté, à résoudre avec une résolution/pinning de registres et une nouvelle recette avant usage durable.
