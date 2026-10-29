# MongoDB optionnel — nouvelles séances, nouveau volume

Mongo stocke les séances, Milvus les vecteurs documentaires. Le socle ne dépend pas de Mongo. Valeur par défaut MONGO_ENABLED=false ; aucun appel DB au chargement de la page. Aucun contenu d’une installation antérieure n’est copié dans RELEASE.

## Première installation seulement

Après setup et le premier build applicatif, sous autorisation d’initialisation d’une base neuve :

```sh
python3 scripts/mongo-config.py
# Éditer privément .env : MONGO_ENABLED=true ; ne rien imprimer.
./scripts/p13 mongo-start
./scripts/p13 doctor
```

Le configurateur refuse un volume existant ou des paramètres déjà définis, génère deux secrets64hex distincts et les ajoute au fichier privé sans affichage. Il ne change pas les credentials d’une base existante. Ne pas l’exécuter pour une rotation/réparation. Pas de clé en ligne de commande/chat/Git/log.

Mongo7.0 épinglé par digest, volume **p13-release_sessions-data**, réseau interne au projet, pas de port27017 publié. Compte applicatif p13_sessions/readWrite sur base p13_sessions ; bootstrap admin séparé jamais injecté au backend. Le script d’initialisation officiel ne crée l’utilisateur que sur volume neuf. Le healthcheck authentifie le compte applicatif, sans sortir le mot de passe.

Si mot de passe invalide, restaurer la configuration privée correspondante, ne pas vider le volume. Une valeur de configuration présente ou status configured_not_probed n’est pas une preuve d’authentification ; la lecture et la nouvelle écriture doivent être constatées.

## Parcours de séance

Dans **Mes séances locales**, sélectionner explicitement une ouverture, puis **Sauvegarder la séance**. Position/historique validés ; option réponse seulement si reçu serveur admis pour cette position/famille. Les fixtures/erreurs/sorties rejetées n’ont pas de reçu réel. La validité applicative n’est pas une validation experte humaine.

Afficher les séances, relever UUID/date, **Consulter**, puis **Reprendre en Étudier / Simulation**. Reprise UI : GET détail puis validation /game/state, sans nouveau conseil/API/vidéo. Une sauvegarde suivante crée un nouvel instantané, pas une mise à jour de l’archive. Pagination UUID lexicale, pas tri par date promis.

**Supprimer** est une action explicite et acquittée ; tester uniquement une nouvelle séance de recette dans cette instance après accord opérateur. Ce n’est pas une garantie d’effacement forensique des backups/journaux. En timeout de sauvegarde, relister avant toute répétition : une écriture déjà envoyée peut aboutir malgré l’absence de réponse.

Reçu HMAC15min et clé éphémère backend ; redémarrage invalide les reçus non sauvegardés, pas les archives. Pas de prompt, clé, corpus intégral, vecteur ou vidéo dans les séances ; pas de sauvegarde automatique ni de conversation multi-tour persistante. Pas de chiffrement au repos, TTL, sauvegarde ou restauration certifiés. Usage local mono-opérateur, aucune donnée personnelle nécessaire.

## Recette de persistance à réaliser

Créer une nouvelle séance-test, confirmer201et relire le même UUID. Après accord, recréer seulement les conteneurs de cette installation en gardant leurs volumes, puis retrouver la séance et la position. Documenter séparément la restauration depuis backup, qui n’est pas couverte par ce cas. **Ces essais Mongo RELEASE n’ont pas été exécutés dans Codex** ; aucun redémarrage de la base de développement ne les remplace.
