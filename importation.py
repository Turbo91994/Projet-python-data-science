
import requests
import json
import csv
import time

BASE_URL = "https://pokeapi.co/api/v2/"


def get_pokemon(pokemon_id):
    """Récupère les informations d'un Pokémon."""

    url = f"{BASE_URL}pokemon/{pokemon_id}"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        data = response.json()

        pokemon = {
            "id": data["id"],
            "name": data["name"],
            "height": data["height"],
            "weight": data["weight"],

            "types": [
                t["type"]["name"]
                for t in data["types"]
            ],

            "abilities": [
                a["ability"]["name"]
                for a in data["abilities"]
            ],

            "stats": {
                stat["stat"]["name"]: stat["base_stat"]
                for stat in data["stats"]
            },

            "sprite": data["sprites"]["front_default"]
        }

        return pokemon

    except requests.exceptions.RequestException as e:
        print(f"Erreur Pokémon {pokemon_id}: {e}")
        return None


def get_all_pokemon(limit=151):
    """Récupère plusieurs Pokémon."""

    pokemon_list = []

    for pokemon_id in range(1, limit + 1):

        print(f"Récupération du Pokémon {pokemon_id}/{limit}")

        pokemon = get_pokemon(pokemon_id)

        if pokemon:
            pokemon_list.append(pokemon)

        time.sleep(0.1)

    return pokemon_list


def save_json(data):
    """Enregistre les données en JSON."""

    with open("pokemon.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    print("Fichier pokemon.json créé !")


def save_csv(data):
    """Enregistre les données en CSV."""

    if not data:
        return

    with open("pokemon.csv", "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "id",
                "name",
                "height",
                "weight",
                "types",
                "abilities",
                "stats",
                "sprite"
            ]
        )

        writer.writeheader()

        for pokemon in data:
            row = pokemon.copy()

            row["types"] = ", ".join(row["types"])
            row["abilities"] = ", ".join(row["abilities"])
            row["stats"] = json.dumps(row["stats"])

            writer.writerow(row)

    print("Fichier pokemon.csv créé !")


if __name__ == "__main__":

    # Récupérer les 151 premiers Pokémon
    pokemons = get_all_pokemon(151)

    # Exporter les données
    save_json(pokemons)
    save_csv(pokemons)

    print(f"\nTerminé ! {len(pokemons)} Pokémon récupérés.")
