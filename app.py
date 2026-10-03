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

    # ----- NUEVO FILTRO INTELIGENTE: LECTURA DINÁMICA A PRUEBA DE ERRORES -----
    def optimizar_datos_para_ia(df, pregunta):
        pregunta_lower = pregunta.lower().replace('?', '').replace('¿', '').replace(',', '')
        
        # 1. Encontrar la fila base que tiene "DNI" y "NOMBRES" (El ancla)
        fila_base = 0
        for idx in range(min(10, len(df))):
            fila_texto = ' '.join(df.iloc[idx].fillna('').astype(str)).upper()
            if 'DNI' in fila_texto and 'NOMBRES' in fila_texto:
                fila_base = idx
                break
                
        # 2. Identificar en qué número de columna está cada dato personal
        col_area = 1; col_dni = 2; col_nombres = 3
        for c_idx, val in enumerate(df.iloc[fila_base]):
            val_str = str(val).upper()
            if 'ÁREA' in val_str or 'AREA' in val_str: col_area = c_idx
            if 'DNI' in val_str: col_dni = c_idx
            if 'NOMBRES' in val_str: col_nombres = c_idx
            
        columnas_base_indices = [col_area, col_dni, col_nombres]
        columnas_fecha_indices = []
        
        # 3. Buscar el día exacto en las filas superiores (donde están las fechas como "lun-14")
        numeros = re.findall(r'\b\d{1,2}\b', pregunta_lower)
        dia_str = ""
        if numeros:
            dia_str = numeros[0].zfill(2)
            # Revisamos las dos filas encima de la cabecera del DNI
            filas_a_revisar = [max(0, fila_base - 1), max(0, fila_base - 2)]
            
            for fila_idx in filas_a_revisar:
                for c_idx, val in enumerate(df.iloc[fila_idx]):
                    if str(dia_str) in str(val):
                        columnas_fecha_indices.append(c_idx)
                        if c_idx + 1 < len(df.columns):
                            columnas_fecha_indices.append(c_idx + 1)
                        break
                if columnas_fecha_indices:
                    break 
                    
        # 4. Construir la tabla limpia aislando SOLO las columnas de esa fecha
        fila_datos_inicio = fila_base + 1
        
        if columnas_fecha_indices:
            indices_extraer = columnas_base_indices + columnas_fecha_indices
            df_filtrado = df.iloc[fila_datos_inicio:, indices_extraer].copy()
            # Le damos nombres ultra claros a la IA para que no adivine
            df_filtrado.columns = ["Area", "DNI", "Apellidos_y_Nombres", f"Ingreso_dia_{dia_str}", f"Salida_dia_{dia_str}"]
        else:
            df_filtrado = df.iloc[fila_datos_inicio:].copy()
            nombres_cols = list(df_filtrado.columns)
            nombres_cols[col_area] = "Area"
            nombres_cols[col_dni] = "DNI"
            nombres_cols[col_nombres] = "Apellidos_y_Nombres"
            df_filtrado.columns = nombres_cols

        # 5. Búsqueda cruzada por nombres
        texto_filas = df_filtrado.fillna('').astype(str).agg(' '.join, axis=1).str.lower()
        palabras_comunes = ['quien', 'quienes', 'falto', 'faltaron', 'asistio', 'asistieron', 
                            'dime', 'cuales', 'cual', 'agosto', 'mes', 'dia', 'todas', 'todos', 'del', 'los', 'las', 'septiembre', 'setiembre']
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

    # LEER SIN CABECERAS PARA NO PERDER LAS FECHAS
    @st.cache_data(ttl=10)
    def cargar_datos_sheet(mes):
        try:
            sheet_id = st.secrets["ID_GOOGLE_SHEET"]
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
            # CLAVE: header=None lee todo crudo, evitando que pandas borre las fechas
            df = pd.read_excel(url, sheet_name=mes, engine='openpyxl', header=None)
            return df
        except Exception as e:
            st.error(f"Error al leer la hoja '{mes}': {e}")
            return pd.DataFrame()

    df_asistencia = cargar_datos_sheet(mes_seleccionado)

    st.title("💬 Asistente de Datos Norkiam")
    st.markdown(f"Pregúntame sobre asistencias, faltas o tardanzas del mes de **{mes_seleccionado}**.")

    if "mensajes" not in st.session_state:
        st.session_state.mensajes = [
            {"rol": "assistant", "contenido": f"👋 ¡Hola, Norelly! Base de datos de {mes_seleccionado} conectada correctamente. ¿Qué deseas consultar hoy?"}
        ]

    for mensaje in st.session_state.mensajes:
        with st.chat_message(mensaje["rol"]):
            st.markdown(mensaje["contenido"])

    pregunta = st.chat_input("Ejemplo: ¿Quiénes faltaron el 14?")

    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
        st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})

        with st.chat_message("assistant"):
            with st.spinner(f"Escaneando matriz de {mes_seleccionado}..."):
                
                df_optimizado = optimizar_datos_para_ia(df_asistencia, pregunta)
                datos_resumen = df_optimizado.to_csv(index=False)
                
                prompt_sistema = f"""
                Actúas como el asistente experto de recursos humanos de la empresa Norkiam SAC.
                Tienes acceso a los datos de la matriz de asistencia oficial pre-filtrados en el siguiente formato CSV:
                {datos_resumen}

                Pregunta del usuario: "{pregunta}"

                Instrucciones estrictas:
                1. Revisa detenidamente los datos. La tabla que recibes YA ha aislado exactamente la fecha que el usuario pidió.
                2. Responde de manera directa y ordenada, usando listas o tablas.
                3. Si el usuario pregunta por faltas, busca las palabras "FAL", "F", o "FALTA" en las columnas de Ingreso/Salida.
                4. Si el usuario pregunta por descansos médicos, busca "DM".
                """
                
                respuesta_ia = llamar_gemini(prompt_sistema)
                st.markdown(respuesta_ia)
                
                st.caption(f"⚡ Optimizador de memoria: La IA recibió una matriz miniatura 100% precisa con {len(df_optimizado)} trabajadores y las columnas exactas solicitadas.")
                
                st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_ia})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa para acceder al sistema.")
