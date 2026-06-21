# -*- coding: utf-8 -*-
"""
Inserta vendedores, clientes, productos e historial de compras de prueba.
Corre:  python datos_prueba.py
"""
import database
from datetime import date, timedelta

database.inicializar()
con = database.conectar()

con.execute("DELETE FROM compras")
con.execute("DELETE FROM productos")
con.execute("DELETE FROM encuestas")
con.execute("DELETE FROM visitas")
con.execute("DELETE FROM clientes")
con.execute("DELETE FROM vendedores")
# Reiniciar IDs AUTOINCREMENT para que vendedores empiecen en 1 y 2
# (de lo contrario los clientes con vendedor_id fijo quedan huérfanos)
con.execute("DELETE FROM sqlite_sequence WHERE name IN "
            "('vendedores','clientes','visitas','encuestas','productos','compras')")

# ── Vendedores ─────────────────────────────────────────────────
con.execute("INSERT INTO vendedores (nombre, pin, zona) VALUES ('Juan Garcia',  '1234', 'Zona Norte')")
con.execute("INSERT INTO vendedores (nombre, pin, zona) VALUES ('Maria Lopez',  '5678', 'Zona Sur')")

# ── Clientes (nombre, dir, lat, lon, vendedor_id, notas, dias_objetivo, giro) ──
clientes = [
    ("Ferreteria ABC",      "Blvd. Zapata 123, Centro",     24.7890, -107.4280, 1, "Cliente frecuente, paga puntual", 7,  "ferreteria"),
    ("Tienda XYZ",          "Av. Obregon 456, Las Quintas", 24.7950, -107.4350, 1, "Interesado en nuevo catalogo",    7,  "abarrotes"),
    ("Distribuidora Norte", "Calle Angel Flores 789",        24.7820, -107.4400, 1, "Debe $3,500 — cobrar",            5,  "ferreteria"),
    ("Abarrotes La Fe",     "Calle Rosales 234",             24.7780, -107.4150, 1, "",                                10, "abarrotes"),
    ("Mini Super El Sol",   "Blvd. Constitucion 567",        24.8010, -107.4450, 1, "",                                14, "abarrotes"),
    ("Farmacia del Pueblo", "Av. Insurgentes 111",           24.7700, -107.4100, 2, "",                                7,  "farmacia"),
    ("Papeleria Escolar",   "Calle Donato Guerra 222",       24.7650, -107.4200, 2, "Temporada escolar proxima",       7,  "papeleria"),
    ("Tortilleria Lupita",  "Blvd. Pedro Infante 333",       24.7600, -107.4300, 2, "",                                10, "abarrotes"),
]
for c in clientes:
    con.execute(
        "INSERT INTO clientes (nombre, direccion, lat, lon, vendedor_id, notas, dias_objetivo, giro) "
        "VALUES (?,?,?,?,?,?,?,?)", c)

# ── Productos (nombre, categoria, precio) ──────────────────────
productos = [
    ("Clavos 2\" (kg)",       "ferreteria",  45),
    ("Pintura blanca 1gal",   "ferreteria", 320),
    ("Cemento gris 50kg",     "ferreteria", 215),
    ("Tubo PVC 1/2\"",        "ferreteria",  38),
    ("Cinta aislante",        "ferreteria",  18),
    ("Aceite 1L",             "abarrotes",   35),
    ("Azucar 1kg",            "abarrotes",   28),
    ("Refresco 600ml (caja)", "abarrotes",  180),
    ("Frijol 1kg",            "abarrotes",   42),
    ("Jabon barra (paq)",     "abarrotes",   55),
    ("Cuaderno profesional",  "papeleria",   32),
    ("Lapices (caja)",        "papeleria",   48),
    ("Hojas blancas (resma)", "papeleria",  120),
    ("Paracetamol (caja)",    "farmacia",    25),
    ("Alcohol 250ml",         "farmacia",    30),
    ("Vitaminas C (frasco)",  "farmacia",   150),
]
for p in productos:
    con.execute("INSERT INTO productos (nombre, categoria, precio) VALUES (?,?,?)", p)

# Mapas nombre -> id para sembrar compras
cli_id  = {r["nombre"]: r["id"] for r in con.execute("SELECT id, nombre FROM clientes")}
prod_id = {r["nombre"]: r["id"] for r in con.execute("SELECT id, nombre FROM productos")}
hoy = date.today()

def compra(cliente, producto, dias_atras, cantidad):
    fecha = (hoy - timedelta(days=dias_atras)).isoformat()
    precio = next(p[2] for p in productos if p[0] == producto)
    con.execute(
        "INSERT INTO compras (cliente_id, producto_id, cantidad, monto, fecha) VALUES (?,?,?,?,?)",
        (cli_id[cliente], prod_id[producto], cantidad, precio * cantidad, fecha))

# Historial: compras recientes + productos abandonados (>21 días) + productos nunca pedidos
# Ferreteria ABC — última compra hace 5 días; Cemento y Tubo abandonados; Cinta nunca comprada
compra("Ferreteria ABC", "Clavos 2\" (kg)",     5,  10)
compra("Ferreteria ABC", "Pintura blanca 1gal", 5,   3)
compra("Ferreteria ABC", "Cemento gris 50kg",  45,  20)
compra("Ferreteria ABC", "Tubo PVC 1/2\"",     68,  50)

# Tienda XYZ (abarrotes) — última hace 9 días; Frijol abandonado; Refresco/Jabon nunca
compra("Tienda XYZ", "Aceite 1L",  9, 24)
compra("Tienda XYZ", "Azucar 1kg", 9, 30)
compra("Tienda XYZ", "Frijol 1kg", 52, 20)

# Distribuidora Norte (ferreteria) — última hace 3 días; Pintura abandonada
compra("Distribuidora Norte", "Clavos 2\" (kg)", 3, 15)
compra("Distribuidora Norte", "Pintura blanca 1gal", 38, 5)
compra("Distribuidora Norte", "Cemento gris 50kg", 3, 10)

# Abarrotes La Fe — última hace 12 días; varios abandonados
compra("Abarrotes La Fe", "Aceite 1L", 12, 12)
compra("Abarrotes La Fe", "Refresco 600ml (caja)", 40, 8)
compra("Abarrotes La Fe", "Jabon barra (paq)", 75, 6)

# Mini Super El Sol — sin historial (cliente nuevo): probará el caso "sin compras previas"

# Clientes de Maria
compra("Farmacia del Pueblo", "Paracetamol (caja)", 6, 20)
compra("Farmacia del Pueblo", "Alcohol 250ml", 35, 15)
compra("Papeleria Escolar", "Cuaderno profesional", 8, 50)
compra("Papeleria Escolar", "Lapices (caja)", 48, 20)

con.commit()
con.close()

print("Datos de prueba insertados:")
print("  Juan Garcia  | PIN: 1234 | Zona Norte | 5 clientes")
print("  Maria Lopez  | PIN: 5678 | Zona Sur   | 3 clientes")
print(f"  {len(productos)} productos  |  historial de compras con fechas variadas")
