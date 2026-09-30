import streamlit as st
import sqlite3
import pandas as pd
from google import genai

# 1. FUNCIÓN PARA CREAR Y LLENAR LA BASE DE DATOS (FASE DE PRUEBA)
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
    
    # Insertamos datos reales de tu PDF para que veas la magia hoy mismo
    c.execute("SELECT COUNT(*) FROM registro_asistencia")
    if c.fetchone()[0] == 0:
        datos_prueba = [
            ('2026-07-01', 'Día', 'APO', 'GARCIA FUENTES LUZ MARIA', '6:40', '15:00', 'Presente'),
            ('2026-07-02', 'Día', 'APO', 'GARCIA FUENTES LUZ MARIA', '6:40', '19:00', 'Presente'),
            ('2026-07-03', 'Día', 'APO', 'GARCIA FUENTES LUZ MARIA', '6:40', '19:00', 'Presente'),
            ('2026-07-01', 'Noche', 'AA', 'AGUILAR DOLORES NARCISO GASPAR', '19:00', '7:00', 'Presente'),
            ('2026-07-02', 'Noche', 'AA', 'AGUILAR DOLORES NARCISO GASPAR', '19:00', '7:00', 'Presente')
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
    st.sidebar.info("Base de datos local conectada y lista.")
    
    # Conectamos el cerebro de Google
    client = genai.Client(api_key=st.secrets["API_KEY_GOOGLE"])
    
    st.title("💬 Asistente de Datos Norkiam")
    st.write("Pregúntame sobre el historial de asistencias, faltas o tardanzas del personal.")
    
    # 3. SISTEMA DE MEMORIA DEL CHAT
    if "mensajes" not in st.session_state:
        st.session_state.mensajes = []

    for mensaje in st.session_state.mensajes:
        with st.chat_message(mensaje["rol"]):
            st.markdown(mensaje["contenido"])

    # 4. EL CEREBRO DEL AGENTE IA
    pregunta = st.chat_input("Ej: Dame el resumen de asistencias de Narciso este mes...")
    
    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
        st.session_state.mensajes.append({"rol": "user", "contenido": pregunta})
        
        with st.chat_message("assistant"):
            with st.spinner("Traduciendo a código y buscando en la base de datos..."):
                try:
                    # Paso A: La IA traduce tu pregunta a código SQL matemático
                    prompt_sql = f"""
                    Eres el traductor SQL de Norkiam. 
                    Tabla: registro_asistencia (fecha, turno, area, nombre_completo, hora_entrada, hora_salida, estado_asistencia)
                    Pregunta: "{pregunta}"
                    Genera ÚNICAMENTE la consulta SQL para responder esto. 
                    Usa siempre LIKE '%...%' y MAYÚSCULAS para buscar nombres (ej: LIKE '%GARCIA%'). 
                    No uses comillas invertidas ni markdown. Solo el código SQL puro.
                    """
                    respuesta_sql = client.models.generate_content(model='gemini-3.8-flash', contents=prompt_sql)
                    query_limpia = respuesta_sql.text.strip().replace('```sql', '').replace('```', '')
                    
                    # Paso B: La Intranet busca en la base de datos invisible en milisegundos
                    conn = sqlite3.connect('norkiam.db')
                    df = pd.read_sql_query(query_limpia, conn)
                    conn.close()
                    
                    # Paso C: La IA traduce los datos puros a un texto hermoso para ti
                    if df.empty:
                        respuesta_final = "No encontré registros en la base de datos para esa consulta. Intenta buscando con otro apellido."
                    else:
                        datos_texto = df.to_csv(index=False)
                        prompt_resumen = f"""
                        El usuario preguntó: "{pregunta}". 
                        La base de datos entregó estos resultados precisos:
                        {datos_texto}
                        
                        Instrucciones:
                        1. Crea una respuesta amable y corporativa.
                        2. Muestra los datos obligatoriamente usando una tabla Markdown limpia y elegante.
                        3. Si el usuario pidió un resumen o cálculo, hazlo basándote en los datos.
                        """
                        respuesta_ia = client.models.generate_content(model='gemini-3.8-flash', contents=prompt_resumen)
                        respuesta_final = respuesta_ia.text
                        
                    st.markdown(respuesta_final)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": respuesta_final})
                    
                except Exception as e:
                    error_msg = f"Lo siento, ocurrió un error técnico al buscar los datos: {e}"
                    st.error(error_msg)
                    st.session_state.mensajes.append({"rol": "assistant", "contenido": error_msg})

elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa.")
