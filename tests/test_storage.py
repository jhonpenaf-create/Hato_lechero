import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import storage


def animal(animal_id=1, arete="EXT-001", nombre="Luna"):
    return {
        "id": animal_id,
        "arete": arete,
        "nombre": nombre,
        "raza": "Holstein",
        "lactancia": 2,
        "peso_kg": 610.5,
        "fecha_parto": "2026-01-10",
        "estado_reproductivo": "vacía",
        "produccion_litros": 28.5,
        "condicion_corporal": 3.0,
        "fecha_ultima_inseminacion": None,
        "toro": None,
    }


class StoragePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

        os.environ["HATO_DATA_FILE"] = os.path.join(self.tmpdir.name, "hato_memoria.json")
        os.environ["HATO_DB_FILE"] = os.path.join(self.tmpdir.name, "hato_memoria.sqlite3")

    def test_round_trip_persists_in_local_sqlite_database(self):
        animales = [animal()]

        storage.guardar_animales_persistidos(animales)

        self.assertTrue(os.path.exists(os.environ["HATO_DB_FILE"]))
        self.assertEqual(storage.cargar_animales_persistidos(), animales)

    def test_legacy_json_is_imported_only_once(self):
        animales = [animal()]
        with open(os.environ["HATO_DATA_FILE"], "w", encoding="utf-8") as fh:
            json.dump(animales, fh)

        self.assertEqual(storage.cargar_animales_persistidos(), animales)
        storage.guardar_animales_persistidos([])
        self.assertEqual(storage.cargar_animales_persistidos(), [])

    def test_migrates_existing_single_user_database(self):
        db_file = os.environ["HATO_DB_FILE"]
        conn = sqlite3.connect(db_file)
        conn.execute(
            """
            CREATE TABLE animales (
                id INTEGER PRIMARY KEY,
                arete TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                raza TEXT NOT NULL,
                lactancia INTEGER NOT NULL,
                peso_kg REAL NOT NULL,
                fecha_parto TEXT NOT NULL,
                estado_reproductivo TEXT NOT NULL,
                produccion_litros REAL NOT NULL,
                condicion_corporal REAL NOT NULL,
                fecha_ultima_inseminacion TEXT,
                toro TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO animales VALUES (
                7, 'OLD-007', 'Mora', 'Jersey', 1, 420, '2026-02-01',
                'vacía', 20, 2.75, NULL, NULL
            )
            """
        )
        conn.commit()
        conn.close()

        expected = animal(7, "OLD-007", "Mora")
        expected.update({
            "lactancia": 1,
            "raza": "Jersey",
            "peso_kg": 420,
            "fecha_parto": "2026-02-01",
            "estado_reproductivo": "vacía",
            "produccion_litros": 20,
            "condicion_corporal": 2.75,
        })
        self.assertEqual(storage.cargar_animales_persistidos(), [expected])

    def test_users_are_isolated_and_can_reuse_animal_identifiers(self):
        first_user_animal = animal()
        second_user_animal = animal(nombre="Estrella")
        storage.crear_usuario("finca_dos", "Finca dos")

        storage.guardar_animales_persistidos([first_user_animal])
        storage.guardar_animales_persistidos([second_user_animal], "finca_dos")

        self.assertEqual(
            storage.cargar_animales_persistidos(),
            [first_user_animal],
        )
        self.assertEqual(
            storage.cargar_animales_persistidos("finca_dos"),
            [second_user_animal],
        )

    def test_empty_payload_deletes_all_animales_for_that_user(self):
        storage.guardar_animales_persistidos([animal()])

        storage.guardar_animales_persistidos([])

        self.assertEqual(storage.cargar_animales_persistidos(), [])

    def test_unknown_user_cannot_read_or_write_animales(self):
        with self.assertRaises(ValueError):
            storage.cargar_animales_persistidos("no_existe")
        with self.assertRaises(ValueError):
            storage.guardar_animales_persistidos([animal()], "no_existe")

    def test_duplicate_arete_is_rejected_within_one_user(self):
        with self.assertRaises(sqlite3.IntegrityError):
            storage.guardar_animales_persistidos([
                animal(1, "DUP-001"),
                animal(2, "DUP-001", "Otra vaca"),
            ])


if __name__ == "__main__":
    unittest.main()
