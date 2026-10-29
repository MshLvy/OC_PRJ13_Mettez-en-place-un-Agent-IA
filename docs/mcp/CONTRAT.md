# Contrat technique candidat — non implémenté

29 octobre 2026. Annexe de la note de 10 pages, à soumettre à revue. Aucun serveur MCP, client, modèle, extraction, endpoint ou collection créé par ces exemples. Spécification de référence MCP 2025-06-18, à négocier avec les SDK choisis avant tout développement.

## Frontières de service

- Host : application backend actuelle ; Angular conserve action et snapshot. LangGraph reste l'orchestrateur et ne délègue pas la politique d'autorisation au LLM.
- Client MCP : composant backend futur, jamais un navigateur contenant des clés fournisseur.
- Serveur MCP : service futur avec deux outils de lecture et contrôle du catalogue autorisé. stdio pour pilote local ; Streamable HTTP seulement avec autorisation conforme, audience et scopes contrôlés. Pas de passthrough de clés YouTube/LLM comme jetons MCP.
- Ingestion : plan opérateur séparé, fichiers déjà admis, jobs bornés. Pas de commande de téléchargement accessible à l'apprenant ou à un texte documentaire.

Un index SQLite versionné/read-only suffit au volume pilote : table assets (droits/provenance), observations (intervalle et disposition) et éventuels états prouvés, index `(catalog_version, layout_hash)` et `(catalog_version, full_fen_hash)`. Un stockage documentaire dédié pourrait remplacer cette implémentation après mesure ; aucun accès aux collections sessions/Milvus actuelles n'est requis. Pas de jointure transactionnelle entre corpus RAG et vidéos.

## Entrée de search_video_positions

Contrat JSON Schema **proposé**, donné pour préciser les champs, pas pour annoncer un outil livré :

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["query_fen", "match_mode", "catalog_version", "snapshot", "limit"],
  "properties": {
    "query_fen": {"type": "string", "maxLength": 256},
    "match_mode": {"enum": ["piece_placement_only", "rule_state", "full_fen"]},
    "catalog_version": {"type": "string", "pattern": "^[a-z0-9_-]{1,64}$"},
    "snapshot": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 3}
  }
}
```

Validation sémantique indispensable en plus du schéma : six champs FEN valides, variante standard uniquement, contexte/snapshot validés côté host, catalogue autorisé par identité et version. Le snapshot est un checksum de synchronisation, pas une preuve d'identité. Une permission de serveur ne se relève pas par un paramètre de requête. Champ libre q, URL, commande shell, destination réseau et credentials interdits.

`get_video_match` prend seulement match_id opaque, catalog_version et snapshot bornés. Il recontrôle les droits, la version et l'expiration ; aucune ancienne URL n'est resservie après un retrait. `readOnlyHint` n'est pas un mécanisme de contrôle d'accès.

## Sortie et règles d'égalité

Enveloppe : status `ok|partial|empty|ambiguous|unavailable|invalid`, request_id, snapshot, catalog_version, match_mode réellement appliqué et zéro à trois matches. Pas de downgrade silencieux de full_fen vers disposition. `structuredContent` doit être contrôlé par le backend avant affichage.

Chaque match aurait :

| Champ | Sens / contrôle |
|---|---|
| match_id, asset_id, asset_sha256 | Identité de version ; aucune ressource arbitraire |
| observation.board_fen | Huit rangées orientées a1–h8 ; disposition seulement |
| turn, castling, ep_square, halfmove_clock, fullmove_number | Valeurs typées **ou null** si inconnues ; `castling="-"` signifie absence prouvée, pas inconnu |
| full_fen | null tant que les six champs ne sont pas prouvés |
| state_proof | type PGN/annotation vérifiée, ancrage et révision ; absence explicite sinon |
| segment_id, start_pts_s, end_pts_s | Intervalle dans le fichier identifié ; cohérent avec time_base et durée |
| timestamp_uncertainty_s | Incertitude estimée et méthode, non une précision garantie |
| match_kind | disposition seule / état réglementaire / six champs prouvés |
| orientation, confidence, model_revision | Sources de l'observation, score déclaré non calibré si tel est le cas |
| rights_status, rights_checked_at, provenance | Contrat valide au moment de la lecture, pas seulement à l'ingestion |
| playback_url | URL canonique depuis un véritable video_id autorisé et timestamp contrôlé, ou null ; pas de faux lien de fixture |
| limitations | Contenu non visionné/certifié, ambiguïtés et contexte manquant |

L'égalité disposition compare la première composante sans symétrie ni changement de couleur. rule_state compare les champs 1–4 avec sérialisation EP convenue ; full_fen compare les six. La légalité et la reconstruction sont vérifiées séparément. L'égalité d'une position n'est ni la pertinence du commentaire ni une recommandation de coup.

Exemple de **forme partielle**, sans vidéo ni lien réel :

```json
{
  "example_only": true,
  "board_fen": "r3k2r/8/8/8/8/8/8/R3K2R",
  "turn": null,
  "castling": null,
  "ep_square": null,
  "halfmove_clock": null,
  "fullmove_number": null,
  "full_fen": null,
  "match_kind": "piece_placement_only",
  "playback_url": null
}
```

## Ingestion, retrait, erreurs et budgets candidats

Manifeste d'actif : preuve de droits, propriétaire, finalité, territoire, expiration, version/hash du fichier, source de l'identifiant de lecture et politique de rétention. Workers sandboxés, lecture des seuls assets admis, aucun réseau libre. Limites initiales à ratifier : durée vidéo≤60min,0,5frame/s nominal,≤2jobs CPU, raffinement près des transitions avec un plafond de frames explicite ; quand le budget est épuisé, publier incomplet ou échouer, pas prétendre à une couverture intégrale. Mesurer décodage réel et coût sur les fichiers autorisés.

L'absence de preuve de roque/EP/trait bloque full_fen. Les coupures/retours de variante interrompent la reconstruction. Contrôles visuels ou FEN ne réparent pas une autorisation manquante. Le score de confiance ne surpasse aucun de ces refus.

Retrait : marquer l'actif bloqué dans le manifeste avant la purge, refuser aussitôt les lectures, retirer observations et dérivés, gérer les sauvegardes conformément au contrat, garder une preuve technique minimale de l'effacement sans copie du média. Refresh de métadonnées YouTube selon catégorie et quota, pas de poll par requête apprenant.

Erreurs candidates : INVALID_CONTEXT, RIGHTS_UNAVAILABLE, AMBIGUOUS_ORIENTATION, UNPROVEN_FULL_FEN, CATALOG_VERSION_MISMATCH, STALE_SNAPSHOT, INDEX_UNAVAILABLE, BUDGET_EXCEEDED. Résultats bornés et messages statiques, pas de corps privé ou chemin stockage exposés. Recherche index avec budget de service2s cible à mesurer, aucune extraction interactive ni retry caché ; jobs opérateur asynchrones via job_id/statut applicatifs, sans supposer une extension MCP non validée.

Tests futurs : schémas, expiration/droits, injection/SSRF, refus de downgrade, snapshot tardif, byte budget, arrêt et reprise de jobs, exactitude des 64 cases et timestamps. Ces tests du système vidéo **ne sont pas exécutés par cette étude**. Les seuls contrôles exécutés ici concernent les documents, mathématiques et artefacts de conception.
