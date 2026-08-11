# agent/memory.py — Memoria de conversaciones con SQLite
# Generado por AgentKit

"""
Sistema de memoria del agente. Guarda el historial de conversaciones
por número de teléfono usando SQLite (local) o PostgreSQL (producción).
"""

import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer, func
from dotenv import load_dotenv

load_dotenv()

# Configuración de base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

# Si es PostgreSQL en producción, ajustar el esquema de URL
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Mensaje(Base):
    """Modelo de mensaje en la base de datos."""
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user", "assistant" o "humano"
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Conversacion(Base):
    """Estado de cada conversación: si responde el bot o un humano."""
    __tablename__ = "conversaciones"

    telefono: Mapped[str] = mapped_column(String(50), primary_key=True)
    modo: Mapped[str] = mapped_column(String(10), default="bot")  # "bot" o "manual"


async def inicializar_db():
    """Crea las tablas si no existen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def guardar_mensaje(telefono: str, role: str, content: str):
    """Guarda un mensaje en el historial de conversación."""
    async with async_session() as session:
        mensaje = Mensaje(
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow()
        )
        session.add(mensaje)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    """
    Recupera los últimos N mensajes de una conversación.

    Args:
        telefono: Número de teléfono del cliente
        limite: Máximo de mensajes a recuperar (default: 20)

    Returns:
        Lista de diccionarios con role y content
    """
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()

        # Invertir para orden cronológico (los más recientes están primero)
        mensajes.reverse()

        return [
            {"role": msg.role, "content": msg.content}
            for msg in mensajes
        ]


async def obtener_modo(telefono: str) -> str:
    """Retorna el modo actual de la conversación: 'bot' (default) o 'manual'."""
    async with async_session() as session:
        query = select(Conversacion).where(Conversacion.telefono == telefono)
        result = await session.execute(query)
        conversacion = result.scalar_one_or_none()
        return conversacion.modo if conversacion else "bot"


async def establecer_modo(telefono: str, modo: str):
    """Cambia el modo de una conversación a 'bot' o 'manual'."""
    async with async_session() as session:
        query = select(Conversacion).where(Conversacion.telefono == telefono)
        result = await session.execute(query)
        conversacion = result.scalar_one_or_none()
        if conversacion:
            conversacion.modo = modo
        else:
            session.add(Conversacion(telefono=telefono, modo=modo))
        await session.commit()


async def listar_conversaciones() -> list[dict]:
    """
    Lista todas las conversaciones con su último mensaje y modo actual,
    ordenadas por actividad más reciente primero.
    """
    async with async_session() as session:
        subquery = (
            select(
                Mensaje.telefono,
                func.max(Mensaje.timestamp).label("ultimo_timestamp"),
            )
            .group_by(Mensaje.telefono)
            .subquery()
        )
        query = select(Mensaje, subquery.c.ultimo_timestamp).join(
            subquery,
            (Mensaje.telefono == subquery.c.telefono)
            & (Mensaje.timestamp == subquery.c.ultimo_timestamp),
        ).order_by(subquery.c.ultimo_timestamp.desc())
        result = await session.execute(query)
        filas = result.all()

        conversaciones = []
        for msg, _ in filas:
            modo = await obtener_modo(msg.telefono)
            conversaciones.append({
                "telefono": msg.telefono,
                "ultimo_mensaje": msg.content,
                "ultimo_role": msg.role,
                "timestamp": msg.timestamp,
                "modo": modo,
            })
        return conversaciones


async def limpiar_historial(telefono: str):
    """Borra todo el historial de una conversación."""
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono)
        result = await session.execute(query)
        mensajes = result.scalars().all()
        for msg in mensajes:
            session.delete(msg)
        await session.commit()
