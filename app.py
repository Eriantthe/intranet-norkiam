import streamlit as st
import pandas as pd
import json
from google import genai
from google.oauth2 import service_account

# 1. DISEÑO DE LA INTRANET
st.set_page_config(page_title="Intranet Norkiam SAC", page_icon="🏢", layout="wide")

st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #0b1a50 !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stSidebar"] input { background-color: white !important; color: #0b1a50 !important; -webkit-text-fill-color: #0b1a50 !important; }
    </style>
""", unsafe_allow_html=True)

try:
    st.image("logo.jpg", width=250)
except:
    pass

st.sidebar.title("⚙ Panel de Control")
clave_ingresada = st.sidebar.text_input("1. Clave de Acceso Corporativo:", type="password")

if clave_ingresada == st.secrets["CLAVE_ACCESO"]:
    st.sidebar.success("✅ Acceso autorizado")
    
    client = genai.Client(api_key=st.secrets["API_KEY_GOOGLE"])
    
    # Función para llamar a Gemini con manejo de errores y múltiples modelos
    def llamar_gemini(prompt):
        modelos = ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash']
        for modelo in modelos:
            try:
                response = client.models.generate_content(model=modelo, contents=prompt)
                return response.text
            except Exception:
                continue
        return "Lo siento, en este momento el servicio de IA está experimentando alta demanda. Inténtalo de nuevo."

    # 2. CARGA ULTRA RÁPIDA DESDE EL GOOGLE SHEET MAESTRO
    @st.cache_data(ttl=60) # Cache de 1 minuto para que vuele
    pasa_cache = True
    def cargar_datos_sheet():
        try:
            # Leemos tu Google Sheet usando pandas directamente mediante su enlace público CSV o credenciales
            # Asegúrate de que tu Google Sheet esté configurado como "Cualquier persona con el enlace puede ver"
            sheet_id = st.secrets["ID_GOOGLE_SHEET"]
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            df = pd.read_csv(url)
            return df
        except Exception as e:
            # Si hubiera algún problema con el enlace, devolvemos un DataFrame vacío con las columnas base
            return pd.DataFrame(columns=["fecha", "turno", "area", "nombre_completo", "hora_entrada", "hora_salida", "estado_asistencia"])

    df_asistencia = cargar_datos_sheet()

    # 3. INTERFAZ DEL CHATBOT
    st.title("💬 Asistente de Datos Norkiam")
    st.markdown("Pregúntame sobre asistencias, faltas, turnos o tardanzas del personal con total libertad.")

    if "mensajes" not in st.session_state:
        st.session_state.mensajes = [
            {"rol": "assistant", "contenido": "👋 ¡Hola, Norelly! La Base de Datos Maestra de Huaral está sincronizada y lista. ¿Qué deseas consultar hoy?"}
        ]

    for mensaje in st.session_state.mensajes:
        with st.chat_message(mensaje["rol"]):
            st.markdown(mensaje["contenido"])

    pregunta = st.chat_input("Ejemplo: ¿Quiénes faltaron el 17 de agosto? o ¿Cuál es el récord de Narciso Aguilar?")

    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
        st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})

        with st.chat_message("assistant"):
            with st.spinner("Analizando datos..."):
                # Convertimos una muestra de los datos a texto para que la IA los analice y responda con precisión
                datos_resumen = df_asistencia.to_csv(index=False)
                
                prompt_sistema = f"""
                Actúas como el asistente de recursos humanos de la empresa Norkiam SAC.
                Tienes acceso a la siguiente base de datos de asistencia en formato CSV:
                {datos_resumen}

                Pregunta del usuario: "{pregunta}"

                Instrucciones:
                1. Analiza los datos proporcionados para responder con precisión exacta.
                2. Si el usuario pide faltas, lista los nombres y fechas correspondientes.
                3. Responde de manera profesional, clara y ordenada, utilizando tablas en Markdown cuando sea útil.
                """
                
                respuesta_ia = llamar_gemini(prompt_sistema)
                st.markdown(respuesta_ia)
                st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_ia})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa para acceder al sistema.")
