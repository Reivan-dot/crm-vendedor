# -*- coding: utf-8 -*-
import subprocess, sys

def pip(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

for paquete in ["fastapi", "uvicorn", "openpyxl"]:
    try:
        __import__(paquete)
    except ImportError:
        pip(paquete)

from fastapi import FastAPI, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional
import uuid, os, socket
from datetime import datetime, date
import database

database.inicializar()


def _sembrar_si_vacio():
    """En un contenedor nuevo (Railway/nube) la base arranca vacía:
    siembra los datos demo y carga el Excel de ventas automáticamente."""
    con = database.conectar()
    try:
        n = con.execute("SELECT COUNT(*) c FROM vendedores").fetchone()["c"]
    except Exception:
        n = 0
    con.close()
    if n == 0:
        try:
            import datos_prueba            # al importarse, siembra demo (vendedores/clientes/productos)
            import importar_ventas
            importar_ventas.importar()      # carga el Excel real del gerente
            print("Datos iniciales sembrados (demo + Excel de ventas).")
        except Exception as e:
            print("Aviso: no se sembraron datos iniciales:", e)


_sembrar_si_vacio()

app = FastAPI(title="CRM GPS Vendedor")
sesiones: dict = {}  # token -> vendedor_id

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

@app.get("/")
def root():
    return RedirectResponse("/static/login.html")

# ── Modelos ────────────────────────────────────────────────────
class LoginData(BaseModel):
    vendedor_id: int
    pin: str

class CheckinData(BaseModel):
    cliente_id: int
    lat: float
    lon: float

class CheckoutData(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None

class EncuestaData(BaseModel):
    hizo_pedido: bool
    monto: Optional[float] = None
    interes: Optional[str] = None      # "alto" | "medio" | "bajo"
    comentario: Optional[str] = ""

# ── Auth ───────────────────────────────────────────────────────
def get_vendedor_id(x_token: str = Header(...)):
    vid = sesiones.get(x_token)
    if not vid:
        raise HTTPException(401, "Sesion invalida. Vuelve a iniciar sesion.")
    return vid

# ── Rutas ──────────────────────────────────────────────────────
@app.get("/api/vendedores")
def listar_vendedores():
    con = database.conectar()
    rows = con.execute("SELECT id, nombre, zona FROM vendedores ORDER BY nombre").fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/login")
def login(data: LoginData):
    con = database.conectar()
    row = con.execute(
        "SELECT id, nombre, zona FROM vendedores WHERE id=? AND pin=?",
        (data.vendedor_id, data.pin)
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(401, "PIN incorrecto.")
    token = str(uuid.uuid4())
    sesiones[token] = row["id"]
    return {"token": token, "nombre": row["nombre"], "zona": row["zona"], "vendedor_id": row["id"]}

@app.get("/api/mis-clientes")
def mis_clientes(x_token: str = Header(...)):
    vid = get_vendedor_id(x_token)
    hoy = date.today().isoformat()
    con = database.conectar()
    clientes = con.execute(
        "SELECT id, nombre, direccion, lat, lon, notas, dias_objetivo FROM clientes WHERE vendedor_id=? ORDER BY nombre",
        (vid,)
    ).fetchall()

    resultado = []
    for c in clientes:
        ultima = con.execute(
            "SELECT fecha FROM visitas WHERE cliente_id=? AND estado='completada' ORDER BY fecha DESC, hora_inicio DESC LIMIT 1",
            (c["id"],)
        ).fetchone()

        activa = con.execute(
            "SELECT id, hora_inicio FROM visitas WHERE cliente_id=? AND vendedor_id=? AND estado='activa' AND fecha=?",
            (c["id"], vid, hoy)
        ).fetchone()

        completada_hoy = con.execute(
            "SELECT id FROM visitas WHERE cliente_id=? AND vendedor_id=? AND estado='completada' AND fecha=?",
            (c["id"], vid, hoy)
        ).fetchone()

        dias_sin_visita = None
        if ultima:
            try:
                dias_sin_visita = (date.today() - date.fromisoformat(ultima["fecha"])).days
            except Exception:
                pass

        resultado.append({
            **dict(c),
            "ultima_visita": ultima["fecha"] if ultima else None,
            "dias_sin_visita": dias_sin_visita,
            "visita_activa_id": activa["id"] if activa else None,
            "visita_activa_hora": activa["hora_inicio"] if activa else None,
            "visitado_hoy": completada_hoy is not None,
        })

    con.close()
    return resultado

@app.post("/api/checkin")
def checkin(data: CheckinData, x_token: str = Header(...)):
    vid = get_vendedor_id(x_token)
    hoy = date.today().isoformat()
    hora = datetime.now().strftime("%H:%M:%S")

    con = database.conectar()
    cliente = con.execute(
        "SELECT id, nombre, lat, lon FROM clientes WHERE id=? AND vendedor_id=?",
        (data.cliente_id, vid)
    ).fetchone()
    if not cliente:
        con.close()
        raise HTTPException(404, "Cliente no encontrado.")

    distancia = database.distancia_metros(data.lat, data.lon, cliente["lat"], cliente["lon"])

    # Cancelar cualquier visita activa previa del día
    con.execute(
        "UPDATE visitas SET estado='cancelada' WHERE vendedor_id=? AND estado='activa' AND fecha=?",
        (vid, hoy)
    )

    cur = con.execute(
        "INSERT INTO visitas (vendedor_id, cliente_id, lat_inicio, lon_inicio, hora_inicio, fecha, estado) VALUES (?,?,?,?,?,?,'activa')",
        (vid, data.cliente_id, data.lat, data.lon, hora, hoy)
    )
    visita_id = cur.lastrowid
    con.commit()
    con.close()

    return {
        "visita_id": visita_id,
        "cliente": cliente["nombre"],
        "hora_inicio": hora,
        "distancia_metros": distancia,
        "alerta_distancia": distancia is not None and distancia > 300,
    }

@app.post("/api/checkout/{visita_id}")
def checkout(visita_id: int, data: CheckoutData, x_token: str = Header(...)):
    vid = get_vendedor_id(x_token)
    hora_fin = datetime.now().strftime("%H:%M:%S")

    con = database.conectar()
    visita = con.execute(
        "SELECT hora_inicio FROM visitas WHERE id=? AND vendedor_id=? AND estado='activa'",
        (visita_id, vid)
    ).fetchone()
    if not visita:
        con.close()
        raise HTTPException(404, "Visita no encontrada o ya terminada.")

    inicio = datetime.strptime(visita["hora_inicio"], "%H:%M:%S")
    fin    = datetime.strptime(hora_fin, "%H:%M:%S")
    duracion = max(0, int((fin - inicio).total_seconds() / 60))

    con.execute(
        "UPDATE visitas SET hora_fin=?, duracion_min=?, lat_fin=?, lon_fin=?, estado='completada' WHERE id=?",
        (hora_fin, duracion, data.lat, data.lon, visita_id)
    )
    con.commit()
    con.close()
    return {"hora_fin": hora_fin, "duracion_min": duracion}

@app.post("/api/encuesta/{visita_id}")
def guardar_encuesta(visita_id: int, data: EncuestaData, x_token: str = Header(...)):
    vid = get_vendedor_id(x_token)
    con = database.conectar()
    visita = con.execute(
        "SELECT cliente_id FROM visitas WHERE id=? AND vendedor_id=?",
        (visita_id, vid)
    ).fetchone()
    if not visita:
        con.close()
        raise HTTPException(404, "Visita no encontrada.")

    hizo = 1 if data.hizo_pedido else 0
    monto = data.monto if data.hizo_pedido else None
    existe = con.execute("SELECT id FROM encuestas WHERE visita_id=?", (visita_id,)).fetchone()
    if existe:
        con.execute(
            "UPDATE encuestas SET hizo_pedido=?, monto=?, interes=?, comentario=? WHERE visita_id=?",
            (hizo, monto, data.interes, data.comentario, visita_id)
        )
    else:
        con.execute(
            "INSERT INTO encuestas (visita_id, cliente_id, vendedor_id, hizo_pedido, monto, interes, comentario, fecha) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (visita_id, visita["cliente_id"], vid, hizo, monto, data.interes,
             data.comentario, date.today().isoformat())
        )
    con.commit()
    con.close()
    return {"ok": True}

@app.get("/api/sugerencias/{cliente_id}")
def sugerencias(cliente_id: int, x_token: str = Header(...)):
    vid = get_vendedor_id(x_token)
    con = database.conectar()
    cliente = con.execute(
        "SELECT id, nombre, giro FROM clientes WHERE id=? AND vendedor_id=?",
        (cliente_id, vid)
    ).fetchone()
    if not cliente:
        con.close()
        raise HTTPException(404, "Cliente no encontrado.")

    hoy = date.today()
    giro = cliente["giro"] or ""

    filas = con.execute(
        "SELECT p.id pid, p.nombre, p.unidad, p.codigo_externo codigo, c.cantidad, c.monto, c.fecha "
        "FROM compras c JOIN productos p ON p.id = c.producto_id "
        "WHERE c.cliente_id=? ORDER BY c.fecha",
        (cliente_id,)
    ).fetchall()
    con.close()

    # ── Última compra (renglones del día más reciente) ──
    ult_fecha = max((f["fecha"] for f in filas), default=None)
    ultima_compra = None
    if ult_fecha:
        items = [f for f in filas if f["fecha"] == ult_fecha]
        ultima_compra = {
            "fecha": ult_fecha,
            "dias": (hoy - date.fromisoformat(ult_fecha)).days,
            "items": [{"codigo": i["codigo"], "nombre": i["nombre"], "cantidad": i["cantidad"], "monto": i["monto"]} for i in items],
            "total": round(sum(i["monto"] for i in items), 2),
        }

    # ── Agrupar por producto: fechas de compra y cantidad por evento ──
    prod = {}
    for f in filas:
        p = prod.setdefault(f["pid"], {"codigo": f["codigo"], "nombre": f["nombre"], "unidad": f["unidad"] or "", "porfecha": {}})
        p["porfecha"][f["fecha"]] = p["porfecha"].get(f["fecha"], 0) + (f["cantidad"] or 0)

    # ── Clasificar por cadencia de resurtido ──
    resurtir = []        # ya toca / está por tocar resurtir
    dejo_de_pedir = []   # antes lo compraba y dejó de pedirlo
    for p in prod.values():
        fechas = sorted(date.fromisoformat(d) for d in p["porfecha"])
        eventos = len(fechas)
        dias_desde = (hoy - fechas[-1]).days
        qtys = list(p["porfecha"].values())
        cant_tipica = max(1, round(sum(qtys) / len(qtys)))

        cadencia = None
        if eventos >= 2:
            difs = [(fechas[i + 1] - fechas[i]).days for i in range(eventos - 1)]
            difs = [d for d in difs if d > 0]
            if difs:
                cadencia = max(1, round(sum(difs) / len(difs)))

        if cadencia:
            ratio = dias_desde / cadencia
            if ratio >= 3:
                dejo_de_pedir.append({"codigo": p["codigo"], "producto": p["nombre"], "hace_dias": dias_desde,
                                      "veces": eventos, "cada_dias": cadencia})
            elif ratio >= 0.8:
                resurtir.append({"codigo": p["codigo"], "producto": p["nombre"], "unidad": p["unidad"],
                                 "cada_dias": cadencia, "hace_dias": dias_desde,
                                 "veces": eventos, "cantidad_tipica": cant_tipica,
                                 "estado": "vencido" if ratio >= 1 else "pronto", "_r": ratio})
        elif dias_desde >= 90:
            dejo_de_pedir.append({"codigo": p["codigo"], "producto": p["nombre"], "hace_dias": dias_desde,
                                  "veces": eventos, "cada_dias": None})

    resurtir.sort(key=lambda x: -x["_r"])
    for r in resurtir:
        r.pop("_r", None)
    dejo_de_pedir.sort(key=lambda x: -x["hace_dias"])

    return {
        "cliente": cliente["nombre"],
        "giro": giro,
        "ultima_compra": ultima_compra,
        "resurtir": resurtir[:15],
        "dejo_de_pedir": dejo_de_pedir[:10],
    }

@app.get("/api/visitas/hoy")
def visitas_hoy(x_token: str = Header(...)):
    get_vendedor_id(x_token)
    hoy = date.today().isoformat()
    con = database.conectar()
    rows = con.execute("""
        SELECT v.id, v.hora_inicio, v.hora_fin, v.duracion_min, v.estado,
               v.lat_inicio, v.lon_inicio,
               c.nombre AS cliente, ve.nombre AS vendedor
        FROM visitas v
        JOIN clientes c  ON c.id  = v.cliente_id
        JOIN vendedores ve ON ve.id = v.vendedor_id
        WHERE v.fecha = ?
        ORDER BY v.hora_inicio DESC
    """, (hoy,)).fetchall()
    con.close()
    return [dict(r) for r in rows]

# ── Arranque ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # En la nube (Railway/Render) el puerto llega por la variable PORT
    port = int(os.environ.get("PORT", 8000))

    def mi_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
        finally:
            s.close()

    try:
        ip = mi_ip()
    except Exception:
        ip = "localhost"
    print("=" * 52)
    print("  CRM GPS VENDEDOR — Backend")
    print("=" * 52)
    print(f"\n  Tu PC:      http://localhost:{port}")
    print(f"  Celular:    http://{ip}:{port}  (misma WiFi)")
    print(f"\n  Ctrl+C para detener\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
