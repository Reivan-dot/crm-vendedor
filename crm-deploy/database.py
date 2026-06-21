# -*- coding: utf-8 -*-
import sqlite3, os, math

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crm.db")

def conectar():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def inicializar():
    con = conectar()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS vendedores (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            pin    TEXT NOT NULL,
            zona   TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS clientes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre       TEXT NOT NULL,
            direccion    TEXT DEFAULT '',
            lat          REAL,
            lon          REAL,
            vendedor_id  INTEGER REFERENCES vendedores(id),
            notas        TEXT DEFAULT '',
            dias_objetivo INTEGER DEFAULT 7
        );
        CREATE TABLE IF NOT EXISTS visitas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            vendedor_id  INTEGER NOT NULL REFERENCES vendedores(id),
            cliente_id   INTEGER NOT NULL REFERENCES clientes(id),
            lat_inicio   REAL,
            lon_inicio   REAL,
            lat_fin      REAL,
            lon_fin      REAL,
            hora_inicio  TEXT,
            hora_fin     TEXT,
            duracion_min INTEGER,
            fecha        TEXT,
            estado       TEXT DEFAULT 'activa'
        );
        CREATE TABLE IF NOT EXISTS encuestas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            visita_id    INTEGER NOT NULL REFERENCES visitas(id),
            cliente_id   INTEGER NOT NULL REFERENCES clientes(id),
            vendedor_id  INTEGER NOT NULL REFERENCES vendedores(id),
            hizo_pedido  INTEGER DEFAULT 0,
            monto        REAL,
            interes      TEXT,
            comentario   TEXT DEFAULT '',
            fecha        TEXT
        );
        CREATE TABLE IF NOT EXISTS productos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT NOT NULL,
            categoria TEXT DEFAULT '',
            precio    REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS compras (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id  INTEGER NOT NULL REFERENCES clientes(id),
            producto_id INTEGER NOT NULL REFERENCES productos(id),
            cantidad    INTEGER DEFAULT 1,
            monto       REAL DEFAULT 0,
            fecha       TEXT
        );
    """)

    # Migraciones: agregar columnas a DBs ya existentes sin perder datos
    def asegurar_columna(tabla, col, ddl):
        cols = [r["name"] for r in con.execute(f"PRAGMA table_info({tabla})")]
        if col not in cols:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {ddl}")

    asegurar_columna("clientes",  "giro",            "TEXT DEFAULT ''")
    asegurar_columna("clientes",  "codigo_externo",  "TEXT")     # código del Excel del gerente
    asegurar_columna("productos", "codigo_externo",  "TEXT")     # código de producto del Excel
    asegurar_columna("productos", "unidad",          "TEXT DEFAULT ''")

    con.commit()
    con.close()

def distancia_metros(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(2 * R * math.asin(math.sqrt(a)))
