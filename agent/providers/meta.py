# agent/providers/meta.py — Adaptador para Meta WhatsApp Cloud API
# Generado por AgentKit

import os
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")

# Meta usa "image"/"document"/"audio"/"video" en el webhook — normalizamos a portugués
TIPOS_MEDIA = {
    "image": "imagem",
    "document": "documento",
    "audio": "audio",
    "video": "video",
    "sticker": "imagem",
}


class ProveedorMeta(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando la API oficial de Meta (Cloud API)."""

    def __init__(self):
        self.access_token = os.getenv("META_ACCESS_TOKEN")
        self.phone_number_id = os.getenv("META_PHONE_NUMBER_ID")
        self.verify_token = os.getenv("META_VERIFY_TOKEN", "agentkit-verify")
        self.api_version = "v21.0"

    async def validar_webhook(self, request: Request) -> dict | int | None:
        """Meta requiere verificación GET con hub.verify_token."""
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        if mode == "subscribe" and token == self.verify_token:
            # Meta espera el challenge como respuesta en texto plano
            return int(challenge)
        return None

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload anidado de Meta Cloud API."""
        body = await request.json()
        mensajes = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Meta envía el nombre de perfil de WhatsApp junto a los mensajes,
                # en un array "contacts" separado — lo mapeamos por número
                nomes_contato = {
                    c.get("wa_id"): c.get("profile", {}).get("name")
                    for c in value.get("contacts", [])
                }

                for msg in value.get("messages", []):
                    tipo_meta = msg.get("type")
                    nome_contato = nomes_contato.get(msg.get("from"))

                    if tipo_meta == "text":
                        mensajes.append(MensajeEntrante(
                            telefono=msg.get("from", ""),
                            texto=msg.get("text", {}).get("body", ""),
                            mensaje_id=msg.get("id", ""),
                            es_propio=False,
                            nome_contato=nome_contato,
                        ))
                    elif tipo_meta == "interactive":
                        # Resposta a uma mensagem com botões ou lista — tratamos o
                        # título escolhido como se o cliente o tivesse escrito
                        interactive = msg.get("interactive", {})
                        escolha = interactive.get("button_reply") or interactive.get("list_reply") or {}
                        mensajes.append(MensajeEntrante(
                            telefono=msg.get("from", ""),
                            texto=escolha.get("title", ""),
                            mensaje_id=msg.get("id", ""),
                            es_propio=False,
                            nome_contato=nome_contato,
                        ))
                    elif tipo_meta in TIPOS_MEDIA:
                        dados_media = msg.get(tipo_meta, {})
                        mensajes.append(MensajeEntrante(
                            telefono=msg.get("from", ""),
                            texto=dados_media.get("caption", ""),
                            mensaje_id=msg.get("id", ""),
                            es_propio=False,
                            tipo=TIPOS_MEDIA[tipo_meta],
                            media_id=dados_media.get("id"),
                            mime_type=dados_media.get("mime_type"),
                            nome_ficheiro=dados_media.get("filename"),
                            nome_contato=nome_contato,
                        ))
        return mensajes

    async def baixar_media(self, media_id: str) -> tuple[bytes, str] | None:
        """Descarga un archivo de Meta: primero pide la URL temporal, luego el contenido."""
        if not self.access_token:
            return None
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://graph.facebook.com/{self.api_version}/{media_id}",
                headers=headers,
            )
            if r.status_code != 200:
                logger.error(f"Error obteniendo URL de media {media_id}: {r.status_code} — {r.text}")
                return None
            url = r.json().get("url")
            mime_type = r.json().get("mime_type", "application/octet-stream")

            r2 = await client.get(url, headers=headers)
            if r2.status_code != 200:
                logger.error(f"Error descargando media {media_id}: {r2.status_code}")
                return None
            return r2.content, mime_type

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Meta WhatsApp Cloud API."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": mensaje},
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API: {r.status_code} — {r.text}")
            return r.status_code == 200

    async def enviar_imagem_url(self, telefono: str, url_imagem: str, legenda: str = "") -> bool:
        """Envía uma imagem a partir de um URL público, com legenda (ex: logótipo + boas-vindas)."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "image",
            "image": {"link": url_imagem, "caption": legenda},
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API (imagem): {r.status_code} — {r.text}")
            return r.status_code == 200

    async def enviar_botoes(self, telefono: str, texto: str, opcoes: list[str]) -> bool:
        """Envía una pregunta con até 3 botões de resposta rápida (WhatsApp Interactive Buttons)."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        botoes = [
            {"type": "reply", "reply": {"id": f"opt_{i}", "title": opcao[:20]}}
            for i, opcao in enumerate(opcoes[:3])
        ]
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto},
                "action": {"buttons": botoes},
            },
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API (botões): {r.status_code} — {r.text}")
            return r.status_code == 200

    async def enviar_botao_link(self, telefono: str, texto: str, texto_botao: str, url: str) -> bool:
        """Envía un mensaje com um botão que abre um link (WhatsApp CTA URL Button)."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url_api = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "cta_url",
                "body": {"text": texto},
                "action": {
                    "name": "cta_url",
                    "parameters": {"display_text": texto_botao[:20], "url": url},
                },
            },
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url_api, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API (botão link): {r.status_code} — {r.text}")
            return r.status_code == 200

    async def enviar_documento(
        self, telefono: str, ficheiro: bytes, nome_ficheiro: str,
        mime_type: str, legenda: str = ""
    ) -> bool:
        """Sube el archivo a Meta y lo envía como imagen o documento, según el tipo."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False

        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient() as client:
            # Paso 1: subir el archivo para obtener un media_id
            upload = await client.post(
                f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/media",
                headers=headers,
                data={"messaging_product": "whatsapp"},
                files={"file": (nome_ficheiro, ficheiro, mime_type)},
            )
            if upload.status_code != 200:
                logger.error(f"Error subiendo archivo a Meta: {upload.status_code} — {upload.text}")
                return False
            media_id = upload.json().get("id")

            # Paso 2: enviar el mensaje referenciando el media_id
            tipo_mensaje = "image" if mime_type.startswith("image/") else "document"
            objeto_media = {"id": media_id}
            if legenda:
                objeto_media["caption"] = legenda
            if tipo_mensaje == "document":
                objeto_media["filename"] = nome_ficheiro

            payload = {
                "messaging_product": "whatsapp",
                "to": telefono,
                "type": tipo_mensaje,
                tipo_mensaje: objeto_media,
            }
            r = await client.post(
                f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages",
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
            )
            if r.status_code != 200:
                logger.error(f"Error enviando documento: {r.status_code} — {r.text}")
            return r.status_code == 200
