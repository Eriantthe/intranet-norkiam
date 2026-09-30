import streamlit as st
import json
import io
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

st.set_page_config(page_title="Intranet Norkiam SAC", page_icon="🏢", layout="wide")

# Mantiene tu diseño azul corporativo
st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        background-color: #0b1a50 !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] div, [data-testid="stSidebar"] label {
        color: white !important;
    }
    [data-testid="stSidebar"] input {
        background-color: white !important;
        color: #0b1a50 !important;
        -webkit-text-fill-color: #0b1a50 !important;
    }
    /* Ajuste para que el texto del menú desplegable se lea bien */
    [data-testid="stSidebar"] [data-baseweb="select"] {
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
st.write("**Bienvenido al sistema de gestión documental.** Consulta directamente los archivos de la nube con nuestro Escáner Inteligente.")

st.sidebar.title("⚙️️ Panel de Control")
clave_ingresada = st.sidebar.text_input("1. Clave de Acceso Corporativo:", type="password")

if clave_ingresada == st.secrets["CLAVE_ACCESO"]:
    st.sidebar.success("✅ Acceso autorizado")
    
    client = genai.Client(api_key=st.secrets["API_KEY_GOOGLE"])
    st.sidebar.subheader("2. Archivos en la Nube")
    
    try:
        # 1. El sistema se identifica con Drive usando la credencial
        credenciales_dict = json.loads(st.secrets["CREDENCIALES_DRIVE"])
        creds = service_account.Credentials.from_service_account_info(
            credenciales_dict, 
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        drive_service = build('drive', 'v3', credentials=creds)
        
        # 2. Busca los PDFs en la carpeta de la empresa
        carpeta_id = st.secrets["CARPETA_DRIVE"]
        resultados = drive_service.files().list(
            q=f"'{carpeta_id}' in parents and trashed=false and mimeType='application/pdf'",
            fields="files(id, name)"
        ).execute()
        archivos = resultados.get('files', [])
        
        if not archivos:
            st.sidebar.warning("📂 La carpeta de Drive está vacía. Sube un PDF allí para comenzar.")
        else:
            # 3. Muestra los archivos encontrados en un menú
            nombres_archivos = ["(Selecciona un registro)"] + [f["name"] for f in archivos]
            archivo_seleccionado = st.sidebar.selectbox("Elige el documento a escanear:", nombres_archivos)
            
            if archivo_seleccionado != "(Selecciona un registro)":
                id_seleccionado = next(f["id"] for f in archivos if f["name"] == archivo_seleccionado)
                
                st.subheader(f"💬 Analizando: {archivo_seleccionado}")
                pregunta = st.text_input("Ingresa tu consulta sobre este registro:")
                
                if pregunta:
                    with st.spinner("Descargando de Drive y analizando con Inteligencia Artificial..."):
                        try:
                            # 4. Descarga silenciosa a la memoria RAM
                            request = drive_service.files().get_media(fileId=id_seleccionado)
                            fh = io.BytesIO()
                            downloader = MediaIoBaseDownload(fh, request)
                            done = False
                            while done is False:
                                status, done = downloader.next_chunk()
                            
                            # 5. Lectura con Gemini 3.8
                            documento = types.Part.from_bytes(
                                data=fh.getvalue(),
                                mime_type='application/pdf'
                            )
                            
                            instruccion = f"""
                            Eres el asistente corporativo de Norkiam SAC.
                            Analiza cuidadosamente este documento escaneado.
                            Responde a la siguiente pregunta basándote ÚNICAMENTE en el documento adjunto.
                            Pregunta del usuario: {pregunta}
                            """
                            
                            respuesta = client.models.generate_content(
                                model='gemini-3.8-flash',
                                contents=[documento, instruccion]
                            )
                            
                            st.info(respuesta.text)
                            
                        except Exception as e:
                            st.error(f"Error al analizar el documento: {e}")
                            
    except Exception as e:
        st.sidebar.error(f"Error de conexión con Drive. Detalle: {e}")
        
elif clave_ingresada:
    st.sidebar.error("❌ Clave incorrecta. Consulta con la administración.")
else:
    st.info("👈 Por favor, ingresa la clave corporativa en el panel lateral para iniciar el sistema.")
