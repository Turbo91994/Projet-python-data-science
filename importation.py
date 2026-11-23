"""Lancer la collecte API seule ; le notebook compare aussi avec les CSV."""

from src.collect import PROJECT_DIR, collect_pokeapi_api, read_config


def Extraction_PokeAPI():
    """Conserver le nom initial avec une seule implémentation partagée."""
    return collect_pokeapi_api()


if __name__ == "__main__":
    # Importer ce fichier ne déclenche aucune requête.
    df = Extraction_PokeAPI()
    folder = PROJECT_DIR / "data" / "collected" / read_config()["pokeapi_api"]["snapshot_id"]
    folder.mkdir(parents=True, exist_ok=True)
    df.to_csv(folder / "pokeapi_api.csv", index=False, encoding="utf-8-sig")
    print(f"Collecte terminée : {len(df)} formes, {df['species_id'].nunique()} espèces.")
    print(df.head().to_string(index=False))
    print("Table enregistrée dans :", folder / "pokeapi_api.csv")
