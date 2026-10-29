# Étude MCP — recherche de position vidéo par FEN et timestamp

**29 octobre 2026 — version 1.0 pour revue. Source Markdown en dix sections correspondant aux dix pages de l’étude.**

---

## Page 1 — Retrouver une position dans une vidéo

Étude de faisabilité Model Context Protocol (MCP) • 29 octobre 2026 • version 1.0 pour revue. Destinataires : direction technique et encadrement pédagogique du scénario FFE. Cette note répond à l’étape 7 du brief : bénéfices, limites, architecture et coûts, sans développer le système de vision. Les dix pages incluent le schéma, le chiffrage et les références ; les annexes techniques restent dans le dépôt.

### Avis proposé, sans autorisation de construire

Go conditionnel pour un pilote de recherche par disposition sur vidéos 2D fournies sous droits ; No-Go pour une collecte automatique de vidéos YouTube quelconques ou une promesse de FEN complète issue d’une image. Commencer par les PGN et timestamps fournis par les créateurs lorsque disponibles. Un contrat MCP rend l’outil interopérable, mais ne résout ni les droits, ni la reconnaissance visuelle, ni la pertinence pédagogique.

Le besoin est précis : au lieu de recevoir une vidéo de 45 minutes sur une ouverture, l’apprenant souhaite retrouver les passages où son échiquier apparaît. Le résultat utile est un intervalle de lecture, sa provenance et son degré de correspondance. Une même position peut revenir dans plusieurs variantes ; l’affichage d’un diagramme ne prouve pas que le commentaire répond à la question de l’élève. La vidéo complète les preuves du conseiller, elle ne remplace ni Stockfish ni les sources RAG.

| Bénéfice attendu | Limite à rendre visible |
| --- | --- |
| Moins de temps à parcourir une longue vidéo | Gain à mesurer sur des tâches comparables, pas encore démontré |
| Réutiliser un catalogue pédagogique autorisé | Coût de droits, annotation et maintenance supérieur au seul stockage |
| Provenance position → passage → timestamp | Erreur de case, orientation ou montage peut produire un faux positif |
| Outil réutilisable via MCP | Authentification, contrats et versionnement restent nécessaires |

### Point de départ vérifiable

Le POC possède un échiquier validé, un conseiller BM25/BGE/Milvus et des générateurs Qwen/Groq/Mistral. J05/J07-I10 recherchent des métadonnées vidéo, pas des pixels ; le handoff I11 rapporte une validation YouTube physique sur L7560. Le rapport Mongo I11 reste PARTIAL pour serveur/auth/volume dans Codex. Les propositions J01/I05 ne sont pas des preuves d’intégration actuelle. Aucun de ces composants n’est modifié ici ; aucune vidéo, frame ou collection n’est acquise ou analysée.

Décision attendue : valider les droits et le périmètre 2D, réserver un budget expérimental plafonné, puis autoriser séparément un benchmark. La présente livraison n’accorde aucun GO d’implémentation, d’extraction ou d’appel API.

---

## Page 2 — Une image ne fournit pas une FEN complète

La FEN standard contient six champs : disposition des pièces, trait, droits au roque, case en passant, compteur de demi-coups et numéro de coup. Une image nette, orientée et non masquée peut renseigner le premier champ. Les cinq autres exigent des indices ou un historique fiables. La convention de sérialisation en passant doit être explicite ; le POC utilise notamment fen(en_passant="fen"). Une FEN ne contient pas non plus l’historique des répétitions [S04].

| Niveau de recherche | Condition et formulation du résultat |
| --- | --- |
| piece_placement_only | Égalité des 64 cases orientées ; trait/roques/en passant/compteurs peuvent être inconnus |
| rule_state | Champs 1 à 4 connus et cohérents ; compteurs non comparés, mode explicitement distinct |
| full_fen | Les six champs sont prouvés et égaux selon une convention commune ; sinon aucun résultat strict |

Deux états peuvent montrer exactement les mêmes pièces sur e1/a1/h1, avec ou sans droits de roque : un roi ou une tour peut avoir bougé puis être revenu. La case en passant dépend du dernier coup ; les compteurs ne se lisent pas sur les cases. Même une suite d’images ne suffit pas si la vidéo commence en milieu de partie, saute un coup, revient en arrière ou explore une variante. Remplir les inconnus avec w - - 0 1 fabriquerait des informations.

### Représentation partielle, jamais un faux état légal

Conserver board_fen avec orientation, confiance et origine ; turn, castling, ep_square et compteurs restent null quand inconnus, full_fen aussi. Un constructeur de bibliothèque créant une Board avec des valeurs par défaut ne constitue pas une preuve. PGN légal depuis une position initiale connue, ancrages temporels et continuité de segment vérifiée peuvent promouvoir un candidat ; une simple proximité visuelle ne le peut pas. Les branches, coupes et répétitions reçoivent des identifiants de segment distincts.

La clé exacte de disposition est calculée sur les cases a1–h8 normalisées, sans rendre équivalentes les rotations ou les couleurs. Une orientation ambiguë impose plusieurs hypothèses signalées ou une abstention. python-chess vérifie les états/coups lorsqu’ils sont connus ; une position syntaxiquement valide ne prouve ni sa trajectoire ni la vérité d’une explication. Ne jamais substituer la position détectée à celle de l’apprenant pour demander un coup moteur.

### Timestamp : un intervalle mesuré, pas une précision inventée

Indexer les horodatages de présentation (PTS) du média et les bornes des segments, pas seulement frame_index/FPS : le débit peut être variable. À un échantillon toutes les 2 secondes, une position très brève peut être manquée. Le lecteur YouTube démarre près d’une image clé et peut se décaler [S11]. Renvoyer un intervalle et une incertitude, proposer quelques secondes avant la position et vérifier l’alignement avec la version publiée. Aucun timestamp authentique n’a été produit dans cette étude.

---

## Page 3 — Détection et conversion image → position

| Approche | Intérêt | Limite / condition de choix |
| --- | --- | --- |
| OpenCV + repères / templates | Peu coûteux pour captures 2D contrôlées ; homographie pour redresser le plan [S05] | Contours sensibles aux overlays, zooms et décor ; homographie ≠ reconnaissance de pièces |
| Localisation + classifieur de 64 cases | 13 classes : vide et 12 pièces/couleurs ; confiance par case ; CNN léger possible | Jeu annoté autorisé, thèmes de pièces et orientations tenus hors entraînement pour tester le transfert |
| Détecteur d’objets type YOLO | Localise plusieurs plateaux/pièces et des occlusions | Annotation plus lourde ; association aux cases ; Ultralytics AGPL ou licence commerciale à examiner [S08] |
| fenify-3D / travaux spécialisés | Piste pour plateau physique et vue oblique ; code MIT [S06–S07] | Distribution et poids à auditer ; pas une brique vidéo prête ni preuve des droits de roque |
| Modèle multimodal hébergé / service tiers | Prototypage assisté ou revue de cas difficiles | Coût par image, confidentialité, hallucinations ; devis et contrat API requis, pas retenu en base |

Pipeline 2D proposé : localiser le plateau principal, vérifier ses quatre coins et l’orientation, redresser, découper 64 cases, classifier, puis agréger sur des images stables. Rejeter les animations de déplacement, curseurs masquants et scènes multi-plateaux ambiguës. Une largeur minimale de plateau de 320 pixels est un seuil de départ à tester, pas une garantie. Des changements de scène déclencheraient une nouvelle calibration, sous budget borné.

Le README fenify-3D annonce une « Full Accuracy » de 0,950 en validation et 0,852 sur un test d’une autre distribution ; il décrit encore des erreurs de cases [S06]. Ces chiffres d’auteur ne sont ni reproduits ici ni des taux de FEN complètes exactes. La licence MIT du code ne prouve pas les droits des poids, données crowdsourcées ou assets Unity mentionnés. Aucun checkpoint n’est téléchargé.

Une précision de 99 % par case donnerait seulement 0,99 puissance 64 ≈ 52,6 % de plateaux entièrement corrects si les erreurs étaient indépendantes. C’est une illustration mathématique, pas une mesure : les erreurs réelles sont corrélées. Mesurer l’échiquier entier, la couverture après abstention et les faux positifs ; ne pas extrapoler une métrique de pièces à un état réglementaire complet.

OpenCV récent est Apache-2.0 [S17]. FFmpeg est principalement LGPL, avec composants GPL optionnels et enjeux de codecs selon le build [S27]. AGPL permet des usages commerciaux sous obligations : ce n’est pas une interdiction commerciale. Versions, flags, modèles, fontes et licences des données doivent figurer dans le manifeste futur. Stockfish n’est pas un correcteur visuel universel : plusieurs plateaux plausibles peuvent être légaux.

---

## Page 4 — Architecture MCP proposée

[Architecture cible — source Mermaid, conception uniquement](ARCHITECTURE_MCP_VIDEO.mmd)

[Source Mermaid](ARCHITECTURE_MCP_VIDEO.mmd)

Schéma de conception, non déployé. Le schéma Mermaid éditable détaille le retrait et le PGN. Aucun export graphique supplémentaire n’est requis. Aucune migration de Mongo séances ou de Milvus n’est proposée sous cette mission.

La lecture est rapide : Angular conserve son snapshot, FastAPI valide la demande, son client MCP appelle un serveur d’outils de lecture. Le serveur vérifie droits et version, interroge un index exact dédié puis renvoie des candidats bornés. La garde FastAPI rejette un résultat obsolète ou un faux niveau de FEN. Le graphe historique ne gagne pas un outil autonome implicite : une future action vidéo explicite et un GO seraient requis.

L’ingestion se déroule hors de la requête de l’apprenant : fichiers originaux fournis sous droits, manifeste, worker de décodage isolé, vision, suivi temporel, revue et publication. Les originaux/dérivés ont un stockage privé séparé ; les métadonnées/index vidéo auraient un espace et un compte de service dédiés, pas la collection de séances ni les vecteurs textuels actuels. Un index B-tree/hash suffit au MVP ; aucun embedding ou Milvus supplémentaire n’est nécessaire pour l’égalité d’une disposition.

MCP standardise découverte et invocation d’outils entre host, client et serveur [S01–S03]. Il ne transporte pas magiquement la vidéo et ne choisit pas les algorithmes. stdio peut servir au pilote local ; Streamable HTTP exigerait identité, scopes et contrôle d’audience. Le décodeur n’est jamais exposé comme commande shell libre au LLM.

---

## Page 5 — Contrat d’outil, sûreté et exploitation

| Interface candidate MCP | Bornes et résultat |
| --- | --- |
| search_video_positions | query_fen validée ; match_mode explicite ; catalogue autorisé ; limit 1..3 ; snapshot et request_id |
| get_video_match | match_id opaque ; version et droits recontrôlés ; intervalle, provenance et niveau de correspondance |
| Ingestion / effacement | Plan de contrôle opérateur distinct ; jobs bornés avec identifiant et statut ; non exposés au client apprenant |

Une réponse contient status (ok/empty/partial/unavailable/ambiguous), match_kind, observation partielle, full_fen nullable, segment/asset/version, modèle et hash, intervalle PTS, incertitude temporelle, état des droits et motif d’abstention. Le score visuel ne devient pas une probabilité de vérité pédagogique. Les correspondances répétées d’une même vidéo sont regroupées sans perdre les segments ; le tri est stable et son critère déclaré.

Les schémas d’entrée et structuredContent de MCP [S02] permettent une validation explicite. Dans le MVP, tout résultat strict full_fen contenant un champ inconnu est rejeté, pas transformé en résultat approximatif silencieux. L’utilisateur peut choisir séparément le mode disposition et lire sa limite. Un état vide n’est pas une panne ; un média supprimé ou dont les droits ont expiré ne doit plus être proposé, même si un ancien index le référence.

### Frontière de confiance

Host et client MCP restent côté backend. Identités de service, allowlist des outils/serveurs et scopes de lecture ; pour HTTP, appliquer l’autorisation spécifiée et vérifier l’audience, sans transmettre les tokens des fournisseurs comme des tokens MCP. readOnlyHint est un indice, pas une permission. Aucune clé vidéo ou LLM dans Angular. Résultats, titres et éventuel OCR sont des données non fiables : ils ne doivent ni modifier le prompt système ni lancer une autre extraction.

L’opérateur sélectionne des asset_id déjà admis, jamais une URL arbitraire à télécharger depuis un outil apprenant. Le worker refuse les chemins sortant du stockage admis, les URLs réseau internes ou de métadonnées cloud (risque SSRF) et les médias démesurés. Le type réel est vérifié ; décodage sans privilèges, ressources et durée plafonnées, image/version auditée. Plafond initial proposé : une vidéo de 60 minutes, deux jobs CPU, quotas de frames et arrêt explicite ; aucune valeur n’est une performance observée.

### Retrait et supervision

Le manifeste trace licence/preuve, finalité, dates, hash, paramètres de sampling, transformations, modèle et révision d’index. Un retrait bloque immédiatement les nouvelles réponses puis purge index et dérivés selon une politique auditée, y compris les copies et sauvegardes. Conserver uniquement des compteurs, durées et codes d’erreur, pas les frames/positions privées dans les logs. Prévoir tests d’expiration, d’arrêt de worker et de reprise idempotente. Pas de transaction distribuée ou de résilience déjà démontrée ici.

---

## Page 6 — Droits et traitement des médias

Les politiques YouTube interdisent au client API le téléchargement, import, cache ou stockage de contenu audiovisuel sans autorisation écrite préalable de YouTube [S09]. Une clé Data API, une vidéo publiquement visible, la mention pédagogique ou l’autorisation de son auteur ne suffisent pas à lever toutes les obligations de plateforme. Le lecteur autorisé n’offre pas un droit d’extraire ses pixels ; pas de capture de lecteur ou d’outil de téléchargement pour contourner ces règles.

| Scénario | Position recommandée |
| --- | --- |
| Fichiers originaux fournis par FFE/créateur | Autorisation écrite : analyse, dérivés, stockage, indexation, finalité, durée et territoire ; vérifier tous les éléments inclus |
| YouTube utilisé pour métadonnées et lecture | Liens/lecteur officiels et quotas ; pas de fichier audiovisuel récupéré ; gestion des API Data par catégorie |
| Copie publique ou licence CC trouvée en ligne | Vérifier auteur et chaîne de droits, conditions de plateforme, attribution/SA/usage commercial ; pas de permission présumée |
| Recherche/exception de fouille de textes et données | Analyse juridique préalable ; accès licite, finalité, réservation de droits et droit national ; ne pas en faire un passe-droit MVP |

En France, CPI L122-4 encadre reproduction/adaptation/représentation sans consentement [S23]. La fouille dans la directive DSM, articles 3 et 4, doit être qualifiée par un juriste : le texte EUR-Lex a renvoyé une réponse 202 non exploitable lors de la consultation [S15/S26]. Cette étude ne certifie pas le bénéfice d’une exception. La position échiquéenne factuelle n’accorde aucun droit sur son support filmé, les commentaires, musique, graphismes ou données de tiers.

Distinguer droits sur fichiers propriétaires et règles sur les métadonnées obtenues par API. Les obligations de rafraîchissement/suppression à 30 jours dépendent des catégories d’API Data et de leur autorisation [S09] ; ne pas appliquer aveuglément une durée unique à tous les originaux licenciés. Proposition conservatrice : revalider les métadonnées exposées au plus tous les 30 jours et traiter rapidement retrait ou vidéo indisponible, sous quota autorisé. Les IDs fournis permettent videos.list par lot, pas nécessairement une nouvelle search.list [S30].

Voix, visages et identifiants de participants peuvent être des données personnelles. Définir finalité et base légale, minimiser, limiter la conservation et permettre les droits ; consulter le DPO pour sous-traitance, transferts et éventuelle AIPD [S24]. Le pilote devrait privilégier plateaux 2D sans mineurs ni audio nécessaire. Si des enfants sont concernés, information adaptée et règles de consentement spécifiques si cette base est retenue ; ne pas confondre absence de reconnaissance faciale et absence de RGPD [S20].

Livrables juridiques avant collecte : registre des actifs et preuves, convention créateur, validation licences des assets/poids, analyse plateforme, politique de retrait et conservation, localisation/sous-traitants, décision DPO/juriste. Un dossier incomplet conduit à No-Go ou à l’alternative PGN/timestamps manuels, jamais à une extraction improvisée.

---

## Page 7 — Protocole d’évaluation et décision

Créer un nouveau corpus expérimental autorisé, séparé des données V1/V2/V3 et de leurs questions réservées. Proposition : 20 vidéos 2D, 6 de développement, 4 de calibration et 10 de test tenues hors réglage. Annoter 25 positions par vidéo dev/calibration et 50 par vidéo test, soit 750 occurrences. Conserver les intervalles PTS et les champs FEN réellement prouvés ; les inconnus ne deviennent pas des labels négatifs.

Séparer par vidéo/auteur/style, pas par frames adjacentes. Deux occurrences d’une même position peuvent compter pour la couverture temporelle, mais ne créent pas deux preuves indépendantes de généralisation. Double lecture d’un sous-échantillon et arbitrage d’un encadrant ; annotation assistée non équivalente à une vérité experte. Les mesures du README fenify ne remplacent pas cette évaluation.

| Porte Go / No-Go candidate | Mesure / refus |
| --- | --- |
| Droits et traçabilité — impératif | 100 % des actifs admis avec preuve et retrait testé ; sinon pas d’ingestion |
| Vérité FEN — impératif | Zéro full_fen émis avec un champ inconnu ; replay PGN prouvé pour les états complets |
| Précision disposition après abstention | ≥99 % ponctuel et borne basse Wilson 95 % ≥98 %, au moins 300 acceptations sur 10 vidéos test |
| Couverture utile | ≥60 % des 500 occurrences test stables ; publier aussi erreurs et abstentions par thème/qualité |
| Repérage temporel | Erreur absolue p95 ≤5 s, médiane ≤2 s, comparée à l’annotation ; vérifier le lecteur réellement utilisé |
| Service et sûreté | Lecture index p95 ≤2 s au volume cible ; droits expirés, injection, panne et ancien snapshot refusés |
| Valeur pédagogique | Essai accompagné : viser −30 % de temps médian de recherche vs vidéo textuelle, pertinence revue séparément |

Ces seuils sont une proposition de décision à ratifier, non une validation existante. Avec seulement 100 succès sans erreur, la précision n’est pas démontrée à 99 % ; les observations d’un même auteur sont corrélées. Publier dénominateurs, cas non jugés et intervalles, puis une analyse par vidéo ; Wilson seul n’efface pas l’effet de grappe. Si moins de 300 résultats sont admis, élargir l’évaluation autorisée ou déclarer preuve insuffisante, sans modifier le seuil sur le test.

Prévoir captures floues, plateau tourné, thèmes inédits, deux échiquiers, promotions, retour de variante, champs cachés et séquences rapides manquées. Évaluer la pertinence du commentaire séparément de la justesse des cases. Le test utilisateur pourrait commencer avec 12 adultes apprenants et 2 encadrants pour éviter une collecte de mineurs non préparée ; il ne représenterait pas encore les jeunes espoirs. Un échec dur déclenche No-Go du périmètre concerné ou bascule explicite vers annotation manuelle. Go économique seulement après acceptation des devis, droits et enveloppes build/opex ; aucun budget n’est autorisé par cette note.

---

## Page 8 — Investissement de construction

Le chiffrage vise un MVP 2D sur 20 vidéos autorisées, pas une reconnaissance 3D universelle. Hypothèses de planification H-BUILD du 29/10/2026 : journée de 7 h, ingénierie 600 €/j, annotation/revue 350 €/j, conseil juridique 900 €/j. Ce ne sont ni des tarifs observés pour le compte ni un devis ; le baromètre général Malt consulté [S21] ne valide pas ces trois montants. Demander deux devis et confirmer la disponibilité des droits avant engagement.

| Lot ingénierie | Jours |
| --- | --- |
| Cadrage et exigences/droits | 2 |
| Corpus et outillage annotation | 3 |
| Vision 2D limitée | 6 |
| Séquences et index exact | 4 |
| MCP et sécurité | 3 |
| Interface et contexte | 2 |
| Tests et exploitation | 4 |
| Total ingénierie | 24 |

| Charge / aléa | Budget central HT |
| --- | --- |
| 24 j ingénierie × 600 € | 14 400,00 € |
| 5 j annotation/revue × 350 € | 1 750,00 € |
| 2 j juridique × 900 € | 1 800,00 € |
| Sous-total | 17 950,00 € |
| Réserve explicite 25 % | 4 487,50 € |
| Enveloppe centrale | 22 437,50 € |

Sensibilité de charge avec les mêmes taux et réserve : 18/3/1 jours (ingénierie/revue/juridique) → 15 937,50 € ; 32/8/3 jours → 30 875,00 €. Ce ne sont pas des intervalles statistiques. La réserve finance les inconnus techniques, pas une autorisation illimitée. Les honoraires de revue ne constituent pas le prix des licences audiovisuelles ; les redevances R_build restent à négocier et s’ajoutent au total.

Charge centrale : 31 journées-personnes réparties sur les rôles, dont 24 pour un ingénieur. Envisager 6–8 semaines calendaires avec revue en parallèle, après disponibilité des médias, plutôt que promettre une réalisation dans les deux semaines du POC initial. Le modèle annoté, les poids choisis et la distribution des styles peuvent déplacer le budget vers le haut ; une étude 3D réclamerait un nouveau cadrage.

Alternative PGN + timestamps fournis/manuels : hypothèse 8 j ingénierie, 3 j revue, 1 j juridique et même réserve → 8 437,50 €. Couverture moins automatique mais état mieux justifiable si le PGN est complet. Passer de 20 à 200 vidéos ajoute au minimum la revue initiale des 180 actifs supplémentaires : 10 min/vidéo à 50 €/h → 1 500 €, hors droits, nouveaux thèmes et entraînement éventuel. Les différences entre options ne sont pas des gains observés.

---

## Page 9 — Coût d’exploitation et dimensionnement

Deux scénarios à stock constant renouvelé de 10 % par mois : A = 20 vidéos ×20 min (6,67 h), B = 200 ×30 min (100 h). Hypothèses H-OPEX : source 2 Mbit/s, échantillon/2 s, miniature conservée 25 Ko, entrée d’index 2 Ko, deux copies facturées ; unités décimales. Cela donne 12 000 /180 000 frames et 12,648 /189,720 Go stockés. Conserver seulement les dérivés nécessaires réduirait la charge ; un catalogue croissant exige de recalculer.

| Poste mensuel, hors licences | A · 20 vidéos | B · 200 vidéos |
| --- | --- | --- |
| VM Linux IPv4 de référence [S29] | 24,00 USD | 44,00 USD |
| Stockage 2 copies à 6,95 USD/To [S12] | 0,0879 USD | 1,3186 USD |
| Infrastructure convertie [S22] | 21,64 € | 40,71 € |
| Maintenance technique (2 h /4 h) | 171,43 € | 342,86 € |
| Revue nouveaux médias (2 /20 ×10 min) | 16,67 € | 166,67 € |
| Total central incrémental /mois | 209,73 € + R_mois | 550,23 € + R_mois |

Prix publics consultés le 29/10/2026 : Lightsail Linux/IPv4 2 vCPU/4 Go à24 USD, 2 vCPU/8 Go à44 USD ; stockage B2 « starts at »6,95 USD/To/mois, sans déduire le palier gratuit. BCE du28/10/2026 : 1 EUR=1,1133 USD. Comparaison de tarifs publics, pas devis pour une région/compte ; vérifier localisation UE, TVA, change bancaire et conditions. Les services POC existants, matériel, achat de droits et une migration/VPS complète sont exclus de cet incrément. Deux copies ne prouvent pas une restauration.

CPU hypothétique : décodage 0,15 cœur-h/heure vidéo + classification 0,25 seconde CPU/frame, marge1,3. Initial A/B : 2,38 /35,75 cœur-h ; renouvellement mensuel : 0,24 /3,58. Sensibilité décodage0,05–0,5 et modèle0,1–1 s : initial0,87–8,67 /13–130 cœur-h. Aucune de ces vitesses n’est mesurée. La VM est payée au mois : on ne refacture pas ces heures en plus. Pas de GPU dans le modèle central ; mesurer contention et mémoire avant cohabitation avec BGE/Qwen/Milvus, sinon worker séparé.

Hypothèses réseau : transferts sortants 10/100 Go mensuels, sous le seuil3×stockage annoncé B2 ; dépassement public0,01 USD/Go. Vérifier la région et les opérations facturables, ajouter une réserve si nécessaire. Recherche locale MCP : zéro appel YouTube par requête. Amorçage éventuel 20/200 search.list : 1 unité/bucket Search Queries par appel,100/jour par défaut [S10] ;200 demanderaient au moins deux jours à cette allocation. Revalidation métadonnées par30jours :1/4 lots de videos.list à1unité [S30], hors retraits plus fréquents. Quota ≠ budget financier garanti.

À droits gratuits réellement obtenus, année1 A ≈24 954,28 € (build central +12mois). B ≈30 540,26 €, incluant1 500 € de revue initiale supplémentaire. Ajouter R_build+12×R_mois ; 200 ou1 000 €/mois de licences ajoutent2 400 ou12 000 €/an. L’opération humaine domine le stockage : la décision doit porter sur la qualité et les droits, pas seulement sur quelques Go.

---

## Page 10 — Références, arbitrages et prochaine revue

Toutes les références ci-dessous ont été consultées le 29 octobre 2026, sauf la date propre du cours BCE indiquée. Les URL complètes complémentaires, codes HTTP, extraits courts et empreintes de contenu sont dans sources.json. Les prix sont des instantanés et les branches de dépôts peuvent évoluer. Le fichier costs.py rend explicites les hypothèses, formules et données ; costs.json/CSV sont recalculables.

- **[S01–S03]** MCP, spécification 2025-06-18 : architecture, outils et sécurité — https://modelcontextprotocol.io/specification/2025-06-18/architecture
- **[S04]** python-chess : FEN / board_fen / en passant — https://python-chess.readthedocs.io/en/latest/core.html
- **[S05 / S17]** OpenCV : homographie ; licence Apache-2.0 (4.10.0) — https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html
- **[S06–S07]** notnil/fenify-3D : README et licence MIT, auteur ; non reproduit — https://github.com/notnil/fenify-3D
- **[S08]** Ultralytics : AGPL / Enterprise, obligations à qualifier — https://www.ultralytics.com/license
- **[S09 / S19]** YouTube : Developer Policies et API Services Terms — https://developers.google.com/youtube/terms/developer-policies
- **[S10 / S30]** YouTube Data API : search.list et videos.list, coûts documentés — https://developers.google.com/youtube/v3/docs/search/list
- **[S11]** YouTube lecteur : start et image clé — https://developers.google.com/youtube/player_parameters
- **[S12]** Backblaze B2 : prix stockage et egress — https://www.backblaze.com/cloud-storage/pricing
- **[S22]** BCE : référence USD/EUR datée du28/10/2026 — https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
- **[S29]** AWS Lightsail : bundles Linux avec IPv4 — https://aws.amazon.com/lightsail/pricing/
- **[S23]** CPI L122-4 : reproduction / consentement — https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006278911
- **[S20 / S24]** CNIL : mineurs et principes RGPD — https://www.cnil.fr/fr/reglement-europeen-protection-donnees/chapitre2
- **[S27]** FFmpeg n7.0.2 : licence et composants optionnels — https://github.com/FFmpeg/FFmpeg/blob/n7.0.2/LICENSE.md
- **[S18 / S21]** FastMCP : interface ; Malt : contexte, pas justification des TJM — https://gofastmcp.com/getting-started/welcome

Accès limités : EUR-Lex RGPD/DSM (S14–S15/S25–S26) a renvoyé202 sans texte exploitable ; synthèse fondée sur les références indiquées, RGPD recoupé CNIL, qualification DSM à faire valider. FFmpeg legal.html a renvoyé503, remplacé par la licence du tag n7.0.2. Les tarifs cloud Hetzner consultés n’ont pas fourni de prix exploitable pour le SKU cible ; ils ne justifient aucun chiffre de cette note.

À faire approuver : finalité et contrats des20vidéos, niveau de vérité accepté, critères de la page7, devis/taux humains et régions de stockage, pilote PGN ou vision2D. Aucun outil MCP, extraction, modèle ou index n’est livré ; aucun benchmark visuel, appel YouTube, téléchargement de média ou écriture Mongo/Milvus n’a eu lieu. Voir les contrôles et limites dans ../VALIDATION.md ; cette étude ne vaut pas recette d’un système de vision. Arrêt pour revue avant livraison finale OpenClassrooms.
