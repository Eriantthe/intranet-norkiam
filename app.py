import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Intranet Norkiam SAC", page_icon="🏢", layout="wide")

st.markdown("""
    <style>
    /* 1. Pintar el fondo del panel lateral con el azul Norkiam */
    [data-testid="stSidebar"] {
        background-color: #0b1a50 !important;
    }
    
    /* 2. Pintar todas las letras del panel lateral de blanco para que resalten */
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3, 
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] div,
    [data-testid="stSidebar"] label {
        color: white !important;
    }
    
    /* 3. Mantener la cajita de la clave en blanco con letras azules */
    [data-testid="stSidebar"] input {
        background-color: white !important;
        color: #0b1a50 !important;
        -webkit-text-fill-color: #0b1a50 !important;
    }
    
    /* 4. NUEVO: Arreglar el texto del archivo subido (para que no sea blanco sobre blanco) */
    [data-testid="stFileUploader"] div,
    [data-testid="stFileUploader"] p,
    [data-testid="stFileUploader"] small {
        color: #0b1a50 !important;
    }
    </style>
""", unsafe_allow_html=True)

try:
    st.image("logo.jpg", width=250)
except:
    pass

st.title("Intranet Corporativa - Norkiam SAC")
st.markdown("---")
st.write("**Bienvenido al sistema de gestión documental.** Sube facturas o asistencias manuscritas y consulta la información al instante con nuestro Escáner Inteligente.")

st.sidebar.title("⚙️ Panel de Control")
# El sistema ahora pide la clave corporativa corta
clave_ingresada = st.sidebar.text_input("1. Clave de Acceso Corporativo:", type="password")

# Verifica si la clave ingresada es correcta ("norkiam2026")
if clave_ingresada == st.secrets["CLAVE_ACCESO"]:
    st.sidebar.success("✅ Acceso autorizado")
    
    # Conecta con Google usando la llave oculta
    client = genai.Client(api_key=st.secrets["API_KEY_GOOGLE"])
    
    st.sidebar.subheader("2. Carga de Documentos")
    archivo_subido = st.sidebar.file_uploader("Sube facturas o asistencias (PDF)", type=["pdf"])
    
    if archivo_subido:
        st.sidebar.success("✅ ¡Documento recibido!")
        
        st.subheader("💬 Asistente Virtual Norkiam (Modo Visión)")
        pregunta = st.text_input("Ingresa tu consulta sobre el registro de asistencia:")
        
        if pregunta:
            with st.spinner("Descifrando la caligrafía y analizando la tabla con el motor 3.8..."):
                try:
                    # Prepara el PDF
                    documento = types.Part.from_bytes(
                        data=archivo_subido.getvalue(),
                        mime_type='application/pdf'
                    )
                    
                    instruccion = f"""
                    Eres el asistente corporativo de Norkiam SAC.
                    Analiza cuidadosamente este documento escaneado, incluyendo las tablas, las firmas y las letras escritas a mano con lapicero.
                    Responde a la siguiente pregunta basándote ÚNICAMENTE en el documento adjunto.
                    Pregunta del usuario: {pregunta}
                    """
                    
                    # Usa el motor visual para leer el documento
                    respuesta = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=[documento, instruccion]
                    )
                    
                    st.info(respuesta.text)
                    
                except Exception as e:
                    st.error(f"Ocurrió un error en la lectura: {e}")
elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta. Consulta con la administración.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa en el panel lateral para iniciar el sistema.")
