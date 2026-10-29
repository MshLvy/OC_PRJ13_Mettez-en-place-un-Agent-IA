# Audit de la distribution source — sécurité, droits et dépendances

29 octobre 2026. **Contrôles de la distribution source avant publication autorisée.** Ce rapport représente les contrôles de la sélection finale, pas un journal d’expérimentations. Les traces d’exécution détaillées restent hors du contenu public.

## Périmètre et isolation

Sources sélectionnées depuis une révision documentaire figée, code applicatif antérieurement validé ; extraction fichier par fichier sans clone/fork/merge d’historique. Le dépôt source est resté en lecture seule, même branche/HEAD/arbre propre. L’export dispose d’un `.git` neuf main, sans alternates ni objets historiques importés. La destination publique a été vérifiée vide en lecture seule avant la création d’un unique commit racine.

Aucun fichier .env réel n’a été lu/modifié. Les seules valeurs de tests sont synthétiques. Les clés injectées dans l’environnement n’ont pas été consultées pour le packaging ; les suites backend vident l’environnement avant import applicatif. Aucun appel fournisseur, modèle acquis, connexion Milvus/Mongo, copie de volume, ingestion, redémarrage ou nettoyage de services.

Le disque disponible≈260 Mio empêchait les acquisitions/builds lourds ; aucune suppression de données ou de caches n’a été nécessaire. Les dépendances déjà disponibles ont servi aux tests sans être copiées dans le candidat. Un lien node_modules temporaire de vérification a été retiré ; caches et build ont été dirigés hors des sources.

## Sélection et adaptations nécessaires

Conserver runtime Angular/FastAPI/LangGraph, tests actuels, catalogue CC0, corpus96 unités CC-BY-SA4.0 et métadonnées modèle. Exclure corpusV1/V2/anciens brouillons, toutes questions/benchmarks, handoffs, rapports internes/journaux, clés/modèles/caches/images et données de séances. [Inventaire](INVENTAIRE_RELEASE.md).

Adaptations de packaging explicitement recensées :

- Collection BGE renommée **p13_openings_bge_1024_v1** dans client/validateurfrontend/worker/politique ; mêmes96textes, même checkpoint/pooling/normalisation/classement/prompts et budgets.
- Contrat documentaire du worker autonome depuis le seul corpus distribué ; nouvelle empreinte de politique/payload, aucun accès à une archive privée. Store/encodeur réutilisés ; marqueur de propriété adapté à RELEASE.
- Commandes et Compose ne ciblent que le projet p13-release, ses images construites publiquement, ses réseaux/volumes propres ; aucun external:true ni dépendance à une image locale privée.
- Chargeur legacyV1 remplacé par un refus explicite, ses données et outils de benchmark étant exclus. Les routes/DTOcompat restent déclarés mais indisponibles, pas transformés en fauxV3.
- Chemins de build/test/cache adaptés au packaging. Les cas unitaires auparavant liés à un benchmark/capture sont remplacés par des échantillons synthétiques explicitement nommés ; aucune question scellée utilisée.

Les13modules et données critiques du comportement courant sont octet-identiques à leur référence : [intégrité](../validation/integrity.json). Aucune correction métier, nouveau fournisseur, corpus généré ou changement du conseiller n’a été ajouté. Les modifications sont dans l’espace RELEASE seulement.

## Sécurité du contenu publiable

Le [contrôle local](../scripts/audit-release.py) parcourt uniquement les fichiers sélectionnés, exclut .envréel/poids/dépendances/caches, vérifie chemins/symlinks/tailles, motifs usuels de credentials, références privées et liens Markdown, syntaxe Python, hash/licence/revue des96 unités et Git indépendant. [Résultats](../validation/audit.json), [liste et empreintes](../validation/files.json).

Un scanner de motifs **ne prouve pas mathématiquement l’absence de tout secret** ; la sélection à partir de sources publiques autorisées et la revue humaine restent nécessaires. Les motifs servent de garde, pas de prétexte à copier un environnement complet. Aucune valeur détectée n’est imprimée ; le rapport donne chemin/ligne/type seulement. Les regex du scanner et les valeurs de tests explicitement synthétiques ne sont pas des credentials réels.

Aucune consultation du contenu des données Mongo, des volumes/collections historiques ou de secrets du poste physique. Capture UI du candidat inspectée visuellement : simulation annoncée et restitution documentaire déterministe, backend réellement exécuté en HTTP local, sans fournisseur ni modèle. La référence FFE relève du scénario pédagogique, pas d’une affiliation officielle ou d’une autorisation de logo.

## Dépendances et droits

49pins runtime backend correspondent aux versions installées utilisées pour les tests ; le locknpm contient150 paquets avec intégrités lorsqu’elles sont disponibles. BundleBGE48 artefacts fixé par SHA256, mais pas acquis dans cette exécution. Le modèle a sixfichiers avec révision/hash/tailles figés ; aucun poids n’est dans le candidat.

Les pins de versions backend ne constituent pas un lock de roues hashé complet ; certaines images app/Milvus/BusyBox ont un tag version plutôt qu’un digest. C’est une limite de durcissement, pas un build bit-à-bit certifié. Le futur build doit conserver TLS/notices et produire un inventaire des artefacts réellement acquis.

[Licence](LICENCES.md) : corpus CC-BY-SA4.0, catalogue CC0, notices conservées ; code original sous GPL-3.0-or-later, choix validé par l’auteur le 29 octobre 2026. python-chess GPL3/Stockfish GPL3etMongo SSPL demandent une vérification adaptée au mode de distribution. Pas de déclaration globale MIT, de permission Wikichess ou de droit d’extraction YouTube inventés. Pas d’auditCVEexhaustif ni de maintenance des versions réalisée sous ce packaging.

## Garde-fous d’installation

Volumes dédiés et contrôle de propriété, pas de remote daemon automatique. Indexation : approbation explicite, serveur2.5.26, pas de collection étrangère,96 identités, schéma/empreintes vérifiés, relecture avant insertion et une seule insertion. Aucun delete/drop/upsert/reset dans la façade ; cible complète conforme⇒vérification sans réencoder, partielle⇒refus. Le worker de requêtes est read-only et vérifie avant/après.

**Une fenêtre opérateur exclusive reste indispensable** : les comparaisons d’inventaire ne sont pas un verrou distribué universel contre tout écrivain concurrent. Les tests couvrent les changements simulés observables, pas une preuve de sérialisabilité d’une base réelle. Ne jamais « réparer » un conflit par suppression, reset ou rattachement à une ancienne collection.

## Décision de livraison

**Sources contrôlées ; publication autorisée par l’auteur sous GPL-3.0-or-later ; reproductibilité Docker vierge PARTIAL/non démontrée.** Aucune incompatibilité de licence bloquante identifiée pour ce périmètre source seul ; les obligations de distribution de futurs binaires/images restent distinctes. La recette sur nouvelle instance avec ressources suffisantes reste nécessaire. Voir [finalisation et publication](PUBLICATION.md).
