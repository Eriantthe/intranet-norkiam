import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Intranet Norkiam SAC", page_icon="🏢", layout="wide")

st.markdown("""
    <style>
    [data-testid="stSidebar"] input {
        color: #0b1a50 !important;
        -webkit-text-fill-color: #0b1a50 !important;
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
# El sistema ahora pide la clave corporativa corta, no la llave de Google
clave_ingresada = st.sidebar.text_input("1. Clave de Acceso Corporativo:", type="password")

# Verifica si la clave ingresada es "norkiam2026" (la que guardaste en Secrets)
if clave_ingresada == st.secrets["CLAVE_ACCESO"]:
    st.sidebar.success("✅ Acceso autorizado")
    
    # Conecta con Google usando la llave oculta en la bóveda
    client = genai.Client(api_key=st.secrets["API_KEY_GOOGLE"])
    
    st.sidebar.subheader("2. Carga de Documentos")
    archivo_subido = st.sidebar.file_uploader("Sube facturas o asistencias (PDF)", type=["pdf"])
    
    if archivo_subido:
        st.sidebar.success("✅ ¡Documento recibido!")
        
        st.subheader("💬 Asistente Virtual Norkiam (Modo Visión)")
        pregunta = st.text_input("Ingresa tu consulta sobre el registro de asistencia:")
        
        if pregunta:
            with st.spinner("Descifrando la caligrafía y analizando la tabla..."):
                try:
                    # Prepara el PDF de forma segura en la memoria
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
