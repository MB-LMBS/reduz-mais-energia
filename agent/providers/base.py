# agent/providers/base.py — Clase base para proveedores de WhatsApp
# Generado por AgentKit

"""
Define la interfaz común que todos los proveedores de WhatsApp deben implementar.
Esto permite cambiar de proveedor sin modificar el resto del código.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from fastapi import Request


@dataclass
class MensajeEntrante:
    """Mensaje normalizado — mismo formato sin importar el proveedor."""
    telefono: str                  # Número del remitente
    texto: str                     # Contenido del mensaje (o legenda, si es un archivo)
    mensaje_id: str                # ID único del mensaje
    es_propio: bool                # True si lo envió el agente (se ignora)
    tipo: str = "texto"            # "texto", "imagem", "documento", "audio" o "video"
    media_id: str | None = None    # ID del archivo en el proveedor (para descargarlo)
    mime_type: str | None = None
    nome_ficheiro: str | None = None
    nome_contato: str | None = None  # Nombre de perfil de WhatsApp del remitente, si el proveedor lo informa


class ProveedorWhatsApp(ABC):
    """Interfaz que cada proveedor de WhatsApp debe implementar."""

    @abstractmethod
    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Extrae y normaliza mensajes del payload del webhook."""
        ...

    @abstractmethod
    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía un mensaje de texto. Retorna True si fue exitoso."""
        ...

    async def enviar_botoes(self, telefono: str, texto: str, opcoes: list[str]) -> bool:
        """
        Envía una pregunta con 2-3 botones de respuesta rápida. Los proveedores
        que no soporten botones nativos deben sobreescribir este método; por
        defecto cae a texto plano con las opciones numeradas.
        """
        linhas = [texto, ""]
        linhas += [f"{i + 1}. {opcao}" for i, opcao in enumerate(opcoes)]
        return await self.enviar_mensaje(telefono, "\n".join(linhas))

    async def enviar_botao_link(self, telefono: str, texto: str, texto_botao: str, url: str) -> bool:
        """
        Envía un mensaje con un botón que abre un link (ex: simulador). Por
        defecto (si el proveedor no soporta botões de link) cae a texto plano
        con el link al final.
        """
        return await self.enviar_mensaje(telefono, f"{texto}\n\n👉 {url}")

    async def enviar_imagem_url(self, telefono: str, url: str, legenda: str = "") -> bool:
        """
        Envía uma imagem a partir de um URL público, com legenda (ex: logótipo
        com a mensagem de boas-vindas). Por defeito (se o proveedor não
        suportar), cai para texto simples.
        """
        return await self.enviar_mensaje(telefono, legenda)

    async def baixar_media(self, media_id: str) -> tuple[bytes, str] | None:
        """Descarga un archivo recibido. Retorna (contenido, mime_type) o None si falla."""
        return None

    async def enviar_documento(
        self, telefono: str, ficheiro: bytes, nome_ficheiro: str,
        mime_type: str, legenda: str = ""
    ) -> bool:
        """Envía un archivo (imagen, PDF, etc). Retorna True si fue exitoso."""
        return False

    async def validar_webhook(self, request: Request) -> dict | int | None:
        """Verificación GET del webhook (solo Meta la requiere). Retorna respuesta o None."""
        return None

    async def enviar_template(self, telefono: str, nome_template: str, parametros: list[str]) -> bool:
        """
        Envía uma mensagem a partir de um template pré-aprovado — necessário
        para o negócio iniciar uma conversa fora da janela de 24h desde a
        última mensagem do destinatário. Os proveedores que não suportem
        templates devem sobrescrever ou aceitar a falha (retorna False).
        """
        return False
