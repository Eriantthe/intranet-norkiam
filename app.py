import streamlit as st
import sqlite3
import pandas as pd

# 1. FUNCIÓN PARA CREAR LA BASE DE DATOS INVISIBLE
def inicializar_base_datos():
    conn = sqlite3.connect('norkiam.db')
    c = conn.cursor()
    # Crea la tabla maestra si no existe
    c.execute('''
        CREATE TABLE IF NOT EXISTS registro_asistencia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE,
            turno TEXT,
            area TEXT,
            nombre_completo TEXT,
            hora_entrada TEXT,
            hora_salida TEXT,
            estado_asistencia TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Ejecutamos la creación de la base de datos
inicializar_base_datos()

# 2. DISEÑO DE LA INTRANET
st.set_page_config(page_title="Intranet Norkiam SAC", page_icon="🏢", layout="wide")

st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #0b1a50 !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stSidebar"] input { background-color: white !important; color: #0b1a50 !important; -webkit-text-fill-color: #0b1a50 !important; }
    </style>
""", unsafe_allow_html=True)

# ---> AQUÍ ESTÁ TU LOGO DE REGRESO <---
try:
    st.image("logo.jpg", width=250)
except:
    pass

st.sidebar.title("⚙ Panel de Control")
clave_ingresada = st.sidebar.text_input("1. Clave de Acceso Corporativo:", type="password")

if clave_ingresada == st.secrets["CLAVE_ACCESO"]:
    st.sidebar.success("✅ Acceso autorizado")
    st.sidebar.info("Base de datos local conectada y lista.")
    
    st.title("💬 Asistente de Datos Norkiam")
    st.write("Pregúntame sobre el historial de asistencias, faltas o tardanzas del personal.")
    
    # 3. SISTEMA DE MEMORIA DEL CHAT
    if "mensajes" not in st.session_state:
        st.session_state.mensajes = []

    # Mostrar mensajes anteriores en la pantalla
    for mensaje in st.session_state.mensajes:
        with st.chat_message(mensaje["rol"]):
            st.markdown(mensaje["contenido"])

    # 4. BARRA DE CHAT INFERIOR
    pregunta = st.chat_input("Ej: Dame el resumen de asistencias de Narciso este mes...")
    
    if pregunta:
        # Mostrar lo que escribió el usuario
        with st.chat_message("user"):
            st.markdown(pregunta)
        st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})
        
        # Aquí conectaremos el cerebro de Gemini en el próximo paso
        with st.chat_message("assistant"):
            respuesta_temporal = "Estoy procesando tu consulta. (El cerebro del Agente IA se conectará aquí en el próximo paso)."
            st.markdown(respuesta_temporal)
        st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_temporal})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa.")
