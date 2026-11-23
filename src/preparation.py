"""Construire une ligne par forme et conserver la trace des enrichissements."""

import json
import hashlib
from datetime import datetime, timezone
import re
import unicodedata

import pandas as pd

from src.collect import PROJECT_DIR, read_config, normalize_pokeapi_table, STAT_NAMES

STAT_COLUMNS = STAT_NAMES


FINAL_STATS = ["pv", "attaque", "defense", "attaque_speciale", "defense_speciale", "vitesse"]
SHOWDOWN_STATS = ["hp", "atk", "def", "spa", "spd", "spe"]


def normalize_name(name):
    """Comparer les noms sans accents, espaces ou tirets (pas les statistiques)."""
    name = name.replace("♀", "f").replace("♂", "m")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub("[^a-z0-9]", "", name.lower())


def build_name_index(showdown):
    """Séparer noms directs et alias déclarés pour ne pas confondre leurs priorités."""
    direct, aliases = {}, {}
    for key, entry in showdown.items():
        for name in [key, entry["name"]]:
            direct.setdefault(normalize_name(name), set()).add(key)
        names = entry.get("cosmeticFormes", []).copy()
        if entry.get("baseForme"):
            names.append(entry["name"] + "-" + entry["baseForme"])
        for name in names:
            aliases.setdefault(normalize_name(name), set()).add(key)
    return direct, aliases


def match_form(name, direct, aliases, config):
    """Chercher une identité ou une représentation cosmétique explicitement décrite."""
    reason = "nom_direct"
    detail = "Identifiant ou nom Showdown, après normalisation."
    search_name = name
    if name in config["alias_formes"]:
        return config["alias_formes"][name], "alias_configure", config["motif_alias"]
    if name.startswith("alcremie-") and name.endswith("-sweet"):
        # Exemple : alcremie-ruby-cream-berry-sweet -> alcremie-ruby-cream.
        search_name = name.rsplit("-", 2)[0]
        reason, detail = "representation_cosmetique", config["motif_charmilly"]
    if name.startswith("minior-") and name.endswith("-meteor"):
        return "miniormeteor", "representation_cosmetique", config["motif_minior"]

    normalized = normalize_name(search_name)
    candidates = direct.get(normalized, set())
    if not candidates:
        candidates = aliases.get(normalized, set())
        if candidates and reason == "nom_direct":
            reason = "alias_declare_showdown"
            detail = "Nom déclaré dans baseForme ou cosmeticFormes."
    if len(candidates) == 1:
        return next(iter(candidates)), reason, detail
    if len(candidates) > 1:
        return None, "ambigu", "Plusieurs fiches portent ce nom normalisé."
    return None, "non_apparie", "Aucune correspondance de nom établie ; pas de repli sur l'espèce."


def resolve_tier(key, showdown):
    """Lire le tier, ou suivre une référence explicite selon les règles Showdown."""
    entry = showdown[key]
    if entry.get("tier"):
        return entry["tier"], key, "explicite"
    # Le moteur ne fait ce repli que lorsque les trois classements sont absents.
    if entry.get("doublesTier") or entry.get("natDexTier"):
        return None, None, "autre_classement_seulement"
    if entry.get("baseSpecies") == "Mimikyu":
        parent, rule = "mimikyu", "reference_mimikyu"
    elif key.endswith("totem"):
        parent, rule = key[:-5], "reference_totem"
    elif isinstance(entry.get("battleOnly"), str):
        parent, rule = normalize_name(entry["battleOnly"]), "reference_combat"
    elif entry.get("battleOnly"):
        return None, None, "references_combat_multiples"
    else:
        parent = normalize_name(entry.get("baseSpecies", ""))
        rule = "reference_baseSpecies"
    tier = showdown.get(parent, {}).get("tier")
    return tier, parent or None, rule if tier else "reference_sans_tier"


def read_preparation_config():
    """Lire le choix CSV/API et les correspondances documentées."""
    return json.loads((PROJECT_DIR / "config" / "preparation.json").read_text(encoding="utf-8"))


def prepare_database(pokeapi, showdown, source="csv"):
    """Enrichir la table commune CSV ou API ; ne pas lire l'autre collecte en secours."""
    assert source in ["csv", "api"], "Source attendue : csv ou api."
    config = read_preparation_config()
    forms = normalize_pokeapi_table(pokeapi).rename(columns={
        "forme": "form_name", "generation": "form_generation", "genre_en": "genus"})
    direct, aliases = build_name_index(showdown)
    assert set(config["alias_formes"].values()) <= set(showdown), "Alias Showdown absent."

    # Ces tags décrivent l'espèce : on conserve les preuves positives, même si
    # une forme n'a pas de fiche Showdown. Une absence de tag ne signifie pas « ordinaire ».
    tags_by_species = {}
    for key, entry in showdown.items():
        number = entry.get("num")
        if number is not None and number > 0:
            for tag in ["Paradox", "Ultra Beast"]:
                if tag in entry.get("tags", []):
                    tags_by_species.setdefault(number, {}).setdefault(tag, []).append(key)

    audit_rows = []
    for _, form in forms.iterrows():
        key, method, detail = match_form(form["form_name"], direct, aliases, config)
        entry = showdown.get(key, {})
        parent_key = normalize_name(entry.get("baseSpecies", ""))
        core_key = parent_key if entry.get("isCosmeticForme") else key
        core = showdown.get(core_key, {})
        number_ok = core.get("num") == form["species_id"] if key else pd.NA
        if key and not number_ok:
            # Conserver le candidat dans l'audit, mais ne rien en transférer.
            method = "espece_incompatible"
        stats_ok = types_ok = pd.NA
        stat_differences = []
        if key and core.get("baseStats"):
            for poke_stat, sd_stat in zip(STAT_COLUMNS, SHOWDOWN_STATS):
                if form[poke_stat] != core["baseStats"].get(sd_stat):
                    stat_differences.append(poke_stat)
            stats_ok = not stat_differences
        if key and core.get("types"):
            poke_types = {int(form["type_1_id"])}
            if pd.notna(form["type_2_id"]):
                poke_types.add(int(form["type_2_id"]))
            sd_types = {config["types_showdown"].get(name) for name in core["types"]}
            types_ok = poke_types == sd_types

        tier, tier_key, tier_rule = None, None, "sans_correspondance"
        if key and number_ok:
            tier, tier_key, tier_rule = resolve_tier(key, showdown)

        evidence = tags_by_species.get(form["species_id"], {})
        paradox_genus = pd.notna(form["genus"]) and form["genus"] == "Paradox Pokémon"
        paradox = paradox_genus or "Paradox" in evidence
        labels, tag_sources = [], []
        if form["is_legendary"] == 1:
            labels.append("Légendaire")
            tag_sources.append("pokemon_species.is_legendary")
        if form["is_mythical"] == 1:
            labels.append("Fabuleux")
            tag_sources.append("pokemon_species.is_mythical")
        if paradox:
            labels.append("Paradoxe")
            if paradox_genus:
                tag_sources.append("pokemon_species_names.genus (anglais)")
            if "Paradox" in evidence:
                tag_sources.append("Showdown: " + ", ".join(evidence["Paradox"]))
        if "Ultra Beast" in evidence:
            labels.append("Ultra-Chimère")
            tag_sources.append("Showdown: " + ", ".join(evidence["Ultra Beast"]))
        audit_rows.append({
            "form_id": form["form_id"], "forme": form["form_name"],
            "source_collecte": source, "source_generation": int(form["version_group_id"]),
            "source_types": "types résolus de la table commune " + source,
            "showdown_id": key, "methode_jointure": method, "explication_jointure": detail,
            "source_stats_showdown": core_key, "espece_concordante": number_ok,
            "stats_concordantes": stats_ok, "stats_divergentes": "; ".join(stat_differences) or None,
            "types_pokeapi": "; ".join(str(form[name]) for name in ["type_1", "type_2"] if pd.notna(form[name])),
            "types_showdown": "; ".join(core.get("types", [])) or None,
            "types_concordants": types_ok, "tier": tier, "source_tier": tier_key,
            "regle_tier": tier_rule, "tag": "; ".join(labels) or "Non étiqueté",
            "source_tag": "; ".join(tag_sources) or None,
            "tags_showdown_fiche": "; ".join(entry.get("tags", [])) or None,
        })
    audit = pd.DataFrame(audit_rows)
    for column in ["espece_concordante", "stats_concordantes", "types_concordants"]:
        audit[column] = audit[column].astype("boolean")

    columns = ["form_id", "pokemon_id", "species_id", "nom_fr", "form_name", "form_generation"]
    columns += STAT_COLUMNS + ["type_1", "type_2", "is_default_form", "is_battle_only", "is_mega"]
    base = forms[columns].rename(columns={
        "form_name": "forme", "form_generation": "generation", **dict(zip(STAT_COLUMNS, FINAL_STATS))})
    base["bst"] = base[FINAL_STATS].sum(axis=1)
    base = base.merge(audit[["form_id", "tag", "tier"]], on="form_id", how="left", validate="one_to_one")
    # Une divergence est visible dans l'audit ; elle ne remplace jamais les valeurs PokéAPI.
    validate_database(base, audit, pokeapi)
    return base, audit


def validate_database(base, audit, pokeapi):
    """Arrêter la préparation si des lignes sont perdues, dupliquées ou incomplètes."""
    assert base["form_id"].is_unique and audit["form_id"].is_unique, "Formes dupliquées."
    assert set(base["form_id"]) == set(pokeapi["form_id"]), "Population modifiée."
    assert set(audit["form_id"]) == set(base["form_id"]), "Audit incomplet."
    required = ["pokemon_id", "species_id", "nom_fr", "forme", "generation", "type_1"] + FINAL_STATS
    assert base[required].notna().all().all(), "Variable essentielle manquante."
    assert base[FINAL_STATS].ge(1).all().all(), "Statistique nulle ou négative."
    assert base["bst"].eq(base[FINAL_STATS].sum(axis=1)).all(), "Somme des statistiques incorrecte."
    # Vérifier que l'enrichissement n'a remplacé aucune donnée PokéAPI.
    original = normalize_pokeapi_table(pokeapi).rename(columns=dict(zip(STAT_COLUMNS, FINAL_STATS)))
    checked = ["form_id"] + required
    pd.testing.assert_frame_equal(base[checked].sort_values("form_id").reset_index(drop=True),
                                  original[checked], check_dtype=False)
    expected = audit.set_index("form_id").loc[base["form_id"], ["tag", "tier"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(base[["tag", "tier"]].reset_index(drop=True), expected)


def summarize_database(base, audit):
    """Présenter couverture et limites avant de commencer les analyses."""
    return pd.Series({
        "Formes conservées": len(base), "Espèces représentées": base["species_id"].nunique(),
        "Sans nom français": base["nom_fr"].isna().sum(),
        "Sans génération": base["generation"].isna().sum(),
        "Sans correspondance Showdown": audit["showdown_id"].isna().sum(),
        "Correspondances à une représentation cosmétique": audit["methode_jointure"].eq("representation_cosmetique").sum(),
        "Statistiques comparées": audit["stats_concordantes"].notna().sum(),
        "Divergences de statistiques": audit["stats_concordantes"].eq(False).sum(),
        "Types comparés": audit["types_concordants"].notna().sum(),
        "Divergences de types": audit["types_concordants"].eq(False).sum(),
        "Sans second type (mono-type)": base["type_2"].isna().sum(),
        "Type littéral ???": base["type_1"].eq("???").sum(),
        "Sans tier": base["tier"].isna().sum(),
        "Sans catégorie positive identifiée": base["tag"].eq("Non étiqueté").sum(),
    }, name="nombre").to_frame()


def export_database(base, audit, pokeapi):
    """Vérifier puis exporter la base, l'audit et leur provenance."""
    validate_database(base, audit, pokeapi)
    matched = audit.loc[audit["showdown_id"].notna()]
    checks = ["espece_concordante", "stats_concordantes", "types_concordants"]
    assert matched[checks].fillna(False).all().all(), "Rapprochement divergent ou non vérifiable : examiner l'audit avant l'export."
    assert audit["source_collecte"].nunique() == 1, "Plusieurs collectes mélangées."
    config = read_config()
    folder = PROJECT_DIR / "data" / "processed" / config["snapshot_id"]
    folder.mkdir(parents=True, exist_ok=True)
    base.to_csv(folder / "pokemon_forms.csv", index=False, encoding="utf-8-sig")
    audit.to_csv(folder / "audit_preparation.csv", index=False, encoding="utf-8-sig")

    # Empreintes pour retrouver les sources et les règles ayant produit ces sorties.
    source = audit["source_collecte"].iloc[0]
    paths = [PROJECT_DIR / "config/sources.json", PROJECT_DIR / "config/preparation.json",
             PROJECT_DIR / "src/collect.py", PROJECT_DIR / "src/preparation.py",
             PROJECT_DIR / "data/raw" / config["snapshot_id"] / "manifest.json"]
    if source == "api":
        paths.append(PROJECT_DIR / "data/raw" / config["pokeapi_api"]["snapshot_id"] / "manifest.json")
    paths += [folder / "pokemon_forms.csv", folder / "audit_preparation.csv"]
    fingerprints = {path.relative_to(PROJECT_DIR).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    provenance = {"exported_at_utc": datetime.now(timezone.utc).isoformat(), "source_pokeapi": source,
                  "snapshot_pokeapi": config["snapshot_id"] if source == "csv" else config["pokeapi_api"]["snapshot_id"],
                  "snapshot_showdown": config["snapshot_id"], "formes": len(base),
                  "colonnes": list(base.columns), "sha256": fingerprints}
    (folder / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return folder
