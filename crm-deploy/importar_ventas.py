# -*- coding: utf-8 -*-
"""
Importa el Excel de ventas del gerente a la base de datos.
- Separa por código de cliente (col 3) → tabla clientes
- Productos (col 7/8) → tabla productos
- Cada renglón → tabla compras (historial)

Uso directo:  python importar_ventas.py [ruta.xlsx]
Reutilizable:  from importar_ventas import importar; importar(ruta, vendedor_id=1)

El formato esperado del Excel (sin encabezados), por renglón de factura:
  0 folio | 1 tipo | 2 fecha | 3 cod_cliente | 4 nombre_cliente |
  5,6 (vacías) | 7 cod_producto | 8 descripcion | 9 cantidad |
  10 unidad | 11 precio | 12 importe | 13 descuento%
"""
import os, sys, subprocess
try:
    import openpyxl
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl", "-q"])
    import openpyxl

import database

RUTA_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "hoja.de.ventas", "HV.xlsx")


def _texto(v):
    return ("" if v is None else str(v)).strip()


def importar(ruta=RUTA_DEFAULT, vendedor_id=1):
    database.inicializar()
    wb = openpyxl.load_workbook(ruta, data_only=True)
    ws = wb.active

    con = database.conectar()
    cur = con.cursor()

    clientes_vistos = {}   # cod_externo -> cliente_id
    productos_vistos = {}  # cod_externo -> producto_id
    filas_compra = []      # (cod_cli, cod_prod, cantidad, monto, fecha)
    descartadas = 0

    for row in ws.iter_rows(values_only=True):
        if not row or row[0] is None:
            continue
        fecha    = row[2]
        cod_cli  = _texto(row[3])
        nom_cli  = _texto(row[4])
        cod_prod = _texto(row[7])
        desc     = _texto(row[8])
        cant     = row[9]
        unidad   = _texto(row[10])
        precio   = row[11]
        importe  = row[12]

        if not cod_cli or not cod_prod or fecha is None:
            descartadas += 1
            continue
        fecha_iso = fecha.date().isoformat() if hasattr(fecha, "date") else str(fecha)

        # ── Cliente (upsert por codigo_externo) ──
        if cod_cli not in clientes_vistos:
            r = cur.execute("SELECT id FROM clientes WHERE codigo_externo=?", (cod_cli,)).fetchone()
            if r:
                cid = r["id"]
                cur.execute("UPDATE clientes SET nombre=? WHERE id=?", (nom_cli, cid))
            else:
                cur.execute(
                    "INSERT INTO clientes (nombre, vendedor_id, giro, codigo_externo) VALUES (?,?,?,?)",
                    (nom_cli, vendedor_id, "autopartes", cod_cli))
                cid = cur.lastrowid
            clientes_vistos[cod_cli] = cid

        # ── Producto (upsert por codigo_externo) ──
        if cod_prod not in productos_vistos:
            r = cur.execute("SELECT id FROM productos WHERE codigo_externo=?", (cod_prod,)).fetchone()
            if r:
                pid = r["id"]
                cur.execute("UPDATE productos SET nombre=?, precio=?, unidad=? WHERE id=?",
                            (desc, precio or 0, unidad, pid))
            else:
                cur.execute(
                    "INSERT INTO productos (nombre, categoria, precio, unidad, codigo_externo) VALUES (?,?,?,?,?)",
                    (desc, "autopartes", precio or 0, unidad, cod_prod))
                pid = cur.lastrowid
            productos_vistos[cod_prod] = pid

        filas_compra.append((clientes_vistos[cod_cli], productos_vistos[cod_prod],
                             cant or 0, importe or 0, fecha_iso))

    # ── Reemplazar compras de los clientes importados (idempotente) ──
    ids = list(clientes_vistos.values())
    if ids:
        marcas = ",".join("?" * len(ids))
        cur.execute(f"DELETE FROM compras WHERE cliente_id IN ({marcas})", ids)
    cur.executemany(
        "INSERT INTO compras (cliente_id, producto_id, cantidad, monto, fecha) VALUES (?,?,?,?,?)",
        filas_compra)

    con.commit()
    con.close()

    return {
        "clientes": len(clientes_vistos),
        "productos": len(productos_vistos),
        "compras": len(filas_compra),
        "descartadas": descartadas,
    }


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else RUTA_DEFAULT
    print(f"Importando: {ruta}")
    res = importar(ruta)
    print(f"  Clientes cargados : {res['clientes']}")
    print(f"  Productos cargados: {res['productos']}")
    print(f"  Renglones compra  : {res['compras']}")
    print(f"  Filas descartadas : {res['descartadas']}")
