import streamlit as st
from supabase import create_client
from datetime import datetime
import base64

st.set_page_config(page_title="Stock de fundas", page_icon="📱")
st.title("📱 Stock de fundas")
st.caption("Los datos se guardan en Supabase.")

try:
    url=st.secrets["SUPABASE_URL"]
    key=st.secrets["SUPABASE_KEY"]
    password=st.secrets.get("APP_PASSWORD","")
except Exception:
    st.error("Faltan los Secrets de Supabase en Streamlit: SUPABASE_URL y SUPABASE_KEY.")
    st.stop()

if password and not st.session_state.get("ok"):
    entered=st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if entered==password:
            st.session_state.ok=True
            st.rerun()
        else: st.error("Contraseña incorrecta.")
    st.stop()

db=create_client(url,key)

def products():
    return db.table("productos").select("*").order("nombre").execute().data or []

def movement(pid,kind,qty,channel):
    db.table("movimientos_stock").insert({"producto_id":int(pid),"tipo":kind,"cantidad":int(qty),"canal":channel,"fecha":datetime.now().astimezone().isoformat()}).execute()

a,b,c=st.tabs(["Agregar producto","Stock","Movimientos"])
with a:
    with st.form("add",clear_on_submit=True):
        name=st.text_input("Nombre del producto *")
        model=st.text_input("Modelo compatible")
        photo=st.file_uploader("Foto opcional",type=["jpg","jpeg","png","webp"])
        wh=st.number_input("Stock mayorista inicial",min_value=0,step=1)
        ret=st.number_input("Stock minorista inicial",min_value=0,step=1)
        go=st.form_submit_button("Guardar producto",use_container_width=True)
    if go:
        if not name.strip(): st.warning("Ingresá un nombre.")
        else:
            try:
                photo_url=""
                if photo:
                    raw=photo.getvalue()
                    if len(raw)>1200000:
                        st.error("La foto debe pesar menos de 1,2 MB.")
                        st.stop()
                    photo_url="data:"+photo.type+";base64,"+base64.b64encode(raw).decode()
                res=db.table("productos").insert({"nombre":name.strip(),"modelo":model.strip(),"foto_url":photo_url,"stock_mayorista":int(wh),"stock_minorista":int(ret)}).execute()
                pid=res.data[0]["id"]
                if wh: movement(pid,"ingreso",wh,"mayorista")
                if ret: movement(pid,"ingreso",ret,"minorista")
                st.success("Producto guardado.")
                st.rerun()
            except Exception as e: st.error("Error al guardar: "+str(e))
with b:
    try:
        ps=products()
        st.metric("Productos registrados",len(ps))
        search=st.text_input("Buscar producto")
        for p in ps:
            if search.lower() not in (str(p.get("nombre",""))+" "+str(p.get("modelo",""))).lower(): continue
            with st.container(border=True):
                st.subheader(p["nombre"])
                if p.get("foto_url"): st.image(p["foto_url"],use_container_width=True)
                st.caption(p.get("modelo",""))
                wh=int(p.get("stock_mayorista") or 0); ret=int(p.get("stock_minorista") or 0)
                x,y,z=st.columns(3); x.metric("Mayorista",wh); y.metric("Minorista",ret); z.metric("Total",wh+ret)
                with st.expander("Ajustar stock / registrar venta"):
                    channel=st.selectbox("Canal",["mayorista","minorista"],key=f"ch{p['id']}")
                    action=st.radio("Movimiento",["Venta (restar)","Ingreso (sumar)","Fijar stock"],key=f"ac{p['id']}")
                    current=wh if channel=="mayorista" else ret
                    qty=st.number_input("Cantidad",min_value=0,step=1,value=1,key=f"q{p['id']}")
                    if st.button("Guardar movimiento",key=f"save{p['id']}"):
                        if qty<=0: st.error("La cantidad debe ser mayor que cero.")
                        elif action=="Venta (restar)" and qty>current: st.error(f"Solo hay {current} unidades.")
                        else:
                            col="stock_mayorista" if channel=="mayorista" else "stock_minorista"
                            new=current-qty if action=="Venta (restar)" else (qty if action=="Fijar stock" else current+qty)
                            kind="venta" if action=="Venta (restar)" else ("correccion" if action=="Fijar stock" else "ingreso")
                            try:
                                db.table("productos").update({col:int(new)}).eq("id",p["id"]).execute()
                                movement(p["id"],kind,qty,channel)
                                st.success("Stock actualizado.")
                                st.rerun()
                            except Exception as e: st.error("Error al actualizar: "+str(e))
    except Exception as e: st.error("Error leyendo productos: "+str(e))
with c:
    try:
        rows=db.table("movimientos_stock").select("*").order("fecha",desc=True).limit(100).execute().data or []
        ps=products(); names={str(p["id"]):p["nombre"] for p in ps}
        if not rows: st.info("Todavía no hay movimientos.")
        for r in rows:
            st.write(f'{str(r.get("fecha","")).replace("T"," ")[:16]} · {names.get(str(r.get("producto_id")),"Producto")} · {r.get("tipo")} {r.get("cantidad")} · {r.get("canal")}')
    except Exception as e: st.error("Error leyendo movimientos: "+str(e))
