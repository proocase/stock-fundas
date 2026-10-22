import streamlit as st
from supabase import create_client
from datetime import datetime, date
import base64

st.set_page_config(page_title="Stock de fundas", page_icon="📱", layout="centered")
st.title("📱 Stock de fundas")
st.caption("Stock, ventas y movimientos guardados en Supabase.")

try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    password = st.secrets.get("APP_PASSWORD", "")
except Exception:
    st.error("Faltan los Secrets de Supabase en Streamlit: SUPABASE_URL y SUPABASE_KEY.")
    st.stop()

if password and not st.session_state.get("ok"):
    entered = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if entered == password:
            st.session_state.ok = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.stop()

db = create_client(url, key)

def products():
    return db.table("productos").select("*").order("nombre").execute().data or []

def movements(limit=1000):
    return db.table("movimientos_stock").select("*").order("fecha", desc=True).limit(limit).execute().data or []

def record_movement(pid, kind, qty, channel, amount=0):
    row = {
        "producto_id": int(pid),
        "tipo": kind,
        "cantidad": int(qty),
        "canal": channel,
        "fecha": datetime.now().astimezone().isoformat(),
        "importe_total": float(amount or 0),
    }
    db.table("movimientos_stock").insert(row).execute()

def money(value):
    try:
        return "$" + f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "$0"

def product_label(p):
    model = (p.get("modelo") or "").strip()
    return f'{p.get("nombre", "Producto")}' + (f" — {model}" if model else "")

# Cargar datos con errores explicados
try:
    ps = products()
    rows = movements()
except Exception as e:
    st.error("No pude leer los datos de Supabase. Revisá la conexión y las columnas de la base de datos.")
    st.caption(str(e))
    st.stop()

tab_add, tab_stock, tab_sale, tab_summary, tab_moves, tab_photo = st.tabs([
    "Agregar producto", "Stock", "Registrar venta", "Resumen", "Movimientos", "Buscar por foto"
])

with tab_add:
    st.subheader("Agregar producto")
    with st.form("add_product", clear_on_submit=True):
        name = st.text_input("Nombre del producto *")
        model = st.text_input("Modelo compatible")
        photo = st.file_uploader("Foto del producto (opcional)", type=["jpg", "jpeg", "png", "webp"])
        cost = st.number_input("Costo por unidad ($)", min_value=0.0, step=100.0, format="%.2f")
        price = st.number_input("Precio de venta por unidad ($)", min_value=0.0, step=100.0, format="%.2f")
        wh = st.number_input("Stock mayorista inicial", min_value=0, step=1)
        ret = st.number_input("Stock minorista inicial", min_value=0, step=1)
        submitted = st.form_submit_button("Guardar producto", use_container_width=True)
    if submitted:
        if not name.strip():
            st.warning("Ingresá el nombre del producto.")
        else:
            try:
                photo_url = ""
                if photo:
                    raw = photo.getvalue()
                    if len(raw) > 1200000:
                        st.error("La foto debe pesar menos de 1,2 MB.")
                        st.stop()
                    photo_url = "data:" + photo.type + ";base64," + base64.b64encode(raw).decode()
                res = db.table("productos").insert({
                    "nombre": name.strip(),
                    "modelo": model.strip(),
                    "foto_url": photo_url,
                    "stock_mayorista": int(wh),
                    "stock_minorista": int(ret),
                    "costo": float(cost),
                    "precio_venta": float(price),
                }).execute()
                pid = res.data[0]["id"]
                if wh:
                    record_movement(pid, "ingreso", wh, "mayorista", 0)
                if ret:
                    record_movement(pid, "ingreso", ret, "minorista", 0)
                st.success("Producto guardado.")
                st.rerun()
            except Exception as e:
                st.error("Error al guardar. Confirmá que ejecutaste el SQL de actualización de la base de datos.")
                st.caption(str(e))

with tab_stock:
    st.subheader("Stock actual")
    search = st.text_input("Buscar por nombre o modelo", key="stock_search")
    filtered = [p for p in ps if search.lower() in (str(p.get("nombre", "")) + " " + str(p.get("modelo", ""))).lower()]
    st.metric("Productos registrados", len(ps))
    if not filtered:
        st.info("No hay productos que coincidan con la búsqueda.")
    for p in filtered:
        with st.container(border=True):
            st.subheader(p.get("nombre", "Producto"))
            if p.get("foto_url"):
                st.image(p["foto_url"], use_container_width=True)
            if p.get("modelo"):
                st.caption(p["modelo"])
            wh = int(p.get("stock_mayorista") or 0)
            ret = int(p.get("stock_minorista") or 0)
            c1, c2, c3 = st.columns(3)
            c1.metric("Mayorista", wh)
            c2.metric("Minorista", ret)
            c3.metric("Total", wh + ret)
            st.write("Costo:", money(p.get("costo", 0)), "· Venta:", money(p.get("precio_venta", 0)))
            with st.expander("Ajustar stock / registrar ingreso"):
                channel = st.selectbox("Canal", ["mayorista", "minorista"], key=f"adjust_channel_{p['id']}")
                action = st.radio("Movimiento", ["Ingreso (sumar)", "Fijar stock"], key=f"adjust_action_{p['id']}")
                current = wh if channel == "mayorista" else ret
                qty = st.number_input("Cantidad", min_value=0, step=1, value=1, key=f"adjust_qty_{p['id']}")
                if st.button("Guardar ajuste", key=f"adjust_save_{p['id']}", use_container_width=True):
                    if qty <= 0:
                        st.error("La cantidad debe ser mayor que cero.")
                    else:
                        col = "stock_mayorista" if channel == "mayorista" else "stock_minorista"
                        new_stock = int(current + qty) if action == "Ingreso (sumar)" else int(qty)
                        try:
                            db.table("productos").update({col: new_stock}).eq("id", p["id"]).execute()
                            record_movement(p["id"], "ingreso" if action == "Ingreso (sumar)" else "correccion", qty, channel, 0)
                            st.success("Stock actualizado.")
                            st.rerun()
                        except Exception as e:
                            st.error("Error al actualizar el stock.")
                            st.caption(str(e))

with tab_sale:
    st.subheader("Registrar una venta")
    if not ps:
        st.info("Primero agregá un producto en la pestaña Agregar producto.")
    else:
        by_label = {product_label(p): p for p in ps}
        with st.form("sale_form", clear_on_submit=True):
            chosen_label = st.selectbox("Producto vendido", list(by_label.keys()))
            chosen = by_label[chosen_label]
            channel = st.selectbox("Canal de venta", ["minorista", "mayorista"])
            available = int(chosen.get("stock_minorista" if channel == "minorista" else "stock_mayorista") or 0)
            st.caption(f"Stock disponible por este canal: {available}")
            qty = st.number_input("Cantidad vendida", min_value=1, max_value=max(1, available), value=1, step=1)
            unit_price = st.number_input(
                "Precio de venta por unidad ($)",
                min_value=0.0,
                value=float(chosen.get("precio_venta") or 0),
                step=100.0,
                format="%.2f",
            )
            sale_submit = st.form_submit_button("Guardar venta y descontar stock", use_container_width=True)
        if sale_submit:
            if available <= 0:
                st.error("No hay stock disponible en ese canal.")
            elif qty > available:
                st.error(f"Solo hay {available} unidades disponibles.")
            else:
                stock_col = "stock_minorista" if channel == "minorista" else "stock_mayorista"
                new_stock = available - int(qty)
                total = float(unit_price) * int(qty)
                try:
                    # Guardar movimiento con el importe de la venta y actualizar stock.
                    record_movement(chosen["id"], "venta", qty, channel, total)
                    db.table("productos").update({stock_col: new_stock}).eq("id", chosen["id"]).execute()
                    st.success(f"Venta guardada: {qty} unidad(es), total {money(total)}. Stock actualizado.")
                    st.rerun()
                except Exception as e:
                    st.error("No se pudo completar la venta. Revisá el movimiento y el stock antes de volver a intentarlo.")
                    st.caption(str(e))

with tab_summary:
    st.subheader("Resumen de ventas")
    today = date.today()
    current_month = today.strftime("%Y-%m")
    sales_today = []
    sales_month = []
    for r in rows:
        if r.get("tipo") != "venta":
            continue
        stamp = str(r.get("fecha", ""))
        amount = float(r.get("importe_total") or 0)
        if stamp[:10] == today.isoformat():
            sales_today.append((r, amount))
        if stamp[:7] == current_month:
            sales_month.append((r, amount))
    total_today = sum(x[1] for x in sales_today)
    total_month = sum(x[1] for x in sales_month)
    units_today = sum(int(x[0].get("cantidad") or 0) for x in sales_today)
    units_month = sum(int(x[0].get("cantidad") or 0) for x in sales_month)
    col1, col2 = st.columns(2)
    col1.metric("Vendido hoy", money(total_today))
    col2.metric("Vendido este mes", money(total_month))
    col3, col4 = st.columns(2)
    col3.metric("Unidades hoy", units_today)
    col4.metric("Unidades este mes", units_month)
    st.caption("El total se calcula con las ventas registradas desde que se activa esta versión. Las ventas antiguas sin importe se muestran como $0.")
    if sales_today:
        st.write("Ventas de hoy")
        for r, amount in sales_today:
            p_name = next((p.get("nombre", "Producto") for p in ps if str(p.get("id")) == str(r.get("producto_id"))), "Producto")
            st.write(f'{str(r.get("fecha", ""))[:16].replace("T", " ")} · {p_name} · {r.get("cantidad", 0)} u. · {money(amount)}')
    else:
        st.info("Todavía no hay ventas registradas hoy.")

with tab_moves:
    st.subheader("Movimientos recientes")
    names = {str(p["id"]): product_label(p) for p in ps}
    if not rows:
        st.info("Todavía no hay movimientos.")
    for r in rows[:200]:
        amount = float(r.get("importe_total") or 0)
        line = f'{str(r.get("fecha", "")).replace("T", " ")[:16]} · {names.get(str(r.get("producto_id")), "Producto")} · {r.get("tipo")} · {r.get("cantidad")} u. · {r.get("canal")}'
        if r.get("tipo") == "venta":
            line += f" · {money(amount)}"
        st.write(line)

with tab_photo:
    st.subheader("Buscar una funda por foto")
    st.info("La búsqueda automática por parecido visual requiere conectar un servicio de reconocimiento de imágenes. Por ahora podés subir la foto acá y comparar con las fotos guardadas de tus productos.")
    query_photo = st.file_uploader("Sacá una foto o elegí una imagen de tu galería", type=["jpg", "jpeg", "png", "webp"], key="visual_search_photo")
    if query_photo:
        st.write("Foto que querés encontrar:")
        st.image(query_photo, use_container_width=True)
        st.write("Fotos guardadas en tu inventario para comparar:")
        pictured = [p for p in ps if p.get("foto_url")]
        if not pictured:
            st.warning("Todavía no hay fotos guardadas en tus productos. Agregá fotos al cargar cada funda.")
        else:
            for p in pictured:
                with st.container(border=True):
                    st.image(p["foto_url"], use_container_width=True)
                    st.write(product_label(p))
                    st.write(f'Mayorista: {int(p.get("stock_mayorista") or 0)} · Minorista: {int(p.get("stock_minorista") or 0)}')
