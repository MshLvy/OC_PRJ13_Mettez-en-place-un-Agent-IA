# Installation neuve et frontières de reproductibilité

Les scripts visent un Docker **local**, projet fixé p13-release, sans dépendance à un dépôt privé ni à une installation préexistante. Ils utilisent le socket local, ne sélectionnent pas un daemon distant. Sur un autre OS/daemon, adapter explicitement après revue plutôt que rediriger silencieusement les opérations.

## Matériel et prérequis

Linux amd64/Python3.12 pour l’outillage BGE épinglé ; Docker avec BuildKit/Compose≥2.24.4 et Git. Le frontend utilise Node22.14.0 dans son image ; les locks backend/frontend fixent les versions des paquets. Sur ARM, le bundleBGE n’est pas compatible : produire un lock adapté et le revalider, pas substituer des roues.

Réseau pour builds publics ; pas de clé pour le mode limité. BGE :6 fichiers totalisant2 293 315 084 octets, au moins12 Gio disponibles avant acquisition ; dépendances BGE48 artefacts plafonnés1,2 Go et disque3 Gio minimum. Les images/build caches et données ont des besoins supplémentaires. RAM16 Gio ou plus recommandée pour le profil BGE+Milvus, à mesurer selon hôte/WSL2 ; Qwen et OS consomment une marge distincte. Aucun chiffre de RSS ou débit d’une installation neuve n’est mesuré ici.

Utiliser une machine dédiée si le POC de développement est actif : ports5173/8001 et sous-réseau172.30.73.0/29 ne doivent pas entrer en conflit. Aucun script n’arrête un service étranger. Tous les volumes/réseaux RELEASE sont propres au projet ; **aucun external:true ni nom de volume historique**.

## Socle sans secrets

Depuis la racine du dépôt cloné :

```sh
./scripts/p13 setup
./scripts/p13 start
./scripts/p13 doctor
./scripts/p13 smoke
```

setup : création exclusive `.env` depuis `.env.example`, permissions600 ; ne pas relancer sur une configuration existante. start : build app puis démarrage frontend/backend. doctor : état de ce projet, pas connexion fournisseur/base. smoke : healthcheck puis historique vide revalidé et header du graphe ; aucun moteur, génération, vidéo, embedding ou écriture DB.

Navigateur5173, backend hôte8001/interne8000 ; aucun alias8000hôte. Le proxy frontend rejoint backend par DNS interne. Les protections d’origine restent celles du code validé. Démarrage Real non nécessaire pour le contrôle initial.

En cas d’occupation de port, image manquante ou TLS : arrêter la procédure, ne pas nettoyer. Sur un réseau d’entreprise, fournir la CA de build via les secrets BuildKit déjà prévus pip_ca/npm_ca ; ne pas désactiver TLS. La CA n’est pas une clé fournisseur et ne doit pas être copiée dans l’image. Aucun contournement de proxy/réseau n’est recommandé.

## Configuration privée persistante

Un seul `.env` local ignoré par Git ; exemples publics sans valeurs. Compose transmet explicitement les variables utiles au backend, jamais tout le fichier au frontend. Ne pas publier `compose config` résolu, Config.Env, HAR ou contenu de fichier privé. Ne pas mettre les clés dans une URL, une commande ou un GGUF.

Les overlays activent les services, les variables activent leurs politiques ; une variable seule ne crée ni modèle, ni collection, ni base. Après édition privée des paramètres API : `./scripts/p13 reload-api` (backend seulement, sans build). Cette commande conserve les overlays des auxiliaires actifs. Les reçus non sauvegardés expirent au redémarrage du backend ; les archives déjà sauvegardées restent des données Mongo.

## Actifs optionnels, à installer séparément

1. [Milvus neuf](BGE_MILVUS.md) ; aucune collection historique attendue. Inspection puis acquisition vérifiée et indexation explicitement approuvée dans la nouvelle instance seulement.
2. [Mongo neuf](MONGODB.md) ; deux mots de passe distincts, bootstrap initial et volume dédié. Ne jamais régénérer des credentials pour « réparer » une base existante.
3. [Qwen et APIs](FOURNISSEURS.md), avec autorisation/quota distincts. Aucun téléchargement de modèle au démarrage des conteneurs.

BGE et Mongo n’empêchent pas le socle de fonctionner : panne dense⇒repli BM25 annoncé ; Mongo absent⇒sauvegarde indisponible ; APILLMabsente⇒erreur en Réel, restitution déterministe en Simulation sans Qwen. Les vidéos restent disabled tant que configurées ainsi.

## Développement natif et tests

Docker reste la cible de recette. Pour développer sans installer un second jeu de services : créer son venv local, installer `backend/requirements-dev.txt` (versions exactes), exécuter les tests via `python scripts/test-backend.py`. Avec npm/node compatibles, `npm ci` depuis frontend puis npm test/build.

Un frontend natif utilise5174et un backend8002 ; si le mode démo/origines est utilisé, le proxy conserve l’origine locale attendue5173 et le contrat d’origine doit être compris. Ce n’est pas un moyen de contourner l’isolation réseau des services Docker ; ne pas publier les ports Milvus/Mongo pour du développement. Les tests n’exigent aucun de ces services.

## Statut de validation

Le code est testé depuis le candidat isolé avec dépendances déjà présentes. Les six compositions sont parsées sans secrets réels. **Aucun build Docker neuf, acquisitionBGE, démarrage de bases ou indexation physique RELEASE n’a été effectué dans Codex**, où≈260 Mio libres ne permettent pas les téléchargements requis. La recette ci-dessus est documentée et contrôlée statiquement, pas annoncée réussie. Voir [validation et critères de recette](VALIDATION.md).


Exemple de préparation des tests sur un clone neuf, sans réutiliser un environnement privé :

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
python scripts/test-backend.py
cd frontend
npm ci
npm test
npm run build
```

Ces installations n’ont pas été effectuées dans Codex pour le candidat ; les pins ont été comparés à l’environnement déjà disponible. Aucun test ne nécessite de clé, poids ou base. Pour un test dans l’image backend, le target `test` emploie le même lanceur offline et des fichiers publics uniquement ; son build/exécution Docker restent à effectuer physiquement.
