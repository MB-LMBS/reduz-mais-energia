# agent/tools.py — Herramientas del agente
# Generado por AgentKit

"""
Herramientas específicas del negocio de Reduz+ Energia.
Estas funciones extienden las capacidades del agente más allá de responder texto.
"""

import os
import csv
import uuid
import yaml
import logging
from datetime import datetime

logger = logging.getLogger("agentkit")

DATA_DIR = "data"


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención del negocio."""
    info = cargar_info_negocio()
    return {
        "horario": info.get("negocio", {}).get("horario", "No disponible"),
        "esta_abierto": True,  # TODO: calcular según hora actual y horario
    }


def obtener_link_simulador() -> str:
    """Retorna el link del simulador de campañas de Reduz+ Energia."""
    info = cargar_info_negocio()
    return info.get("negocio", {}).get("simulador_url", "")


def buscar_en_knowledge(consulta: str) -> str:
    """
    Busca información relevante en los archivos de /knowledge.
    Retorna el contenido más relevante encontrado.
    """
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


def _escribir_fila_csv(nombre_archivo: str, cabeceras: list[str], fila: dict):
    """Agrega una fila a un CSV en /data, creando el archivo y las cabeceras si hace falta."""
    os.makedirs(DATA_DIR, exist_ok=True)
    ruta = os.path.join(DATA_DIR, nombre_archivo)
    existe = os.path.isfile(ruta)
    with open(ruta, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cabeceras)
        if not existe:
            writer.writeheader()
        writer.writerow(fila)


# ════════════════════════════════════════════════════════════
# Calificación y registro de leads (electricidad, gas, solar)
# ════════════════════════════════════════════════════════════

def registrar_lead(telefono: str, tipo_cliente: str, interesse: str, nivel_tensao: str = "") -> str:
    """
    Registra un lead nuevo en data/leads.csv.

    Args:
        telefono: Número de contacto del cliente
        tipo_cliente: "empresa" o "particular"
        interesse: servicio de interés (electricidade, gas, solar, comunidade solar)
        nivel_tensao: BTN, BTE o MT (si aplica, sobre todo para instalaciones solares)
    """
    _escribir_fila_csv(
        "leads.csv",
        ["timestamp", "telefono", "tipo_cliente", "interesse", "nivel_tensao"],
        {
            "timestamp": datetime.utcnow().isoformat(),
            "telefono": telefono,
            "tipo_cliente": tipo_cliente,
            "interesse": interesse,
            "nivel_tensao": nivel_tensao,
        },
    )
    logger.info(f"Lead registrado: {telefono} — {interesse} ({tipo_cliente})")
    return "Lead registrado correctamente."


# ════════════════════════════════════════════════════════════
# Agendamiento de llamadas / reuniones de consultoría
# ════════════════════════════════════════════════════════════

def agendar_chamada(telefono: str, nome: str, data_preferida: str, hora_preferida: str) -> str:
    """Registra una solicitud de llamada de consultoría en data/citas.csv."""
    _escribir_fila_csv(
        "citas.csv",
        ["timestamp", "telefono", "nome", "data_preferida", "hora_preferida"],
        {
            "timestamp": datetime.utcnow().isoformat(),
            "telefono": telefono,
            "nome": nome,
            "data_preferida": data_preferida,
            "hora_preferida": hora_preferida,
        },
    )
    logger.info(f"Chamada agendada: {telefono} — {data_preferida} {hora_preferida}")
    return "Solicitud de llamada registrada. Un consultor confirmará el horario."


# ════════════════════════════════════════════════════════════
# Pedidos de simulación / propuesta
# ════════════════════════════════════════════════════════════

def registrar_pedido_simulacao(telefono: str, tipo_servico: str) -> str:
    """Registra un pedido de simulación o propuesta en data/pedidos.csv."""
    _escribir_fila_csv(
        "pedidos.csv",
        ["timestamp", "telefono", "tipo_servico"],
        {
            "timestamp": datetime.utcnow().isoformat(),
            "telefono": telefono,
            "tipo_servico": tipo_servico,
        },
    )
    logger.info(f"Pedido de simulação registrado: {telefono} — {tipo_servico}")
    return f"Pedido registrado. Puedes acceder al simulador aquí: {obtener_link_simulador()}"


# ════════════════════════════════════════════════════════════
# Soporte post-venta
# ════════════════════════════════════════════════════════════

def crear_ticket_suporte(telefono: str, problema: str) -> str:
    """Crea un ticket de soporte post-venta en data/tickets.csv y retorna su ID."""
    ticket_id = str(uuid.uuid4())[:8]
    _escribir_fila_csv(
        "tickets.csv",
        ["timestamp", "ticket_id", "telefono", "problema", "estado"],
        {
            "timestamp": datetime.utcnow().isoformat(),
            "ticket_id": ticket_id,
            "telefono": telefono,
            "problema": problema,
            "estado": "abierto",
        },
    )
    logger.info(f"Ticket de soporte creado: {ticket_id} — {telefono}")
    return ticket_id
