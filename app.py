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
    [data-testid="stSidebar"] input, [data-testid="stSidebar"] select { background-color: white !important; color: #0b1a50 !important; -webkit-text-fill-color: #0b1a50 !important; }
    </style>
""", unsafe_allow_html=True)

try:
    st.image("logo.png", width=300)
except:
    try:
        st.image("logo.jpg", width=300)
    except:
        st.warning("⚠️ No se encontró el logo.")

st.sidebar.title("⚙ Panel de Control")
clave_ingresada = st.sidebar.text_input("1. Clave de Acceso Corporativo:", type="password")

if clave_ingresada == st.secrets["CLAVE_ACCESO"]:
    st.sidebar.success("✅ Acceso autorizado")
    
    meses = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SETIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
    mes_seleccionado = st.sidebar.selectbox("2. Mes a consultar:", meses, index=8)
    
    client = genai.Client(api_key=st.secrets["API_KEY_GOOGLE"])
    
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
                    return "⏳ ¡Uy! El sistema de RRHH está procesando muchas consultas simultáneas. Por favor, espera 1 minuto."
                return f"Lo siento, ocurrió un error técnico: {error_msg}"
        return "El servidor de IA está experimentando alta demanda. Intenta de nuevo en 1 minuto."

    # ----- NUEVO FILTRO: PREPARADO PARA CABECERAS DOBLES -----
    def optimizar_datos_para_ia(df, pregunta):
        pregunta_lower = pregunta.lower().replace('?', '').replace('¿', '').replace(',', '')
        
        columnas_base = list(df.columns[:5]) 
        columnas_fecha = []
        
        numeros = re.findall(r'\b\d{1,2}\b', pregunta_lower)
        if numeros:
            dia = numeros[0].zfill(2)
            # Buscamos en todas las columnas si contienen el día
            # Pandas nombra las columnas descombinadas como "sáb-12", "Unnamed: 31", etc.
            # Por seguridad, si encuentra "sáb-12", tomaremos esa columna y la siguiente.
            for i, col in enumerate(df.columns[5:]): 
                if str(dia) in str(col): 
                    # Agregamos la columna de Ingreso
                    columnas_fecha.append(df.columns[5 + i])
                    # Verificamos que exista una columna siguiente para la Salida
                    if (5 + i + 1) < len(df.columns):
                        columnas_fecha.append(df.columns[5 + i + 1])
                    break # Encontramos el día, no necesitamos buscar más
                    
        if columnas_fecha:
            df_filtrado = df[columnas_base + columnas_fecha]
            
            # Renombramos las columnas para que la IA no se confunda
            nuevos_nombres = columnas_base.copy()
            if len(columnas_fecha) >= 1:
                nuevos_nombres.append(f"Ingreso_dia_{dia}")
            if len(columnas_fecha) >= 2:
                nuevos_nombres.append(f"Salida_dia_{dia}")
            
            # Aseguramos que la longitud de nuevos_nombres coincida con las columnas
            if len(nuevos_nombres) == len(df_filtrado.columns):
                 df_filtrado.columns = nuevos_nombres

        else:
            df_filtrado = df.copy()

        texto_filas = df_filtrado.fillna('').astype(str).agg(' '.join, axis=1).str.lower()
        
        palabras_comunes = ['quien', 'quienes', 'falto', 'faltaron', 'asistio', 'asistieron', 
                            'dime', 'cuales', 'cual', 'agosto', 'mes', 'dia', 'todas', 'todos', 'del', 'los', 'las']
        palabras_clave = [p for p in pregunta_lower.split() if len(p) > 3 and p not in palabras_comunes]
        
        if palabras_clave:
            mask_nombre = pd.Series(False, index=df_filtrado.index)
            for palabra in palabras_clave:
                mask_nombre = mask_nombre | texto_filas.str.contains(palabra)
            if mask_nombre.any():
                df_filtrado = df_filtrado[mask_nombre]

        if len(df_filtrado) > 1500:
            df_filtrado = df_filtrado.tail(1500)
            
        return df_filtrado

    @st.cache_data(ttl=10)
    def cargar_datos_sheet(mes):
        try:
            sheet_id = st.secrets["ID_GOOGLE_SHEET"]
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
            # header=[2,3] no siempre funciona bien, así que leemos saltando las primeras filas basura
            # Saltamos las primeras 3 filas (0, 1, 2) y usamos la fila 3 (índice 3, que es la cabecera real con los días)
            df = pd.read_excel(url, sheet_name=mes, engine='openpyxl', header=3)
            return df
        except Exception as e:
            st.error(f"Error al leer la hoja '{mes}': {e}")
            return pd.DataFrame()

    df_asistencia = cargar_datos_sheet(mes_seleccionado)

    st.title("💬 Asistente de Datos Norkiam")
    st.markdown(f"Pregúntame sobre asistencias, faltas o tardanzas del mes de **{mes_seleccionado}**.")

    if "mensajes" not in st.session_state:
        st.session_state.mensajes = [
            {"rol": "assistant", "contenido": f"👋 ¡Hola, Norelly! Base de datos de {mes_seleccionado} conectada correctamente ({len(df_asistencia)} empleados cargados). ¿Qué deseas consultar hoy?"}
        ]

    if len(st.session_state.mensajes) > 0 and st.session_state.mensajes[0]["rol"] == "assistant" and "conectada correctamente" in st.session_state.mensajes[0]["contenido"]:
        st.session_state.mensajes[0]["contenido"] = f"👋 ¡Hola, Norelly! Base de datos de {mes_seleccionado} conectada correctamente ({len(df_asistencia)} empleados cargados). ¿Qué deseas consultar hoy?"

    for mensaje in st.session_state.mensajes:
        with st.chat_message(mensaje["rol"]):
            st.markdown(mensaje["contenido"])

    pregunta = st.chat_input("Ejemplo: ¿Quiénes faltaron el 19?")

    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
        st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})

        with st.chat_message("assistant"):
            with st.spinner(f"Procesando matriz de {mes_seleccionado}..."):
                
                df_optimizado = optimizar_datos_para_ia(df_asistencia, pregunta)
                datos_resumen = df_optimizado.to_csv(index=False)
                
                prompt_sistema = f"""
                Actúas como el asistente experto de recursos humanos de la empresa Norkiam SAC.
                Tienes acceso a los datos de la matriz de asistencia de {mes_seleccionado} oficial pre-filtrados en el siguiente formato CSV:
                {datos_resumen}

                Pregunta del usuario: "{pregunta}"

                Instrucciones estrictas:
                1. Revisa detenidamente los datos para dar una respuesta exacta. Cada fila es un trabajador y las últimas dos columnas corresponden al Ingreso y Salida de la fecha solicitada.
                2. Responde de manera directa, clara y ordenada, usando listas o tablas en Markdown.
                3. Si el usuario pregunta por faltas, busca "FAL", "F", o "FALTA" en las columnas de Ingreso o Salida.
                4. Si el usuario pregunta por descansos médicos, busca "DM".
                """
                
                respuesta_ia = llamar_gemini(prompt_sistema)
                st.markdown(respuesta_ia)
                
                st.caption(f"⚡ Optimizador de memoria: La IA evaluó {len(df_optimizado)} trabajadores y aisló únicamente las columnas relevantes de {mes_seleccionado}.")
                
                st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_ia})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa para acceder al sistema.")
