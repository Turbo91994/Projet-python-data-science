# Projet Python pour la Data Science - Pokémon

Auteurs : Safaa, Ariël et Paul.

**Question :** les générations récentes introduisent-elles des Pokémon aux statistiques plus élevées ou plus spécialisées ? Les différences persistent-elles entre catégories comparables ?

## Démarrer

Le notebook final est **`notebook/constitution_base.ipynb`**. Exécuter ses cellules dans l'ordre, y compris la cellule de présentation des tableaux.

Avec Python 3.11, depuis la racine du projet :

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m jupyterlab
```

La première collecte API peut prendre plusieurs minutes. Les réponses sont sauvegardées : les exécutions suivantes réutilisent le cache. Avec les deux instantanés complets, la collecte et la préparation fonctionnent hors ligne. Les illustrations du notebook nécessitent une connexion.

## Où se trouve le code ?

| Fichier | Rôle |
|---|---|
| `src/collect.py` | Télécharger ou relire les sources, assembler la table CSV, collecter par API et comparer les deux méthodes. |
| `src/exploration.py` | Rattacher espèces, variétés et statistiques aux formes, puis produire les diagnostics affichés dans le notebook. |
| `src/preparation.py` | Rapprocher les formes de Showdown, vérifier les correspondances, ajouter les catégories et exporter la base. |
| `importation.py` | Lancer uniquement la collecte API. |
| `config/sources.json` | Adresses des sources et noms des instantanés. |
| `config/preparation.json` | Alias de noms, justification des cas particuliers et choix CSV/API. |

La jointure des formes, variétés, espèces et statistiques est écrite une seule fois dans `explore_forms()`. La collecte CSV réutilise ce résultat. Les fonctions de diagnostic observent les sources sans les corriger.

Les autres notebooks sont des versions de travail ou des étapes antérieures. Ils ne sont pas nécessaires pour exécuter le notebook final et ne sont pas le parcours de référence.

## Les étapes du notebook

1. Charger les sources et comprendre leurs identifiants, types et valeurs manquantes.
2. Construire la même table PokéAPI par CSV et par API, puis vérifier leur égalité.
3. Rapprocher les noms avec Showdown et vérifier séparément l'espèce, les statistiques et les types.
4. Exporter la base, puis comparer le BST et la spécialisation selon les générations.

Les deux collectes produisent **27 colonnes communes**. Showdown ne fait pas partie de cette comparaison. Un doublon d'identifiant, une forme absente d'une collecte ou une différence de valeur est signalé.

## Les choix de données

- La base finale conserve les **1 579 formes** de l'instantané, avec **20 variables**. Les formes cosmétiques, régionales, Méga et Gigamax ne sont pas supprimées.
- La génération est celle de l'introduction de la forme. Les six statistiques viennent de sa variété et correspondent à l'instantané actuel.
- Les types propres à la forme sont prioritaires. A défaut, les types de la variété sont utilisés. Le second type reste vide pour un Pokémon à un seul type.
- La fusion avec Showdown repose sur les noms et références déclarées, jamais sur l'égalité des statistiques. Les alias particuliers sont documentés dans la configuration.
- Les formes sans correspondance restent présentes. Aucun tier n'est inventé. Le tier peut venir d'une référence explicite, notamment une référence de combat.
- Les catégories peuvent se cumuler. `Non étiqueté` ne signifie pas nécessairement un Pokémon ordinaire.
- Les talents et conditions d'évolution restent hors périmètre. Les populations utilisées pour les comparaisons sont précisées dans le notebook.

## Fichiers produits

| Dossier | Contenu |
|---|---|
| `data/raw/reference_01/` | CSV PokéAPI et JSON Showdown, avec leurs dates et empreintes. |
| `data/raw/api_01/` | Réponses API mises en cache. |
| `data/collected/reference_01_vs_api_01/` | Les deux tables communes et le rapport de comparaison. |
| `data/processed/reference_01/` | Base finale, audit de fusion et provenance. |

L'audit contient les correspondances, les contrôles d'espèce, de statistiques et de types, ainsi que l'origine des tiers. La provenance conserve la date d'export, les instantanés utilisés et une copie des règles de préparation. Les empreintes restent utilisées pour protéger les fichiers bruts et le cache API ; elles ne sont plus recalculées pour tous les scripts à chaque export.

Pour actualiser les sources, choisir de nouveaux noms d'instantanés dans la configuration. Ne pas mélanger les anciennes réponses et de nouveaux téléchargements dans un instantané déjà complet.

## Vérifier le projet

Depuis la racine du dépôt, avec les sources locales présentes :

```bat
python -m unittest discover -s tests -v
```

Pour lancer seulement la collecte API :

```bat
python importation.py
```

Pour la vérification complète, redémarrer le noyau puis exécuter tout le notebook final. La préparation s'arrête si une correspondance Showdown est divergente ou non vérifiable.
