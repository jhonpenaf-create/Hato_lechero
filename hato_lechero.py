"""
╔══════════════════════════════════════════════════════════════════╗
║          HatoGest Pro — Sistema de Gestión de Hato Lechero       ║
║          Parámetros reproductivos de alta eficiencia             ║
║          Ejecutar: streamlit run hato_lechero.py                 ║
╚══════════════════════════════════════════════════════════════════╝

Dependencias:
    pip install streamlit pandas plotly

"""

import streamlit as st # pyright: ignore[reportMissingImports]
import pandas as pd # pyright: ignore[reportMissingModuleSource]
import plotly.graph_objects as go # pyright: ignore[reportMissingImports]
import plotly.express as px # pyright: ignore[reportMissingImports]
from datetime import date, timedelta, datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List
import json
import copy
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from storage import cargar_animales_persistidos, guardar_animales_persistidos # pyright: ignore[reportMissingImports]

# ═══════════════════════════════════════════════════════════════════
# PARÁMETROS REPRODUCTIVOS DE ALTA EFICIENCIA
# ═══════════════════════════════════════════════════════════════════
PARAMS = {
    "dias_voluntario_espera": 50,        # DVE: días post-parto antes de inseminar
    "dias_gestacion": 280,               # días de gestación (Holstein/Pardo Suizo)
    "dias_secar": 60,                    # días de periodo seco
    "periodo_prenatal": 21,             # días de preparto/transición
    "dias_deteccion_calor": 21,         # ciclo estral
    "servicios_por_concepcion": 1.8,    # promedio SPC eficiencia
    "tasa_concepcion_objetivo": 0.40,   # 40% tasa de concepción objetivo
    "dias_abiertos_objetivo": 110,      # días abiertos objetivo
    "intervalo_parto_meses": 12.5,      # meses entre partos (objetivo)
    "alerta_calor_dias": [18, 19, 20, 21, 22, 23],  # ventana de celo post-IA
    "dias_en_leche_optimo": 305,        # días en leche estándar
}

RAZAS = ["Holstein", "Pardo Suizo", "Girolando", "Normando", "Simmental", "Jersey", "Brahman Lechero"]
ESTADOS = ["vacía", "inseminada", "gestante", "seca"]

ESTADO_COLORES = {
    "gestante": "#10b981",
    "inseminada": "#3b82f6",
    "vacía": "#f59e0b",
    "seca": "#8b5cf6",
}

ESTADO_EMOJIS = {
    "gestante": "🤰",
    "inseminada": "💉",
    "vacía": "⭕",
    "seca": "🔴",
}

PRIORIDAD_COLORES = {
    "urgente": "#ef4444",
    "alta": "#f97316",
    "media": "#eab308",
    "baja": "#22c55e",
}

PRIORIDAD_EMOJIS = {
    "urgente": "🚨",
    "alta": "⚠️",
    "media": "📋",
    "baja": "ℹ️",
}

TIPO_ALERTA_EMOJIS = {
    "vde": "📅",
    "celo": "🔥",
    "dg": "🔬",
    "secado": "🛑",
    "preparto": "🏥",
    "parto": "👶",
    "eficiencia": "📊",
}


# ═══════════════════════════════════════════════════════════════════
# MODELOS DE DATOS
# ═══════════════════════════════════════════════════════════════════
@dataclass
class Animal:
    id: int
    arete: str
    nombre: str
    raza: str
    lactancia: int
    peso_kg: float
    fecha_parto: str                        # ISO format: YYYY-MM-DD
    estado_reproductivo: str
    produccion_litros: float
    condicion_corporal: float
    fecha_ultima_inseminacion: Optional[str] = None
    toro: Optional[str] = None

    def fecha_parto_date(self) -> date:
        return date.fromisoformat(self.fecha_parto)

    def fecha_inseminacion_date(self) -> Optional[date]:
        if self.fecha_ultima_inseminacion:
            return date.fromisoformat(self.fecha_ultima_inseminacion)
        return None


@dataclass
class Alerta:
    tipo: str
    mensaje: str
    fecha: date
    dias_restantes: int
    prioridad: str


@dataclass
class FechasClave:
    inicio_vde: date
    primera_inseminacion: date
    secado_estandar: date
    dias_en_leche: int
    dias_abiertos: int
    diagnostico_gestacion: Optional[date] = None
    confirmacion_gestacion: Optional[date] = None
    parto_estimado: Optional[date] = None
    secado_estimado: Optional[date] = None
    preparto_estimado: Optional[date] = None
    ventana_celo: Optional[List[date]] = None


# ═══════════════════════════════════════════════════════════════════
# LÓGICA DE NEGOCIO
# ═══════════════════════════════════════════════════════════════════
def calcular_fechas_clave(animal: Animal) -> FechasClave:
    hoy = date.today()
    parto = animal.fecha_parto_date()
    insem = animal.fecha_inseminacion_date()

    inicio_vde = parto + timedelta(days=PARAMS["dias_voluntario_espera"])
    primera_ia = parto + timedelta(days=PARAMS["dias_voluntario_espera"] + PARAMS["dias_deteccion_calor"])
    secado_estandar = parto + timedelta(days=305)
    dias_en_leche = (hoy - parto).days
    dias_abiertos = (insem - parto).days if insem else (hoy - parto).days

    fechas = FechasClave(
        inicio_vde=inicio_vde,
        primera_inseminacion=primera_ia,
        secado_estandar=secado_estandar,
        dias_en_leche=dias_en_leche,
        dias_abiertos=dias_abiertos,
    )

    if insem:
        fechas.diagnostico_gestacion = insem + timedelta(days=28)
        fechas.confirmacion_gestacion = insem + timedelta(days=60)

        if animal.estado_reproductivo == "gestante":
            parto_est = insem + timedelta(days=PARAMS["dias_gestacion"])
            fechas.parto_estimado = parto_est
            fechas.secado_estimado = parto_est - timedelta(days=PARAMS["dias_secar"])
            fechas.preparto_estimado = parto_est - timedelta(days=PARAMS["periodo_prenatal"])

        if animal.estado_reproductivo == "inseminada":
            fechas.ventana_celo = [
                insem + timedelta(days=d) for d in PARAMS["alerta_calor_dias"]
            ]

    return fechas


def generar_alertas(animal: Animal) -> List[Alerta]:
    fechas = calcular_fechas_clave(animal)
    hoy = date.today()
    alertas = []

    def add(tipo, mensaje, fecha, prioridad="media"):
        dias = (fecha - hoy).days
        alertas.append(Alerta(tipo=tipo, mensaje=mensaje, fecha=fecha,
                               dias_restantes=dias, prioridad=prioridad))

    # Alerta DVE (días voluntario de espera)
    if 0 <= fechas.dias_en_leche < PARAMS["dias_voluntario_espera"]:
        restantes = PARAMS["dias_voluntario_espera"] - fechas.dias_en_leche
        add("vde", f"Inicio DVE en {restantes} días", fechas.inicio_vde, "baja")

    dias_vde = (fechas.inicio_vde - hoy).days
    if 0 <= dias_vde <= 5 and animal.estado_reproductivo == "vacía":
        add("celo", "¡Iniciar detección de celo — DVE cumplido!", fechas.inicio_vde, "alta")

    # Diagnóstico de gestación
    if fechas.diagnostico_gestacion:
        d = (fechas.diagnostico_gestacion - hoy).days
        if 0 <= d <= 5:
            add("dg", "Diagnóstico de gestación (28 días post-IA)", fechas.diagnostico_gestacion, "alta")
        elif 5 < d <= 10:
            add("dg", "Programar diagnóstico de gestación", fechas.diagnostico_gestacion, "media")

    # Ventana de repetición de celo
    if fechas.ventana_celo and animal.fecha_inseminacion_date():
        insem = animal.fecha_inseminacion_date()
        for fecha_celo in fechas.ventana_celo:
            d = (fecha_celo - hoy).days
            if 0 <= d <= 2:
                dia_num = (fecha_celo - insem).days
                add("celo", f"Ventana repetición de celo (día {dia_num} post-IA)", fecha_celo, "alta")

    # Secado
    if fechas.secado_estimado:
        d = (fechas.secado_estimado - hoy).days
        if 0 <= d <= 14:
            prioridad = "alta" if d <= 7 else "media"
            add("secado", f"Secado en {d} días — Preparar protocolo", fechas.secado_estimado, prioridad)

    # Preparto
    if fechas.preparto_estimado:
        d = (fechas.preparto_estimado - hoy).days
        if 0 <= d <= 21:
            prioridad = "alta" if d <= 7 else "media"
            add("preparto", f"Mover a manga de preparto en {d} días", fechas.preparto_estimado, prioridad)

    # Parto estimado
    if fechas.parto_estimado:
        d = (fechas.parto_estimado - hoy).days
        if 0 <= d <= 14:
            prioridad = "urgente" if d <= 7 else "alta"
            add("parto", f"Parto estimado en {d} días", fechas.parto_estimado, prioridad)

    # Días abiertos excedidos
    if fechas.dias_abiertos > PARAMS["dias_abiertos_objetivo"] and animal.estado_reproductivo == "vacía":
        add("eficiencia",
            f"Días abiertos excedidos: {fechas.dias_abiertos} días (objetivo ≤ {PARAMS['dias_abiertos_objetivo']})",
            hoy, "alta")

    orden = {"urgente": 0, "alta": 1, "media": 2, "baja": 3}
    return sorted(alertas, key=lambda a: orden[a.prioridad])


def fmt_fecha(d: Optional[date]) -> str:
    if not d:
        return "—"
    meses = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{d.day:02d} {meses[d.month-1]} {d.year}"


def fmt_dias_restantes(dias: int) -> str:
    if dias == 0:
        return "⚡ Hoy"
    elif dias > 0:
        return f"En {dias} día(s)"
    else:
        return f"Hace {abs(dias)} día(s)"


# ═══════════════════════════════════════════════════════════════════
# DATOS DE EJEMPLO
# ═══════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════
# PERSISTENCIA DE DATOS
# ═══════════════════════════════════════════════════════════════════
DATA_FILE = os.environ.get("HATO_DATA_FILE", str(APP_DIR / "hato_memoria.json"))


def cargar_datos() -> List[Animal]:
    """Carga los datos desde el almacenamiento persistente, o retorna datos de ejemplo si no existe."""
    try:
        datos = cargar_animales_persistidos()
        if datos:
            return [Animal(**animal_dict) for animal_dict in datos]
    except Exception as e:
        st.warning(f"Error al cargar datos persistidos: {e}. Usando datos de ejemplo.")
    return datos_ejemplo()


def guardar_datos(animales: List[Animal]):
    """Guarda los animales en almacenamiento persistente (JSON y SQLite)."""
    try:
        guardar_animales_persistidos([asdict(a) for a in animales])
    except Exception as e:
        st.error(f"Error al guardar datos: {e}")

def datos_ejemplo() -> List[Animal]:
    hoy = date.today()
    return [
        Animal(id=1, arete="CO-001-4521", nombre="Valentina", raza="Holstein",
               lactancia=3, peso_kg=620,
               fecha_parto=(hoy - timedelta(days=85)).isoformat(),
               fecha_ultima_inseminacion=(hoy - timedelta(days=28)).isoformat(),
               estado_reproductivo="inseminada",
               produccion_litros=32, condicion_corporal=3.0, toro="Absolute"),
        Animal(id=2, arete="CO-001-3892", nombre="Esperanza", raza="Pardo Suizo",
               lactancia=2, peso_kg=580,
               fecha_parto=(hoy - timedelta(days=62)).isoformat(),
               fecha_ultima_inseminacion=None, estado_reproductivo="vacía",
               produccion_litros=24, condicion_corporal=2.75, toro=None),
        Animal(id=3, arete="CO-001-5103", nombre="Fortuna", raza="Holstein",
               lactancia=4, peso_kg=650,
               fecha_parto=(hoy - timedelta(days=240)).isoformat(),
               fecha_ultima_inseminacion=(hoy - timedelta(days=195)).isoformat(),
               estado_reproductivo="gestante",
               produccion_litros=18, condicion_corporal=3.25, toro="Missouri"),
        Animal(id=4, arete="CO-001-6210", nombre="Diamante", raza="Girolando",
               lactancia=1, peso_kg=490,
               fecha_parto=(hoy - timedelta(days=48)).isoformat(),
               fecha_ultima_inseminacion=None, estado_reproductivo="vacía",
               produccion_litros=20, condicion_corporal=3.5, toro=None),
        Animal(id=5, arete="CO-001-7845", nombre="Princesa", raza="Holstein",
               lactancia=5, peso_kg=700,
               fecha_parto=(hoy - timedelta(days=260)).isoformat(),
               fecha_ultima_inseminacion=(hoy - timedelta(days=240)).isoformat(),
               estado_reproductivo="gestante",
               produccion_litros=14, condicion_corporal=3.0, toro="Standup"),
    ]


# ═══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN STREAMLIT
# ═══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="HatoGest Pro",
    page_icon="🐄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Barlow', sans-serif;
}

/* Fondo principal */
.stApp {
    background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: rgba(15,32,39,0.92) !important;
    border-right: 1px solid rgba(255,255,255,0.08);
}
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }

/* Métricas */
[data-testid="metric-container"] {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 12px 16px;
}
[data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important; }

/* Tablas */
.stDataFrame { border-radius: 10px; overflow: hidden; }

/* Inputs */
.stTextInput input, .stNumberInput input, .stSelectbox select, .stDateInput input {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #000000 !important;
    border-radius: 8px !important;
}

/* Botones */
.stButton > button {
    background: #34d399 !important;
    color: #0f2027 !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
}
.stButton > button:hover {
    background: #10b981 !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(52,211,153,0.3) !important;
}

/* Expanders */
.streamlit-expanderHeader {
    background: rgba(255,255,255,0.05) !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
}

/* Texto general */
p, span, label, div { color: #e2e8f0; }
h1, h2, h3 { color: #f1f5f9 !important; }

/* Alerta cards custom */
.alerta-card {
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 8px;
    border-left: 4px solid;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
# ESTADO DE LA APLICACIÓN
# ═══════════════════════════════════════════════════════════════════
if "animales" not in st.session_state:
    st.session_state.animales = cargar_datos()
if "vista" not in st.session_state:
    st.session_state.vista = "Dashboard"
if "animal_sel_id" not in st.session_state:
    st.session_state.animal_sel_id = None


def get_animales() -> List[Animal]:
    return st.session_state.animales


def get_animal(aid: int) -> Optional[Animal]:
    for a in get_animales():
        if a.id == aid:
            return a
    return None


def guardar_animal(animal: Animal):
    animales = get_animales()
    ids = [a.id for a in animales]
    if animal.id in ids:
        idx = ids.index(animal.id)
        st.session_state.animales[idx] = animal
    else:
        st.session_state.animales.append(animal)
    guardar_datos(st.session_state.animales)


def eliminar_animal(aid: int):
    st.session_state.animales = [a for a in get_animales() if a.id != aid]
    guardar_datos(st.session_state.animales)


def next_id() -> int:
    animales = get_animales()
    return max((a.id for a in animales), default=0) + 1


# ═══════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🐄 HatoGest Pro")
    st.markdown("*Sistema de Gestión Lechera*")
    st.divider()

    animales = get_animales()
    todas_alertas = []
    for a in animales:
        for alerta in generar_alertas(a):
            todas_alertas.append((a, alerta))

    alertas_urgentes = [(a, al) for a, al in todas_alertas if al.prioridad in ("urgente", "alta")]

    st.markdown(f"""
    **Hato activo:** {len(animales)} animales
    **Producción total:** {sum(a.produccion_litros for a in animales):.0f} L/día
    **Alertas activas:** {len(todas_alertas)}
    """)
    st.divider()

    vista = st.radio(
        "Navegación",
        ["📊 Dashboard", "🐄 Hato", "🔔 Alertas", "🔍 Detalle Animal", "⚙️ Parámetros"],
        index=["📊 Dashboard", "🐄 Hato", "🔔 Alertas", "🔍 Detalle Animal", "⚙️ Parámetros"].index(
            st.session_state.get("nav_radio", "📊 Dashboard")
        ),
        key="nav_radio",
    )

    st.divider()
    st.caption(f"📅 {date.today().strftime('%d %b %Y')}")


# ═══════════════════════════════════════════════════════════════════
# FUNCIONES DE RENDERIZADO
# ═══════════════════════════════════════════════════════════════════

def render_alerta_html(animal: Animal, alerta: Alerta) -> str:
    color = PRIORIDAD_COLORES[alerta.prioridad]
    emoji = TIPO_ALERTA_EMOJIS.get(alerta.tipo, "📌")
    prioridad_label = alerta.prioridad.upper()
    dias_label = fmt_dias_restantes(alerta.dias_restantes)
    return f"""
    <div style="background:{color}18; border-left:4px solid {color}; border-radius:0 10px 10px 0;
                padding:12px 16px; margin-bottom:8px; display:flex; align-items:center; gap:12px;">
      <span style="font-size:22px">{emoji}</span>
      <div>
        <div style="font-size:12px; font-weight:700; color:{color}">{prioridad_label} · {animal.nombre} ({animal.arete})</div>
        <div style="font-size:13px; color:#e2e8f0; margin-top:2px">{alerta.mensaje}</div>
        <div style="font-size:11px; color:#94a3b8; margin-top:2px">📆 {fmt_fecha(alerta.fecha)} · {dias_label}</div>
      </div>
    </div>
    """


def render_estado_badge(estado: str) -> str:
    color = ESTADO_COLORES.get(estado, "#94a3b8")
    emoji = ESTADO_EMOJIS.get(estado, "")
    return f'<span style="background:{color}25; color:{color}; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:600">{emoji} {estado.capitalize()}</span>'


# ═══════════════════════════════════════════════════════════════════
# VISTA: DASHBOARD
# ═══════════════════════════════════════════════════════════════════
def vista_dashboard():
    st.title("📊 Dashboard General")
    animales = get_animales()

    # ── Estadísticas principales ────────────────────────────────
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("🐄 Total Animales", len(animales))
    with col2:
        gestantes = sum(1 for a in animales if a.estado_reproductivo == "gestante")
        st.metric("🤰 Gestantes", gestantes)
    with col3:
        inseminadas = sum(1 for a in animales if a.estado_reproductivo == "inseminada")
        st.metric("💉 Inseminadas", inseminadas)
    with col4:
        vacias = sum(1 for a in animales if a.estado_reproductivo == "vacía")
        st.metric("⭕ Vacías", vacias)
    with col5:
        st.metric("🔔 Alertas Activas", len(todas_alertas))
    with col6:
        prod = sum(a.produccion_litros for a in animales)
        st.metric("🥛 Producción (L)", f"{prod:.0f}")

    st.divider()

    # ── Alertas prioritarias y gráfico ─────────────────────────
    col_izq, col_der = st.columns([3, 2])

    with col_izq:
        st.markdown("### 🚨 Alertas Prioritarias del Día")
        if not alertas_urgentes:
            st.success("✅ Sin alertas urgentes hoy. ¡El hato está al día!")
        else:
            for animal, alerta in alertas_urgentes[:8]:
                st.markdown(render_alerta_html(animal, alerta), unsafe_allow_html=True)

    with col_der:
        st.markdown("### 📊 Estado Reproductivo")

        conteos = {e: sum(1 for a in animales if a.estado_reproductivo == e) for e in ESTADOS}
        fig = go.Figure(go.Pie(
            labels=[f"{ESTADO_EMOJIS[e]} {e.capitalize()}" for e in ESTADOS],
            values=list(conteos.values()),
            marker=dict(colors=[ESTADO_COLORES[e] for e in ESTADOS],
                        line=dict(color="#0f2027", width=2)),
            textfont=dict(color="white", size=13),
            hole=0.45,
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e2e8f0"),
            legend=dict(font=dict(color="#e2e8f0")),
            margin=dict(t=10, b=10, l=10, r=10),
            height=280,
            showlegend=True,
        )
        st.plotly_chart(fig, width="stretch")

        # Barras de progreso
        for estado in ESTADOS:
            count = conteos[estado]
            pct = count / len(animales) if animales else 0
            color = ESTADO_COLORES[estado]
            emoji = ESTADO_EMOJIS[estado]
            st.markdown(f"""
            <div style="margin-bottom:10px">
              <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                <span style="font-size:13px">{emoji} {estado.capitalize()}</span>
                <span style="font-size:13px; font-weight:700; color:{color}">{count} ({pct:.0%})</span>
              </div>
              <div style="background:rgba(255,255,255,0.08); border-radius:4px; height:6px">
                <div style="background:{color}; width:{pct*100:.1f}%; height:6px; border-radius:4px"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # ── Indicadores del hato ────────────────────────────────────
    st.markdown("### ⚙️ Indicadores Clave del Hato")
    vacias_list = [a for a in animales if a.estado_reproductivo != "gestante"]
    dias_abiertos_prom = (
        sum((date.today() - a.fecha_parto_date()).days for a in vacias_list) / len(vacias_list)
        if vacias_list else 0
    )
    prod_prom = sum(a.produccion_litros for a in animales) / len(animales) if animales else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        color = "#ef4444" if dias_abiertos_prom > PARAMS["dias_abiertos_objetivo"] else "#34d399"
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.09);
                    border-radius:12px; padding:16px">
          <div style="font-size:11px; color:rgba(255,255,255,0.5); text-transform:uppercase; letter-spacing:.06em">Días Abiertos Prom.</div>
          <div style="font-size:28px; font-weight:800; color:{color}; margin:8px 0">{dias_abiertos_prom:.0f} d</div>
          <div style="font-size:11px; color:rgba(255,255,255,0.35)">Objetivo: ≤ {PARAMS["dias_abiertos_objetivo"]} días</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        color2 = "#ef4444" if prod_prom < 28 else "#34d399"
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.09);
                    border-radius:12px; padding:16px">
          <div style="font-size:11px; color:rgba(255,255,255,0.5); text-transform:uppercase; letter-spacing:.06em">Producción Promedio</div>
          <div style="font-size:28px; font-weight:800; color:{color2}; margin:8px 0">{prod_prom:.1f} L</div>
          <div style="font-size:11px; color:rgba(255,255,255,0.35)">Objetivo: ≥ 28 L/vaca/día</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.09);
                    border-radius:12px; padding:16px">
          <div style="font-size:11px; color:rgba(255,255,255,0.5); text-transform:uppercase; letter-spacing:.06em">DVE Configurado</div>
          <div style="font-size:28px; font-weight:800; color:#34d399; margin:8px 0">{PARAMS["dias_voluntario_espera"]} d</div>
          <div style="font-size:11px; color:rgba(255,255,255,0.35)">Días voluntario de espera</div>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.09);
                    border-radius:12px; padding:16px">
          <div style="font-size:11px; color:rgba(255,255,255,0.5); text-transform:uppercase; letter-spacing:.06em">Gestación</div>
          <div style="font-size:28px; font-weight:800; color:#34d399; margin:8px 0">{PARAMS["dias_gestacion"]} d</div>
          <div style="font-size:11px; color:rgba(255,255,255,0.35)">Período estándar Holstein</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Gráfico de producción por animal ───────────────────────
    st.divider()
    st.markdown("### 🥛 Producción por Animal")
    df_prod = pd.DataFrame([{
        "Animal": f"{a.nombre}\n({a.arete})",
        "Producción (L)": a.produccion_litros,
        "Estado": a.estado_reproductivo,
    } for a in animales])
    fig2 = px.bar(
        df_prod, x="Animal", y="Producción (L)", color="Estado",
        color_discrete_map=ESTADO_COLORES,
        template="plotly_dark",
    )
    fig2.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.15)",
        font=dict(color="#e2e8f0"), height=300,
        margin=dict(t=20, b=20),
        legend=dict(font=dict(color="#e2e8f0")),
    )
    fig2.add_hline(y=28, line_dash="dash", line_color="#34d399",
                   annotation_text="Objetivo 28L", annotation_font_color="#34d399")
    st.plotly_chart(fig2, width="stretch")


# ═══════════════════════════════════════════════════════════════════
# VISTA: HATO
# ═══════════════════════════════════════════════════════════════════
def vista_hato():
    st.title("🐄 Gestión del Hato")
    animales = get_animales()

    # Filtros
    col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
    with col_f1:
        busqueda = st.text_input("🔍 Buscar por arete o nombre", placeholder="CO-001-...")
    with col_f2:
        filtro = st.selectbox("Estado reproductivo", ["Todos"] + ESTADOS)
    with col_f3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Registrar Nuevo Animal"):
            st.session_state.modal_nuevo = True
            st.rerun()

    # Filtrar
    filtrados = animales
    if busqueda:
        filtrados = [a for a in filtrados if busqueda.lower() in a.arete.lower() or busqueda.lower() in a.nombre.lower()]
    if filtro != "Todos":
        filtrados = [a for a in filtrados if a.estado_reproductivo == filtro]

    st.divider()

    if not filtrados:
        st.warning("No se encontraron animales con los filtros seleccionados.")
        return

    # Tabla
    filas = []
    for a in filtrados:
        fechas = calcular_fechas_clave(a)
        alertas = generar_alertas(a)
        prox = alertas[0] if alertas else None
        cc_color = "🔴" if a.condicion_corporal < 2.75 else ("🟡" if a.condicion_corporal > 3.5 else "🟢")
        del_color = "🔴" if fechas.dias_en_leche > 305 else "🟢"
        filas.append({
            "Arete": a.arete,
            "Nombre": a.nombre,
            "Raza": a.raza,
            "Lact.": a.lactancia,
            "DEL": f"{del_color} {fechas.dias_en_leche}d",
            "Estado": f"{ESTADO_EMOJIS.get(a.estado_reproductivo,'')} {a.estado_reproductivo.capitalize()}",
            "Prod. (L)": a.produccion_litros,
            "C.C.": f"{cc_color} {a.condicion_corporal}",
            "Próx. Alerta": (f"{TIPO_ALERTA_EMOJIS.get(prox.tipo,'📌')} {prox.mensaje[:40]}..." if prox else "✅ Sin alertas"),
        })

    df = pd.DataFrame(filas)
    st.dataframe(df, width="stretch", hide_index=True)

    st.divider()

    # Cards de acción individual
    st.markdown("### Acciones por Animal")
    cols = st.columns(min(len(filtrados), 3))
    for i, a in enumerate(filtrados):
        with cols[i % 3]:
            estado_color = ESTADO_COLORES.get(a.estado_reproductivo, "#94a3b8")
            st.markdown(f"""
            <div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.09);
                        border-top:3px solid {estado_color}; border-radius:12px; padding:14px; margin-bottom:12px">
              <div style="font-weight:700; font-size:15px">{a.nombre}</div>
              <div style="font-size:12px; color:rgba(255,255,255,0.45); font-family:monospace">{a.arete}</div>
              <div style="margin-top:8px; font-size:12px">{a.raza} · Lact. {a.lactancia}</div>
            </div>
            """, unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("👁 Ver", key=f"ver_{a.id}"):
                    st.session_state.animal_sel_id = a.id
                    st.session_state.nav_radio = "🔍 Detalle Animal"
                    st.rerun()
            with c2:
                if st.button("✏️ Edit", key=f"edit_{a.id}"):
                    st.session_state[f"editar_{a.id}"] = True
                    st.rerun()
            with c3:
                if st.button("🗑 Elim", key=f"del_{a.id}"):
                    eliminar_animal(a.id)
                    st.rerun()

            if st.session_state.get(f"editar_{a.id}"):
                with st.expander(f"✏️ Editar {a.nombre}", expanded=True):
                    render_form_animal(a)


# ═══════════════════════════════════════════════════════════════════
# VISTA: ALERTAS
# ═══════════════════════════════════════════════════════════════════
def vista_alertas():
    st.title("🔔 Centro de Alertas")

    # Resumen por prioridad
    cols = st.columns(4)
    for i, (prioridad, emoji) in enumerate(PRIORIDAD_EMOJIS.items()):
        count = sum(1 for _, al in todas_alertas if al.prioridad == prioridad)
        color = PRIORIDAD_COLORES[prioridad]
        with cols[i]:
            st.markdown(f"""
            <div style="background:{color}18; border-left:4px solid {color}; border-radius:0 10px 10px 0;
                        padding:14px; text-align:center">
              <div style="font-size:24px">{emoji}</div>
              <div style="font-size:30px; font-weight:800; color:{color}">{count}</div>
              <div style="font-size:11px; color:#6b7280; font-weight:600">{prioridad.upper()}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Filtro de prioridad
    filtro_p = st.selectbox("Filtrar por prioridad", ["Todas"] + list(PRIORIDAD_EMOJIS.keys()))

    st.markdown("### 📋 Listado de Alertas")
    if not todas_alertas:
        st.success("✅ ¡Sin alertas activas! El hato está completamente al día.")
        return

    for animal, alerta in todas_alertas:
        if filtro_p != "Todas" and alerta.prioridad != filtro_p:
            continue
        st.markdown(render_alerta_html(animal, alerta), unsafe_allow_html=True)

    # Tabla exportable
    st.divider()
    st.markdown("### 📥 Exportar Alertas")
    df_alertas = pd.DataFrame([{
        "Prioridad": al.prioridad.upper(),
        "Animal": a.nombre,
        "Arete": a.arete,
        "Tipo": al.tipo,
        "Mensaje": al.mensaje,
        "Fecha": fmt_fecha(al.fecha),
        "Días Restantes": al.dias_restantes,
    } for a, al in todas_alertas])
    st.dataframe(df_alertas, width="stretch", hide_index=True)

    csv = df_alertas.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV de Alertas", csv,
                       f"alertas_hato_{date.today().isoformat()}.csv", "text/csv")


# ═══════════════════════════════════════════════════════════════════
# VISTA: DETALLE ANIMAL
# ═══════════════════════════════════════════════════════════════════
def vista_detalle():
    st.title("🔍 Detalle del Animal")
    animales = get_animales()

    if not animales:
        st.warning("No hay animales registrados.")
        return

    opciones = {f"{a.nombre} ({a.arete})": a.id for a in animales}
    sel_key = st.selectbox("Seleccionar animal", list(opciones.keys()),
                           index=list(opciones.values()).index(st.session_state.animal_sel_id)
                           if st.session_state.animal_sel_id in opciones.values() else 0)
    aid = opciones[sel_key]
    st.session_state.animal_sel_id = aid
    a = get_animal(aid)
    if not a:
        return

    fechas = calcular_fechas_clave(a)
    alertas = generar_alertas(a)

    # ── Cabecera ────────────────────────────────────────────────
    estado_color = ESTADO_COLORES.get(a.estado_reproductivo, "#94a3b8")
    st.markdown(f"""
    <div style="background:linear-gradient(135deg, {estado_color}22, rgba(255,255,255,0.03));
                border:1px solid {estado_color}44; border-radius:14px; padding:20px 24px; margin-bottom:20px">
      <div style="display:flex; justify-content:space-between; align-items:center">
        <div>
          <div style="font-size:24px; font-weight:800; color:#f1f5f9">{a.nombre}</div>
          <div style="font-size:13px; color:rgba(255,255,255,0.45); font-family:monospace">{a.arete}</div>
        </div>
        <div style="text-align:right">
          <div style="background:{estado_color}30; color:{estado_color}; padding:6px 16px;
                      border-radius:20px; font-size:14px; font-weight:700">
            {ESTADO_EMOJIS.get(a.estado_reproductivo,'')} {a.estado_reproductivo.capitalize()}
          </div>
          <div style="font-size:12px; color:rgba(255,255,255,0.35); margin-top:4px">
            {a.raza} · Lactancia {a.lactancia}
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🐄 Información General")
        data_gen = {
            "Arete / ID": a.arete,
            "Nombre": a.nombre,
            "Raza": a.raza,
            "Lactancia N°": a.lactancia,
            "Peso": f"{a.peso_kg} kg",
            "Condición Corporal": f"{a.condicion_corporal} / 5.0",
            "Producción": f"{a.produccion_litros} L/día",
            "Toro / Pajilla": a.toro or "—",
        }
        for k, v in data_gen.items():
            col_k, col_v = st.columns([2, 2])
            col_k.markdown(f"<span style='color:rgba(255,255,255,0.5);font-size:13px'>{k}</span>", unsafe_allow_html=True)
            col_v.markdown(f"<span style='color:#f1f5f9;font-weight:600;font-size:13px'>{v}</span>", unsafe_allow_html=True)
            st.divider()

    with col2:
        st.markdown("#### 📅 Fechas Clave")
        fechas_mostrar = [
            ("Último parto", fmt_fecha(a.fecha_parto_date())),
            ("Días en leche", f"{fechas.dias_en_leche} días"),
            ("Días abiertos", f"{fechas.dias_abiertos} días"),
            ("Fin DVE", fmt_fecha(fechas.inicio_vde)),
            ("Ult. Inseminación", fmt_fecha(a.fecha_inseminacion_date())),
            ("Diag. Gestación (28d)", fmt_fecha(fechas.diagnostico_gestacion)),
            ("Confirm. Gestación (60d)", fmt_fecha(fechas.confirmacion_gestacion)),
            ("Parto Estimado", fmt_fecha(fechas.parto_estimado)),
            ("Secado Estimado", fmt_fecha(fechas.secado_estimado)),
            ("Preparto Estimado", fmt_fecha(fechas.preparto_estimado)),
        ]
        for k, v in fechas_mostrar:
            ck, cv = st.columns([2, 2])
            ck.markdown(f"<span style='color:rgba(255,255,255,0.5);font-size:13px'>{k}</span>", unsafe_allow_html=True)
            cv.markdown(f"<span style='color:#34d399;font-weight:600;font-size:13px'>{v}</span>", unsafe_allow_html=True)
            st.divider()

    # ── Timeline de línea de vida ────────────────────────────────
    if fechas.parto_estimado:
        st.markdown("#### 📆 Línea de Vida Reproductiva")
        hitos = [
            ("Parto", a.fecha_parto_date(), "#10b981"),
            ("Fin DVE", fechas.inicio_vde, "#3b82f6"),
        ]
        if fechas.diagnostico_gestacion:
            hitos.append(("DG (28d)", fechas.diagnostico_gestacion, "#f59e0b"))
        if fechas.confirmacion_gestacion:
            hitos.append(("Confirm. (60d)", fechas.confirmacion_gestacion, "#8b5cf6"))
        if fechas.secado_estimado:
            hitos.append(("Secado", fechas.secado_estimado, "#ef4444"))
        if fechas.preparto_estimado:
            hitos.append(("Preparto", fechas.preparto_estimado, "#f97316"))
        if fechas.parto_estimado:
            hitos.append(("Parto Est.", fechas.parto_estimado, "#34d399"))

        fig = go.Figure()
        hoy = date.today()
        for nombre, fecha, color in hitos:
            fig.add_trace(go.Scatter(
                x=[fecha], y=[0],
                mode="markers+text",
                marker=dict(size=14, color=color, line=dict(color="white", width=2)),
                text=[nombre],
                textposition="top center",
                textfont=dict(color=color, size=10),
                name=nombre,
                hovertemplate=f"<b>{nombre}</b><br>{fmt_fecha(fecha)}<extra></extra>",
            ))
        fig.add_vline(x=hoy.isoformat(), line_dash="dash", line_color="#34d399",
                      annotation_text="Hoy", annotation_font_color="#34d399")
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.1)",
            yaxis=dict(visible=False), xaxis=dict(color="#94a3b8"),
            height=180, margin=dict(t=50, b=20, l=10, r=10),
            showlegend=False, font=dict(color="#e2e8f0"),
        )
        st.plotly_chart(fig, width="stretch")

    # ── Alertas del animal ───────────────────────────────────────
    st.markdown("#### 🔔 Alertas y Eventos Programados")
    if not alertas:
        st.success("✅ Sin alertas activas para este animal.")
    else:
        for alerta in alertas:
            st.markdown(render_alerta_html(a, alerta), unsafe_allow_html=True)

    # ── Ventana de celo ──────────────────────────────────────────
    if fechas.ventana_celo:
        st.markdown("#### 🔥 Ventana de Repetición de Celo")
        hoy = date.today()
        cols_celo = st.columns(len(fechas.ventana_celo))
        insem = a.fecha_inseminacion_date()
        for i, (fecha_celo, col) in enumerate(zip(fechas.ventana_celo, cols_celo)):
            d = (fecha_celo - hoy).days
            dia_num = (fecha_celo - insem).days if insem else "?"
            es_hoy = d == 0
            es_cercano = 0 < d <= 2
            bg = "#ef4444" if es_hoy else ("#f97316" if es_cercano else "rgba(255,255,255,0.06)")
            txt = "#fff" if (es_hoy or es_cercano) else "#e2e8f0"
            label = "¡HOY!" if es_hoy else (f"En {d}d" if d >= 0 else f"Hace {abs(d)}d")
            with col:
                st.markdown(f"""
                <div style="background:{bg}; border-radius:10px; padding:10px; text-align:center">
                  <div style="font-size:11px; font-weight:700; color:{txt}">Día {dia_num}</div>
                  <div style="font-size:13px; color:{txt}; font-weight:600">{fmt_fecha(fecha_celo)}</div>
                  <div style="font-size:10px; color:{txt}; margin-top:2px">{label}</div>
                </div>
                """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
# VISTA: PARÁMETROS
# ═══════════════════════════════════════════════════════════════════
def vista_parametros():
    st.title("⚙️ Parámetros Reproductivos")
    st.info("Los parámetros se configuran directamente en el código (constante `PARAMS`). "
            "En una versión de producción se guardarían en base de datos.")

    grupos = [
        ("📋 Parámetros de Manejo", [
            ("Días Voluntario de Espera (DVE)", PARAMS["dias_voluntario_espera"], "días", "Días post-parto antes de iniciar IA"),
            ("Días de Gestación", PARAMS["dias_gestacion"], "días", "Duración media Holstein/Pardo Suizo"),
            ("Período Seco", PARAMS["dias_secar"], "días", "Días de descanso productivo"),
            ("Período Preparto", PARAMS["periodo_prenatal"], "días", "Días de manga de transición"),
        ]),
        ("🎯 Objetivos de Eficiencia", [
            ("Días Abiertos Objetivo", PARAMS["dias_abiertos_objetivo"], "días", "Días entre parto y preñez"),
            ("Intervalo Entre Partos", PARAMS["intervalo_parto_meses"], "meses", "Meta de alta eficiencia"),
            ("Servicios por Concepción", PARAMS["servicios_por_concepcion"], "IA", "Índice SPC objetivo"),
            ("Tasa de Concepción", f"{PARAMS['tasa_concepcion_objetivo']*100:.0f}", "%", "Objetivo de preñez por IA"),
        ]),
        ("🔥 Detección de Celo", [
            ("Ciclo Estral", PARAMS["dias_deteccion_calor"], "días", "Duración media del ciclo"),
            ("Inicio Ventana de Celo", min(PARAMS["alerta_calor_dias"]), "días post-IA", "Inicio de vigilancia de retorno"),
            ("Fin Ventana de Celo", max(PARAMS["alerta_calor_dias"]), "días post-IA", "Fin de vigilancia de retorno"),
        ]),
    ]

    for titulo, items in grupos:
        st.markdown(f"### {titulo}")
        cols = st.columns(len(items))
        for col, (label, valor, unidad, desc) in zip(cols, items):
            with col:
                st.markdown(f"""
                <div style="background:rgba(52,211,153,0.08); border:1px solid rgba(52,211,153,0.2);
                            border-radius:12px; padding:16px; height:120px">
                  <div style="font-size:11px; color:rgba(255,255,255,0.45); text-transform:uppercase;
                              letter-spacing:.06em; margin-bottom:8px">{label}</div>
                  <div style="font-size:26px; font-weight:800; color:#34d399">{valor} <span style="font-size:14px">{unidad}</span></div>
                  <div style="font-size:11px; color:rgba(255,255,255,0.35); margin-top:6px">{desc}</div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown("")


# ═══════════════════════════════════════════════════════════════════
# FORMULARIO NUEVO / EDITAR ANIMAL
# ═══════════════════════════════════════════════════════════════════
def render_form_animal(animal: Optional[Animal] = None):
    es_nuevo = animal is None
    prefix = f"form_{animal.id if animal else 'nuevo'}"

    with st.form(key=prefix, clear_on_submit=True):
        st.markdown(f"{'➕ Nuevo Animal' if es_nuevo else f'✏️ Editar: {animal.nombre}'}")
        c1, c2 = st.columns(2)
        with c1:
            arete = st.text_input("Arete / ID", value=animal.arete if animal else "")
            nombre = st.text_input("Nombre", value=animal.nombre if animal else "")
            raza = st.selectbox("Raza", RAZAS,
                                index=RAZAS.index(animal.raza) if animal and animal.raza in RAZAS else 0)
            lactancia = st.number_input("N° de Lactancia", min_value=1, max_value=20,
                                        value=animal.lactancia if animal else 1)
            peso_kg = st.number_input("Peso (kg)", min_value=100.0, max_value=1200.0,
                                      value=float(animal.peso_kg) if animal else 500.0)
        with c2:
            fecha_parto = st.date_input("Fecha de Último Parto",
                                        value=animal.fecha_parto_date() if animal else date.today())
            estado = st.selectbox("Estado Reproductivo", ESTADOS,
                                  index=ESTADOS.index(animal.estado_reproductivo) if animal else 0)
            fecha_ia = st.date_input("Fecha Última IA (opcional)",
                                     value=animal.fecha_inseminacion_date() if animal and animal.fecha_ultima_inseminacion else None)
            produccion = st.number_input("Producción (L/día)", min_value=0.0, max_value=100.0,
                                         value=float(animal.produccion_litros) if animal else 20.0)
            cc = st.number_input("Condición Corporal (1–5)", min_value=1.0, max_value=5.0,
                                  step=0.25, value=float(animal.condicion_corporal) if animal else 3.0)
            toro = st.text_input("Toro / Pajilla", value=animal.toro or "" if animal else "")

        submitted = st.form_submit_button("💾 Guardar" if not es_nuevo else "➕ Registrar")
        if submitted:
            if not arete or not nombre:
                st.error("Arete y nombre son obligatorios.")
            else:
                nuevo = Animal(
                    id=animal.id if animal else next_id(),
                    arete=arete, nombre=nombre, raza=raza,
                    lactancia=int(lactancia), peso_kg=float(peso_kg),
                    fecha_parto=fecha_parto.isoformat(),
                    estado_reproductivo=estado,
                    produccion_litros=float(produccion),
                    condicion_corporal=float(cc),
                    fecha_ultima_inseminacion=fecha_ia.isoformat() if fecha_ia else None,
                    toro=toro or None,
                )
                guardar_animal(nuevo)
                if animal:
                    st.session_state[f"editar_{animal.id}"] = False
                st.success(f"✅ Animal {'actualizado' if animal else 'registrado'}: {nombre}")
                st.rerun()


# ═══════════════════════════════════════════════════════════════════
# MODAL NUEVO ANIMAL (en vista Hato)
# ═══════════════════════════════════════════════════════════════════
if st.session_state.get("modal_nuevo"):
    with st.expander("➕ Registrar Nuevo Animal", expanded=True):
        render_form_animal(None)
    if st.button("❌ Cancelar registro"):
        st.session_state.modal_nuevo = False
        st.rerun()


# ═══════════════════════════════════════════════════════════════════
# ROUTER DE VISTAS
# ═══════════════════════════════════════════════════════════════════
if vista == "📊 Dashboard":
    vista_dashboard()
elif vista == "🐄 Hato":
    vista_hato()
elif vista == "🔔 Alertas":
    vista_alertas()
elif vista == "🔍 Detalle Animal":
    vista_detalle()
elif vista == "⚙️ Parámetros":
    vista_parametros()

