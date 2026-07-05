import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import storage


class StoragePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

        os.environ["HATO_DATA_FILE"] = os.path.join(self.tmpdir.name, "hato_memoria.json")
        os.environ["HATO_DB_FILE"] = os.path.join(self.tmpdir.name, "hato_memoria.sqlite3")
        storage.DATA_FILE = os.environ["HATO_DATA_FILE"]
        storage.DB_FILE = os.environ["HATO_DB_FILE"]
        storage.DATA_DIR = os.path.dirname(storage.DATA_FILE)

    def test_round_trip_persists_animales(self):
        animales = [{
            "id": 99,
            "arete": "EXT-001",
            "nombre": "Luna",
            "raza": "Holstein",
            "lactancia": 2,
            "peso_kg": 610.5,
            "fecha_parto": "2026-01-10",
            "estado_reproductivo": "vacía",
            "produccion_litros": 28.5,
            "condicion_corporal": 3.0,
            "fecha_ultima_inseminacion": None,
            "toro": None,
        }]

        storage.guardar_animales_persistidos(animales)

        self.assertTrue(os.path.exists(storage.DATA_FILE))
        self.assertEqual(storage.cargar_animales_persistidos(), animales)

        with open(storage.DATA_FILE, "r", encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), animales)


if __name__ == "__main__":
    unittest.main()
