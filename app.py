import streamlit as st
import sqlite3
import pandas as pd
import json
import io
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 1. INICIALIZAR BASE DE DATOS (Vacía, lista para llenarse con Drive)
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
    
    # --- EL EXTRACTOR AUTOMÁTICO DE DRIVE ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("📥 Base de Datos")
    if st.sidebar.button("🔄 Leer PDFs desde Drive"):
        with st.spinner("Extrayendo tablas a mano con IA... (Puede tomar un par de minutos)"):
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
                
                if not archivos:
                    st.sidebar.warning("No hay PDFs en la carpeta de Drive.")
                else:
                    conn = sqlite3.connect('norkiam.db')
                    c = conn.cursor()
                    c.execute('DELETE FROM registro_asistencia') # Limpia datos antiguos para evitar duplicados
                    
                    for archivo in archivos:
                        request = drive_service.files().get_media(fileId=archivo['id'])
                        fh = io.BytesIO()
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while not done:
                            status, done = downloader.next_chunk()
                            
                        documento = types.Part.from_bytes(data=fh.getvalue(), mime_type='application/pdf')
                        
                        instruccion = """
                        Extrae los registros de asistencia de estas tablas escritas a mano.
                        Devuelve ÚNICAMENTE un arreglo JSON válido con esta estructura exacta para cada fila:
                        [
                          {"fecha": "YYYY-MM-DD", "turno": "Día/Noche", "area": "...", "nombre_completo": "...", "hora_entrada": "...", "hora_salida": "...", "estado_asistencia": "Presente/Falta/Descanso/Permiso"}
                        ]
                        Asegúrate de extraer absolutamente todos los nombres legibles. No uses markdown ni texto adicional. Solo el JSON puro.
                        """
                        respuesta = client.models.generate_content(model='gemini-3.8-flash', contents=[documento, instruccion])
                        texto_json = respuesta.text.strip().replace('```json', '').replace('```', '')
                        
                        datos_extraidos = json.loads(texto_json)
                        for fila in datos_extraidos:
                            c.execute('''INSERT INTO registro_asistencia 
                                         (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia) 
                                         VALUES (?,?,?,?,?,?,?)''', 
                                      (fila.get('fecha'), fila.get('turno'), fila.get('area'), fila.get('nombre_completo'), 
                                       fila.get('hora_entrada'), fila.get('hora_salida'), fila.get('estado_asistencia')))
                    
                    conn.commit()
                    conn.close()
                    st.sidebar.success("✅ Base de datos actualizada exitosamente.")
            except Exception as e:
                st.sidebar.error(f"Error en sincronización: {e}")
    st.sidebar.markdown("---")
    # ----------------------------------------------
    
    st.title("💬 Asistente de Datos Norkiam")
    st.write("Pregúntame sobre el historial de asistencias o cálculos de planillas quincenales.")
    
    if "mensajes" not in st.session_state:
        st.session_state.mensajes = []

    for mensaje in st.session_state.mensajes:
        with st.chat_message(mensaje["rol"]):
            st.markdown(mensaje["contenido"])

    pregunta = st.chat_input("Ej: Genera la asistencia completa de la primera quincena...")
    
    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
        st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})
        
        with st.chat_message("assistant"):
            with st.spinner("Buscando en la base de datos..."):
                try:
                    prompt_sql = f"""
                    Eres el traductor SQL de Norkiam. 
                    Tabla: registro_asistencia (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia)
                    Pregunta: "{pregunta}"
                    Genera ÚNICAMENTE la consulta SQL para responder esto. 
                    
                    REGLAS VITALES:
                    1. Divide el nombre en palabras y usa LIKE separadas por AND.
                    2. No uses markdown. Solo el código SQL puro.
                    """
                    respuesta_sql = client.models.generate_content(model='gemini-3.8-flash', contents=prompt_sql)
                    query_limpia = respuesta_sql.text.strip().replace('```sql', '').replace('```', '')
                    
                    conn = sqlite3.connect('norkiam.db')
                    df = pd.read_sql_query(query_limpia, conn)
                    conn.close()
                    
                    if df.empty:
                        respuesta_final = "No encontré registros en la base de datos para esa consulta. Asegúrate de haber sincronizado el PDF de Drive primero."
                    else:
                        datos_texto = df.to_csv(index=False)
                        prompt_resumen = f"""
                        El usuario preguntó: "{pregunta}". 
                        Datos obtenidos:
                        {datos_texto}
                        
                        Instrucciones:
                        1. Muestra los datos en una tabla Markdown limpia.
                        2. Si pide cálculos para planillas (ej. quincenas), suma los días basados en el estado de asistencia y entrégale el reporte.
                        """
                        respuesta_ia = client.models.generate_content(model='gemini-3.8-flash', contents=prompt_resumen)
                        respuesta_final = respuesta_ia.text
                        
                    st.markdown(respuesta_final)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_final})
                    
                except Exception as e:
                    st.error(f"Error técnico: {e}")

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa.")
