import streamlit as st
import sqlite3
import pandas as pd
import json
import io
import time
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 1. INICIALIZAR BASE DE DATOS Y MEMORIA DE ARCHIVOS
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
    
    # 3. SINCRONIZACIÓN AUTÓNOMA CON PROTECCIÓN 503
    if "drive_sincronizado" not in st.session_state:
        with st.spinner("Verificando nuevos registros en Drive..."):
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
                        Extrae los registros de asistencia. Devuelve ÚNICAMENTE un arreglo JSON con:
                        [{"fecha": "YYYY-MM-DD", "turno": "Día/Noche", "area": "...", "nombre_completo": "...", "hora_entrada": "...", "hora_salida": "...", "estado_asistencia": "Presente/FALTA/Descanso/Permiso"}]
                        """
                        
                        # Intento con reintento automático si falla por 503
                        respuesta = None
                        for intento in range(3):
                            try:
                                respuesta = client.models.generate_content(model='gemini-3.8-flash', contents=[documento, instruccion])
                                break
                            except Exception:
                                time.sleep(2)
                                
                        if respuesta:
                            texto_json = respuesta.text.strip().replace('```json', '').replace('```', '')
                            datos_extraidos = json.loads(texto_json)
                            for fila in datos_extraidos:
                                c.execute('''INSERT INTO registro_asistencia 
                                             (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia) 
                                             VALUES (?,?,?,?,?,?,?)''', 
                                          (fila.get('fecha'), fila.get('turno'), fila.get('area'), fila.get('nombre_completo'), 
                                           fila.get('hora_entrada'), fila.get('hora_salida'), fila.get('estado_asistencia')))
                            
                            c.execute("INSERT INTO archivos_procesados (id_archivo, nombre_archivo) VALUES (?, ?)", (archivo['id'], archivo['name']))
                            conn.commit()
                        
                conn.close()
                st.session_state.drive_sincronizado = True
            except Exception as e:
                st.session_state.drive_sincronizado = True

    # 4. INTERFAZ DE CHAT
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
            with st.spinner("Analizando consulta y consultando base de datos..."):
                try:
                    prompt_sql = f"""
                    Eres el traductor SQL de Norkiam. 
                    Tabla: registro_asistencia (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia)
                    Pregunta del usuario: "{pregunta}"
                    Genera ÚNICAMENTE una consulta SQL válida para SQLite que responda esto.
                    
                    REGLAS ESTRICTAS:
                    1. Si la pregunta es general o no especifica nombre, haz un SELECT general filtrando por fechas o estados si aplica (Ej: SELECT * FROM registro_asistencia WHERE estado_asistencia = 'FALTA').
                    2. Si especifica nombre, usa LIKE para buscar palabras clave.
                    3. ESTÁ PROHIBIDO usar MONTH(), YEAR() o DAY(). Usa formato fecha 'YYYY-MM-DD' o BETWEEN.
                    4. No uses markdown ni explicaciones. Solo el código SQL puro.
                    """
                    
                    # Llamada a Gemini con reintento automático ante el error 503
                    respuesta_sql = None
                    for intento in range(3):
                        try:
                            respuesta_sql = client.models.generate_content(model='gemini-3.8-flash', contents=prompt_sql)
                            break
                        except Exception:
                            time.sleep(2)
                            
                    if not respuesta_sql:
                        raise Exception("Los servidores de Google están experimentando alta demanda en este momento. Por favor, intenta de nuevo en unos segundos.")
                        
                    query_limpia = respuesta_sql.text.strip().replace('```sql', '').replace('```', '')
                    
                    conn = sqlite3.connect('norkiam.db')
                    df = pd.read_sql_query(query_limpia, conn)
                    conn.close()
                    
                    if df.empty:
                        respuesta_final = "No encontré registros que coincidan con esa consulta en la base de datos."
                    else:
                        datos_texto = df.to_csv(index=False)
                        prompt_resumen = f"""
                        El usuario preguntó: "{pregunta}". 
                        Datos obtenidos:
                        {datos_texto}
                        
                        Instrucciones:
                        1. Responde de forma natural y corporativa.
                        2. Muestra los resultados en una tabla Markdown limpia.
                        3. Haz los cálculos necesarios si pidieron resúmenes o totales.
                        """
                        
                        respuesta_ia = client.models.generate_content(model='gemini-3.8-flash', contents=prompt_resumen)
                        respuesta_final = respuesta_ia.text
                        
                    st.markdown(respuesta_final)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_final})
                    
                except Exception as e:
                    error_msg = f"Aviso del sistema: {e}"
                    st.warning(error_msg)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": error_msg})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa.")
