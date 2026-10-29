# Publication et maintenance de la distribution source

29 octobre 2026. Publication des sources autorisée par l’auteur sous **GPL-3.0-or-later**. Le contenu public est un export autonome, sans historique privé. Il commence par un unique commit racine sur `main`. Aucun binaire, poids, clé ou donnée de séance n’est distribué.

## Finalisation exécutée

- Export des 205 fichiers approuvés dans un répertoire indépendant ; comparaison de leurs SHA256 avant adaptation.
- Déclaration GPL-3.0-or-later et maintien du texte intégral GNU, des droits CC-BY-SA/CC0 et des notices tierces.
- README produit actualisé ; limites de reproductibilité et tests réellement exécutés conservés.
- Nouvelle vérification des chemins, secrets usuels, références privées, Python, six configurations Compose, corpus et dépendances. [Résultats](../validation/audit.json) et [manifeste recalculé](../validation/files.json).
- Code applicatif, données, locks, paramètres et capture inchangés ; seul l’outillage d’audit est ajusté pour reconnaître la licence définitive.

## Traçabilité

[Contrôles de finalisation](../validation/publication.json). Le SHA du premier commit se consulte dans l’historique de la branche `main` : un fichier ne peut inclure sans récursion le SHA du commit qui le contient. La preuve de push et de synchronisation est vérifiée après publication et communiquée séparément.

## Reproduire les contrôles

```sh
python3 scripts/audit-release.py
git diff --check
git rev-list --max-parents=0 main
git remote -v
```

Le scanner régénère ses deux JSON de validation. Il ne lance aucun fournisseur, modèle, base ou conteneur. Son résultat est un contrôle borné, pas un audit de sécurité universel. Une modification future impose un nouveau manifeste et des contrôles adaptés. Ne jamais utiliser un remote privé, importer un historique ancien, forcer la publication ou ajouter des poids/secrets dans Git.

## Recette encore nécessaire

Les tests applicatifs et le scénario navigateur limité sont décrits dans [VALIDATION](VALIDATION.md). L’installation Docker complète sur une machine vierge, les acquisitions/inférences BGE, Milvus et MongoDB réels ne sont **pas validés** par la publication des sources. Aucun dépôt automatique sur une plateforme de formation n’a lieu.
