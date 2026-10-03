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

    def optimizar_datos_para_ia(df, pregunta):
        pregunta_lower = pregunta.lower().replace('?', '').replace('¿', '').replace(',', '')
        
        fila_base = 0
        for idx in range(min(15, len(df))):
            fila_texto = ' '.join(df.iloc[idx].fillna('').astype(str)).upper()
            if 'DNI' in fila_texto and 'NOMBRES' in fila_texto:
                fila_base = idx
                break
                
        col_area = 1; col_dni = 2; col_nombres = 3
        for c_idx, val in enumerate(df.iloc[fila_base]):
            val_str = str(val).upper()
            if 'ÁREA' in val_str or 'AREA' in val_str: col_area = c_idx
            if 'DNI' in val_str: col_dni = c_idx
            if 'NOMBRES' in val_str: col_nombres = c_idx
            
        columnas_base_indices = [col_area, col_dni, col_nombres]
        columnas_fecha_indices = []
        
        numeros = re.findall(r'\b\d{1,2}\b', pregunta_lower)
        dia_str = ""
        if numeros:
            dia_str = numeros[0].zfill(2)
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
                    
        fila_datos_inicio = fila_base + 1
        
        if columnas_fecha_indices:
            indices_extraer = columnas_base_indices + columnas_fecha_indices
            df_filtrado = df.iloc[fila_datos_inicio:, indices_extraer].copy()
            df_filtrado.columns = ["Area", "DNI", "Apellidos_y_Nombres", f"Ingreso_dia_{dia_str}", f"Salida_dia_{dia_str}"]
        else:
            df_filtrado = df.iloc[fila_datos_inicio:].copy()
            nombres_cols = list(df_filtrado.columns)
            nombres_cols[col_area] = "Area"
            nombres_cols[col_dni] = "DNI"
            nombres_cols[col_nombres] = "Apellidos_y_Nombres"
            df_filtrado.columns = nombres_cols

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
            df = pd.read_excel(url, sheet_name=mes, engine='openpyxl', header=None)
            return df
        except Exception as e:
            st.error(f"Error al leer la hoja '{mes}': {e}")
            return pd.DataFrame()

    df_asistencia = cargar_datos_sheet(mes_seleccionado)

    # =========================================================================
    # TABS (PESTAÑAS)
    # =========================================================================
    tab_chat, tab_planilla = st.tabs(["💬 Chat Asistente", "📝 Planilla Interactiva"])

    # -------------------------------------------------------------------------
    # PESTAÑA 1: CHAT
    # -------------------------------------------------------------------------
    with tab_chat:
        st.markdown(f"Pregúntame sobre asistencias, faltas o tardanzas del mes de **{mes_seleccionado}**.")

        if "mensajes" not in st.session_state:
            st.session_state.mensajes = [
                {"rol": "assistant", "contenido": f"👋 ¡Hola, Norelly! Base de datos conectada. ¿Qué deseas consultar hoy?"}
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
                    Tienes acceso a los datos de la matriz pre-filtrados en el siguiente formato CSV:
                    {datos_resumen}

                    Pregunta del usuario: "{pregunta}"

                    Instrucciones estrictas:
                    1. Revisa detenidamente los datos.
                    2. Responde de manera directa y ordenada, usando listas o tablas.
                    3. Si el usuario pregunta por faltas, busca "FAL", "F", o "FALTA".
                    """
                    
                    respuesta_ia = llamar_gemini(prompt_sistema)
                    st.markdown(respuesta_ia)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_ia})

    # -------------------------------------------------------------------------
    # PESTAÑA 2: PLANILLA Y BONOS INDIVIDUALES
    # -------------------------------------------------------------------------
    with tab_planilla:
        st.header("💰 Generador de Planillas Quincenales")
        st.markdown("Calcula los pagos por quincena, aplica descuentos y asigna **bonos individuales** manualmente.")
        
        # 1. Selector de Quincena
        quincena_sel = st.radio("📅 Selecciona la Quincena a procesar:", ["1ra Quincena", "2da Quincena"], horizontal=True)
        
        # 2. Tarifas Globales
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        pago_hora_base = col1.number_input("Sueldo Base por Hora (S/.)", min_value=0.0, value=4.71, step=0.01)
        dcto_falta = col2.number_input("Descuento por Falta (S/.)", min_value=0.0, value=37.67, step=0.01)
        porcentaje_onp = col3.number_input("Descuento ONP/AFP (%)", min_value=0.0, value=13.0, step=0.5)
        
        # 3. Nombres dinámicos extraídos del Excel
        default_horas = "1ERA QUINCENA" if quincena_sel == "1ra Quincena" else "2DA QUINCENA"
        
        st.markdown("---")
        st.caption("Nombres de columnas exactos detectados en tu Excel:")
        c1, c2 = st.columns(2)
        col_horas_input = c1.text_input("Columna de Horas:", value=default_horas)
        col_faltas_input = c2.text_input("Columna de Faltas:", value="FAL")

        if not df_asistencia.empty:
            # Buscar la fila base de manera segura
            fila_base_p = 0
            for idx in range(min(15, len(df_asistencia))):
                fila_texto = ' '.join(df_asistencia.iloc[idx].fillna('').astype(str)).upper()
                if 'DNI' in fila_texto and 'NOMBRE' in fila_texto:
                    fila_base_p = idx
                    break
            
            df_temp = df_asistencia.iloc[fila_base_p + 1:].copy()
            # Forzamos la cabecera a string de manera robusta
            df_temp.columns = df_asistencia.iloc[fila_base_p].fillna('').astype(str).str.strip().str.upper()
            
            col_horas_upper = col_horas_input.strip().upper()
            col_faltas_upper = col_faltas_input.strip().upper()
            
            if col_horas_upper in df_temp.columns and col_faltas_upper in df_temp.columns:
                
                # --- SOLUCIÓN DEL ERROR TIPO: BÚSQUEDA SEGURA DE COLUMNAS ---
                columnas_dni = [c for c in df_temp.columns if 'DNI' in str(c).upper()]
                columnas_nom = [c for c in df_temp.columns if 'NOMBRE' in str(c).upper()]
                
                if not columnas_dni or not columnas_nom:
                    st.error("❌ No se detectó la columna 'DNI' o 'NOMBRES' en la matriz. Verifica la estructura del archivo.")
                else:
                    col_dni_name = columnas_dni[0]
                    col_nom_name = columnas_nom[0]
                    
                    horas = pd.to_numeric(df_temp[col_horas_upper], errors='coerce').fillna(0)
                    faltas = pd.to_numeric(df_temp[col_faltas_upper], errors='coerce').fillna(0)
                    
                    # CREAR TABLA BASE PARA EL EDITOR (INTERACTIVO)
                    df_editor = pd.DataFrame({
                        "DNI": df_temp[col_dni_name],
                        "NOMBRES": df_temp[col_nom_name],
                        "HORAS": horas,
                        "FALTAS": faltas,
                        "BONO INDIVIDUAL (S/.)": 0.0  # El usuario editará esta columna
                    })
                    
                    # Filtrar filas vacías de manera segura
                    df_editor = df_editor[df_editor["DNI"].astype(str).str.strip() != "nan"]
                    df_editor = df_editor[df_editor["DNI"].astype(str).str.strip() != ""]
                    
                    st.subheader("👇 Asigna Bonos Individuales")
                    st.info("Haz doble clic en la columna 'Bono Individual' para darle un extra a trabajadores específicos antes de calcular el pago.")
                    
                    # RENDERIZAR LA TABLA EDITABLE EN PANTALLA
                    df_editado = st.data_editor(
                        df_editor,
                        disabled=["DNI", "NOMBRES", "HORAS", "FALTAS"], # Bloquea la identidad para evitar errores
                        use_container_width=True,
                        key=f"editor_bonos_{mes_seleccionado}_{quincena_sel}",
                        column_config={
                            "BONO INDIVIDUAL (S/.)": st.column_config.NumberColumn(
                                "Bono Individual (S/.)",
                                min_value=0.0,
                                format="S/. %.2f"
                            )
                        }
                    )
                    
                    st.markdown("---")
                    if st.button("⚙️ Procesar Planilla y Calcular Neto"):
                        # Cálculos con los datos del editor
                        sueldo_bruto = df_editado["HORAS"] * pago_hora_base
                        dcto_faltas_total = df_editado["FALTAS"] * dcto_falta
                        monto_onp = sueldo_bruto * (porcentaje_onp / 100)
                        bonos_personales = df_editado["BONO INDIVIDUAL (S/.)"]
                        
                        # Ecuación Final
                        sueldo_neto = sueldo_bruto - dcto_faltas_total - monto_onp + bonos_personales
                        sueldo_neto = sueldo_neto.clip(lower=0) # Para que nunca salga pago negativo
                        
                        df_final = pd.DataFrame({
                            "DNI": df_editado["DNI"],
                            "NOMBRES": df_editado["NOMBRES"],
                            "HORAS PAGADAS": df_editado["HORAS"],
                            "SUELDO BRUTO (S/.)": sueldo_bruto.round(2),
                            f"ONP/AFP {porcentaje_onp}% (S/.)": monto_onp.round(2),
                            "DCTO FALTAS (S/.)": dcto_faltas_total.round(2),
                            "BONOS EXTRAS (S/.)": bonos_personales.round(2),
                            "NETO A PAGAR (S/.)": sueldo_neto.round(2)
                        })
                        
                        st.success("✅ ¡Planilla calculada exitosamente!")
                        st.dataframe(df_final, use_container_width=True)
                        
                        csv_descarga = df_final.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label=f"📥 Descargar Archivo Excel CSV ({quincena_sel})",
                            data=csv_descarga,
                            file_name=f"Planilla_Pagos_{quincena_sel[:3]}_Norkiam_{mes_seleccionado}.csv",
                            mime="text/csv"
                        )
            else:
                st.error(f"❌ Asegúrate de que las columnas '{col_horas_input}' y '{col_faltas_input}' existan en tu Google Sheets.")

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa para acceder al sistema.")
