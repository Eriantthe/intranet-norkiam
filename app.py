import streamlit as st
import google.generativeai as genai

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
api_key = st.sidebar.text_input("1. Llave de Acceso (API Key):", type="password")

if api_key:
    genai.configure(api_key=api_key)
    
    st.sidebar.subheader("2. Carga de Documentos")
    archivo_subido = st.sidebar.file_uploader("Sube facturas o asistencias (PDF)", type=["pdf"])
    
    if archivo_subido:
        st.sidebar.success("✅ ¡Documento recibido!")
        
        st.subheader("💬 Asistente Virtual Norkiam (Modo Visión)")
        pregunta = st.text_input("Ingresa tu consulta sobre el registro de asistencia:")
        
        if pregunta:
            with st.spinner("Descifrando la caligrafía y analizando la tabla con el motor 3.8..."):
                try:
                    # ACTUALIZADO A LA VERSIÓN QUE EXIGE GOOGLE
                    modelo = genai.GenerativeModel(model_name="gemini-3.8-flash")
                    
                    documento_inline = {
                        "mime_type": "application/pdf",
                        "data": archivo_subido.getvalue()
                    }
                    
                    instruccion = f"""
                    Eres el asistente corporativo de Norkiam SAC.
                    Analiza cuidadosamente este documento escaneado, incluyendo las tablas, las firmas y las letras escritas a mano con lapicero.
                    Responde a la siguiente pregunta basándote ÚNICAMENTE en el documento adjunto.
                    Pregunta del usuario: {pregunta}
                    """
                    
                    respuesta = modelo.generate_content([documento_inline, instruccion])
                    st.info(respuesta.text)
                    
                except Exception as e:
                    st.error(f"Ocurrió un error en la lectura: {e}")
else:
    st.info("👈 Por favor, ingresa la llave de acceso en el panel lateral para iniciar el sistema.")