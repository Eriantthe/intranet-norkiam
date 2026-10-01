import streamlit as st
import pandas as pd
import time
import re
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

# Solución para el Logo
try:
    st.image("logo.png", width=300)
except:
    try:
        st.image("logo.jpg", width=300)
    except:
        st.warning("⚠️ No se encontró el logo. Revisa el nombre del archivo.")

st.sidebar.title("⚙ Panel de Control")
clave_ingresada = st.sidebar.text_input("1. Clave de Acceso Corporativo:", type="password")

if clave_ingresada == st.secrets["CLAVE_ACCESO"]:
    st.sidebar.success("✅ Acceso autorizado")
    
    client = genai.Client(api_key=st.secrets["API_KEY_GOOGLE"])
    
    # Motor IA blindado con reintentos
    def llamar_gemini(prompt):
        for intento in range(4): 
            try:
                response = client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
                return response.text
            except Exception as e:
                error_msg = str(e)
                if "503" in error_msg or "UNAVAILABLE" in error_msg:
                    time.sleep(3) 
                    continue
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    return "⏳ ¡Uy! El sistema de RRHH está procesando muchas consultas simultáneas. Por favor, espera 1 minuto y vuelve a intentarlo."
                return f"Lo siento, ocurrió un error técnico: {error_msg}"
        return "El servidor de IA está experimentando alta demanda. Intenta de nuevo en 1 minuto."

    # ----- LA MAGIA DE LA OPCIÓN 1: OPTIMIZADOR DE MEMORIA -----
    def optimizar_datos_para_ia(df, pregunta):
        pregunta_lower = pregunta.lower().replace('?', '').replace('¿', '').replace(',', '')
        df_filtrado = df.copy()
        
        # 1. Filtro inteligente por Fecha (Días)
        numeros = re.findall(r'\b\d{1,2}\b', pregunta_lower)
        if numeros:
            mask_fecha = pd.Series(False, index=df_filtrado.index)
            for num in numeros:
                dia = num.zfill(2) # Convierte "19" a "19", o "5" a "05"
                mask_fecha = mask_fecha | df_filtrado['fecha'].astype(str).str.contains(f"-{dia}")
            if mask_fecha.any():
                df_filtrado = df_filtrado[mask_fecha]

        # 2. Filtro inteligente por Nombres 
        palabras_comunes = ['quien', 'quienes', 'falto', 'faltaron', 'asistio', 'asistieron', 
                            'dime', 'cuales', 'cual', 'agosto', 'mes', 'dia', 'todas', 'todos', 'del', 'los', 'las']
        palabras_clave = [p for p in pregunta_lower.split() if len(p) > 3 and p not in palabras_comunes]
        
        if palabras_clave:
            mask_nombre = pd.Series(False, index=df_filtrado.index)
            for palabra in palabras_clave:
                mask_nombre = mask_nombre | df_filtrado['nombre_completo'].str.lower().str.contains(palabra, na=False)
            if mask_nombre.any():
                df_filtrado = df_filtrado[mask_nombre]

        # 3. Seguro Anti-Colapso: Si la pregunta es muy abierta y no filtró nada, envía máximo 1500 filas
        if len(df_filtrado) > 1500:
            df_filtrado = df_filtrado.tail(1500)
            
        return df_filtrado
    # -----------------------------------------------------------

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
            with st.spinner("Filtrando datos en milisegundos..."):
                
                # ¡Aplicamos el filtro ANTES de llamar a la IA!
                df_optimizado = optimizar_datos_para_ia(df_asistencia, pregunta)
                datos_resumen = df_optimizado.to_csv(index=False)
                
                prompt_sistema = f"""
                Actúas como el asistente experto de recursos humanos de la empresa Norkiam SAC.
                Tienes acceso a los datos oficiales pre-filtrados en el siguiente formato CSV:
                {datos_resumen}

                Pregunta del usuario: "{pregunta}"

                Instrucciones estrictas:
                1. Revisa detenidamente los datos para dar una respuesta exacta.
                2. Responde de manera directa, clara y ordenada, usando listas o tablas en Markdown.
                3. Si el usuario pregunta por faltas, busca los estados "FALTA" o "F".
                """
                
                respuesta_ia = llamar_gemini(prompt_sistema)
                st.markdown(respuesta_ia)
                
                # Esto es un detalle visual genial para que tú y tu papá vean cuánto ahorró el filtro:
                st.caption(f"⚡ Optimizador de memoria: La IA analizó solo {len(df_optimizado)} registros relevantes en lugar de los {len(df_asistencia)} totales.")
                
                st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_ia})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa para acceder al sistema.")
