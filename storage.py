import json
import os
import sqlite3
from typing import Any, Dict, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_FILE = os.path.join(BASE_DIR, "hato_memoria.json")
DEFAULT_DB_FILE = os.path.join(BASE_DIR, "hato_memoria.sqlite3")
DEFAULT_USER_ID = "usuario_local"
DEFAULT_USER_NAME = "Usuario local"

ANIMAL_FIELDS = (
    "id",
    "arete",
    "nombre",
    "raza",
    "lactancia",
    "peso_kg",
    "fecha_parto",
    "estado_reproductivo",
    "produccion_litros",
    "condicion_corporal",
    "fecha_ultima_inseminacion",
    "toro",
)


def _storage_paths() -> tuple[str, str, str]:
    data_file = os.environ.get("HATO_DATA_FILE", DEFAULT_DATA_FILE)
    db_file = os.environ.get("HATO_DB_FILE", DEFAULT_DB_FILE)
    data_dir = os.path.dirname(data_file) or "."
    return data_file, db_file, data_dir


def _create_animales_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE animales (
            usuario_id TEXT NOT NULL REFERENCES usuarios(id),
            id INTEGER NOT NULL,
            arete TEXT NOT NULL,
            nombre TEXT NOT NULL,
            raza TEXT NOT NULL,
            lactancia INTEGER NOT NULL,
            peso_kg REAL NOT NULL,
            fecha_parto TEXT NOT NULL,
            estado_reproductivo TEXT NOT NULL,
            produccion_litros REAL NOT NULL,
            condicion_corporal REAL NOT NULL,
            fecha_ultima_inseminacion TEXT,
            toro TEXT,
            PRIMARY KEY (usuario_id, id),
            UNIQUE (usuario_id, arete)
        )
        """
    )


def _insert_animales(
    conn: sqlite3.Connection,
    usuario_id: str,
    animales: List[Dict[str, Any]],
) -> None:
    for animal in animales:
        values: list[Any] = [usuario_id]
        values.extend(animal.get(field) for field in ANIMAL_FIELDS)
        conn.execute(
            """
            INSERT INTO animales (
                usuario_id, id, arete, nombre, raza, lactancia, peso_kg,
                fecha_parto, estado_reproductivo, produccion_litros,
                condicion_corporal, fecha_ultima_inseminacion, toro
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO usuarios (id, nombre) VALUES (?, ?)",
        (DEFAULT_USER_ID, DEFAULT_USER_NAME),
    )

    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'animales'"
    ).fetchone()
    if not table_exists:
        _create_animales_table(conn)
        return

    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(animales)").fetchall()
    }
    if "usuario_id" in columns:
        return

    legacy_table = "animales_legacy_migration"
    legacy_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (legacy_table,),
    ).fetchone()
    if legacy_exists:
        raise RuntimeError(f"No se puede completar la migración: ya existe {legacy_table}.")

    conn.execute(f"ALTER TABLE animales RENAME TO {legacy_table}")
    _create_animales_table(conn)
    legacy_rows = conn.execute(
        f"SELECT * FROM {legacy_table} ORDER BY id"
    ).fetchall()
    _insert_animales(
        conn,
        DEFAULT_USER_ID,
        [{key: row[key] for key in row.keys()} for row in legacy_rows],
    )
    conn.execute(f"DROP TABLE {legacy_table}")
    conn.execute(
        "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)",
        ("importacion_json_completada", "1"),
    )


def _init_db() -> sqlite3.Connection:
    _, db_file, _ = _storage_paths()
    os.makedirs(os.path.dirname(db_file) or ".", exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            _ensure_schema(conn)
    except Exception:
        conn.close()
        raise
    return conn


def _validar_usuario(conn: sqlite3.Connection, usuario_id: str) -> None:
    if not usuario_id:
        raise ValueError("El identificador del usuario no puede estar vacío.")
    exists = conn.execute(
        "SELECT 1 FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    if not exists:
        raise ValueError(f"El usuario '{usuario_id}' no existe en la base de datos.")


def crear_usuario(usuario_id: str, nombre: str) -> None:
    """Crea un usuario para separar sus datos de los demás usuarios locales."""
    usuario_id = usuario_id.strip()
    nombre = nombre.strip()
    if not usuario_id or not nombre:
        raise ValueError("El identificador y el nombre del usuario son obligatorios.")

    conn = _init_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO usuarios (id, nombre) VALUES (?, ?)",
                (usuario_id, nombre),
            )
    finally:
        conn.close()


def _importar_json_legacy(conn: sqlite3.Connection) -> None:
    completed = conn.execute(
        "SELECT valor FROM configuracion WHERE clave = ?",
        ("importacion_json_completada",),
    ).fetchone()
    if completed:
        return

    data_file, _, _ = _storage_paths()
    if os.path.exists(data_file):
        with open(data_file, "r", encoding="utf-8") as fh:
            animales = json.load(fh)
        if not isinstance(animales, list):
            raise ValueError("El archivo JSON legado debe contener una lista de animales.")
        if not all(isinstance(animal, dict) for animal in animales):
            raise ValueError("El archivo JSON legado contiene registros no válidos.")

        has_animales = conn.execute(
            "SELECT 1 FROM animales WHERE usuario_id = ? LIMIT 1",
            (DEFAULT_USER_ID,),
        ).fetchone()
        if animales and not has_animales:
            _insert_animales(conn, DEFAULT_USER_ID, animales)

    conn.execute(
        "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)",
        ("importacion_json_completada", "1"),
    )


def cargar_animales_persistidos(
    usuario_id: str = DEFAULT_USER_ID,
) -> List[Dict[str, Any]]:
    conn = _init_db()
    try:
        with conn:
            _validar_usuario(conn, usuario_id)
            if usuario_id == DEFAULT_USER_ID:
                _importar_json_legacy(conn)
            rows = conn.execute(
                """
                SELECT id, arete, nombre, raza, lactancia, peso_kg, fecha_parto,
                       estado_reproductivo, produccion_litros, condicion_corporal,
                       fecha_ultima_inseminacion, toro
                FROM animales
                WHERE usuario_id = ?
                ORDER BY id
                """,
                (usuario_id,),
            ).fetchall()
        return [{field: row[field] for field in ANIMAL_FIELDS} for row in rows]
    finally:
        conn.close()


def guardar_animales_persistidos(
    animales: List[Dict[str, Any]],
    usuario_id: str = DEFAULT_USER_ID,
) -> None:
    conn = _init_db()
    try:
        with conn:
            _validar_usuario(conn, usuario_id)
            conn.execute(
                "DELETE FROM animales WHERE usuario_id = ?",
                (usuario_id,),
            )
            _insert_animales(conn, usuario_id, animales)
            if usuario_id == DEFAULT_USER_ID:
                conn.execute(
                    "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)",
                    ("importacion_json_completada", "1"),
                )
    finally:
        conn.close()
