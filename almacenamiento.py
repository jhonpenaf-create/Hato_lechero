import streamlit as st
import json
import os

# --- 1. Ruta absoluta y estable, sin importar desde dónde se ejecute streamlit run ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_JSON = os.path.join(BASE_DIR, "datos.json")


# --- 2. Funciones de carga y guardado, SIN @st.cache_data porque los datos cambian ---
def cargar_datos():
    """Lee el JSON. Si no existe o está vacío/corrupto, devuelve una lista vacía."""
    if not os.path.exists(RUTA_JSON):
        return []
    try:
        with open(RUTA_JSON, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
            if not contenido:
                return []
            return json.loads(contenido)
    except json.JSONDecodeError:
        st.warning("El archivo JSON estaba corrupto, se reinició vacío.")
        return []


def guardar_datos(lista_datos):
    """Sobrescribe el archivo con la LISTA COMPLETA (no solo el dato nuevo)."""
    with open(RUTA_JSON, "w", encoding="utf-8") as f:
        json.dump(lista_datos, f, ensure_ascii=False, indent=2)


def agregar_dato(nuevo_dato: dict):
    """Patrón correcto: lee todo -> agrega -> guarda todo."""
    datos = cargar_datos()      # 1. Cargar lo que ya existe
    datos.append(nuevo_dato)    # 2. Agregar el nuevo registro
    guardar_datos(datos)        # 3. Guardar la lista completa de vuelta


# --- 3. Interfaz de Streamlit ---
st.title("Ejemplo de persistencia de datos con JSON")

with st.form("form_nuevo_registro", clear_on_submit=True):
    nombre = st.text_input("Nombre")
    valor = st.number_input("Valor", step=1.0)
    enviado = st.form_submit_button("Guardar")

    if enviado:
        if nombre.strip() == "":
            st.error("El nombre no puede estar vacío.")
        else:
            agregar_dato({"nombre": nombre, "valor": valor})
            st.success("¡Dato guardado correctamente!")

st.subheader("Datos almacenados actualmente")
datos_actuales = cargar_datos()
if datos_actuales:
    st.dataframe(datos_actuales)
else:
    st.info("Aún no hay datos guardados.")

st.caption(f"Archivo JSON usado: {RUTA_JSON}") 