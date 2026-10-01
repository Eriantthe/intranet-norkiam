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
    # Tabla para recordar qué PDFs ya se leyeron
    c.execute('''
        CREATE TABLE IF NOT EXISTS archivos_procesados (
            id_archivo TEXT PRIMARY KEY,
            nombre_archivo TEXT
        )
    ''')
    
    # Datos de prueba iniciales (solo si está vacía) para probar sin esperar
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
    
    # 3. SINCRONIZACIÓN AUTÓNOMA (Se ejecuta una sola vez al entrar)
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
                
                nuevos_archivos = 0
                for archivo in archivos:
                    # Verifica si el archivo ya fue procesado antes
                    c.execute("SELECT id_archivo FROM archivos_procesados WHERE id_archivo = ?", (archivo['id'],))
                    if not c.fetchone():
                        nuevos_archivos += 1
                        st.info(f"📄 Analizando nuevo documento: {archivo['name']} (Esto puede tardar unos minutos...)")
                        
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
                        respuesta = client.models.generate_content(model='gemini-3.8-flash', contents=[documento, instruccion])
                        texto_json = respuesta.text.strip().replace('```json', '').replace('```', '')
                        
                        datos_extraidos = json.loads(texto_json)
                        for fila in datos_extraidos:
                            c.execute('''INSERT INTO registro_asistencia 
                                         (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia) 
                                         VALUES (?,?,?,?,?,?,?)''', 
                                      (fila.get('fecha'), fila.get('turno'), fila.get('area'), fila.get('nombre_completo'), 
                                       fila.get('hora_entrada'), fila.get('hora_salida'), fila.get('estado_asistencia')))
                        
                        # Marca el archivo como procesado
                        c.execute("INSERT INTO archivos_procesados (id_archivo, nombre_archivo) VALUES (?, ?)", (archivo['id'], archivo['name']))
                        conn.commit()
                        
                conn.close()
                st.session_state.drive_sincronizado = True
                if nuevos_archivos > 0:
                    st.success(f"✅ {nuevos_archivos} nuevos documentos procesados y añadidos a la base de datos.")
            except Exception as e:
                st.error(f"Error al verificar Drive: {e}")
                st.session_state.drive_sincronizado = True # Evita bucles infinitos de error

    # 4. INTERFAZ DE CHAT Y CÁLCULO DE PLANILLAS
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
            with st.spinner("Buscando en la base de datos..."):
                try:
                    # REGLAS SQL ACTUALIZADAS PARA EVITAR EL ERROR DE 'MONTH'
                    prompt_sql = f"""
                    Eres el traductor SQL de Norkiam. 
                    Tabla: registro_asistencia (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia)
                    Pregunta: "{pregunta}"
                    Genera ÚNICAMENTE la consulta SQL para responder esto. 
                    
                    REGLAS VITALES Y ESTRICTAS:
                    1. Divide el nombre en palabras y usa LIKE separadas por AND (Ej: LIKE '%NARCISO%').
                    2. ES SINTAXIS SQLITE: ¡ESTÁ ESTRICTAMENTE PROHIBIDO USAR MONTH(), YEAR() O DAY()!
                    3. Para buscar meses o quincenas usa formato texto. Ejemplo para julio: fecha LIKE '%-07-%'. Ejemplo para quincenas: fecha BETWEEN '2026-07-01' AND '2026-07-15'.
                    4. No uses markdown. Solo el código SQL puro.
                    """
                    respuesta_sql = client.models.generate_content(model='gemini-3.8-flash', contents=prompt_sql)
                    query_limpia = respuesta_sql.text.strip().replace('```sql', '').replace('```', '')
                    
                    conn = sqlite3.connect('norkiam.db')
                    df = pd.read_sql_query(query_limpia, conn)
                    conn.close()
                    
                    if df.empty:
                        respuesta_final = "No encontré registros en la base de datos para esa consulta. Revisa si el nombre está escrito correctamente o si el archivo correspondiente ya se subió a Drive."
                    else:
                        datos_texto = df.to_csv(index=False)
                        prompt_resumen = f"""
                        El usuario preguntó: "{pregunta}". 
                        Datos obtenidos de la base de datos:
                        {datos_texto}
                        
                        Instrucciones:
                        1. Responde de forma natural, corporativa y amable.
                        2. Si hay varios registros, muéstralos en una tabla Markdown limpia.
                        3. Si el usuario solicita cálculos (quincenas, días asistidos, faltas), realiza el conteo exacto basándote EXCLUSIVAMENTE en los datos provistos y entrégale el reporte claro para planillas.
                        """
                        respuesta_ia = client.models.generate_content(model='gemini-3.8-flash', contents=prompt_resumen)
                        respuesta_final = respuesta_ia.text
                        
                    st.markdown(respuesta_final)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_final})
                    
                except Exception as e:
                    st.error(f"Lo siento, ocurrió un error técnico en la base de datos: {e}")

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa.")
