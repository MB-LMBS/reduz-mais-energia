# agent/memory.py — Memoria de conversaciones con SQLite
# Generado por AgentKit

"""
Sistema de memoria del agente. Guarda el historial de conversaciones
por número de teléfono usando SQLite (local) o PostgreSQL (producción).
"""

import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer, func, inspect, text
from dotenv import load_dotenv

logger = logging.getLogger("agentkit")

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
    tipo: Mapped[str] = mapped_column(String(20), default="texto")  # texto, imagem, documento, audio, video
    media_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nome_ficheiro: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Conversacion(Base):
    """Estado de cada conversación: si responde el bot o un humano, y si sigue abierta."""
    __tablename__ = "conversaciones"

    telefono: Mapped[str] = mapped_column(String(50), primary_key=True)
    modo: Mapped[str] = mapped_column(String(10), default="bot")      # "bot" o "manual"
    estado: Mapped[str] = mapped_column(String(10), default="aberta")  # "aberta" o "tratada"
    nome_contato: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Categoría comercial: "sem_categoria", "interessado", "ganho" o "perdido"
    categoria: Mapped[str] = mapped_column(String(20), default="sem_categoria")


class Agendamento(Base):
    """Uma chamada agendada com um cliente."""
    __tablename__ = "agendamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    nome_cliente: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Guardado como hora local de Portugal (naive), não UTC — simplifica a grelha de slots
    data_hora: Mapped[datetime] = mapped_column(DateTime, index=True)
    informacao: Mapped[str] = mapped_column(Text)  # o que o cliente quer discutir
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    estado: Mapped[str] = mapped_column(String(20), default="agendado")  # agendado, realizado, cancelado


def _columnas_existentes(conn, tabla: str) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns(tabla)}


async def inicializar_db():
    """
    Crea las tablas si no existen y añade columnas nuevas a tablas ya
    existentes (SQLAlchemy no hace esto automáticamente — sin esto, un
    despliegue con una base de datos persistente antigua y un modelo
    nuevo rompería el webhook con "no such column").
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        for tabla in Base.metadata.tables.values():
            existentes = await conn.run_sync(_columnas_existentes, tabla.name)
            for columna in tabla.columns:
                if columna.name not in existentes:
                    tipo = columna.type.compile(engine.dialect)
                    logger.info(f"Migrando: adicionando coluna {tabla.name}.{columna.name} ({tipo})")
                    await conn.execute(text(f"ALTER TABLE {tabla.name} ADD COLUMN {columna.name} {tipo}"))


async def guardar_mensaje(
    telefono: str, role: str, content: str, tipo: str = "texto",
    media_path: str | None = None, nome_ficheiro: str | None = None
):
    """Guarda un mensaje en el historial de conversación."""
    async with async_session() as session:
        mensaje = Mensaje(
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow(),
            tipo=tipo,
            media_path=media_path,
            nome_ficheiro=nome_ficheiro,
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
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "tipo": msg.tipo,
                "media_path": msg.media_path,
                "nome_ficheiro": msg.nome_ficheiro,
                "timestamp": msg.timestamp,
            }
            for msg in mensajes
        ]


async def obtener_mensagens_novas(telefono: str, desde_id: int) -> list[dict]:
    """
    Retorna as mensagens de uma conversa com id maior que desde_id — usado
    pelo painel para atualizar a conversa automaticamente sem refresh.
    """
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono, Mensaje.id > desde_id)
            .order_by(Mensaje.timestamp.asc())
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()
        return [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "tipo": msg.tipo,
                "media_path": msg.media_path,
                "nome_ficheiro": msg.nome_ficheiro,
                "timestamp": msg.timestamp,
            }
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


async def obtener_estado(telefono: str) -> str:
    """Retorna el estado actual de la conversación: 'aberta' (default) o 'tratada'."""
    async with async_session() as session:
        query = select(Conversacion).where(Conversacion.telefono == telefono)
        result = await session.execute(query)
        conversacion = result.scalar_one_or_none()
        return conversacion.estado if conversacion else "aberta"


async def establecer_estado(telefono: str, estado: str):
    """Cambia el estado de una conversación a 'aberta' o 'tratada'."""
    async with async_session() as session:
        query = select(Conversacion).where(Conversacion.telefono == telefono)
        result = await session.execute(query)
        conversacion = result.scalar_one_or_none()
        if conversacion:
            conversacion.estado = estado
        else:
            session.add(Conversacion(telefono=telefono, estado=estado))
        await session.commit()


async def obtener_nome_contato(telefono: str) -> str | None:
    """Retorna el nombre de perfil de WhatsApp del contacto, si ya lo conocemos."""
    async with async_session() as session:
        query = select(Conversacion).where(Conversacion.telefono == telefono)
        result = await session.execute(query)
        conversacion = result.scalar_one_or_none()
        return conversacion.nome_contato if conversacion else None


async def establecer_nome_contato(telefono: str, nome: str):
    """Guarda o actualiza el nombre de perfil de WhatsApp del contacto."""
    if not nome:
        return
    async with async_session() as session:
        query = select(Conversacion).where(Conversacion.telefono == telefono)
        result = await session.execute(query)
        conversacion = result.scalar_one_or_none()
        if conversacion:
            conversacion.nome_contato = nome
        else:
            session.add(Conversacion(telefono=telefono, nome_contato=nome))
        await session.commit()


CATEGORIAS_VALIDAS = ("sem_categoria", "interessado", "ganho", "perdido")


async def obtener_categoria(telefono: str) -> str:
    """Retorna la categoría comercial actual: 'sem_categoria' (default), 'interessado', 'ganho' o 'perdido'."""
    async with async_session() as session:
        query = select(Conversacion).where(Conversacion.telefono == telefono)
        result = await session.execute(query)
        conversacion = result.scalar_one_or_none()
        return conversacion.categoria if conversacion else "sem_categoria"


async def establecer_categoria(telefono: str, categoria: str):
    """Cambia la categoría comercial de una conversación."""
    async with async_session() as session:
        query = select(Conversacion).where(Conversacion.telefono == telefono)
        result = await session.execute(query)
        conversacion = result.scalar_one_or_none()
        if conversacion:
            conversacion.categoria = categoria
        else:
            session.add(Conversacion(telefono=telefono, categoria=categoria))
        await session.commit()


async def listar_conversaciones() -> list[dict]:
    """
    Lista todas las conversaciones con su último mensaje, modo y estado,
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
            estado = await obtener_estado(msg.telefono)
            nome_contato = await obtener_nome_contato(msg.telefono)
            categoria = await obtener_categoria(msg.telefono)
            conversaciones.append({
                "telefono": msg.telefono,
                "ultimo_mensaje": msg.content,
                "ultimo_role": msg.role,
                "ultimo_tipo": msg.tipo,
                "timestamp": msg.timestamp,
                "modo": modo,
                "estado": estado,
                "nome_contato": nome_contato,
                "categoria": categoria,
            })
        return conversaciones


async def obtener_horarios_ocupados(inicio: datetime, fim: datetime) -> set[datetime]:
    """Retorna os horários (hora local) já ocupados por agendamentos ativos num intervalo."""
    async with async_session() as session:
        query = select(Agendamento.data_hora).where(
            Agendamento.data_hora >= inicio,
            Agendamento.data_hora < fim,
            Agendamento.estado == "agendado",
        )
        result = await session.execute(query)
        return set(result.scalars().all())


async def criar_agendamento(
    telefono: str, nome_cliente: str | None, data_hora: datetime, informacao: str
) -> bool:
    """
    Cria um agendamento se o horário ainda estiver livre.
    Retorna False se alguém já tiver ocupado esse horário entretanto.
    """
    async with async_session() as session:
        query = select(Agendamento).where(
            Agendamento.data_hora == data_hora,
            Agendamento.estado == "agendado",
        )
        result = await session.execute(query)
        if result.scalar_one_or_none():
            return False
        session.add(Agendamento(
            telefono=telefono, nome_cliente=nome_cliente,
            data_hora=data_hora, informacao=informacao,
        ))
        await session.commit()
        return True


async def listar_agendamentos(apenas_futuros: bool = True) -> list[dict]:
    """Lista os agendamentos ativos, mais próximos primeiro."""
    async with async_session() as session:
        query = select(Agendamento).where(Agendamento.estado == "agendado")
        if apenas_futuros:
            agora_lisboa = datetime.now(ZoneInfo("Europe/Lisbon")).replace(tzinfo=None)
            query = query.where(Agendamento.data_hora >= agora_lisboa)
        query = query.order_by(Agendamento.data_hora.asc())
        result = await session.execute(query)
        return [
            {
                "id": a.id,
                "telefono": a.telefono,
                "nome_cliente": a.nome_cliente,
                "data_hora": a.data_hora,
                "informacao": a.informacao,
            }
            for a in result.scalars().all()
        ]


async def limpiar_historial(telefono: str):
    """Borra todo el historial de una conversación."""
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono)
        result = await session.execute(query)
        mensajes = result.scalars().all()
        for msg in mensajes:
            await session.delete(msg)
        await session.commit()


async def editar_mensagem(mensagem_id: int, novo_texto: str) -> bool:
    """
    Corrige o texto de uma mensagem enviada manualmente pelo painel (role
    'humano'). Só edita o registo local — não altera nem reenvia nada no
    WhatsApp do cliente, que já recebeu a mensagem original.
    """
    async with async_session() as session:
        msg = await session.get(Mensaje, mensagem_id)
        if not msg or msg.role != "humano":
            return False
        msg.content = novo_texto
        await session.commit()
        return True


async def apagar_mensagem(mensagem_id: int) -> bool:
    """
    Remove do registo local uma mensagem enviada manualmente pelo painel
    (role 'humano'). Só apaga o registo local — não a remove do WhatsApp
    do cliente, que já a recebeu.
    """
    async with async_session() as session:
        msg = await session.get(Mensaje, mensagem_id)
        if not msg or msg.role != "humano":
            return False
        await session.delete(msg)
        await session.commit()
        return True
