import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="Stock de Fundas", page_icon="📱", layout="wide")

DB_PATH = Path("stock_fundas.db")
UPLOAD_DIR = Path("imagenes")
UPLOAD_DIR.mkdir(exist_ok=True)

def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                model TEXT DEFAULT '',
                photo TEXT DEFAULT '',
                wholesale INTEGER NOT NULL DEFAULT 0,
                retail INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                movement TEXT NOT NULL,
                created_at TEXT NOT NULL,
                note TEXT DEFAULT ''
            )
        """)

init_db()

st.title("📱 Stock de fundas")
st.caption("Control sencillo de stock mayorista y minorista")

with st.sidebar:
    st.header("Menú")
    page = st.radio("Ir a", ["Productos y stock", "Registrar venta", "Historial"])

if page == "Productos y stock":
    st.subheader("Agregar producto")
    with st.form("new_product", clear_on_submit=True):
        name = st.text_input("Nombre del producto *", placeholder="Ej.: Funda transparente iPhone 15")
        model = st.text_input("Modelo compatible", placeholder="Ej.: iPhone 15 / 15 Pro")
        photo = st.file_uploader("Foto de referencia (opcional)", type=["png", "jpg", "jpeg", "webp"])
        c1, c2 = st.columns(2)
        with c1:
            wholesale = st.number_input("Stock mayorista inicial", min_value=0, step=1)
        with c2:
            retail = st.number_input("Stock minorista inicial", min_value=0, step=1)
        submit = st.form_submit_button("Guardar producto", type="primary")
        if submit:
            if not name.strip():
                st.error("Escribí el nombre del producto.")
            else:
                photo_path = ""
                if photo:
                    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{Path(photo.name).name}"
                    photo_path = str(UPLOAD_DIR / safe_name)
                    with open(photo_path, "wb") as f:
                        f.write(photo.getbuffer())
                with connect() as con:
                    con.execute("INSERT INTO products(name, model, photo, wholesale, retail) VALUES (?, ?, ?, ?, ?)",
                                (name.strip(), model.strip(), photo_path, int(wholesale), int(retail)))
                st.success("Producto guardado.")
                st.rerun()

    st.divider()
    st.subheader("Buscar y ver stock")
    search = st.text_input("Buscar por nombre o modelo", placeholder="Escribí iPhone 15, transparente...")
    with connect() as con:
        df = pd.read_sql_query("SELECT * FROM products ORDER BY name", con)
    if search:
        df = df[df["name"].str.contains(search, case=False, na=False) |
                df["model"].str.contains(search, case=False, na=False)]
    if df.empty:
        st.info("Todavía no hay productos para mostrar. Agregá el primero arriba.")
    else:
        st.metric("Productos registrados", len(df))
        for _, product in df.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([1, 3])
                with c1:
                    if product["photo"] and Path(product["photo"]).exists():
                        st.image(product["photo"], use_container_width=True)
                    else:
                        st.write("📦 Sin foto")
                with c2:
                    st.markdown(f"**{product['name']}**")
                    if product["model"]:
                        st.caption(product["model"])
                    a, b, c = st.columns(3)
                    a.metric("Mayorista", int(product["wholesale"]))
                    b.metric("Minorista", int(product["retail"]))
                    c.metric("Total", int(product["wholesale"]) + int(product["retail"]))
                    with st.expander("Ajustar stock"):
                        with st.form(f"adjust_{int(product['id'])}"):
                            channel = st.selectbox("Tipo de stock", ["Mayorista", "Minorista"], key=f"ch_{int(product['id'])}")
                            adjustment = st.number_input("Cantidad a sumar o restar (usar negativo para restar)", value=0, step=1, key=f"adj_{int(product['id'])}")
                            if st.form_submit_button("Aplicar ajuste"):
                                field = "wholesale" if channel == "Mayorista" else "retail"
                                current = int(product[field])
                                new_value = current + int(adjustment)
                                if new_value < 0:
                                    st.error("El stock no puede quedar negativo.")
                                else:
                                    with connect() as con:
                                        con.execute(f"UPDATE products SET {field}=? WHERE id=?", (new_value, int(product["id"])))
                                        con.execute("INSERT INTO movements(product_id, channel, quantity, movement, created_at, note) VALUES (?, ?, ?, ?, ?, ?)",
                                                    (int(product["id"]), channel, abs(int(adjustment)), "Ajuste", datetime.now().isoformat(timespec="seconds"), f"Ajuste de {int(adjustment)}"))
                                    st.success("Stock actualizado.")
                                    st.rerun()

elif page == "Registrar venta":
    st.subheader("Registrar una venta")
    with connect() as con:
        products = pd.read_sql_query("SELECT id, name, model, wholesale, retail FROM products ORDER BY name", con)
    if products.empty:
        st.info("Primero agregá productos en Productos y stock.")
    else:
        options = {f"{row['name']} — {row['model']}".strip(" —"): int(row["id"]) for _, row in products.iterrows()}
        with st.form("sale_form", clear_on_submit=True):
            selected_label = st.selectbox("Producto", list(options.keys()))
            channel = st.radio("Tipo de venta", ["Mayorista", "Minorista"], horizontal=True)
            quantity = st.number_input("Unidades vendidas", min_value=1, value=1, step=1)
            note = st.text_input("Nota (opcional)", placeholder="Ej.: cliente / pedido")
            sale_date = st.date_input("Fecha", value=datetime.now().date())
            submit_sale = st.form_submit_button("Registrar venta", type="primary")
            if submit_sale:
                pid = options[selected_label]
                row = products[products["id"] == pid].iloc[0]
                field = "wholesale" if channel == "Mayorista" else "retail"
                current = int(row[field])
                if int(quantity) > current:
                    st.error(f"No alcanza el stock {channel.lower()}. Disponible: {current}.")
                else:
                    with connect() as con:
                        con.execute(f"UPDATE products SET {field}=? WHERE id=?", (current - int(quantity), pid))
                        con.execute("INSERT INTO movements(product_id, channel, quantity, movement, created_at, note) VALUES (?, ?, ?, ?, ?, ?)",
                                    (pid, channel, int(quantity), "Venta", datetime.combine(sale_date, datetime.now().time()).isoformat(timespec="seconds"), note))
                    st.success(f"Venta registrada. Se descontaron {int(quantity)} unidad(es) del stock {channel.lower()}.")
                    st.rerun()

elif page == "Historial":
    st.subheader("Historial de movimientos")
    with connect() as con:
        history = pd.read_sql_query("""
            SELECT m.created_at AS Fecha, p.name AS Producto, m.channel AS Canal,
                   m.movement AS Movimiento, m.quantity AS Cantidad, m.note AS Nota
            FROM movements m LEFT JOIN products p ON p.id=m.product_id
            ORDER BY m.created_at DESC
        """, con)
    if history.empty:
        st.info("Todavía no hay movimientos.")
    else:
        st.dataframe(history, use_container_width=True, hide_index=True)
        st.download_button("Descargar historial CSV", history.to_csv(index=False).encode("utf-8-sig"),
                           file_name="historial_stock.csv", mime="text/csv")

st.divider()
st.caption("Importante: esta versión inicial sirve para probar la interfaz. En alojamiento gratuito, los archivos locales pueden perderse al reiniciar o volver a desplegar. No cargues el inventario real hasta configurar una base de datos persistente y acceso privado.")
