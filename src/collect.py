"""Collecte locale des sources brutes, sans filtrer ni regrouper les formes."""

from datetime import datetime, timezone
from pathlib import Path
import concurrent.futures
import hashlib
import json
import time

import pandas as pd
import requests

from src.exploration import explore_forms, STAT_COLUMNS
from src.s3_backup import open_backup, read_remote_manifest, restore_file, save_missing_files


# collect.py est dans src/ ; la configuration et les données restent à la racine.
PROJECT_DIR = Path(__file__).resolve().parent.parent


def read_config():
    """Lire les adresses des sources et le nom de l'instantané."""
    path = PROJECT_DIR / "config" / "sources.json"
    return json.loads(path.read_text(encoding="utf-8"))


# Codes que le serveur renvoie en cas de panne passagère (522 = délai de connexion dépassé).
RETRY_STATUS = [500, 502, 503, 504, 520, 521, 522, 523, 524]


def fetch_once(url):
    """Une seule requête GET."""
    response = requests.get(url, timeout=(5, 15))
    response.raise_for_status()
    return response.content


def download_source(url, attempts=3, deadline=20):
    """Télécharger une source : au plus `attempts` tentatives, chacune coupée après `deadline` secondes.

    Le délai de `requests` ne limite pas la durée totale (DNS, réponse qui goutte à goutte) ;
    la requête est donc lancée dans un fil et abandonnée si elle dépasse `deadline`.
    """
    name = url.rstrip("/").split("/")[-1]
    last_error = None
    for attempt in range(1, attempts + 1):
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            content = pool.submit(fetch_once, url).result(timeout=deadline)
            assert content, f"Fichier téléchargé vide : {url}."
            return content
        except concurrent.futures.TimeoutError:
            last_error = requests.Timeout(f"aucune réponse après {deadline} s")
        except requests.HTTPError as error:
            last_error = error
            if error.response.status_code not in RETRY_STATUS:
                break  # inutile de réessayer une erreur 404, par exemple
        except requests.RequestException as error:
            last_error = error
        finally:
            pool.shutdown(wait=False)
        print(f"  Tentative {attempt}/{attempts} échouée pour {name} : {last_error}", flush=True)
        if attempt < attempts:
            time.sleep(2)
    raise last_error


def collect_sources():
    """Télécharger les fichiers absents ; vérifier et conserver ceux déjà présents.

    Si le site est en panne (erreur 522, par exemple) ou si la copie locale a disparu,
    la source est restaurée depuis la copie de secours S3, après vérification de son empreinte.
    """
    config = read_config()
    folder = PROJECT_DIR / "data" / "raw" / config["snapshot_id"]
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"snapshot_id": config["snapshot_id"], "files": {}}
    assert manifest["snapshot_id"] == config["snapshot_id"], "Instantané incohérent."

    backup = open_backup(config, config["snapshot_id"])
    remote_manifest = read_remote_manifest(backup) if backup else None

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
            saved = manifest["files"].get(source_id)
            content = None
            # Ne pas remplacer une copie datée perdue par une nouvelle version de l'API.
            if saved is None:
                try:
                    content = download_source(source["url"])
                    saved = {
                        "filename": path.name,
                        "download_url": source["url"],
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "size_bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                    print("Téléchargé :", path.name)
                except requests.RequestException as error:
                    print(f"Téléchargement impossible : {path.name} ({error}).")
            if content is None:
                restored = restore_file(backup, remote_manifest, source) if backup else None
                assert restored is not None, (
                    f"Fichier indisponible : {path.name}. Réessayer plus tard, restaurer l'instantané "
                    "depuis Git ou activer la copie de secours S3 (config/sources.json).")
                content, remote_entry = restored
                if saved is not None:
                    assert remote_entry["sha256"] == saved["sha256"], f"Copie S3 différente de la provenance locale : {path.name}."
                else:
                    saved = {**remote_entry, "restored_from": "s3"}
                print("Restauré depuis S3 :", path.name)
            path.write_bytes(content)
            manifest["files"][source_id] = saved
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if backup:
        # La copie de secours ne doit jamais bloquer la collecte.
        try:
            sent = save_missing_files(backup, folder, manifest, remote_manifest, config["sources"])
            print(f"Copie de secours S3 : {sent} fichier(s) ajouté(s).")
        except Exception as error:
            print(f"Copie de secours S3 non mise à jour ({type(error).__name__} : {error}).")
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
    """Vérifier les clés et les relations nécessaires aux jointures."""
    summary = []
    for source in read_config()["sources"]:
        table = data[source["id"]]
        assert len(table) > 0, f"Source vide : {source['id']}."
        if source["format"] == "csv":
            assert not table[source["key"]].isna().any().any(), f"Identifiant manquant : {source['id']}."
            assert not table.duplicated(source["key"]).any(), f"Identifiant répété : {source['id']}."
        summary.append({"source": source["id"], "lignes_ou_fiches": len(table)})

    varieties = data["pokemon"]
    forms = data["pokemon_forms"]
    stats = data["pokemon_stats"]
    assert varieties["species_id"].isin(data["pokemon_species"]["id"]).all(), "Espèce absente."
    assert forms["pokemon_id"].isin(varieties["id"]).all(), "Variété d'une forme absente."
    assert forms["introduced_in_version_group_id"].isin(data["version_groups"]["id"]).all(), "Groupe de jeux absent."
    expected = data["stats"].loc[data["stats"]["identifier"].isin(STAT_NAMES), "id"]
    assert len(expected) == 6 and set(stats["stat_id"]) == set(expected), "Dictionnaire des statistiques incomplet."
    counts = stats.groupby("pokemon_id").size().reindex(varieties["id"], fill_value=0)
    assert counts.eq(6).all(), "Une variété n'a pas ses six statistiques."
    assert stats["base_stat"].gt(0).all() and stats["base_stat"].mod(1).eq(0).all(), "Statistique invalide."
    assert data["pokemon_types"]["pokemon_id"].isin(varieties["id"]).all(), "Variété d'un type absente."
    assert data["pokemon_form_types"]["pokemon_form_id"].isin(forms["id"]).all(), "Forme d'un type absente."
    for table in [data["pokemon_types"], data["pokemon_form_types"]]:
        assert table["type_id"].isin(data["type_names"]["type_id"]).all(), "Type inconnu."
    print(f"Contrôles terminés : {len(forms)} formes conservées ; aucun filtre ni regroupement.")
    return pd.DataFrame(summary)


# La comparaison concerne ces informations du projet, pas tous les champs bruts.
STAT_NAMES = STAT_COLUMNS
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
    """Réutiliser les jointures de l'EDA, puis ajouter les libellés nécessaires."""
    table = explore_forms(data).rename(columns={
        "form_name": "forme", "variety_name": "variete", "species_name": "espece",
        "form_generation": "generation", "species_generation": "generation_espece"})
    species = data["pokemon_species"].set_index("id")
    table["is_legendary"] = table["species_id"].map(species["is_legendary"])
    table["is_mythical"] = table["species_id"].map(species["is_mythical"])

    names = data["pokemon_species_names"]
    french = names[names["local_language_id"] == 5].set_index("pokemon_species_id")
    english = names[names["local_language_id"] == 9].set_index("pokemon_species_id")
    table["nom_fr"] = table["species_id"].map(french["name"])
    table["genre_en"] = table["species_id"].map(english["genus"])

    # Prendre les types de la forme, sinon ceux de sa variété.
    types = table["explicit_form_types"].combine_first(table["variety_types"])
    names = data["type_names"]
    type_ids = names[names["local_language_id"] == 9].set_index("name")["type_id"]
    french_types = names[names["local_language_id"] == 5].set_index("type_id")["name"]
    for slot in [1, 2]:
        table[f"type_{slot}_id"] = types.str[slot - 1].map(type_ids)
        table[f"type_{slot}"] = table[f"type_{slot}_id"].map(french_types)
    return normalize_pokeapi_table(table[POKEAPI_COLUMNS])


def resource_id(resource):
    """Lire l'identifiant dans une adresse telle que .../pokemon/493/."""
    return int(resource["url"].rstrip("/").split("/")[-1])


def translated_value(entries, language, field):
    """Chercher la traduction demandée, ou garder une valeur manquante."""
    for entry in entries:
        if entry["language"]["name"] == language:
            return entry[field]
    return None


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