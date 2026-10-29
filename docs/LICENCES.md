# Licences, droits et dépendances

Audit documentaire du29 octobre 2026 à partir des notices présentes, métadonnées des versions installées, locks et provenance du corpus. Ce n’est pas une consultation juridique ni un scan CVE exhaustif. **Le code original est sous GPL-3.0-or-later**, par choix explicite de Michel Levy le 29 octobre 2026. Les œuvres tierces conservent leurs licences ; aucune licence MIT globale n’est attribuée. Voir [LICENSE](../LICENSE.md).

## Contenu redistribué

| Ressource | Droits établis / traitement | Réserve |
|---|---|---|
|96 unités pédagogiques françaises | CC-BY-SA4.0, citations/révisions/historiques des contributeurs et notices de modification dans chaque chunk ; [index](CORPUS.md) | Revue experte pending ; la licence ne prouve pas l’exactitude pédagogique |
| Catalogue Lichess chess-openings | CC0-1.0 ; [texte original](../backend/app/data/openings/upstream/COPYING.txt), README et TSV versionnés conservés | Noms/positions≠évaluation optimale de coup |
| Capture Angular | Véritable candidat exécuté avec backend local ; analyses/coups synthétiques annoncés et passages BM25 réels ; pas de contenu privé ni vidéo copiée | Pas preuve de résultats live, pas marque FFE officielle |
| Étude MCP | Sources rédactionnelles et schéma/costs éditables, citations documentaires datées ; aucune vidéo extraite | Mentions et citations des auteurs conservées ; données tarifaires à réactualiser |
| Wikichess/FICGS et textes tiers non admis | Aucun texte redistribué | Droits non établis, pas de permission inférée |
| CorpusV1/V2, questions dev/réservées et preuves privées | Exclus | Aucun jeu scellé ouvert pour créer la release |

La source des unités reste en.wikibooks.org ; les URL d’historique des auteurs et révisions permettent l’attribution sans dépendance à une ressource privée. Ne pas enlever les licences/notices lors d’un export, d’une citation ou d’une adaptation. La sélection/modification française est explicitement indiquée dans les chunks. Les versions/flags d’archive restent inchangés ; pas de promotion automatique en « production validée ».

## Code et composants à acquérir

| Composant | Licence/conditions déclarées | Conséquence pratique |
|---|---|---|
| python-chess/chess1.11.2 | GPL-3.0-or-later, notice vérifiée dans la distribution installée | GPL-3.0-or-later du projet compatible avec ce composant ; conserver licence/notices et fournir les sources correspondantes en cas de redistribution de binaires |
| Stockfish15.1-4Debian | GPL3, notices dans l’image Debian | Si un binaire/image est redistribué, fournir l’accès aux sources correspondantes et respecter les notices ; le dépôt ne publie pas de binaire |
| FastAPI, LangGraph, Angular | MIT selon notices/locks | Conserver copyrights et notices lors de redistribution |
| HTTPX/HTTPcore, torch | BSD3selon métadonnées/projets ; dépendances distinctes | Ne pas généraliser une seule licence à toutes les transitives |
| PyMongo, Milvus, Transformers | Apache2.0déclarée | Notices propres et licences des dépendances à préserver |
| MongoDB Community7.0 | SSPL, pas une licence OSI | Examiner les conditions du mode de service avant hébergement ; pas d’exposition publique DB dans le POC |
| BusyBox | GPLv2 | Source correspondante/notices requises si son binaire/image est redistribué |
| BAAI/bge-m3 | MITdéclarée au checkpoint, révision/hash figés | Poids non redistribués ici, acquisition opérateur vérifiée, obligations du dépôt modèle à consulter |
| Qwen2.5-1.5B-Instruct-GGUF | Apache2.0déclarée | GGUF non distribué, hash/provenance à conserver par opérateur |
| llama.cpp | MITdéclarée | Image publique séparément acquise, digest fixé |
| Lichess/YouTube/Mistral/Groq | Conditions d’API et de compte, pas une licence des données/vidéos | Quotas, confidentialité, coût et droits distincts ; aucune autorisation d’extraction YouTube |

[Inventaire structuré des49pins backend et150 paquets du lock frontend](../validation/dependencies.json), [lockBGE48 artefacts](../retrieval/requirements.lock). Un champ licence absent vaut UNVERIFIED, pas licence libre implicite. Les métadonnées ne remplacent pas l’examen des notices de distribution réellement fournies lors d’un futur build. Les SDK installés, node_modules, roues et images ne sont pas copiés dans Git.

## Sources et redistribution des images

Les Dockerfiles demandent aux registres officiels/PyPI/npm les versions épinglées ; les paquets installés conservent leurs notices dans leurs distributions. Debian publie la source Stockfish15.1-4 à https://sources.debian.org/src/stockfish/15.1-4/ ; python-chess à https://github.com/niklasf/python-chess/tree/v1.11.2 et https://pypi.org/project/chess/1.11.2/ ; GNU GPL3 à https://www.gnu.org/licenses/gpl-3.0.html. Ces références documentent l’accès, elles ne constituent pas une promesse légale générale de conformité d’une future distribution de binaires.

Aucune image/binaire tiers n’est publié par ce candidat. Si le jury/déploiement exige de distribuer aussi des images, vérifier la méthode de fourniture des sources correspondantes, les notices et la compatibilité de l’ensemble. Ne pas utiliser une simple mention « crédits » comme substitut.

## Compatibilités et périmètre de cette publication

Le dépôt ne redistribue que le code source original, les données identifiées et les notices. Aucune dépendance installée, binaire Stockfish, image Docker, poids, sortie compilée Angular ou vidéo ne fait partie de cette publication. Les Dockerfiles et locks décrivent des acquisitions réalisées ultérieurement par l’opérateur auprès de leurs éditeurs ; ils ne constituent pas une redistribution de ces artefacts dans Git.

- **python-chess GPL-3.0-or-later et Stockfish GPL3** : le choix GPL-3.0-or-later du code lève le conflit de licence envisagé. Une distribution binaire combinée avec un composant GPLv3-only doit respecter les conditions GPLv3 applicables à cet ensemble ; elle ne donne pas le droit de relicencier Stockfish sous une autre version. Stockfish demeure un programme UCI distinct. Son code Debian modifié doit correspondre exactement au binaire redistribué, pas seulement à la dernière version amont.
- **MIT, BSD-2/3-Clause, ISC et Apache-2.0** : compatibles avec une combinaison sous GPLv3 en conservant les copyrights, licences, disclaimers et éventuels fichiers NOTICE. Apache-2.0 impose aussi ses dispositions de brevets et le signalement des modifications ; aucune licence tierce n’est remplacée dans ses fichiers.
- **MPL-2.0** : les dépendances déclarées MPL-2.0 gardent leur copyleft au niveau du fichier et leurs notices ; toute combinaison/redistribution doit examiner les clauses de licences secondaires et la présence éventuelle d’« Incompatible With Secondary Licenses ». Aucun de leurs fichiers n’est incorporé ou modifié dans les sources publiées ici.
- **PSF-2.0 et dépendances Python** : notices distinctes ; les licences du système Python et de ses bibliothèques ne sont pas remplacées par celle de l’application.
- **MongoDB SSPL et BusyBox GPLv2** : programmes/services séparés, non copiés dans le dépôt et non relicenciés GPLv3. Leur orchestration ne vaut pas incorporation de leur code. La mise à disposition d’un service MongoDB et la redistribution d’images demandent leur propre examen ; aucune autorisation générale d’hébergement n’est déduite ici.
- **CC-BY-SA-4.0 et CC0** : jeux documentaires/factuels séparés du code. Les adaptations restent attribuées et partagées sous leur licence. Le choix GPL du code ne constitue pas un changement de licence du corpus.

Références : [compatibilités GNU](https://www.gnu.org/licenses/license-list.html), [GPLv3 et sources correspondantes, articles 4–6](https://www.gnu.org/licenses/gpl-3.0.html), [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0), [MPL-2.0](https://www.mozilla.org/MPL/2.0/), [FAQ MPL](https://www.mozilla.org/MPL/2.0/FAQ/), [SSPL MongoDB](https://www.mongodb.com/legal/licensing/server-side-public-license), [CC-BY-SA-4.0](https://creativecommons.org/licenses/by-sa/4.0/legalcode), [CC0](https://creativecommons.org/publicdomain/zero/1.0/legalcode). Analyse documentaire datée du 29 octobre 2026, pas un avis juridique ni une garantie de conformité de futurs binaires.

**Conclusion pour les seuls fichiers source publiés : aucune incompatibilité juridique bloquante identifiée.** Les licences déclarées des 49 pins backend et 150 paquets npm ont été recensées, pas les licences de binaires futurs encore non construits. Avant distribution d’une image ou d’un bundle, conserver et fournir l’ensemble des notices applicables et les sources correspondantes selon le mode de redistribution ; un simple lien amont n’est pas une offre légale universelle de sources.

## Points restant à suivre

Maintenance des versions épinglées, obligations des distributions binaires futures, revue experte du corpus, usage des API chez des mineurs et protection des données. Aucun droit de copier ou d’extraire une vidéo n’est créé par cette publication. Les documents originaux conservent leurs crédits, sans réattribution des citations tierces.
