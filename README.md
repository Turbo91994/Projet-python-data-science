# Projet Python pour la Data Science — Pokémon

Auteurs : Safaa, Ariël et Paul.

**Question :** les générations récentes introduisent-elles des Pokémon aux statistiques plus élevées ou plus spécialisées ? Les différences persistent-elles entre catégories comparables ?

Nous travaillons en local avec Git. La base de référence conservera toutes les formes PokéAPI pour permettre ensuite des analyses par forme, variété, espèce ou génération. Aucun regroupement, filtre sur la forme par défaut ou retrait des Gigamax n’est appliqué à la collecte. Les talents et conditions d’évolution sont hors périmètre.

## Notebook à exécuter

Ouvrir **`notebook/constitution_base.ipynb`** et exécuter toutes les cellules dans l’ordre. C’est désormais le parcours de référence : chargement des sources, choix de l’unité d’observation, valeurs manquantes, comparaison CSV/API, fusion Showdown, contrôles et export. Il comprend **13 cellules de code** ; les fonctions restent dans `src/`.

Les imports et chargements ne sont réalisés qu’une fois. Les trois notebooks numérotés sont conservés comme versions séparées d’origine ; leur exécution n’est plus nécessaire pour reconstruire la base.

## Structure

```text
importation.py                     Lancement de la collecte API seule
src/collect.py                     Collectes CSV/API, cache, contrôles et comparaison
src/exploration.py                 Fonctions de diagnostic des sources
src/preparation.py                 Construction de la base et audit des jointures
config/sources.json                Sources CSV/Showdown et configuration API
config/preparation.json            Correspondances de noms et justifications
requirements.txt                   Dépendances
notebook/
  constitution_base.ipynb           Parcours unique : des sources à la base finale
  01_collecte.ipynb                 Ancien parcours séparé de collecte
  02_exploration.ipynb              Ancien parcours séparé d’exploration
  03_preparation.ipynb              Ancien parcours séparé de préparation
  analyse_brouillon.ipynb           Ancienne analyse, à adapter après l’EDA
tests/test_collect.py               Tests hors ligne de la collecte et de la comparaison
data/raw/reference_01/              CSV bruts et JSON Showdown, avec manifeste
data/raw/api_01/                    Réponses API datées et vérifiées
data/collected/                     Deux tables comparables et rapports régénérables
```

Les CSV PokéAPI proviennent d’une même révision figée du dépôt de la source. Showdown est une copie datée ; il permettra des vérifications après rapprochement et l’ajout des catégories Paradoxe, Ultra-Chimère et du tier.

## Exécuter les deux collectes

L’environnement a été vérifié avec Python 3.11. Depuis la racine du dépôt, sous Windows, ces commandes fonctionnent sans activer l’environnement :

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m jupyterlab
```

Ouvrir `notebook/constitution_base.ipynb` et sélectionner cet environnement Python. Exécuter les cellules dans l’ordre : les sources brutes sont chargées au début et la comparaison avec l’API intervient après l’examen de leur structure. Avec les instantanés complets, le parcours fonctionne hors ligne ; sans cache API, le premier lancement télécharge les réponses.

### Méthode CSV

`collect_sources()` télécharge ou vérifie les dix CSV PokéAPI et le JSON Showdown. `load_sources()` les ouvre séparément ; `check_sources(data)` vérifie leurs clés, rattachements et statistiques. Ces fonctions restent compatibles avec l’EDA et la préparation existantes.

`pokeapi_from_csv(data)` assemble une table de comparaison, une ligne par forme. Les types explicites de forme sont utilisés lorsqu’ils existent, sinon ceux de la variété. Les fichiers bruts ne sont jamais réécrits.

### Méthode API

`collect_pokeapi_api()` parcourt toutes les pages de `/pokemon-form/`, sans limite de génération ou d’espèce et sans utiliser les identifiants des CSV. Chaque forme référence sa variété, qui fournit les statistiques et l’espèce. Le groupe de jeux de la forme donne sa génération d’introduction. Les types viennent directement de la forme. Le code ne recherche jamais les statistiques via `/pokemon/nom-de-forme`.

La première exécution demande plusieurs milliers de requêtes et peut durer plusieurs minutes. Les réponses JSON complètes sont sauvegardées dans `data/raw/api_01/responses/` avec l’adresse, la date UTC et une empreinte de leur contenu. Les noms de fichiers sont les empreintes des URL, pour distinguer les ressources et les pages. Une pause entre téléchargements et une session HTTP réutilisée limitent les appels, conformément à la [documentation PokéAPI](https://pokeapi.co/docs/v2).

Une erreur HTTP interrompt la collecte. Relancer reprend avec le cache déjà acquis ; aucune erreur n’est remplacée silencieusement par une autre valeur. Une fois l’instantané complet, le manifeste enregistre les fichiers attendus : une réponse supprimée ou modifiée doit être restaurée, pas remplacée silencieusement par une nouvelle version. Le cache complet peut être relu hors ligne. Les réponses d’une première collecte interrompue peuvent avoir des dates différentes ; l’API publique ne fournit pas un instantané atomique à la révision des CSV.

Pour lancer seulement cette collecte en invite de commandes :

```bat
.venv\Scripts\python.exe importation.py
```

Ce script utilise les fonctions de `src/collect.py`, affiche un aperçu et exporte `data/collected/api_01/pokeapi_api.csv`. Importer le module ne lance aucune collecte. GemRate et les fonctions S3/SSP Cloud ont été retirés ; aucune dépendance supplémentaire n’est nécessaire.

### Comparaison et sortie commune

Les deux méthodes produisent les mêmes **27 colonnes** : identifiants forme/variété/espèce, noms techniques, nom français de l’espèce, catégorie anglaise, groupe de jeux, générations de la forme et de l’espèce, six indicateurs, six statistiques et deux types (identifiants et libellés français). Le dictionnaire détaillé figure dans le notebook. Les seconds types manquants restent manquants ; les formes partageant leurs statistiques restent distinctes.

`compare_pokeapi()` vérifie la population complète et les 26 valeurs associées à chaque `form_id`. L’ordre des lignes et les types Python sont harmonisés ; les valeurs ne sont pas corrigées. Un doublon de clé bloque le contrôle, une forme absente d’une source est signalée, et une absence d’un seul côté compte comme un écart. Deux valeurs manquantes au même endroit sont considérées égales.

**Showdown est exclu de la comparaison.** L’égalité porte uniquement sur ces 27 colonnes PokéAPI, pas sur tous les champs des fichiers bruts. Par exemple, les habitats, ordres d’affichage et traductions non retenues ne sont pas déclarés identiques par ce contrôle. Les CSV sont figés, alors que l’API peut évoluer : une égalité est un résultat à vérifier, pas une hypothèse imposée.

`export_collections()` écrit quatre fichiers dans `data/collected/reference_01_vs_api_01/` :

- `pokeapi_csv.csv` et `pokeapi_api.csv` : les deux tables au même format ;
- `comparaison_resume.csv` : les effectifs et le nombre de cellules différentes ;
- `comparaison_ecarts.csv` : chaque forme absente ou valeur différente, avec les deux versions.

Le rapport est enregistré même en présence d’écarts ; la dernière cellule du notebook échoue alors explicitement. Il faut comprendre ces écarts avant de choisir une source pour la fusion avec Showdown. Les tables API et CSV sont deux voies d’obtention des mêmes variables : ne pas les concaténer, ce qui doublerait les observations. L’EDA et la préparation existantes continuent pour l’instant à lire les CSV bruts.

**Résultat vérifié pour `reference_01` et `api_01` :** les deux tables contiennent 1 579 formes et 27 colonnes. Aucune forme ne manque d’un côté et aucune valeur ne diffère sur les 26 colonnes comparées par identifiant. Une nouvelle collecte doit refaire ce contrôle.

### Tester sans réseau

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Les tests couvrent notamment la pagination, la génération propre aux formes, les statistiques de variété, l’absence d’appel lors d’un import, les erreurs HTTP, l’intégrité du cache et la détection des écarts. La vérification complète avec les données réelles est effectuée dans `notebook/constitution_base.ipynb`, jusqu’à l’export de la base et de son audit.

## Explorer les sources

Les sections 2 à 5 de `notebook/constitution_base.ipynb` explorent les sources déjà chargées. Le détail du code est dans `src/exploration.py` ; le notebook présente les observations, leurs explications et les décisions de préparation. Aucun second chargement n’est nécessaire.

Le parcours examine les espèces/variétés/formes, les statistiques et dates, les types, les valeurs manquantes PokéAPI et Showdown, puis les candidats de rapprochement. Les propositions de traitement restent distinctes des décisions prises. Les tables sont des diagnostics en mémoire ; aucune source brute n’est modifiée et aucune base finale n’est exportée.

## Construire la base pour l’analyse

Les sections 7 à 9 du notebook unique utilisent les tables CSV/API déjà comparées, construisent la base finale avec chacune et vérifient que les deux bases finales sont identiques. `source_pokeapi` dans `config/preparation.json` choisit ensuite la version exportée : `csv` par défaut, ou `api`. Le cache complet permet cette vérification sans nouveau téléchargement.

La fonction `prepare_database(pokeapi, showdown, source)` reçoit la table commune et les fiches Showdown. Elle n’utilise pas l’autre collecte pour combler des données. Les types Showdown sont vérifiés avec un dictionnaire d’identifiants documenté dans la configuration. Le numéro d’espèce et les six statistiques sont vérifiés après la correspondance de noms, sans servir à la choisir.

L’export produit `pokemon_forms.csv`, `audit_preparation.csv` et `provenance.json` dans `data/processed/reference_01/`. La provenance enregistre la source retenue, les instantanés et les empreintes du code, de la configuration, des manifestes et des résultats. Ces fichiers sont régénérables et ignorés par Git. Aucune dépendance supplémentaire n’est nécessaire.

Une correspondance Showdown divergente ou non vérifiable bloque l’export, mais reste consultable dans l’audit en mémoire. Une forme sans correspondance est conservée avec ses enrichissements manquants. Les données PokéAPI ne sont jamais remplacées par celles de Showdown.

La base contient une ligne par forme, les identifiants forme/variété/espèce, le nom français de l’espèce et l’identifiant de forme, sa génération d’introduction, les six statistiques, leur somme (BST), les deux types, les catégories identifiées et le tier disponible. Les indicateurs de forme par défaut, de combat et Méga restent disponibles. Le notebook donne le dictionnaire des variables et leurs limites.

Dans cet instantané, les 1 579 formes sont conservées. Les 1 518 rapprochements de formes avec Showdown présentent des statistiques et types concordants ; 61 formes restent sans correspondance retenue et sans tier. Ces absences ne suppriment aucune ligne. Les rapprochements reposent sur les noms et les références déclarées, puis les statistiques sont vérifiées indépendamment. L’audit explique les correspondances, les représentations cosmétiques communes et l’origine des types, générations, tags et tiers.

Les catégories peuvent se cumuler : Koraidon et Miraidon sont légendaires et Paradoxes. Le libellé « Non étiqueté » ne garantit pas une catégorie « ordinaire ». Les statistiques sont celles de l’instantané, et les tiers ne sont pas des classements historiques à l’introduction des formes. Les moyennes par forme donneront davantage de poids aux espèces ayant plusieurs formes : cette limite devra être examinée dans l’analyse.

## Partager les mêmes données

Le petit instantané brut est destiné à être versionné dans ce dépôt avec son manifeste. Après clonage de cette version, la collecte peut être relancée sans accès réseau tant que les sources de la configuration sont déjà présentes. Les 11 fichiers contiennent notamment 1 579 formes PokéAPI et 1 518 fiches Showdown dans cet instantané.

Le manifeste contient l’adresse, la date de récupération et l’empreinte SHA-256 de chaque fichier. Une modification accidentelle arrête la collecte. Si un fichier de cet instantané a été supprimé, le restaurer depuis Git : ne pas le remplacer silencieusement par une nouvelle version de Showdown.

Pour actualiser les CSV/Showdown, choisir un nouveau `snapshot_id` principal dans la configuration. Pour actualiser l’API, choisir un nouveau `pokeapi_api.snapshot_id` (par exemple `api_02`). Ne pas réutiliser un instantané API partiellement effacé. Si les CSV PokéAPI sont actualisés, leurs adresses doivent pointer vers une même nouvelle révision. Le premier téléchargement nécessite Internet. Les fichiers d’un instantané existant ne sont jamais écrasés automatiquement.

Le dossier `data/` figure dans `.gitignore` : les nouvelles réponses API et sorties régénérables ne sont pas ajoutées à Git. Les fichiers bruts déjà suivis restent suivis ; une règle d’exclusion ne les retire pas de l’historique. Aucun compte SSP Cloud, accès S3 ou secret n’est nécessaire.

## État du travail

La collecte conserve les sources, l’EDA les examine et la préparation applique les choix documentés. Aucune forme n’est supprimée ni regroupée. Les enrichissements Showdown encore non établis restent manquants.

`analyse_brouillon.ipynb` conserve les premiers calculs sur 1 025 espèces, avec leurs anciennes sorties. Il utilise encore sa propre collecte API et ne doit pas être confondu avec le nouveau périmètre de toutes les formes. Ses graphiques et indicateurs pourront être repris après validation de la base.

Les dépendances de ce brouillon sont incluses dans `requirements.txt`. `importation.py` est désormais un point d’entrée court vers `src/collect.py` ; les anciens traitements S3 et GemRate ne font plus partie de la collecte.
