import streamlit as st
import pandas as pd
import time
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

# Solución para el Logo: Buscamos ambos formatos comunes
try:
    st.image("logo.png", width=300)
except:
    try:
        st.image("logo.jpg", width=300)
    except:
        st.warning("⚠️ No se encontró el logo. Revisa si el archivo en tu carpeta se llama exactamente 'logo.png' o 'logo.jpg'.")

st.sidebar.title("⚙ Panel de Control")
clave_ingresada = st.sidebar.text_input("1. Clave de Acceso Corporativo:", type="password")

if clave_ingresada == st.secrets["CLAVE_ACCESO"]:
    st.sidebar.success("✅ Acceso autorizado")
    
    client = genai.Client(api_key=st.secrets["API_KEY_GOOGLE"])
    
    # Motor IA blindado: Usa el modelo exigido y reintenta si hay saturación (503)
    def llamar_gemini(prompt):
        for intento in range(4): # 4 intentos para atravesar la alta demanda
            try:
                response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
                return response.text
            except Exception as e:
                error_msg = str(e)
                # Si el servidor está saturado (503), descansa 3 segundos y vuelve a intentar
                if "503" in error_msg or "UNAVAILABLE" in error_msg:
                    time.sleep(3) 
                    continue
                return f"Lo siento, ocurrió un error técnico: {error_msg}"
        
        return "El servidor de IA está experimentando un pico de alta demanda inusual. Por favor, intenta de nuevo en 1 minuto."

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
            # Si se demora, mostrará este mensaje mientras la IA hace los reintentos
            with st.spinner("Analizando registros (esto puede tomar unos segundos extra si el servidor está lleno)..."):
                datos_resumen = df_asistencia.to_csv(index=False)
                
                prompt_sistema = f"""
                Actúas como el asistente experto de recursos humanos de la empresa Norkiam SAC.
                Tienes acceso a los datos oficiales de asistencia en el siguiente formato CSV:
                {datos_resumen}

                Pregunta del usuario: "{pregunta}"

                Instrucciones estrictas:
                1. Revisa detenidamente los datos para dar una respuesta exacta.
                2. Si el usuario pregunta por faltas, busca a los que tienen "FALTA" o "F" en estado_asistencia en esa fecha.
                3. Responde de manera clara usando listas o tablas.
                """
                
                respuesta_ia = llamar_gemini(prompt_sistema)
                st.markdown(respuesta_ia)
                st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_ia})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa para acceder al sistema.")
