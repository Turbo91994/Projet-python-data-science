# Projet Python pour la Data Science — Pokémon

Auteurs : Safaa, Ariël et Paul.

**Question :** les générations récentes introduisent-elles des Pokémon aux statistiques plus élevées ou plus spécialisées ? Les différences persistent-elles entre catégories comparables ?

Nous travaillons en local avec Git. La base de référence conservera toutes les formes PokéAPI pour permettre ensuite des analyses par forme, variété, espèce ou génération. Aucun regroupement, filtre sur la forme par défaut ou retrait des Gigamax n’est appliqué à la collecte. Les talents et conditions d’évolution sont hors périmètre.

## Structure

```text
src/collect.py                     Fonctions de collecte, lecture et contrôle
src/exploration.py                 Fonctions de diagnostic des sources
config/sources.json                Adresses et description des 11 sources
requirements.txt                   Dépendances
notebook/
  01_collecte.ipynb                 Collecte courte : 4 cellules de code
  02_exploration.ipynb              Exploration commentée des sources
  analyse_brouillon.ipynb           Ancienne analyse, à adapter après l’EDA
data/raw/reference_01/              Instantané brut et manifeste de provenance
```

Les CSV PokéAPI proviennent d’une même révision figée du dépôt de la source. Showdown est une copie datée ; il permettra des vérifications après rapprochement et l’ajout des catégories Paradoxe, Ultra-Chimère et du tier.

## Exécuter la collecte

L’environnement a été vérifié avec Python 3.11. Depuis la racine de ce dépôt :

```bash
python -m venv .venv
```

Activer l’environnement : `.venv\Scripts\Activate.ps1` sous PowerShell, ou `source .venv/bin/activate` sous Linux/macOS. Puis :

```bash
python -m pip install -r requirements.txt
jupyter lab
```

Ouvrir `notebook/01_collecte.ipynb`, sélectionner l’environnement Python du projet et exécuter toutes les cellules dans l’ordre. VS Code peut également ouvrir le notebook avec cet environnement.

Le notebook appelle trois fonctions simples :

- `collect_sources()` vérifie les fichiers existants et télécharge seulement les nouvelles sources absentes ;
- `load_sources()` lit les CSV et le JSON sans les fusionner ;
- `check_sources(data)` contrôle les identifiants, les rattachements et la présence des six statistiques.

## Explorer les sources

Après la collecte, ouvrir `notebook/02_exploration.ipynb` et exécuter ses cellules dans l’ordre. Il charge ses propres données : aucun état du notebook 01 n’est nécessaire. Le détail du code est dans `src/exploration.py` ; le notebook présente les tableaux, les constats, les explications et les conclusions.

Le parcours examine les espèces/variétés/formes, les statistiques et dates, les types, les valeurs manquantes PokéAPI et Showdown, puis les candidats de rapprochement. Les propositions de traitement restent distinctes des décisions prises. Les tables sont des diagnostics en mémoire ; aucune source brute n’est modifiée et aucune base finale n’est exportée.

## Partager les mêmes données

Le petit instantané brut est destiné à être versionné dans ce dépôt avec son manifeste. Après clonage de cette version, la collecte peut être relancée sans accès réseau tant que les sources de la configuration sont déjà présentes. Les 11 fichiers contiennent notamment 1 579 formes PokéAPI et 1 518 fiches Showdown dans cet instantané.

Le manifeste contient l’adresse, la date de récupération et l’empreinte SHA-256 de chaque fichier. Une modification accidentelle arrête la collecte. Si un fichier de cet instantané a été supprimé, le restaurer depuis Git : ne pas le remplacer silencieusement par une nouvelle version de Showdown.

Pour une collecte volontairement actualisée, choisir un nouveau `snapshot_id` dans la configuration. Si les CSV PokéAPI sont actualisés, leurs adresses doivent pointer vers une même nouvelle révision. Le premier téléchargement nécessite Internet. Les fichiers d’un instantané existant ne sont jamais écrasés automatiquement.

Les données préparées et les sorties régénérables sont ignorées par Git. Aucun compte SSP Cloud, accès S3 ou secret n’est nécessaire.

## État du travail

La collecte ne corrige pas les valeurs manquantes et n’applique aucune fusion entre formes. Ces choix seront documentés dans l’EDA et la préparation.

`analyse_brouillon.ipynb` conserve les premiers calculs sur 1 025 espèces, avec leurs anciennes sorties. Il utilise encore sa propre collecte API et ne doit pas être confondu avec le nouveau périmètre de toutes les formes. Ses graphiques et indicateurs pourront être repris après validation de la base.

Les dépendances de ce brouillon sont incluses dans `requirements.txt`. Les anciens scripts de collecte, de lecture S3 et leur ébauche GemRate ont été remplacés par `src/collect.py` ; leur historique reste accessible dans Git.
