"""Contrôles reproductibles : aucune requête réseau réelle dans ces tests."""

import copy
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import requests

from src import collect


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.url = "https://pokeapi.co/api/v2/"
        self.config = {"base_url": self.url, "snapshot_id": "api_test",
                       "timeout_seconds": 30, "pause_seconds": 0}

    def resource(self, endpoint, identifier):
        return {"name": str(identifier), "url": f"{self.url}{endpoint}/{identifier}/"}

    def fixture(self):
        # Deux formes d'une espèce de génération 1, dont une introduite en génération 8.
        form = {"id": 6, "name": "charizard", "pokemon": self.resource("pokemon", 6),
                "version_group": self.resource("version-group", 1), "is_default": True,
                "is_battle_only": False, "is_mega": False,
                "types": [{"slot": 1, "type": self.resource("type", 10)}]}
        pokemon = {"id": 6, "name": "charizard", "species": self.resource("pokemon-species", 6),
                   "is_default": True,
                   "stats": [{"stat": {"name": name}, "base_stat": 78} for name in collect.STAT_NAMES]}
        species = {"id": 6, "name": "charizard", "generation": self.resource("generation", 1),
                   "is_legendary": False, "is_mythical": False,
                   "names": [{"language": {"name": "fr"}, "name": "Dracaufeu"}],
                   "genera": [{"language": {"name": "en"}, "genus": "Flame Pokémon"}]}
        games = {"id": 1, "generation": self.resource("generation", 1)}
        return form, pokemon, species, games

    def table(self):
        row = collect.api_form_row(*self.fixture(), {10: "Feu"})
        return collect.normalize_pokeapi_table(pd.DataFrame([row]))

    def test_generation_forme_et_statistiques_variete(self):
        form, pokemon, species, games = self.fixture()
        form.update(name="charizard-gmax", is_default=False)
        games["generation"] = self.resource("generation", 8)
        row = collect.api_form_row(form, pokemon, species, games, {10: "Feu"})
        self.assertEqual(row["generation"], 8)
        self.assertEqual(row["generation_espece"], 1)
        self.assertEqual(row["hp"], 78)
        self.assertEqual(row["is_default_form"], 0)
        self.assertEqual(row["is_default_variety"], 1)
        self.assertIsNone(row["type_2_id"])

    def test_comparaison_signale_valeur_absence_et_forme_manquante(self):
        table = self.table()
        self.assertTrue(collect.compare_pokeapi(table, table)["identiques"])
        changed = table.copy()
        changed.loc[0, "hp"] = 79
        changed.loc[0, "nom_fr"] = pd.NA
        result = collect.compare_pokeapi(table, changed)
        self.assertFalse(result["identiques"])
        self.assertEqual(set(result["ecarts"]["champ"]), {"hp", "nom_fr"})
        added = table.copy()
        added.loc[0, "form_id"] = 99999
        result = collect.compare_pokeapi(table, added)
        self.assertEqual(result["ecarts"]["champ"].tolist(), ["presence", "presence"])
        duplicated = pd.concat([table, table])
        with self.assertRaisesRegex(AssertionError, "dupliqué"):
            collect.compare_pokeapi(table, duplicated)

    def test_erreur_http_ne_cree_pas_de_cache(self):
        session = MagicMock()
        session.get.return_value.raise_for_status.side_effect = requests.HTTPError("503")
        with self.assertRaises(requests.HTTPError):
            collect.get_api_json(self.url, session, self.folder, self.config)
        self.assertEqual(list(self.folder.rglob("*.json")), [])

    def test_cache_reutilise_et_modification_detectee(self):
        session = MagicMock()
        session.get.return_value.json.return_value = {"id": 6}
        first = collect.get_api_json(self.url, session, self.folder, self.config)
        second = collect.get_api_json(self.url, session, self.folder, self.config)
        self.assertEqual(first, second)
        self.assertEqual(session.get.call_count, 1)
        path = next(self.folder.rglob("*.json"))
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved["data"]["id"] = 7
        path.write_text(json.dumps(saved), encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "Cache API modifié"):
            collect.get_api_json(self.url, session, self.folder, self.config)

    def test_collecte_complete_pagination_reprise_hors_ligne(self):
        form, pokemon, species, games = self.fixture()
        gmax, gmax_pokemon, gmax_games = copy.deepcopy(form), copy.deepcopy(pokemon), copy.deepcopy(games)
        gmax.update(id=10365, name="charizard-gmax", pokemon=self.resource("pokemon", 10196),
                    version_group=self.resource("version-group", 20), is_battle_only=True)
        gmax_pokemon.update(id=10196, name="charizard-gmax", is_default=False)
        gmax_games.update(id=20, generation=self.resource("generation", 8))
        first_page = self.url + "pokemon-form/?limit=1000"
        second_page = self.url + "pokemon-form/?offset=1&limit=1000"
        payloads = {
            first_page: {"count": 2, "results": [self.resource("pokemon-form", 6)], "next": second_page},
            second_page: {"count": 2, "results": [self.resource("pokemon-form", 10365)], "next": None},
            self.resource("pokemon-form", 6)["url"]: form,
            self.resource("pokemon-form", 10365)["url"]: gmax,
            self.resource("pokemon", 6)["url"]: pokemon,
            self.resource("pokemon", 10196)["url"]: gmax_pokemon,
            self.resource("pokemon-species", 6)["url"]: species,
            self.resource("version-group", 1)["url"]: games,
            self.resource("version-group", 20)["url"]: gmax_games,
            self.resource("type", 10)["url"]: {"names": [{"language": {"name": "fr"}, "name": "Feu"}]},
        }
        session = MagicMock()
        session.__enter__.return_value = session

        def respond(url, timeout):
            response = MagicMock()
            response.json.return_value = payloads[url]  # Toute URL inventée fait échouer le test.
            return response

        session.get.side_effect = respond
        with patch.object(collect, "PROJECT_DIR", self.folder), patch.object(collect, "read_config", return_value={"pokeapi_api": self.config}), patch.object(collect.requests, "Session", return_value=session):
            first = collect.collect_pokeapi_api()
            self.assertEqual(first["form_id"].tolist(), [6, 10365])
            self.assertEqual(first["generation"].tolist(), [1, 8])
            self.assertEqual(session.get.call_count, len(payloads))
            session.get.side_effect = AssertionError("Aucun accès réseau attendu avec un cache complet")
            second = collect.collect_pokeapi_api()
            pd.testing.assert_frame_equal(first, second)
            cache_file = next((self.folder / "data/raw/api_test/responses").glob("*.json"))
            cache_file.unlink()
            with self.assertRaisesRegex(AssertionError, "Réponses API manquantes"):
                collect.collect_pokeapi_api()

    def test_pagination_incomplete_refusee(self):
        page = {"count": 2, "results": [self.resource("pokemon-form", 6)], "next": None}
        with patch.object(collect, "get_api_json", return_value=page):
            with self.assertRaisesRegex(AssertionError, "Catalogue API incomplet"):
                collect.list_api_forms(MagicMock(), self.folder, self.config)

    def test_importation_ne_lance_pas_de_collecte(self):
        with patch.object(collect, "collect_pokeapi_api", side_effect=AssertionError("Appel inattendu")):
            import importation
            importlib.reload(importation)


if __name__ == "__main__":
    unittest.main()
