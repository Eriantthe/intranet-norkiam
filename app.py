import streamlit as st
import sqlite3
import pandas as pd
import json
import io
import time
import re
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 1. INICIALIZAR BASE DE DATOS Y MEMORIA
def inicializar_base_datos():
    conn = sqlite3.connect('norkiam.db')
    c = conn.cursor()
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS archivos_procesados (
            id_archivo TEXT PRIMARY KEY,
            nombre_archivo TEXT
        )
    ''')
    
    # Datos de prueba para que la tabla no esté vacía al iniciar
    c.execute("SELECT COUNT(*) FROM registro_asistencia")
    if c.fetchone()[0] == 0:
        datos_prueba = [
            ('2026-07-01', 'Día', 'APO', 'GARCIA FUENTES LUZ MARIA', '6:40', '15:00', 'Presente'),
            ('2026-07-01', 'Noche', 'AA', 'AGUILAR DOLORES NARCISO GASPAR', '19:00', '7:00', 'Presente'),
            ('2026-07-02', 'Noche', 'AA', 'AGUILAR DOLORES NARCISO GASPAR', '', '', 'FALTA'),
            ('2026-07-03', 'Noche', 'AA', 'AGUILAR DOLORES NARCISO GASPAR', '', '', 'FALTA')
        ]
        c.executemany('''INSERT INTO registro_asistencia 
                         (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia) 
                         VALUES (?,?,?,?,?,?,?)''', datos_prueba)
    conn.commit()
    conn.close()

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

try:
    st.image("logo.jpg", width=250)
except:
    pass

st.sidebar.title("⚙ Panel de Control")
clave_ingresada = st.sidebar.text_input("1. Clave de Acceso Corporativo:", type="password")

if clave_ingresada == st.secrets["CLAVE_ACCESO"]:
    st.sidebar.success("✅ Acceso autorizado")
    
    client = genai.Client(api_key=st.secrets["API_KEY_GOOGLE"])
    
    # --- NUEVO SISTEMA DE ESCUDO (MODEL FALLBACK) ---
    def llamar_gemini_blindado(prompt_o_lista):
        # Lista de modelos de élite. Si uno falla o no está autorizado, salta al siguiente silenciosamente.
        modelos_disponibles = [
            'gemini-1.5-pro',
            'gemini-1.5-flash-002',
            'gemini-1.5-pro-latest',
            'gemini-2.0-flash-exp',
            'gemini-pro'
        ]
        ultimo_error = None
        
        for modelo in modelos_disponibles:
            try:
                return client.models.generate_content(model=modelo, contents=prompt_o_lista)
            except Exception as e:
                ultimo_error = e
                continue # Falla silenciosamente y prueba el siguiente modelo de la lista
        
        # Si todos fallan (muy improbable), mostramos el error
        raise Exception(f"No se pudo conectar a ningún modelo de Gemini. Detalle: {ultimo_error}")
    
    # 3. SINCRONIZACIÓN AUTÓNOMA SILENCIOSA
    if "drive_sincronizado" not in st.session_state:
        with st.spinner("Sincronizando archivos corporativos..."):
            try:
                credenciales_dict = json.loads(st.secrets["CREDENCIALES_DRIVE"])
                creds = service_account.Credentials.from_service_account_info(
                    credenciales_dict, scopes=['https://www.googleapis.com/auth/drive.readonly']
                )
                drive_service = build('drive', 'v3', credentials=creds)
                carpeta_id = st.secrets["CARPETA_DRIVE"]
                
                resultados = drive_service.files().list(
                    q=f"'{carpeta_id}' in parents and trashed=false and mimeType='application/pdf'",
                    fields="files(id, name)"
                ).execute()
                archivos = resultados.get('files', [])
                
                conn = sqlite3.connect('norkiam.db')
                c = conn.cursor()
                
                for archivo in archivos:
                    c.execute("SELECT id_archivo FROM archivos_procesados WHERE id_archivo = ?", (archivo['id'],))
                    if not c.fetchone():
                        request = drive_service.files().get_media(fileId=archivo['id'])
                        fh = io.BytesIO()
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while not done:
                            status, done = downloader.next_chunk()
                            
                        documento = types.Part.from_bytes(data=fh.getvalue(), mime_type='application/pdf')
                        instruccion = """
                        Extrae los registros de asistencia. Devuelve ÚNICAMENTE un JSON puro con este formato exacto, sin markdown ni explicaciones:
                        [{"fecha": "2026-07-01", "turno": "Día", "area": "AA", "nombre_completo": "NOMBRE APELLIDO", "hora_entrada": "07:00", "hora_salida": "19:00", "estado_asistencia": "Presente"}]
                        """
                        
                        try:
                            respuesta = llamar_gemini_blindado([documento, instruccion])
                            texto_limpio = re.sub(r'```json|```', '', respuesta.text).strip()
                            datos_extraidos = json.loads(texto_limpio)
                            
                            for fila in datos_extraidos:
                                c.execute('''INSERT INTO registro_asistencia 
                                             (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia) 
                                             VALUES (?,?,?,?,?,?,?)''', 
                                          (fila.get('fecha'), fila.get('turno'), fila.get('area'), fila.get('nombre_completo'), 
                                           fila.get('hora_entrada'), fila.get('hora_salida'), fila.get('estado_asistencia')))
                            
                            c.execute("INSERT INTO archivos_procesados (id_archivo, nombre_archivo) VALUES (?, ?)", (archivo['id'], archivo['name']))
                            conn.commit()
                        except Exception as e:
                            print(f"Error procesando {archivo['name']}: {e}")
                            
                conn.close()
                st.session_state.drive_sincronizado = True
            except Exception as e:
                st.session_state.drive_sincronizado = True
                st.sidebar.warning("Aviso: No se pudo conectar con Drive en este momento.")

    # 4. CHATBOT CORPORATIVO
    st.title("💬 Asistente de Datos Norkiam")
    st.write("Pregúntame sobre el historial de asistencias o cálculos de planillas quincenales.")
    
    if "mensajes" not in st.session_state:
        st.session_state.mensajes = []

    for mensaje in st.session_state.mensajes:
        with st.chat_message(mensaje["rol"]):
            st.markdown(mensaje["contenido"])

    pregunta = st.chat_input("Ej: Dame las faltas de Narciso de la quincena de julio...")
    
    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
        st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})
        
        with st.chat_message("assistant"):
            with st.spinner("Procesando consulta..."):
                query_limpia = ""
                try:
                    prompt_sql = f"""
                    Actúas como un motor SQL estricto para SQLite. 
                    Tabla: registro_asistencia (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia)
                    Pregunta: "{pregunta}"
                    
                    Reglas inquebrantables:
                    1. Devuelve ÚNICAMENTE la consulta SQL que empiece con SELECT. NADA DE TEXTO EXTRA.
                    2. Si buscan un nombre, sepáralo y usa: nombre_completo LIKE '%PALABRA1%' AND nombre_completo LIKE '%PALABRA2%'.
                    3. Para faltas, usa: estado_asistencia LIKE '%FALTA%'.
                    4. NUNCA uses funciones como MONTH(), YEAR(), o DAY(). Usa LIKE '%-07-%' para meses o igualdades simples.
                    """
                    
                    respuesta_sql = llamar_gemini_blindado(prompt_sql)
                    
                    texto_ia = respuesta_sql.text.replace('```sql', '').replace('```', '').strip()
                    inicio_select = texto_ia.upper().find('SELECT')
                    
                    if inicio_select != -1:
                        query_limpia = texto_ia[inicio_select:]
                    else:
                        query_limpia = "SELECT * FROM registro_asistencia LIMIT 1"
                        
                    query_limpia = query_limpia.rstrip(';')
                    
                    conn = sqlite3.connect('norkiam.db')
                    df = pd.read_sql_query(query_limpia, conn)
                    conn.close()
                    
                    if df.empty:
                        respuesta_final = "No encontré registros exactos en la base de datos para esa consulta. Intenta buscar por el apellido principal."
                    else:
                        datos_texto = df.to_csv(index=False)
                        prompt_resumen = f"""
                        Pregunta original: "{pregunta}". 
                        Datos filtrados obtenidos:
                        {datos_texto}
                        
                        Instrucciones:
                        1. Responde de forma profesional.
                        2. Muestra los resultados siempre en una tabla Markdown atractiva.
                        3. Haz el cálculo si piden sumatorias.
                        """
                        
                        respuesta_ia = llamar_gemini_blindado(prompt_resumen)
                        respuesta_final = respuesta_ia.text
                        
                    st.markdown(respuesta_final)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_final})
                    
                except Exception as e:
                    error_msg = f"**Error técnico detectado:** {e}"
                    st.error(error_msg)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": error_msg})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa.")
