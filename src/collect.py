"""Collecte locale des sources brutes, sans filtrer ni regrouper les formes."""

from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib
import json
import time

import pandas as pd
import requests


# collect.py est dans src/ ; la configuration et les données restent à la racine.
PROJECT_DIR = Path(__file__).resolve().parent.parent


def read_config():
    """Lire les adresses des sources et le nom de l'instantané."""
    path = PROJECT_DIR / "config" / "sources.json"
    return json.loads(path.read_text(encoding="utf-8"))


def collect_sources():
    """Télécharger les fichiers absents ; vérifier et conserver ceux déjà présents."""
    config = read_config()
    folder = PROJECT_DIR / "data" / "raw" / config["snapshot_id"]
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"snapshot_id": config["snapshot_id"], "files": {}}
    assert manifest["snapshot_id"] == config["snapshot_id"], "Instantané incohérent."

    for source in config["sources"]:
        path = folder / source["filename"]
        source_id = source["id"]
        if path.exists():
            # L'empreinte change si le contenu du fichier change.
            assert source_id in manifest["files"], f"Provenance absente : {path.name}."
            saved = manifest["files"][source_id]
            assert saved["download_url"] == source["url"], "Adresse modifiée : créer un nouvel instantané."
            fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
            assert fingerprint == saved["sha256"], f"Fichier modifié : {path.name}. Restaurer la copie d'origine."
            print("Conservé et vérifié :", path.name)
        else:
            # Ne pas remplacer une copie datée perdue par une nouvelle version de l'API.
            assert source_id not in manifest["files"], f"Fichier manquant : {path.name}. Restaurer l'instantané depuis Git."
            request = Request(source["url"], headers={"User-Agent": "ENSAE-Pokemon-Project/1.0"})
            with urlopen(request, timeout=30) as response:
                content = response.read()
            assert content, f"Fichier téléchargé vide : {path.name}."
            path.write_bytes(content)
            manifest["files"][source_id] = {
                "filename": path.name,
                "download_url": source["url"],
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("Téléchargé :", path.name)
    return folder


def load_sources():
    """Ouvrir les CSV et le JSON séparément, sans préparer une base fusionnée."""
    config = read_config()
    folder = PROJECT_DIR / "data" / "raw" / config["snapshot_id"]
    data = {}
    for source in config["sources"]:
        path = folder / source["filename"]
        if source["format"] == "csv":
            data[source["id"]] = pd.read_csv(path)
        else:
            data[source["id"]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def check_sources(data):
    """Contrôler les clés, les rattachements et les six statistiques ; résumer les fichiers."""
    summary = []
    for source in read_config()["sources"]:
        table = data[source["id"]]
        assert len(table) > 0, f"Source vide : {source['id']}."
        if source["format"] == "csv":
            key = source["key"]
            assert not table[key].isna().any().any(), f"Identifiant manquant : {source['id']}."
            assert not table.duplicated(key).any(), f"Identifiant répété : {source['id']}."
        summary.append({"source": source["id"], "lignes_ou_fiches": len(table)})

    species = data["pokemon_species"]
    varieties = data["pokemon"]
    forms = data["pokemon_forms"]
    stats = data["pokemon_stats"]
    assert varieties["species_id"].isin(species["id"]).all(), "Espèce référencée absente."
    assert forms["pokemon_id"].isin(varieties["id"]).all(), "Variété d'une forme absente."
    assert stats["pokemon_id"].isin(varieties["id"]).all(), "Variété des statistiques absente."
    assert forms["introduced_in_version_group_id"].isin(data["version_groups"]["id"]).all(), "Groupe de jeux absent."
    assert data["version_groups"]["generation_id"].notna().all(), "Génération d'un groupe de jeux absente."
    assert data["pokemon_species_names"]["pokemon_species_id"].isin(species["id"]).all(), "Espèce d'une traduction absente."

    stat_names = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]
    expected_stats = data["stats"].loc[data["stats"]["identifier"].isin(stat_names)]
    assert len(expected_stats) == 6, "Dictionnaire des six statistiques incomplet."
    assert set(stats["stat_id"]) == set(expected_stats["id"]), "Statistiques inattendues."
    counts = stats.groupby("pokemon_id").size().reindex(varieties["id"], fill_value=0)
    assert counts.eq(6).all(), "Une variété n'a pas ses six statistiques."
    assert stats["base_stat"].gt(0).all() and stats["base_stat"].mod(1).eq(0).all(), "Statistique absente ou invalide."

    assert data["pokemon_types"]["pokemon_id"].isin(varieties["id"]).all(), "Variété d'un type absente."
    assert data["pokemon_form_types"]["pokemon_form_id"].isin(forms["id"]).all(), "Forme d'un type absente."
    for table in [data["pokemon_types"], data["pokemon_form_types"]]:
        assert table["type_id"].isin(data["type_names"]["type_id"]).all(), "Type inconnu."

    # Les fiches cosmétiques Showdown peuvent ne pas répéter leurs statistiques.
    showdown = data["showdown_pokedex"]
    assert isinstance(showdown, dict), "Structure Showdown inattendue."
    for key, entry in showdown.items():
        assert entry.get("name"), f"Fiche Showdown sans nom : {key}."
        if entry.get("isCosmeticForme", False):
            assert entry.get("baseSpecies"), f"Référence cosmétique absente : {key}."
        else:
            assert set(entry.get("baseStats", {})) == {"hp", "atk", "def", "spa", "spd", "spe"}, f"Statistiques Showdown incomplètes : {key}."

    print(f"Contrôles terminés : {len(forms)} formes conservées ; aucun filtre ni regroupement.")
    return pd.DataFrame(summary)


# La comparaison concerne ces informations du projet, pas tous les champs bruts.
STAT_NAMES = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]
TEXT_COLUMNS = ["forme", "variete", "espece", "nom_fr", "genre_en", "type_1", "type_2"]
POKEAPI_COLUMNS = [
    "form_id", "pokemon_id", "species_id", "forme", "variete", "espece", "nom_fr", "genre_en",
    "version_group_id", "generation", "generation_espece", "is_default_form", "is_default_variety",
    "is_battle_only", "is_mega", "is_legendary", "is_mythical",
    *STAT_NAMES, "type_1_id", "type_2_id", "type_1", "type_2",
]


def normalize_pokeapi_table(table):
    """Même ordre de colonnes et mêmes types Python, sans corriger les valeurs."""
    assert set(table.columns) == set(POKEAPI_COLUMNS), "Colonnes inattendues ou absentes."
    table = table[POKEAPI_COLUMNS].copy()
    for column in POKEAPI_COLUMNS:
        table[column] = table[column].astype("string" if column in TEXT_COLUMNS else "Int64")
    assert table["form_id"].notna().all() and table["form_id"].is_unique, "Identifiant de forme absent ou dupliqué."
    required = ["pokemon_id", "species_id", "forme", "generation", "type_1_id"] + STAT_NAMES
    assert table[required].notna().all().all(), "Information essentielle manquante."
    assert table[STAT_NAMES].gt(0).all().all(), "Statistique invalide."
    return table.sort_values("form_id").reset_index(drop=True)


def pokeapi_from_csv(data):
    """Présenter les CSV en une ligne par forme, au format commun avec l'API."""
    forms = data["pokemon_forms"].rename(columns={
        "id": "form_id", "identifier": "forme", "is_default": "is_default_form",
        "introduced_in_version_group_id": "version_group_id"})
    varieties = data["pokemon"][["id", "identifier", "species_id", "is_default"]].rename(columns={
        "id": "pokemon_id", "identifier": "variete", "is_default": "is_default_variety"})
    table = forms.merge(varieties, on="pokemon_id", how="left", validate="many_to_one")
    species = data["pokemon_species"][["id", "identifier", "generation_id", "is_legendary", "is_mythical"]].rename(columns={
        "id": "species_id", "identifier": "espece", "generation_id": "generation_espece"})
    table = table.merge(species, on="species_id", how="left", validate="many_to_one")
    games = data["version_groups"][["id", "generation_id"]].rename(columns={"id": "version_group_id", "generation_id": "generation"})
    table = table.merge(games, on="version_group_id", how="left", validate="many_to_one")

    names = data["pokemon_species_names"]
    french = names.loc[names["local_language_id"].eq(5), ["pokemon_species_id", "name"]].rename(
        columns={"pokemon_species_id": "species_id", "name": "nom_fr"})
    english = names.loc[names["local_language_id"].eq(9), ["pokemon_species_id", "genus"]].rename(
        columns={"pokemon_species_id": "species_id", "genus": "genre_en"})
    table = table.merge(french, on="species_id", how="left", validate="many_to_one")
    table = table.merge(english, on="species_id", how="left", validate="many_to_one")

    stats = data["pokemon_stats"].merge(data["stats"][["id", "identifier"]],
        left_on="stat_id", right_on="id", validate="many_to_one")
    stats = stats.pivot(index="pokemon_id", columns="identifier", values="base_stat")
    table = table.merge(stats[STAT_NAMES], left_on="pokemon_id", right_index=True, how="left", validate="many_to_one")

    # Regrouper les slots de types avant la jointure évite de multiplier les formes.
    variety_types = data["pokemon_types"].sort_values("slot").groupby("pokemon_id")["type_id"].agg(list)
    form_types = data["pokemon_form_types"].sort_values("slot").groupby("pokemon_form_id")["type_id"].agg(list)
    types = table["form_id"].map(form_types).combine_first(table["pokemon_id"].map(variety_types))
    assert types.map(lambda values: isinstance(values, list) and 1 <= len(values) <= 2).all(), "Types absents ou invalides."
    french_types = data["type_names"].loc[data["type_names"]["local_language_id"].eq(5)].set_index("type_id")["name"]
    table["type_1_id"] = types.map(lambda values: values[0])
    table["type_2_id"] = types.map(lambda values: values[1] if len(values) == 2 else None)
    table["type_1"] = table["type_1_id"].map(french_types)
    table["type_2"] = table["type_2_id"].map(french_types)
    assert set(table["form_id"]) == set(data["pokemon_forms"]["id"]), "Formes perdues."
    return normalize_pokeapi_table(table[POKEAPI_COLUMNS])


def resource_id(resource):
    """Lire l'identifiant dans une adresse telle que .../pokemon/493/."""
    return int(resource["url"].rstrip("/").split("/")[-1])


def translated_value(entries, language, field):
    """Lire une traduction ; conserver une absence au lieu d'inventer un nom."""
    values = [entry[field] for entry in entries if entry["language"]["name"] == language]
    assert len(values) <= 1, "Traduction dupliquée."
    return values[0] if values else None


def json_fingerprint(data):
    """Empreinte d'un contenu JSON, indépendante de sa mise en page."""
    content = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_api_json(url, session, folder, config):
    """Réutiliser une réponse vérifiée ou la télécharger, sans cacher les erreurs HTTP."""
    filename = hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json"
    path = folder / "responses" / filename
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["url"] == url, "Adresse de cache incohérente."
        assert json_fingerprint(saved["data"]) == saved["sha256"], f"Cache API modifié : {path.name}."
        return saved["data"]

    # Une erreur arrête la collecte ; la relance réutilise les réponses déjà sauvegardées.
    response = session.get(url, timeout=config["timeout_seconds"])
    response.raise_for_status()
    data = response.json()
    assert isinstance(data, dict), f"Réponse JSON inattendue : {url}."
    saved = {"url": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
             "sha256": json_fingerprint(data), "data": data}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    time.sleep(config["pause_seconds"])
    return data


def list_api_forms(session, folder, config):
    """Parcourir toutes les pages de formes, sans limite de génération ni d'espèce."""
    url = config["base_url"].rstrip("/") + "/pokemon-form/?limit=1000"
    forms, visited = [], set()
    expected_count = None
    while url:
        assert url not in visited, "Boucle dans la pagination API."
        visited.add(url)
        page = get_api_json(url, session, folder, config)
        if expected_count is None:
            expected_count = page["count"]
        assert page["count"] == expected_count, "Le catalogue a changé pendant la pagination."
        forms.extend(page["results"])
        url = page["next"]
    ids = [resource_id(form) for form in forms]
    assert len(ids) == len(set(ids)) == expected_count, "Catalogue API incomplet ou dupliqué."
    return forms


def api_form_row(form, pokemon, species, games, type_names):
    """Stats de la variété, types et génération propres à la forme."""
    assert resource_id(form["pokemon"]) == pokemon["id"], "Variété incohérente."
    assert resource_id(pokemon["species"]) == species["id"], "Espèce incohérente."
    assert resource_id(form["version_group"]) == games["id"], "Groupe de jeux incohérent."
    stats = {entry["stat"]["name"]: entry["base_stat"] for entry in pokemon["stats"]}
    assert len(pokemon["stats"]) == 6 and set(stats) == set(STAT_NAMES), "Six statistiques attendues."
    # L'API fournit les types résolus de la forme, y compris Arceus et Silvallié.
    types = sorted(form["types"], key=lambda entry: entry["slot"])
    assert [entry["slot"] for entry in types] in [[1], [1, 2]], "Slots de types invalides."
    first = resource_id(types[0]["type"])
    second = resource_id(types[1]["type"]) if len(types) == 2 else None
    return {
        "form_id": form["id"], "pokemon_id": pokemon["id"], "species_id": species["id"],
        "forme": form["name"], "variete": pokemon["name"], "espece": species["name"],
        "nom_fr": translated_value(species["names"], "fr", "name"),
        "genre_en": translated_value(species["genera"], "en", "genus"),
        "version_group_id": games["id"], "generation": resource_id(games["generation"]),
        "generation_espece": resource_id(species["generation"]),
        "is_default_form": int(form["is_default"]), "is_default_variety": int(pokemon["is_default"]),
        "is_battle_only": int(form["is_battle_only"]), "is_mega": int(form["is_mega"]),
        "is_legendary": int(species["is_legendary"]), "is_mythical": int(species["is_mythical"]),
        **stats, "type_1_id": first, "type_2_id": second,
        "type_1": type_names[first], "type_2": type_names[second] if second is not None else None,
    }


def collect_pokeapi_api():
    """Collecter toutes les formes API, indépendamment des identifiants des CSV."""
    config = read_config()["pokeapi_api"]
    folder = PROJECT_DIR / "data" / "raw" / config["snapshot_id"]
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["base_url"] == config["base_url"], "API modifiée : choisir un nouvel instantané."
        if manifest["complete"]:
            missing = [name for name in manifest["response_files"] if not (folder / "responses" / name).exists()]
            assert not missing, "Réponses API manquantes : restaurer le cache ou choisir un nouvel instantané."
    else:
        manifest = {"snapshot_id": config["snapshot_id"], "base_url": config["base_url"],
                    "started_at_utc": datetime.now(timezone.utc).isoformat(), "complete": False}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    rows, type_names = [], {}
    with requests.Session() as session:
        session.headers.update({"User-Agent": "ENSAE-Pokemon-Project/1.0"})
        catalogue = list_api_forms(session, folder, config)
        print(f"Catalogue API : {len(catalogue)} formes. Les réponses en cache seront réutilisées.", flush=True)
        for number, reference in enumerate(catalogue, start=1):
            form = get_api_json(reference["url"], session, folder, config)
            assert form["id"] == resource_id(reference), "Identifiant de forme incohérent."
            pokemon = get_api_json(form["pokemon"]["url"], session, folder, config)
            species = get_api_json(pokemon["species"]["url"], session, folder, config)
            games = get_api_json(form["version_group"]["url"], session, folder, config)
            for item in form["types"]:
                type_id = resource_id(item["type"])
                if type_id not in type_names:
                    type_data = get_api_json(item["type"]["url"], session, folder, config)
                    type_names[type_id] = translated_value(type_data["names"], "fr", "name")
            rows.append(api_form_row(form, pokemon, species, games, type_names))
            if number % 100 == 0 or number == len(catalogue):
                print(f"Formes lues : {number}/{len(catalogue)}", flush=True)
    table = normalize_pokeapi_table(pd.DataFrame(rows))
    assert len(table) == len(catalogue), "Formes API perdues."
    if not manifest["complete"]:
        manifest.update({"complete": True, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                         "forms": len(table), "response_files": sorted(path.name for path in (folder / "responses").glob("*.json"))})
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return table


def compare_pokeapi(csv_table, api_table):
    """Comparer population et chaque cellule ; Showdown n'entre jamais dans ce contrôle."""
    csv_table = normalize_pokeapi_table(csv_table).set_index("form_id")
    api_table = normalize_pokeapi_table(api_table).set_index("form_id")
    only_csv = csv_table.index.difference(api_table.index)
    only_api = api_table.index.difference(csv_table.index)
    common = csv_table.index.intersection(api_table.index)
    differences = []
    for form_id in only_csv:
        differences.append({"form_id": form_id, "champ": "presence", "csv": csv_table.loc[form_id, "forme"], "api": None})
    for form_id in only_api:
        differences.append({"form_id": form_id, "champ": "presence", "csv": None, "api": api_table.loc[form_id, "forme"]})
    for column in csv_table.columns:
        left, right = csv_table.loc[common, column], api_table.loc[common, column]
        equal = left.eq(right).fillna(False) | (left.isna() & right.isna())
        for form_id in common[~equal]:
            differences.append({"form_id": form_id, "champ": column, "csv": left.loc[form_id], "api": right.loc[form_id]})
    details = pd.DataFrame(differences, columns=["form_id", "champ", "csv", "api"])
    summary = pd.Series({
        "Formes CSV": len(csv_table), "Formes API": len(api_table), "Formes communes": len(common),
        "Formes seulement CSV": len(only_csv), "Formes seulement API": len(only_api),
        "Colonnes comparées hors identifiant": len(csv_table.columns),
        "Cellules différentes sur les formes communes": len(details) - len(only_csv) - len(only_api),
    }, name="nombre").to_frame()
    return {"identiques": details.empty, "resume": summary, "ecarts": details}


def export_collections(csv_table, api_table, comparison):
    """Conserver les deux tables et le rapport, même lorsqu'il existe des écarts."""
    config = read_config()
    folder = PROJECT_DIR / "data" / "collected" / (config["snapshot_id"] + "_vs_" + config["pokeapi_api"]["snapshot_id"])
    folder.mkdir(parents=True, exist_ok=True)
    csv_table.to_csv(folder / "pokeapi_csv.csv", index=False, encoding="utf-8-sig")
    api_table.to_csv(folder / "pokeapi_api.csv", index=False, encoding="utf-8-sig")
    comparison["resume"].to_csv(folder / "comparaison_resume.csv", encoding="utf-8-sig")
    comparison["ecarts"].to_csv(folder / "comparaison_ecarts.csv", index=False, encoding="utf-8-sig")
    return folder
