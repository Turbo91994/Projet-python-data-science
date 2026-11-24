"""Diagnostics exploratoires : aucune correction, exclusion ou export de données."""

import pandas as pd


STAT_COLUMNS = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]


def explore_forms(data):
    """Rattacher les informations aux formes, sans choisir de type final ni de fiche Showdown."""
    forms = data["pokemon_forms"].rename(columns={
        "id": "form_id", "identifier": "form_name", "is_default": "is_default_form"})
    varieties = data["pokemon"][["id", "identifier", "species_id", "is_default"]].rename(columns={
        "id": "pokemon_id", "identifier": "variety_name", "is_default": "is_default_variety"})
    forms = forms.merge(varieties, on="pokemon_id", how="left", validate="many_to_one")
    species = data["pokemon_species"][["id", "identifier", "generation_id"]].rename(columns={
        "id": "species_id", "identifier": "species_name", "generation_id": "species_generation"})
    forms = forms.merge(species, on="species_id", how="left", validate="many_to_one")

    named_stats = data["pokemon_stats"].merge(data["stats"][["id", "identifier"]],
        left_on="stat_id", right_on="id", how="left", validate="many_to_one")
    stats = named_stats.pivot(index="pokemon_id", columns="identifier", values="base_stat")
    forms = forms.merge(stats, left_on="pokemon_id", right_index=True, how="left", validate="many_to_one")

    games = data["version_groups"][["id", "identifier", "generation_id"]].rename(columns={
        "id": "version_group_id", "identifier": "introduction_games", "generation_id": "form_generation"})
    forms = forms.merge(games, left_on="introduced_in_version_group_id", right_on="version_group_id",
                        how="left", validate="many_to_one")

    # Regrouper les lignes de TYPES en listes évite de multiplier les lignes de FORMES.
    english_types = data["type_names"].loc[data["type_names"]["local_language_id"].eq(9), ["type_id", "name"]]
    variety_types = data["pokemon_types"].merge(english_types, on="type_id", how="left", validate="many_to_one")
    assert variety_types["name"].notna().all(), "Libellé de type de variété absent."
    variety_types = variety_types.sort_values(["pokemon_id", "slot"]).groupby("pokemon_id")["name"].agg(tuple)
    forms = forms.merge(variety_types.rename("variety_types"), left_on="pokemon_id", right_index=True,
                        how="left", validate="many_to_one")
    form_types = data["pokemon_form_types"].merge(english_types, on="type_id", how="left", validate="many_to_one")
    assert form_types["name"].notna().all(), "Libellé de type de forme absent."
    form_types = form_types.sort_values(["pokemon_form_id", "slot"]).groupby("pokemon_form_id")["name"].agg(tuple)
    forms = forms.merge(form_types.rename("explicit_form_types"), left_on="form_id", right_index=True,
                        how="left", validate="one_to_one")

    assert forms["form_id"].is_unique, "La jointure a multiplié des formes."
    assert set(forms["form_id"]) == set(data["pokemon_forms"]["id"]), "La population de formes a changé."
    assert forms[["pokemon_id", "species_id"]].notna().all().all(), "Rattachement incomplet."
    return forms


def summarize_forms(forms):
    """Compter les observations et les informations disponibles au niveau forme."""
    default_counts = forms.groupby("pokemon_id")["is_default_form"].sum()
    return pd.Series({
        "Formes": len(forms),
        "Identifiants de forme distincts": forms["form_id"].nunique(),
        "Variétés représentées": forms["pokemon_id"].nunique(),
        "Espèces représentées": forms["species_id"].nunique(),
        "Formes non définies par défaut": int(forms["is_default_form"].eq(0).sum()),
        "Formes Gigamax": int(forms["form_name"].str.endswith("-gmax").sum()),
        "Variétés sans forme par défaut": int(default_counts.eq(0).sum()),
        "Formes avec une statistique manquante": int(forms[STAT_COLUMNS].isna().any(axis=1).sum()),
        "Formes sans génération renseignée": int(forms["form_generation"].isna().sum()),
        "Formes datées avant leur espèce": int(forms["form_generation"].lt(forms["species_generation"]).sum()),
        "Formes sans types de variété": int(forms["variety_types"].isna().sum()),
        "Formes avec types propres explicites": int(forms["explicit_form_types"].notna().sum()),
    }, name="nombre").to_frame()


def summarize_species(forms):
    """Décrire la composition de l'inventaire sans modifier ses observations."""
    return forms.groupby(["species_id", "species_name"], as_index=False).agg(
        forms=("form_id", "size"), varieties=("pokemon_id", "nunique"))


def inspect_form_types(forms):
    """Repérer toutes les variétés ayant des types explicitement renseignés pour leurs formes."""
    variety_ids = forms.loc[forms["explicit_form_types"].notna(), "pokemon_id"].unique()
    return forms.loc[forms["pokemon_id"].isin(variety_ids),
                     ["form_id", "form_name", "pokemon_id", "variety_types", "explicit_form_types"]]


def missing_pokeapi(data):
    """Compter les cellules manquantes et les textes vides dans chaque table CSV."""
    rows = []
    for table_name, table in data.items():
        if isinstance(table, pd.DataFrame):
            for column in table.columns:
                missing = int(table[column].isna().sum())
                blank = int(table[column].astype("string").str.strip().eq("").sum())
                if missing or blank:
                    rows.append({"table": table_name, "champ": column, "lignes": len(table),
                                 "manquantes": missing, "texte_vide": blank,
                                 "pourcentage_manquant": round(100 * missing / len(table), 1)})
    return pd.DataFrame(rows, columns=["table", "champ", "lignes", "manquantes", "texte_vide", "pourcentage_manquant"])


def missing_pokeapi_context(data):
    """Chercher les répartitions qui aident à interpréter les absences PokéAPI."""
    species = data["pokemon_species"]
    varieties = data["pokemon"]
    names = data["pokemon_species_names"]
    habitat = species.assign(absent=species["habitat_id"].isna()).groupby("generation_id").agg(
        especes=("id", "size"), habitats_absents=("absent", "sum"))
    variety_missing = varieties.assign(experience_absente=varieties["base_experience"].isna(),
        ordre_absent=varieties["order"].isna()).groupby("is_default").agg(
        varietes=("id", "size"), experiences_absentes=("experience_absente", "sum"), ordres_absents=("ordre_absent", "sum"))
    translations = names.assign(nom_absent=names["name"].isna(), description_absente=names["genus"].isna()).groupby("local_language_id").agg(
        lignes=("pokemon_species_id", "size"), noms_absents=("nom_absent", "sum"), descriptions_absentes=("description_absente", "sum"))
    return {"habitat": habitat, "varieties": variety_missing, "translations": translations}



def missing_showdown(showdown):
    """Distinguer champ omis, valeur explicitement nulle et contenu vide dans le JSON."""
    fields = ["num", "baseStats", "types", "heightm", "weightkg", "tags", "tier", "gen", "baseSpecies", "forme"]
    rows = []
    for field in fields:
        absent = null = empty = 0
        for entry in showdown.values():
            if field not in entry:
                absent += 1
            elif entry[field] is None:
                null += 1
            elif entry[field] == [] or entry[field] == {} or (isinstance(entry[field], str) and entry[field].strip() == ""):
                empty += 1
        rows.append({"champ": field, "fiches": len(showdown), "champ_absent": absent,
                     "valeur_nulle": null, "contenu_vide": empty})
    return pd.DataFrame(rows)


def inspect_showdown_references(showdown):
    """Compter les références utiles et afficher les désaccords de tier."""
    by_name = {entry["name"]: entry for entry in showdown.values()}
    assert len(by_name) == len(showdown), "Nom Showdown ambigu."
    fields = ["num", "baseStats", "types", "heightm", "weightkg"]
    missing_core = cosmetic = complete_parent = missing_tags = parent_tags = 0
    tier_rows = []
    for key, entry in showdown.items():
        parent = by_name.get(entry.get("baseSpecies"), {})
        if any(field not in entry for field in fields):
            missing_core += 1
            cosmetic += bool(entry.get("isCosmeticForme"))
            complete_parent += all(parent.get(field) is not None for field in fields)
        if "tier" not in entry:
            battle = entry.get("battleOnly")
            battle_parent = by_name.get(battle, {}) if isinstance(battle, str) else {}
            tier_rows.append({"cle": key, "baseSpecies": entry.get("baseSpecies"),
                "battleOnly": battle, "tier_base": parent.get("tier"),
                "tier_combat": battle_parent.get("tier")})
        if "tags" not in entry:
            missing_tags += 1
            parent_tags += bool(parent.get("tags"))
    tiers = pd.DataFrame(tier_rows, columns=["cle", "baseSpecies", "battleOnly", "tier_base", "tier_combat"])
    conflicts = tiers[tiers["tier_combat"].notna() & tiers["tier_combat"].ne(tiers["tier_base"])]
    summary = pd.Series({
        "Fiches avec un champ commun absent": missing_core,
        "Dont explicitement cosmétiques": cosmetic,
        "Dont référence contenant les cinq champs": complete_parent,
        "Fiches sans tier explicite": len(tiers),
        "Dont tier disponible dans baseSpecies": tiers["tier_base"].notna().sum(),
        "Désaccords entre références de tier": len(conflicts),
        "Fiches sans champ tags": missing_tags,
        "Dont référence contenant des tags": parent_tags,
        "Fiches étiquetées Paradox": sum("Paradox" in e.get("tags", []) for e in showdown.values()),
        "Fiches étiquetées Ultra Beast": sum("Ultra Beast" in e.get("tags", []) for e in showdown.values()),
    }, name="nombre").to_frame()
    return {"summary": summary, "tier_conflicts": conflicts}


def inspect_showdown_candidates(forms, showdown):
    """Compter les candidats aux mêmes statistiques ; ce n'est pas une fusion validée."""
    mapping = {"hp": "hp", "attack": "atk", "defense": "def", "special-attack": "spa", "special-defense": "spd", "speed": "spe"}
    rows = []
    for key, entry in showdown.items():
        values = entry.get("baseStats", {})
        if entry.get("num", 0) > 0 and all(stat in values for stat in mapping.values()):
            row = {"showdown_key": key, "showdown_name": entry["name"], "species_id": entry["num"]}
            for stat, source_name in mapping.items():
                row[stat] = values[source_name]
            rows.append(row)
    keys = ["species_id"] + STAT_COLUMNS
    # Cette table de candidats est séparée de l'inventaire : ses répétitions ne lui sont pas ajoutées.
    candidates = forms[["form_id", "form_name"] + keys].merge(
        pd.DataFrame(rows, columns=["showdown_key", "showdown_name"] + keys),
        on=keys, how="left", validate="many_to_many")
    counts = candidates.groupby("form_id")["showdown_key"].count().rename("numeric_candidates")
    report = forms[["form_id", "form_name"]].merge(counts, on="form_id", how="left", validate="one_to_one")
    assert report["form_id"].is_unique and set(report["form_id"]) == set(forms["form_id"])
    summary = pd.Series({
        "Formes sans candidat numérique": int(report["numeric_candidates"].eq(0).sum()),
        "Formes avec un candidat numérique": int(report["numeric_candidates"].eq(1).sum()),
        "Formes avec plusieurs candidats numériques": int(report["numeric_candidates"].gt(1).sum()),
    }, name="nombre").to_frame()
    return {"summary": summary, "candidates": candidates}
