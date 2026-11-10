import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import pytz
import time
import requests
import json
import uuid

# === GENERADOR DE PDF NATIVO ===
try:
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    import io
    PDF_ACTIVO = True
except ImportError:
    PDF_ACTIVO = False

# === ENLACES OFICIALES DE GOOGLE SHEETS ===
URL_APPS_SCRIPT = "https://script.google.com/macros/s/AKfycbwodCUKKTc0M1zY23bzMN3TZbsrH4BzwV32JcrSuUpv6_YTTuswbmhlk1IU8Dk4jA77/exec"
URL_CSV_USUARIOS = "https://docs.google.com/spreadsheets/d/13e2p-qGmZrcUNERjJR9j-BUyGakT0Xsp1pffwZUfreM/export?format=csv&gid=1575432411"

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="SIMA - Intranet Talleres UNALM", layout="wide", initial_sidebar_state="expanded")

# --- FUNCIONES DE BASE DE DATOS (NUBE) ---
@st.cache_data(ttl=60)
def cargar_docentes():
    try:
        df = pd.read_csv(URL_CSV_USUARIOS, header=None)
        fila_head = 0
        for idx, row in df.iterrows():
            valores = [str(x).lower().strip() for x in row.values]
            if any("dni" in v for v in valores) or any("nombres" in v for v in valores) or any("patern" in v for v in valores):
                fila_head = idx
                break
        
        df.columns = df.iloc[fila_head].astype(str).str.strip()
        df = df.iloc[fila_head+1:].dropna(how="all")
        
        col_nom = next((c for c in df.columns if "nombres" in c.lower()), None)
        col_pat = next((c for c in df.columns if "patern" in c.lower()), None)
        col_mat = next((c for c in df.columns if "mate" in c.lower()), None)
        col_dni = next((c for c in df.columns if "dni" in c.lower()), None)
        
        docentes_auth = {}
        if col_dni and col_nom and col_pat:
            for _, r in df.iterrows():
                dni = str(r[col_dni]).replace(".0", "").strip()
                nombres = str(r[col_nom]).strip()
                ap_pat = str(r[col_pat]).strip()
                ap_mat = str(r[col_mat]).strip() if col_mat else ""
                
                primer_nombre = nombres.split()[0].title() if nombres else ""
                primer_apellido = ap_pat.split()[0].title() if ap_pat else ""
                nombre_saludo = f"{primer_nombre} {primer_apellido}".strip()
                nombre_oficial = f"{ap_pat} {ap_mat}, {nombres}".upper().strip()
                
                if dni and dni.lower() != "nan":
                    docentes_auth[dni] = {
                        "saludo": nombre_saludo,
                        "oficial": nombre_oficial
                    }
        return docentes_auth
    except Exception:
        return {}

def cargar_reservas():
    try:
        r = requests.get(URL_APPS_SCRIPT, timeout=10)
        data = r.json()
        if len(data) > 0:
            df = pd.DataFrame(data)
            for col in ["Estado", "Eliminado_por", "Fecha_Eliminacion"]:
                if col not in df.columns:
                    df[col] = ""
            if "Materiales" not in df.columns:
                df["Materiales"] = "(Ninguno)"
            if "Semana" not in df.columns:
                df["Semana"] = "Historial"
            if "Fecha_Reserva" not in df.columns:
                df["Fecha_Reserva"] = ""
            if "ID_Reserva" not in df.columns:
                df["ID_Reserva"] = [str(uuid.uuid4()) for _ in range(len(df))]
            
            df["Estado"] = df["Estado"].replace("", "Activa")
            return df
    except Exception:
        pass
        
    return pd.DataFrame(columns=[
        "ID_Reserva", "Semana", "Día", "Fecha_Reserva", "Horario", "Profesor", "Ambientes", 
        "Equipos", "Materiales", "Operario", "Fecha/Hora Registro",
        "Estado", "Eliminado_por", "Fecha_Eliminacion"
    ])

def guardar_reservas_en_nube(df):
    try:
        df = df.fillna("")
        registros = df.to_dict(orient='records')
        payload = {"action": "save", "reservas": registros}
        resp = requests.post(URL_APPS_SCRIPT, data=json.dumps(payload), headers={'Content-Type': 'application/json'}, timeout=15)
        if resp.status_code == 200:
            resultado = resp.json()
            return resultado.get("status") == "success"
        return False
    except Exception:
        return False

# --- VARIABLES DE ESTADO DE SESIÓN ---
if "rol_actual" not in st.session_state: st.session_state.rol_actual = None  
if "usuario_actual" not in st.session_state: st.session_state.usuario_actual = ""
if "nombre_saludo" not in st.session_state: st.session_state.nombre_saludo = ""
if "nombre_oficial" not in st.session_state: st.session_state.nombre_oficial = ""
if "form_key" not in st.session_state: st.session_state.form_key = 0
if "mostrar_exito" not in st.session_state: st.session_state.mostrar_exito = False
if "reservas" not in st.session_state or st.session_state.reservas.empty:
    st.session_state.reservas = cargar_reservas()

# ==========================================
# LÓGICA DE TIEMPO (RESERVA CON 1 SEMANA DE ANTICIPACIÓN)
# ==========================================
tz_lima = pytz.timezone('America/Lima')
ahora_utc = datetime.utcnow()
ahora = ahora_utc.replace(tzinfo=pytz.utc).astimezone(tz_lima)

wd = ahora.weekday() # 0=Lunes, 1=Martes, ..., 6=Domingo
hora_actual = ahora.hour

# El sistema cierra los jueves a medianoche (Viernes de 00:00 a 07:59 am)
formulario_cerrado = (wd == 4 and hora_actual < 8)

if wd < 4 or formulario_cerrado:
    # Lunes a Jueves (o Viernes madrugada) -> Se reserva para la PRÓXIMA semana
    dias_al_lunes = 7 - wd
else:
    # Viernes después de las 8am, Sábado y Domingo -> Se reserva para la SUBSIGUIENTE semana
    dias_al_lunes = 14 - wd

lunes_obj = ahora + timedelta(days=dias_al_lunes)
viernes_obj = lunes_obj + timedelta(days=4)
str_semana = f"Semana del {lunes_obj.strftime('%d/%m')} al {viernes_obj.strftime('%d/%m')}"

# Nueva variable: Fechas exactas del calendario para los días seleccionados
fechas_semana = {
    "Lunes": lunes_obj.strftime("%d/%m/%Y"),
    "Martes": (lunes_obj + timedelta(days=1)).strftime("%d/%m/%Y"),
    "Miércoles": (lunes_obj + timedelta(days=2)).strftime("%d/%m/%Y"),
    "Jueves": (lunes_obj + timedelta(days=3)).strftime("%d/%m/%Y"),
    "Viernes": viernes_obj.strftime("%d/%m/%Y")
}

dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
horas = ["08:00 am - 09:50 am", "11:00 am - 12:50 pm", "02:00 pm - 03:50 pm", "04:00 pm - 05:50 pm"]
ambientes_base = ["Soldadura", "Metalmecánica", "Motores", "Pool", "Patio", "Rejas", "Campo"]
equipos_base = [
    "Ningún Equipo en particular", "NH TD5.80", "NH TD5.100", "NH TD90", "JD 3050B", 
    "JD 1040", "NH B110B", "NH L223", "SOLD ELECTRODO MANUAL", "SOLD OXI", 
    "SOLD TIG", "SOLD MIG/MAG", "TORNO", "FRESADORA", "ESMERIL", "PRENSA HIDRAULICA", 
    "REMACHADORA", "FRAGUA", "MAQUETA MOTOR"
]

profesores_lista = [
    "ROJAS ALEJANDRO, FRANCISCO", "GARCIA ARMAS, JUVENAL", "ALTAMIRANO CHUNGA, LUIS", 
    "CACERES GUERRERO, FREDY", "CHEVARRIA MOSCOSO, MARGARITA", "REBAZA PINO, ALFREDO", 
    "ZINGG ROSELL, AUGUSTO", "VASQUEZ CACERES, JAIME", "ORELLANA PARDAVE, JOSE", 
    "SALAS PEÑA, CARLO", "RUBIO VALLE, ALEXIS", "YARIN ACHACHAGUA, ANWAR", "SALAS PINTO, DIONISIO", "ADMINISTRACIÓN - NORELLY", "ALATA REY, JOSUÉ ELIEZER"
]

def obtener_color_profesor(prof_nombre):
    prof_upper = str(prof_nombre).upper()
    if "ROJAS" in prof_upper: return "#FFD1DC"          
    if "GARCIA" in prof_upper or "GARCÍA" in prof_upper: return "#B5EAD7" 
    if "ALTAMIRANO" in prof_upper: return "#FFEAA7"     
    if "CACERES" in prof_upper or "CÁCERES" in prof_upper: return "#DFCCF1" 
    if "CHEVARRIA" in prof_upper or "CHEVARRÍA" in prof_upper: return "#FFD8B1" 
    if "REBAZA" in prof_upper: return "#C7CEEA"         
    if "ZINGG" in prof_upper: return "#E2F0CB"          
    if "ORELLANA" in prof_upper: return "#A0C4FF"       
    if "SALAS PEÑA" in prof_upper: return "#FDFFB6"     
    if "SALAS PINTO" in prof_upper: return "#FF9AA2"    
    if "RUBIO" in prof_upper: return "#CAFFBF"          
    if "YARIN" in prof_upper or "YARÍN" in prof_upper: return "#FFC6FF" 
    if "NORELLY" in prof_upper: return "#FFB703"        
    if "ALATA" in prof_upper: return "#9BF6FF"          
    return "#E5E5E5"                                    

# --- ESTILO VISUAL ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Grand+Hotel&display=swap');
    
    section[data-testid="stSidebar"] {
        background-color: #006b3f !important;
        width: 380px;
    }
    
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
        max-width: 100% !important;
    }
    
    [data-testid="stSidebar"] .stMarkdown p, [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: white !important; }
    [data-testid="stSidebar"] label p { color: white !important; }
    input { color: black !important; background-color: white !important; }
    .stDataFrame { border: 2px solid #e6e6e6; border-radius: 8px; }
    div.stButton > button:first-child { background-color: #006b3f; color: white; border-color: #006b3f; font-weight: bold; }
    
    .caja-sesion { background-color: #e8f5e9; color: #006b3f; padding: 15px; border-radius: 10px; font-weight: bold; text-align: center; margin-bottom: 20px; border: 2px solid #69f0ae; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .saludo-ios { font-family: 'Grand Hotel', cursive; font-size: 55px; font-weight: 400; background: linear-gradient(90deg, #002b12 0%, #008f4c 50%, #69f0ae 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-top: -20px; margin-bottom: 35px; line-height: 1.3; padding: 5px 25px 5px 5px; display: inline-block; }
    .bloque-dia { background-color: #e8f5e9; padding: 15px; border-radius: 8px; margin-top: 15px; margin-bottom: 15px; border-left: 6px solid #006b3f;}
    .titulo-dia { font-size: 18px; font-weight: bold; color: #006b3f; margin-bottom: 10px;}
    .bloque-hora { background-color: #ffffff; padding: 12px; border-radius: 5px; margin-top: 15px; margin-bottom: 5px; border-left: 4px solid #4CAF50; border: 1px solid #dcdcdc;}
    .titulo-hora { font-size: 15px; font-weight: bold; color: #333333; margin-bottom: 8px;}
    .tarjeta-fluido { background-color: white; padding: 15px; border-radius: 15px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); text-align: center; border-bottom: 5px solid #006b3f; margin-bottom: 10px;}
    .icono-fluido { font-size: 40px; margin-bottom: 5px; }
    .valor-fluido { font-size: 24px; font-weight: bold; color: #2c3e50; margin: 0; }
    .titulo-fluido { font-size: 12px; color: #7f8c8d; text-transform: uppercase; font-weight: bold; letter-spacing: 0.5px;}
    
    .stTabs [data-baseweb="tab-list"] { gap: 15px; overflow-x: visible !important; }
    .stTabs [data-baseweb="tab"] { background-color: #f0f2f6; border-radius: 8px 8px 0px 0px; padding: 12px 25px !important; font-weight: bold !important; font-size: 17px !important; min-width: fit-content !important; white-space: nowrap !important; overflow: visible !important; }
    .stTabs [data-baseweb="tab"] span { overflow: visible !important; white-space: nowrap !important; }
    .stTabs [aria-selected="true"] { background-color: #006b3f !important; color: white !important; border-bottom: 4px solid #69f0ae !important; }

    .marca-de-agua {
        position: fixed;
        bottom: 25px; 
        left: 25px; 
        font-family: Arial, sans-serif;
        font-size: 13px;
        color: #7f8c8d;
        background-color: rgba(255, 255, 255, 0.8);
        padding: 5px 10px;
        border-radius: 8px;
        box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
        z-index: 9999;
        pointer-events: none;
    }
    </style>
    
    <div class="marca-de-agua">Desarrollado por <b>Norelly Cárdenas</b></div>
""", unsafe_allow_html=True)

# FILTRO GLOBAL: Mostrar reservas activas de la semana que se está planificando
if not st.session_state.reservas.empty:
    df_validas = st.session_state.reservas[
        (st.session_state.reservas["Estado"] != "Eliminado") & 
        (st.session_state.reservas["Semana"] == str_semana)
    ]
else:
    df_validas = pd.DataFrame()

# --- MENÚ LATERAL DE AUTENTICACIÓN ---
st.sidebar.markdown("### 🚜 SIMA - UNALM")
st.sidebar.markdown("Sistema de Maquinaria Agrícola.")
st.sidebar.markdown("<br><br><br>", unsafe_allow_html=True)

if st.session_state.rol_actual:
    if st.session_state.rol_actual == "Admin":
        if st.session_state.usuario_actual == "Norelly2026":
            st.sidebar.markdown(f'<div class="caja-sesion">👑 Super Admin<br><span style="color:#555; font-size:16px;">Ing. {st.session_state.nombre_saludo}</span></div>', unsafe_allow_html=True)
        else:
            st.sidebar.markdown(f'<div class="caja-sesion">👑 Administrador<br><span style="color:#555; font-size:16px;">Ing. {st.session_state.nombre_saludo}</span></div>', unsafe_allow_html=True)
    elif st.session_state.rol_actual == "Docente":
        if "MARGARITA" in st.session_state.nombre_saludo.upper():
            st.sidebar.markdown(f'<div class="caja-sesion">👩‍🏫 Sesión Activa<br><span style="color:#555; font-size:16px;">Ingeniera {st.session_state.nombre_saludo}</span></div>', unsafe_allow_html=True)
        else:
            st.sidebar.markdown(f'<div class="caja-sesion">👨‍🏫 Sesión Activa<br><span style="color:#555; font-size:16px;">Ing. {st.session_state.nombre_saludo}</span></div>', unsafe_allow_html=True)
        
    st.sidebar.markdown("<br>", unsafe_allow_html=True)
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.rol_actual = None
        st.session_state.usuario_actual = ""
        st.session_state.nombre_saludo = ""
        st.session_state.nombre_oficial = ""
        st.rerun()
else:
    st.sidebar.markdown("### 🔐 Acceso al Sistema")
    usuario_input = st.sidebar.text_input("Usuario")
    clave_input = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Entrar"):
        docentes_dict = cargar_docentes()
        if usuario_input == "Norelly2026" and clave_input == "Pool2026":
            st.session_state.rol_actual = "Admin"
            st.session_state.usuario_actual = "Norelly2026"
            st.session_state.nombre_saludo = "Norelly"
            st.session_state.nombre_oficial = "ADMINISTRACIÓN - NORELLY"
            st.rerun()
        elif usuario_input == clave_input and usuario_input in docentes_dict:
            datos_doc = docentes_dict[usuario_input]
            if usuario_input == "41264537": 
                st.session_state.rol_actual = "Admin"
            else:
                st.session_state.rol_actual = "Docente"
            st.session_state.usuario_actual = usuario_input
            st.session_state.nombre_saludo = datos_doc["saludo"]
            st.session_state.nombre_oficial = datos_doc["oficial"]
            st.rerun()
        else:
            st.sidebar.error("Usuario o contraseña incorrectos.")

# ==========================================
# VISTA 1: ADMINISTRADOR (CONTROL TOTAL)
# ==========================================
if st.session_state.rol_actual == "Admin":
    
    if "NORELLY" in st.session_state.nombre_saludo.upper():
        st.markdown(f'<div class="saludo-ios">Bienvenida Ing. {st.session_state.nombre_saludo}</div>', unsafe_allow_html=True)
    elif "MARGARITA" in st.session_state.nombre_saludo.upper():
        st.markdown(f'<div class="saludo-ios">Bienvenida Ingeniera {st.session_state.nombre_saludo}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="saludo-ios">Bienvenido Ing. {st.session_state.nombre_saludo}</div>', unsafe_allow_html=True)
        
    st.title("⚙️ Panel de Control Administrativo - SIMA")
    
    sheet_id = "13e2p-qGmZrcUNERjJR9j-BUyGakT0Xsp1pffwZUfreM"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=58572181"
    df_datos = pd.DataFrame()
    tractores = []
    cols_fechas = []
    error_excel = None
    
    try:
        df_crudo = pd.read_csv(csv_url, header=None)
        fila_encabezado = 0
        for idx, fila in df_crudo.iterrows():
            textos = [str(x).strip().lower() for x in fila.values]
            if any("tipo de tractor" in t for t in textos) or any("registro" in t for t in textos):
                fila_encabezado = idx
                break
        
        fila_cols = df_crudo.iloc[fila_encabezado].copy()
        fila_fechas = df_crudo.iloc[fila_encabezado + 1] if (fila_encabezado + 1) < len(df_crudo) else fila_cols
        
        columnas_finales = []
        for col_i in range(len(fila_cols)):
            val_c = str(fila_cols[col_i]).strip()
            val_f = str(fila_fechas[col_i]).strip()
            if col_i == 0: columnas_finales.append("Tractor")
            elif col_i == 1: columnas_finales.append("Registro")
            elif col_i == 2: columnas_finales.append("UN")
            else: columnas_finales.append(val_f if val_f and val_f != "nan" else val_c)
        
        df_datos = df_crudo.iloc[fila_encabezado + 2:].copy()
        df_datos.columns = columnas_finales
        df_datos["Tractor"] = df_datos["Tractor"].replace("", None).ffill()
        df_datos = df_datos.dropna(subset=["Registro"])
        df_datos["Registro"] = df_datos["Registro"].astype(str).str.strip().str.lower()
        
        tractores = df_datos["Tractor"].dropna().unique().tolist()
        cols_fechas = [c for c in df_datos.columns if c not in ["Tractor", "Registro", "UN"]]
    except Exception as e:
        error_excel = e

    tab_maquinaria, tab_evidencias, tab_reservas, tab_horario, tab_hacer_reserva = st.tabs([
        "🚜 Control Visual", "📸 Evidencias", "🗑️ Gestionar Reservas", "🖨️ Exportar Horario", "📝 Hacer Reserva"
    ])
    
    with tab_maquinaria:
        st.subheader("Estado Analítico e Historial de Maquinaria")
        if error_excel:
            st.error(f"⚠️ Error procesando la hoja de registros: {error_excel}")
        elif tractores:
            tractor_sel = st.selectbox("🚜 Seleccione el equipo para inspeccionar:", tractores)
            df_trac = df_datos[df_datos["Tractor"] == tractor_sel].copy()
            
            def mapear_nivel(val):
                if pd.isna(val): return 0.0
                txt = str(val).strip().lower()
                if txt == "max": return 100.0
                if "3/4" in txt and "max" in txt: return 87.5
                if txt == "3/4": return 75.0
                if "2/4" in txt and "3/4" in txt: return 62.5
                if txt in ["2/4", "1/2"]: return 50.0
                if "1/4" in txt and "2/4" in txt: return 37.5
                if txt == "1/4": return 25.0
                if txt == "min": return 15.0
                try: return float(txt.replace('%', '').replace(',', ''))
                except: return 0.0

            ultima_col_fecha = cols_fechas[-1] if cols_fechas else None
            
            def obtener_valor_actual(parametro):
                fila = df_trac[df_trac["Registro"].str.contains(parametro, na=False)]
                if not fila.empty and ultima_col_fecha: return str(fila[ultima_col_fecha].values[0])
                return "Sin dato"

            comb_txt = obtener_valor_actual("combustible")
            refri_txt = obtener_valor_actual("refrigerante")
            aceite_m_txt = obtener_valor_actual("aceite de motor")
            aceite_h_txt = obtener_valor_actual("hidráulico")
            horo_txt = obtener_valor_actual("horometro")
            if horo_txt == "Sin dato": horo_txt = obtener_valor_actual("horómetro")

            val_comb, val_refri, val_aceite_m, val_aceite_h = mapear_nivel(comb_txt), mapear_nivel(refri_txt), mapear_nivel(aceite_m_txt), mapear_nivel(aceite_h_txt)
            fecha_etiqueta = f" ({ultima_col_fecha})" if ultima_col_fecha else ""
            st.markdown(f"### 📌 Nivel Más Reciente: **{tractor_sel}**{fecha_etiqueta}")
            
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                st.markdown(f"""<div class="tarjeta-fluido"><div class="icono-fluido">⛽</div><div class="titulo-fluido">Combustible</div><p class="valor-fluido">{comb_txt}</p></div>""", unsafe_allow_html=True)
                st.progress(min(max(int(val_comb), 0), 100) / 100)
            with c2:
                st.markdown(f"""<div class="tarjeta-fluido"><div class="icono-fluido">🏺</div><div class="titulo-fluido">Refrigerante</div><p class="valor-fluido">{refri_txt}</p></div>""", unsafe_allow_html=True)
                st.progress(min(max(int(val_refri), 0), 100) / 100)
            with c3:
                st.markdown(f"""<div class="tarjeta-fluido"><div class="icono-fluido">🛢️</div><div class="titulo-fluido">A. Motor</div><p class="valor-fluido">{aceite_m_txt}</p></div>""", unsafe_allow_html=True)
                st.progress(min(max(int(val_aceite_m), 0), 100) / 100)
            with c4:
                st.markdown(f"""<div class="tarjeta-fluido"><div class="icono-fluido">⚙️</div><div class="titulo-fluido">A. Hidráulico</div><p class="valor-fluido">{aceite_h_txt}</p></div>""", unsafe_allow_html=True)
                st.progress(min(max(int(val_aceite_h), 0), 100) / 100)
            with c5:
                st.markdown(f"""<div class="tarjeta-fluido"><div class="icono-fluido">⏱️</div><div class="titulo-fluido">Horómetro</div><p class="valor-fluido">{horo_txt} <span style="font-size:16px;">hrs</span></p></div>""", unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("### 📈 Análisis Histórico de Rendimiento")
            metrica_grafico = st.selectbox("Seleccione el indicador:", ["Combustible", "Refrigerante", "Aceite de Motor", "Aceite Hidráulico", "Horómetro"])
            clave_param = {"Combustible": "combustible", "Refrigerante": "refrigerante", "Aceite de Motor": "aceite de motor", "Aceite Hidráulico": "hidráulico", "Horómetro": "horometro"}[metrica_grafico]
            
            fila_metrica = df_trac[df_trac["Registro"].str.contains(clave_param, na=False)]
            if not fila_metrica.empty and cols_fechas:
                valores_temporales = []
                for f in cols_fechas:
                    val_crudo = fila_metrica[f].values[0]
                    v_num = float(str(val_crudo).replace(',', '')) if metrica_grafico == "Horómetro" else mapear_nivel(val_crudo)
                    valores_temporales.append({"Fecha": f, "Valor": v_num, "Texto": str(val_crudo)})
                
                df_historico_plot = pd.DataFrame(valores_temporales)
                if metrica_grafico == "Horómetro":
                    fig = px.area(df_historico_plot, x="Fecha", y="Valor", markers=True, title=f"Horómetro Acumulado (hrs) - {tractor_sel}", hover_data={"Texto": True, "Valor": False})
                    fig.update_traces(line_color="#ff5722", fillcolor="rgba(255, 87, 34, 0.25)", marker=dict(size=8, color="#006b3f"))
                else:
                    fig = px.line(df_historico_plot, x="Fecha", y="Valor", markers=True, title=f"Evolución de {metrica_grafico} (%) - {tractor_sel}", hover_data={"Texto": True, "Valor": True}, line_shape="spline")
                    fig.update_traces(line_color="#006b3f", marker=dict(size=8, color="#ff5722"))
                    fig.update_layout(yaxis=dict(range=[0, 105], title="Nivel Estimado (%)"))
                st.plotly_chart(fig, use_container_width=True)

    with tab_evidencias:
        st.subheader("📸 Buscador Automático de Evidencias en Google Drive")
        if error_excel:
            st.error(f"⚠️ Error cargando datos base: {error_excel}")
        elif tractores:
            c_trac, c_fec, c_flu = st.columns(3)
            with c_trac: tractor_ev = st.selectbox("🚜 Seleccione Tractor", tractores, key="ev_trac")
            with c_fec: fecha_ev = st.selectbox("📅 Fecha de Inspección", list(reversed(cols_fechas)) if cols_fechas else [], key="ev_fec")
            with c_flu: fluido_ev = st.selectbox("💧 Tipo de Fluido", ["Combustible", "Refrigerante", "Aceite de Motor", "Aceite Hidráulico", "Horómetro"], key="ev_flu")
            
            clave_param_ev = {"Combustible": "combustible", "Refrigerante": "refrigerante", "Aceite de Motor": "aceite de motor", "Aceite Hidráulico": "hidráulico", "Horómetro": "horometro"}[fluido_ev]
            df_trac_ev = df_datos[df_datos["Tractor"] == tractor_ev]
            fila_metrica_ev = df_trac_ev[df_trac_ev["Registro"].str.contains(clave_param_ev, na=False)]
            valor_registrado = str(fila_metrica_ev[fecha_ev].values[0]) if not fila_metrica_ev.empty and fecha_ev in fila_metrica_ev.columns else "No registrado"
            
            st.markdown(f"**Nivel reportado en Excel:** `{valor_registrado}`")
            st.markdown("---")
            if st.button("🔍 Buscar y Mostrar Fotografía en Google Drive", type="primary"):
                with st.spinner("Buscando evidencia en Drive..."):
                    try:
                        res = requests.get(URL_APPS_SCRIPT, params={"action": "getFoto", "tractor": tractor_ev, "fecha": fecha_ev, "fluido": fluido_ev}, timeout=20)
                        datos_foto = res.json()
                        if "url" in datos_foto: st.image(datos_foto["url"], caption=f"Evidencia: {fluido_ev} - {tractor_ev} ({fecha_ev})", width=600)
                        else: st.error(f"❌ {datos_foto.get('error', 'No se encontró la foto.')}")
                    except Exception as e:
                        st.error(f"Error de conexión: {e}")

    with tab_reservas:
        st.subheader(f"Borrador de Reservas Activas ({str_semana})")
        
        columnas_orden = ["ID_Reserva", "Fecha/Hora Registro", "Día", "Fecha_Reserva", "Horario", "Profesor", "Ambientes", "Equipos", "Materiales", "Operario"]
        df_mostrar = df_validas[[c for c in columnas_orden if c in df_validas.columns]].copy()
        df_mostrar.insert(0, "❌ Borrar", False)
        
        df_editado = st.data_editor(
            df_mostrar, 
            use_container_width=True, 
            hide_index=True, 
            column_config={"ID_Reserva": None}
        )
        
        if st.button("🗑️ Procesar Eliminaciones en la Nube"):
            with st.spinner('⏳ Archivando registros en la nube...'):
                ids_a_borrar = df_editado[df_editado["❌ Borrar"] == True]["ID_Reserva"].tolist()
                
                if len(ids_a_borrar) > 0:
                    ts_elim = datetime.now(tz_lima).strftime("%d/%m/%Y %I:%M %p")
                    
                    for id_res in ids_a_borrar:
                        filtro = st.session_state.reservas["ID_Reserva"] == id_res
                        if filtro.any():
                            idx = st.session_state.reservas[filtro].index[0]
                            st.session_state.reservas.at[idx, "Estado"] = "Eliminado"
                            st.session_state.reservas.at[idx, "Eliminado_por"] = st.session_state.nombre_saludo
                            st.session_state.reservas.at[idx, "Fecha_Eliminacion"] = ts_elim
                        
                    if guardar_reservas_en_nube(st.session_state.reservas):
                        st.cache_data.clear()
                        st.session_state.reservas = cargar_reservas()
                        st.success("✅ Reservas enviadas a la papelera.")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error("Error al comunicarse con Google Sheets.")
                else:
                    st.info("No marcaste ninguna reserva para borrar.")
                    
        st.markdown("---")
        st.subheader("🗄️ Historial de Reservas Eliminadas (Auditoría Global)")
        df_eliminadas = st.session_state.reservas[st.session_state.reservas["Estado"] == "Eliminado"]
        if not df_eliminadas.empty:
            cols_auditoria = ["Semana", "Día", "Fecha_Reserva", "Horario", "Profesor", "Ambientes", "Equipos", "Eliminado_por", "Fecha_Eliminacion"]
            st.dataframe(df_eliminadas[[c for c in cols_auditoria if c in df_eliminadas.columns]], use_container_width=True)
        else:
            st.write("No hay registros eliminados en la papelera.")
            
    with tab_horario:
        st.subheader(f"🖨️ Exportar Horario ({str_semana})")
        
        if PDF_ACTIVO:
            def generar_pdf():
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
                elements = []
                styles = getSampleStyleSheet()
                elements.append(Paragraph(f"<b>CRONOGRAMA DE USO DE TALLERES Y EQUIPOS - SIMA ({str_semana})</b>", styles['Title']))
                elements.append(Paragraph("<br/>", styles['Normal']))
                
                data = [["Hora", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]]
                for h in horas:
                    row = [h]
                    for d in dias:
                        reserva = df_validas[(df_validas["Día"] == d) & (df_validas["Horario"] == h)]
                        if not reserva.empty:
                            texto = ""
                            for _, r in reserva.iterrows():
                                op = " [C/ Operario]" if r.get("Operario") == "Sí" else ""
                                mat = str(r.get('Materiales', '-'))
                                if not mat or mat.lower() == "nan" or mat == "(Ninguno)": mat = "-"
                                texto += f"• {r['Profesor']}{op}\nAmb: {r['Ambientes']}\nEq: {r['Equipos']}\nMat: {mat}\n\n"
                            row.append(texto.strip())
                        else:
                            row.append("Libre")
                    data.append(row)
                    
                t = Table(data, colWidths=[80, 130, 130, 130, 130, 130])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#006b3f")),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('GRID', (0,0), (-1,-1), 1, colors.black),
                    ('FONTSIZE', (0,0), (-1,-1), 8),
                    ('BACKGROUND', (0,1), (0,-1), colors.lightgrey),
                ]))
                elements.append(t)
                doc.build(elements)
                buffer.seek(0)
                return buffer
                
            pdf_data = generar_pdf()
            st.download_button(
                label="📥 DESCARGAR PDF NATIVO",
                data=pdf_data,
                file_name=f"Horario_SIMA_{lunes_obj.strftime('%d_%m')}.pdf",
                mime="application/pdf",
                type="primary"
            )
        else:
            st.warning("⚠️ Recuerda añadir **reportlab** a tu archivo de *requirements.txt* para habilitar el PDF.")

        st.markdown("<br>", unsafe_allow_html=True)
        html_table = f"""<html><head><meta charset="utf-8">
        <style>
            table {{ width: 100%; border-collapse: collapse; font-family: Arial; font-size: 12px; }}
            th {{ background-color: #006b3f; color: white; border: 1px solid #000; padding: 10px; text-align: center; }}
            td {{ border: 1px solid #000; padding: 6px; vertical-align: top; width: 16%; }}
            .hora {{ background-color: #f2f2f2; font-weight: bold; text-align: center; vertical-align: middle; }}
            .tarjeta-reserva {{ padding: 8px; border-radius: 6px; margin-bottom: 6px; border: 1px solid rgba(0,0,0,0.15); }}
        </style></head><body>
        <table><tr><th>Hora</th>"""
        for d in dias: 
            fecha_col = fechas_semana.get(d, "")
            html_table += f"<th>{d}<br><small>{fecha_col}</small></th>"
        html_table += "</tr>"
        
        for h in horas:
            html_table += f"<tr><td class='hora'>{h}</td>"
            for d in dias:
                reserva = df_validas[(df_validas["Día"] == d) & (df_validas["Horario"] == h)]
                if not reserva.empty:
                    contenido = ""
                    for _, r in reserva.iterrows():
                        prof = r["Profesor"]
                        bg_color = obtener_color_profesor(prof) 
                        op_tag = " <b style='color:#b71c1c;'>[Requiere Operario]</b>" if r.get("Operario", "") == "Sí" else ""
                        mat = str(r.get('Materiales', '-'))
                        if not mat or mat.lower() == "nan" or mat == "(Ninguno)": mat = "-"
                        
                        contenido += f"""
                        <div class="tarjeta-reserva" style="background-color: {bg_color};">
                            <b>{prof}</b>{op_tag}<br>
                            <i>Amb.:</i> {r['Ambientes']}<br>
                            <i>Eq.:</i> {r['Equipos']}<br>
                            <i>Mat.:</i> <b>{mat}</b>
                        </div>"""
                    html_table += f"<td>{contenido}</td>"
                else: 
                    html_table += "<td></td>"
            html_table += "</tr>"
        html_table += "</table></body></html>"
        
        st.components.v1.html(html_table, height=600, scrolling=True)

    with tab_hacer_reserva:
        st.subheader("🗓️ Separación Semanal de Ambientes y Equipos")
        
        if st.session_state.mostrar_exito:
            st.balloons()
            st.success("✅ ¡Guardado satisfactoriamente! El formulario se ha reiniciado.")
            st.session_state.mostrar_exito = False
        
        if formulario_cerrado:
            st.error("🔒 **SISTEMA CERRADO.** El plazo para reservas venció el jueves a la medianoche. El sistema se reabrirá el viernes a las 8:00 am para la próxima semana.")
        else:
            st.info(f"✅ **SISTEMA ABIERTO.** Registrando horarios para la **{str_semana}**.")
            st.warning("⏱️ **RECORDATORIO IMPORTANTE:** El horario se cierra los **jueves a la medianoche (12:00 am)** y los **viernes desde las 8:00 am** inicia el registro de la siguiente semana.")
            
            if st.button("🔄 Actualizar Disponibilidad (Admin)"):
                with st.spinner("🔄 Actualizando..."):
                    st.cache_data.clear()
                    st.session_state.reservas = cargar_reservas()
                st.rerun()
                
            st.subheader("📊 Recursos Ocupados en Tiempo Real")
            matriz = pd.DataFrame(index=horas, columns=dias)
            matriz.fillna("🟢 Libre", inplace=True)
            for d in dias:
                for h in horas:
                    acts = df_validas[(df_validas["Día"] == d) & (df_validas["Horario"] == h)]
                    if not acts.empty:
                        ocupados = []
                        for _, r in acts.iterrows():
                            if str(r["Ambientes"]) != "(Ninguno)": ocupados.append(str(r["Ambientes"]))
                            if str(r["Equipos"]) != "(Ninguno)": ocupados.append(str(r["Equipos"]))
                        matriz.at[h, d] = f"🔴 SEPARADO:\n{', '.join(ocupados)}"
            st.dataframe(matriz, use_container_width=True)
            st.markdown("---")
            
            st.subheader("📝 Formulario de Registro de Separación")
            
            if st.session_state.usuario_actual == "Norelly2026":
                profesor = st.selectbox("Docente Responsable (Modo Administrador)", profesores_lista, key=f"prof_{st.session_state.form_key}")
            else:
                st.text_input("Docente Responsable (Autocompletado y Bloqueado)", value=st.session_state.nombre_oficial, disabled=True)
                profesor = st.session_state.nombre_oficial
            
            dias_sel = st.multiselect("1. Seleccione los días de práctica:", dias, key=f"dias_main_admin_{st.session_state.form_key}")
            reservas_temporales = []
            
            if dias_sel:
                st.markdown("##### 2. Requerimientos por Bloque Horario")
                for d in dias_sel:
                    fecha_asignada = fechas_semana.get(d, "")
                    st.markdown(f'<div class="bloque-dia"><div class="titulo-dia">🗓️ {d.upper()} ({fecha_asignada})</div>', unsafe_allow_html=True)
                    h_sel = st.multiselect(f"⏰ Horarios para el {d}:", horas, key=f"h_admin_{d}_{st.session_state.form_key}")
                    if h_sel:
                        for h in h_sel:
                            st.markdown(f'<div class="bloque-hora"><div class="titulo-hora">⏱️ Bloque: {h}</div>', unsafe_allow_html=True)
                            ocupados_en_bloque = df_validas[(df_validas["Día"] == d) & (df_validas["Horario"] == h)]
                            amb_ya_ocupados, eq_ya_ocupados = set(), set()
                            for _, fila_o in ocupados_en_bloque.iterrows():
                                for a in str(fila_o["Ambientes"]).split(","):
                                    if a.strip() and a.strip() not in ["(Ninguno)", "Campo"]: amb_ya_ocupados.add(a.strip())
                                for e in str(fila_o["Equipos"]).split(","):
                                    if e.strip() and e.strip() not in ["(Ninguno)", "Ningún Equipo en particular"]: eq_ya_ocupados.add(e.strip())

                            def formatear_amb(n): return f"🔴 [OCUPADO] {n}" if n in amb_ya_ocupados else n
                            def formatear_eq(n): return f"🔴 [OCUPADO] {n}" if n in eq_ya_ocupados else n

                            col_a, col_e = st.columns(2)
                            with col_a: a_sel = st.multiselect("🏢 Ambientes", ambientes_base, format_func=formatear_amb, key=f"a_admin_{d}_{h}_{st.session_state.form_key}")
                            with col_e: e_sel = st.multiselect("🚜 Equipos", equipos_base, format_func=formatear_eq, key=f"e_admin_{d}_{h}_{st.session_state.form_key}")
                            
                            if [a for a in a_sel if a in amb_ya_ocupados] or [e for e in e_sel if e in eq_ya_ocupados]:
                                st.warning("⚠️ **Atención:** Algún recurso seleccionado ya está ocupado.")
                                
                            col_mat, col_op = st.columns([3, 1])
                            with col_mat: m_sel = st.text_input("🛠️ Materiales extra (Ej. Dinamómetro)", key=f"m_admin_{d}_{h}_{st.session_state.form_key}")
                            with col_op:
                                st.write(""); st.write("")
                                req_operario = st.checkbox("👷 Requiere Operario", key=f"op_admin_{d}_{h}_{st.session_state.form_key}")
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                            reservas_temporales.append({
                                "ID_Reserva": str(uuid.uuid4()),
                                "Semana": str_semana,
                                "Día": d,
                                "Fecha_Reserva": fecha_asignada,
                                "Horario": h, "Profesor": profesor, 
                                "Ambientes": ", ".join(a_sel) if a_sel else "(Ninguno)", 
                                "Equipos": ", ".join(e_sel) if e_sel else "(Ninguno)", 
                                "Materiales": m_sel if m_sel else "(Ninguno)", 
                                "Operario": "Sí" if req_operario else "No",
                                "Fecha/Hora Registro": datetime.now(tz_lima).strftime("%d/%m/%Y %I:%M %p"),
                                "Estado": "Activa",
                                "Eliminado_por": "",
                                "Fecha_Eliminacion": ""
                            })
                    st.markdown('</div>', unsafe_allow_html=True)
                
                if reservas_temporales:
                    st.markdown("---")
                    st.markdown("### 👁️ Previsualización de su Horario")
                    st.info("Verifique su horario. Lo reservado por otros aparece en ROJO. Su separación actual resalta en AZUL.")
                    
                    df_horario_visual = matriz.copy()
                    for res in reservas_temporales:
                        tag_op = " [Operario: SÍ]" if res["Operario"] == "Sí" else ""
                        texto_celda_azul = f"🔵 SU SELECCIÓN:\nAmb: {res['Ambientes']}\nEq: {res['Equipos']}{tag_op}"
                        actual = df_horario_visual.at[res["Horario"], res["Día"]]
                        
                        if "🟢" in str(actual): 
                            df_horario_visual.at[res["Horario"], res["Día"]] = texto_celda_azul
                        else: 
                            df_horario_visual.at[res["Horario"], res["Día"]] = str(actual) + "\n\n" + texto_celda_azul
                            
                    st.table(df_horario_visual)
                    
                    placeholder_exito = st.empty()
                    if st.button("✅ Confirmar Separación Definitiva", use_container_width=True, key="btn_admin_save"):
                        with st.spinner("⏳ Guardando en la nube..."):
                            cruces = []
                            
                            st.cache_data.clear()
                            df_remoto_actualizado = cargar_reservas()
                            st.session_state.reservas = df_remoto_actualizado
                            
                            df_validas_refresh = st.session_state.reservas[
                                (st.session_state.reservas["Estado"] != "Eliminado") & 
                                (st.session_state.reservas["Semana"] == str_semana)
                            ] if not st.session_state.reservas.empty else pd.DataFrame()
                            
                            for res in reservas_temporales:
                                d, h = res["Día"], res["Horario"]
                                if not df_validas_refresh.empty:
                                    for _, act in df_validas_refresh[(df_validas_refresh["Día"] == d) & (df_validas_refresh["Horario"] == h)].iterrows():
                                        amb_act = set([a.strip() for a in str(act["Ambientes"]).split(",") if a.strip() and a.strip() != "(Ninguno)"])
                                        eq_act = set([e.strip() for e in str(act["Equipos"]).split(",") if e.strip() and e.strip() != "(Ninguno)"])
                                        if [a for a in res["List_Amb"] if a in amb_act and a != "Campo"] or [e for e in res["List_Eq"] if e in eq_act and e != "Ningún Equipo en particular"]:
                                            cruces.append(f"{d} a las {h}")
                            
                            if cruces: 
                                st.error("⚠️ **Cruce detectado:** Otros docentes acaban de separar estos recursos.")
                            else:
                                df_nuevas = pd.DataFrame(reservas_temporales)
                                if not st.session_state.reservas.empty:
                                    df_final = pd.concat([st.session_state.reservas, df_nuevas], ignore_index=True)
                                else:
                                    df_final = df_nuevas
                                
                                if guardar_reservas_en_nube(df_final):
                                    st.cache_data.clear()
                                    st.session_state.reservas = cargar_reservas()
                                    st.toast("✅ ¡Guardado satisfactoriamente!", icon="🎉")
                                    placeholder_exito.success("✅ ¡Guardado permanentemente en la Nube!")
                                    time.sleep(2)
                                    st.session_state.form_key += 1
                                    st.session_state.mostrar_exito = True
                                    st.rerun()
                                else: 
                                    st.error("Error guardando en Google Sheets.")

elif st.session_state.rol_actual == "Docente":

    if "MARGARITA" in st.session_state.nombre_saludo.upper():
        st.markdown(f'<div class="saludo-ios">Bienvenida Ingeniera {st.session_state.nombre_saludo}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="saludo-ios">Bienvenido Ing. {st.session_state.nombre_saludo}</div>', unsafe_allow_html=True)
    
    st.title("🗓️ Separación Semanal de Ambientes y Equipos")
    
    tab_reservar, tab_mis_reservas = st.tabs(["📝 Hacer Reserva", "🗑️ Mis Reservas"])
    
    with tab_reservar:
        if st.session_state.mostrar_exito:
            st.balloons()
            st.success("✅ ¡Guardado satisfactoriamente! El formulario se ha reiniciado.")
            st.session_state.mostrar_exito = False
        
        if formulario_cerrado:
            st.error("🔒 **SISTEMA CERRADO.** El plazo para reservas venció el jueves a la medianoche. El sistema se reabrirá el viernes a las 8:00 am para la próxima semana.")
        else:
            st.info(f"✅ **SISTEMA ABIERTO.** Registrando horarios para la **{str_semana}**.")
            st.warning("⏱️ **RECORDATORIO IMPORTANTE:** El horario se cierra los **jueves a la medianoche (12:00 am)** y los **viernes desde las 8:00 am** inicia el registro de la siguiente semana.")
            
            if st.button("🔄 Actualizar Disponibilidad"):
                with st.spinner("🔄 Actualizando base de datos..."):
                    st.cache_data.clear()
                    st.session_state.reservas = cargar_reservas()
                st.rerun()
                
            st.subheader("📊 Recursos Ocupados en Tiempo Real")
            matriz = pd.DataFrame(index=horas, columns=dias)
            matriz.fillna("🟢 Libre", inplace=True)
            for d in dias:
                for h in horas:
                    acts = df_validas[(df_validas["Día"] == d) & (df_validas["Horario"] == h)]
                    if not acts.empty:
                        ocupados = []
                        for _, r in acts.iterrows():
                            if str(r["Ambientes"]) != "(Ninguno)": ocupados.append(str(r["Ambientes"]))
                            if str(r["Equipos"]) != "(Ninguno)": ocupados.append(str(r["Equipos"]))
                        matriz.at[h, d] = f"🔴 SEPARADO:\n{', '.join(ocupados)}"
            st.dataframe(matriz, use_container_width=True)
            st.markdown("---")
            
            st.subheader("📝 Formulario de Registro de Separación")
            
            st.text_input("Docente Responsable (Autocompletado)", value=st.session_state.nombre_oficial, disabled=True)
            profesor = st.session_state.nombre_oficial
            
            dias_sel = st.multiselect("1. Seleccione los días de práctica:", dias, key=f"dias_main_{st.session_state.form_key}")
            reservas_temporales = []
            
            if dias_sel:
                st.markdown("##### 2. Requerimientos por Bloque Horario")
                for d in dias_sel:
                    fecha_asignada = fechas_semana.get(d, "")
                    st.markdown(f'<div class="bloque-dia"><div class="titulo-dia">🗓️ {d.upper()} ({fecha_asignada})</div>', unsafe_allow_html=True)
                    h_sel = st.multiselect(f"⏰ Horarios para el {d}:", horas, key=f"h_{d}_{st.session_state.form_key}")
                    if h_sel:
                        for h in h_sel:
                            st.markdown(f'<div class="bloque-hora"><div class="titulo-hora">⏱️ Bloque: {h}</div>', unsafe_allow_html=True)
                            ocupados_en_bloque = df_validas[(df_validas["Día"] == d) & (df_validas["Horario"] == h)]
                            amb_ya_ocupados, eq_ya_ocupados = set(), set()
                            for _, fila_o in ocupados_en_bloque.iterrows():
                                for a in str(fila_o["Ambientes"]).split(","):
                                    if a.strip() and a.strip() not in ["(Ninguno)", "Campo"]: amb_ya_ocupados.add(a.strip())
                                for e in str(fila_o["Equipos"]).split(","):
                                    if e.strip() and e.strip() not in ["(Ninguno)", "Ningún Equipo en particular"]: eq_ya_ocupados.add(e.strip())

                            def formatear_amb(n): return f"🔴 [OCUPADO] {n}" if n in amb_ya_ocupados else n
                            def formatear_eq(n): return f"🔴 [OCUPADO] {n}" if n in eq_ya_ocupados else n

                            col_a, col_e = st.columns(2)
                            with col_a: a_sel = st.multiselect("🏢 Ambientes", ambientes_base, format_func=formatear_amb, key=f"a_{d}_{h}_{st.session_state.form_key}")
                            with col_e: e_sel = st.multiselect("🚜 Equipos", equipos_base, format_func=formatear_eq, key=f"e_{d}_{h}_{st.session_state.form_key}")
                            
                            if [a for a in a_sel if a in amb_ya_ocupados] or [e for e in e_sel if e in eq_ya_ocupados]:
                                st.warning("⚠️ **Atención:** Algún recurso seleccionado ya está ocupado.")
                                
                            col_mat, col_op = st.columns([3, 1])
                            with col_mat: m_sel = st.text_input("🛠️ Materiales extra", key=f"m_{d}_{h}_{st.session_state.form_key}")
                            with col_op:
                                st.write(""); st.write("")
                                req_operario = st.checkbox("👷 Requiere Operario", key=f"op_{d}_{h}_{st.session_state.form_key}")
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                            reservas_temporales.append({
                                "ID_Reserva": str(uuid.uuid4()),
                                "Semana": str_semana,
                                "Día": d,
                                "Fecha_Reserva": fecha_asignada,
                                "Horario": h, "Profesor": profesor, 
                                "Ambientes": ", ".join(a_sel) if a_sel else "(Ninguno)", 
                                "Equipos": ", ".join(e_sel) if e_sel else "(Ninguno)", 
                                "Materiales": m_sel if m_sel else "(Ninguno)", 
                                "Operario": "Sí" if req_operario else "No",
                                "Fecha/Hora Registro": datetime.now(tz_lima).strftime("%d/%m/%Y %I:%M %p"),
                                "Estado": "Activa",
                                "Eliminado_por": "",
                                "Fecha_Eliminacion": ""
                            })
                    st.markdown('</div>', unsafe_allow_html=True)
                
                if reservas_temporales:
                    st.markdown("---")
                    st.markdown("### 👁️ Previsualización de su Horario")
                    st.info("Verifique su horario. Lo reservado por otros aparece en ROJO. Su separación actual resalta en AZUL.")
                    
                    df_horario_visual = matriz.copy()
                    for res in reservas_temporales:
                        tag_op = " [Operario: SÍ]" if res["Operario"] == "Sí" else ""
                        texto_celda_azul = f"🔵 SU SELECCIÓN:\nAmb: {res['Ambientes']}\nEq: {res['Equipos']}{tag_op}"
                        actual = df_horario_visual.at[res["Horario"], res["Día"]]
                        
                        if "🟢" in str(actual): 
                            df_horario_visual.at[res["Horario"], res["Día"]] = texto_celda_azul
                        else: 
                            df_horario_visual.at[res["Horario"], res["Día"]] = str(actual) + "\n\n" + texto_celda_azul
                            
                    st.table(df_horario_visual)
                    
                    placeholder_exito = st.empty()
                    if st.button("✅ Confirmar Separación Definitiva", use_container_width=True):
                        with st.spinner("⏳ Guardando en la nube..."):
                            cruces = []
                            
                            st.cache_data.clear()
                            df_remoto_actualizado = cargar_reservas()
                            st.session_state.reservas = df_remoto_actualizado
                            
                            df_validas_refresh = st.session_state.reservas[
                                (st.session_state.reservas["Estado"] != "Eliminado") & 
                                (st.session_state.reservas["Semana"] == str_semana)
                            ] if not st.session_state.reservas.empty else pd.DataFrame()
                            
                            for res in reservas_temporales:
                                d, h = res["Día"], res["Horario"]
                                if not df_validas_refresh.empty:
                                    for _, act in df_validas_refresh[(df_validas_refresh["Día"] == d) & (df_validas_refresh["Horario"] == h)].iterrows():
                                        amb_act = set([a.strip() for a in str(act["Ambientes"]).split(",") if a.strip() and a.strip() != "(Ninguno)"])
                                        eq_act = set([e.strip() for e in str(act["Equipos"]).split(",") if e.strip() and e.strip() != "(Ninguno)"])
                                        if [a for a in res["List_Amb"] if a in amb_act and a != "Campo"] or [e for e in res["List_Eq"] if e in eq_act and e != "Ningún Equipo en particular"]:
                                            cruces.append(f"{d} a las {h}")
                            
                            if cruces: 
                                st.error("⚠️ **Cruce detectado:** Otros docentes acaban de separar estos recursos.")
                            else:
                                df_nuevas = pd.DataFrame(reservas_temporales)
                                if not st.session_state.reservas.empty:
                                    df_final = pd.concat([st.session_state.reservas, df_nuevas], ignore_index=True)
                                else:
                                    df_final = df_nuevas
                                
                                if guardar_reservas_en_nube(df_final):
                                    st.cache_data.clear()
                                    st.session_state.reservas = cargar_reservas()
                                    st.toast("✅ ¡Guardado satisfactoriamente!", icon="🎉")
                                    placeholder_exito.success("✅ ¡Guardado permanentemente en la Nube!")
                                    time.sleep(2)
                                    st.session_state.form_key += 1
                                    st.session_state.mostrar_exito = True
                                    st.rerun()
                                else: 
                                    st.error("Error guardando en Google Sheets.")

    with tab_mis_reservas:
        st.subheader(f"🗑️ Anular Mis Reservas Activas ({str_semana})")
        st.write("Si cometió un error o desea cancelar una clase, seleccione la reserva y proceda a anularla. Esta acción liberará el espacio para otros docentes.")
        
        mis_reservas = df_validas[df_validas["Profesor"] == st.session_state.nombre_oficial].copy()
        
        if not mis_reservas.empty:
            columnas_orden_mis = ["ID_Reserva", "Fecha/Hora Registro", "Día", "Fecha_Reserva", "Horario", "Ambientes", "Equipos", "Materiales", "Operario"]
            df_mostrar_mis = mis_reservas[[c for c in columnas_orden_mis if c in mis_reservas.columns]].copy()
            df_mostrar_mis.insert(0, "❌ Anular", False)
            
            df_editado_mis = st.data_editor(
                df_mostrar_mis, 
                use_container_width=True, 
                hide_index=True,
                column_config={"ID_Reserva": None}
            )
            
            if st.button("🗑️ Procesar Anulación de Seleccionadas"):
                with st.spinner('⏳ Liberando espacios en la nube...'):
                    ids_a_borrar_mis = df_editado_mis[df_editado_mis["❌ Anular"] == True]["ID_Reserva"].tolist()
                    
                    if len(ids_a_borrar_mis) > 0:
                        ts_elim = datetime.now(tz_lima).strftime("%d/%m/%Y %I:%M %p")
                            
                        for id_res in ids_a_borrar_mis:
                            filtro = st.session_state.reservas["ID_Reserva"] == id_res
                            if filtro.any():
                                idx = st.session_state.reservas[filtro].index[0]
                                st.session_state.reservas.at[idx, "Estado"] = "Eliminado"
                                st.session_state.reservas.at[idx, "Eliminado_por"] = st.session_state.nombre_saludo
                                st.session_state.reservas.at[idx, "Fecha_Eliminacion"] = ts_elim
                            
                        if guardar_reservas_en_nube(st.session_state.reservas):
                            st.cache_data.clear()
                            st.session_state.reservas = cargar_reservas()
                            st.success("✅ Reservas anuladas correctamente. El espacio ya está libre.")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Error al comunicarse con Google Sheets.")
                    else:
                        st.info("No marcaste ninguna reserva para anular.")
        else:
            st.info("No tiene reservas activas programadas en este momento.")

# ==========================================
# VISTA 3: PÚBLICA (SIN LOGUEARSE)
# ==========================================
else:
    st.title("🚜 SIMA - Intranet de Talleres UNALM")
    st.markdown("### Sistema Oficial de Separación de Maquinaria e Implementos")
    
    st.info("👈 Por favor, ingrese sus credenciales en el menú lateral izquierdo para acceder a su perfil y separar recursos.")
    st.warning("⏱️ **RECORDATORIO IMPORTANTE:** El horario se cierra los **jueves a la medianoche (12:00 am)** y los **viernes desde las 8:00 am** inicia el registro de la siguiente semana.")
    
    st.subheader("📊 Disponibilidad en Tiempo Real")
    st.write(f"Estado general de los talleres para la **{str_semana}**")
    
    matriz = pd.DataFrame(index=horas, columns=dias)
    matriz.fillna("🟢 Libre", inplace=True)
    
    for d in dias:
        for h in horas:
            acts = df_validas[(df_validas["Día"] == d) & (df_validas["Horario"] == h)]
            if not acts.empty:
                ocupados = []
                for _, r in acts.iterrows():
                    if str(r["Ambientes"]) != "(Ninguno)": ocupados.append(str(r["Ambientes"]))
                    if str(r["Equipos"]) != "(Ninguno)": ocupados.append(str(r["Equipos"]))
                matriz.at[h, d] = f"🔴 SEPARADO:\n{', '.join(ocupados)}"
                
    st.dataframe(matriz, use_container_width=True)
