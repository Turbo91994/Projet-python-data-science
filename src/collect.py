"""Collecte locale des sources brutes, sans filtrer ni regrouper les formes."""

from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib
import json

import pandas as pd


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
