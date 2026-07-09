import json
import os
import sqlite3
from typing import Any, Dict, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_FILE = os.path.join(BASE_DIR, "hato_memoria.json")
DEFAULT_DB_FILE = os.path.join(BASE_DIR, "hato_memoria.sqlite3")


def _storage_paths() -> tuple[str, str, str]:
    data_file = os.environ.get("HATO_DATA_FILE", DEFAULT_DATA_FILE)
    db_file = os.environ.get("HATO_DB_FILE", DEFAULT_DB_FILE)
    data_dir = os.path.dirname(data_file) or "."
    return data_file, db_file, data_dir


def _ensure_storage_dir() -> None:
    _, _, data_dir = _storage_paths()
    os.makedirs(data_dir, exist_ok=True)


def _init_db() -> sqlite3.Connection:
    _ensure_storage_dir()
    _, db_file, _ = _storage_paths()
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS animales (
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
    conn.commit()
    return conn


def cargar_animales_persistidos() -> List[Dict[str, Any]]:
    _ensure_storage_dir()

    _, db_file, _ = _storage_paths()
    if os.path.exists(db_file):
        try:
            conn = _init_db()
            rows = conn.execute(
                "SELECT id, arete, nombre, raza, lactancia, peso_kg, fecha_parto, estado_reproductivo, produccion_litros, condicion_corporal, fecha_ultima_inseminacion, toro FROM animales ORDER BY id"
            ).fetchall()
            conn.close()
            if rows:
                return [
                    {
                        "id": row[0],
                        "arete": row[1],
                        "nombre": row[2],
                        "raza": row[3],
                        "lactancia": row[4],
                        "peso_kg": row[5],
                        "fecha_parto": row[6],
                        "estado_reproductivo": row[7],
                        "produccion_litros": row[8],
                        "condicion_corporal": row[9],
                        "fecha_ultima_inseminacion": row[10],
                        "toro": row[11],
                    }
                    for row in rows
                ]
        except Exception:
            pass

    data_file, _, _ = _storage_paths()
    if os.path.exists(data_file):
        try:
            with open(data_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    return data
        except Exception:
            pass

    return []


def _guardar_json(animales: List[Dict[str, Any]], data_file: str) -> None:
    temp_path = f"{data_file}.tmp"
    with open(temp_path, "w", encoding="utf-8") as fh:
        json.dump(animales, fh, indent=2, ensure_ascii=False)
    os.replace(temp_path, data_file)


def guardar_animales_persistidos(animales: List[Dict[str, Any]]) -> None:
    _ensure_storage_dir()

    db_error = None
    try:
        conn = _init_db()
        conn.execute("DELETE FROM animales")

        for animal in animales:
            conn.execute(
                """
                INSERT INTO animales (
                    id, arete, nombre, raza, lactancia, peso_kg, fecha_parto, estado_reproductivo,
                    produccion_litros, condicion_corporal, fecha_ultima_inseminacion, toro
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    animal.get("id"),
                    animal.get("arete"),
                    animal.get("nombre"),
                    animal.get("raza"),
                    animal.get("lactancia"),
                    animal.get("peso_kg"),
                    animal.get("fecha_parto"),
                    animal.get("estado_reproductivo"),
                    animal.get("produccion_litros"),
                    animal.get("condicion_corporal"),
                    animal.get("fecha_ultima_inseminacion"),
                    animal.get("toro"),
                ),
            )

        conn.commit()
        conn.close()
    except Exception as exc:
        db_error = exc

    data_file, _, _ = _storage_paths()
    try:
        _guardar_json(animales, data_file)
    except Exception as exc:
        if db_error is None:
            raise exc

    if db_error is not None:
        return
