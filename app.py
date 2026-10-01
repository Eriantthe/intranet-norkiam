import streamlit as st
import pandas as pd
from google import genai

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
    
    # LA IDEA DE NORELLY: CASCADA DE MODELOS (Model Fallback)
    def llamar_gemini(prompt):
        # Lista de modelos desde los más capaces hasta los clásicos de rescate
        modelos_rescate = [
            'gemini-1.5-pro',
            'gemini-1.5-flash-8b',
            'gemini-1.0-pro',
            'gemini-pro'
        ]
        
        for modelo in modelos_rescate:
            try:
                # Intenta con el modelo actual
                response = client.models.generate_content(model=modelo, contents=prompt)
                return response.text
            except Exception:
                # Si está lleno (503) o no existe (404), salta al siguiente inmediatamente
                continue
                
        # Solo si absolutamente TODOS los modelos fallan, muestra este mensaje
        return "Lo siento, todos los servidores de IA están saturados en este momento. Inténtalo de nuevo en unos segundos."

    @st.cache_data(ttl=10)
    def cargar_datos_sheet():
        try:
            sheet_id = st.secrets["ID_GOOGLE_SHEET"]
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            df = pd.read_csv(url)
            return df
        except Exception as e:
            st.error(f"Error al leer el Google Sheet: {e}")
            return pd.DataFrame(columns=["fecha", "turno", "area", "nombre_completo", "hora_entrada", "hora_salida", "estado_asistencia"])

    df_asistencia = cargar_datos_sheet()

    st.title("💬 Asistente de Datos Norkiam")
    st.markdown("Pregúntame sobre asistencias, faltas, turnos o tardanzas del personal con total libertad.")

    if "mensajes" not in st.session_state:
        st.session_state.mensajes = [
            {"rol": "assistant", "contenido": f"👋 ¡Hola, Norelly! Base de datos conectada correctamente ({len(df_asistencia)} registros cargados). ¿Qué deseas consultar hoy?"}
        ]

    for mensaje in st.session_state.mensajes:
        with st.chat_message(mensaje["rol"]):
            st.markdown(mensaje["contenido"])

    pregunta = st.chat_input("Ejemplo: ¿Quiénes faltaron el 19 de agosto?")

    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
        st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})

        with st.chat_message("assistant"):
            with st.spinner("Buscando en los registros con la IA..."):
                datos_resumen = df_asistencia.to_csv(index=False)
                
                prompt_sistema = f"""
                Actúas como el asistente experto de recursos humanos de la empresa Norkiam SAC.
                Tienes acceso a los datos oficiales de asistencia en el siguiente formato CSV:
                {datos_resumen}

                Pregunta del usuario: "{pregunta}"

                Instrucciones estrictas:
                1. Revisa detenidamente los datos para dar una respuesta exacta basada en la fecha y nombres solicitados.
                2. Si el usuario pregunta por faltas o asistencias de un día específico, busca todas las coincidencias en la columna de fechas.
                3. Responde de manera profesional, clara y ordenada, usando tablas en Markdown si hay varios registros.
                """
                
                respuesta_ia = llamar_gemini(prompt_sistema)
                st.markdown(respuesta_ia)
                st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_ia})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa para acceder al sistema.")
