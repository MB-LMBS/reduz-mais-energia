# agent/formatacao_whatsapp.py — Formatação de mensagens de sistema para WhatsApp
# Generado por AgentKit

"""
Ajuda a formatar mensagens fixas (não geradas pela IA) para ficarem tão
organizadas no WhatsApp real como ficam no painel /admin: rótulos "Campo:"
em negrito nativo do WhatsApp, e links extraídos para enviar como botão
nativo (cta_url) em vez de aparecerem como URL cru no meio do texto.
"""

import re
from urllib.parse import urlparse

URL_REGEX = re.compile(r"https?://\S+")
CAMPO_REGEX = re.compile(r"^([^\n:]{1,40}):(?=[ \t])", re.MULTILINE)


def negrito_campos(texto: str) -> str:
    """Envolve rótulos "Campo:" no início de cada linha em *negrito* nativo do
    WhatsApp — mesma lógica usada no painel /admin, mas com marcadores reais
    em vez de HTML. Ignora linhas já envolvidas em asteriscos."""

    def _substituir(m: re.Match) -> str:
        rotulo = m.group(1)
        if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", rotulo):
            return m.group(0)
        return f"*{rotulo}*:"

    return CAMPO_REGEX.sub(_substituir, texto)


def rotulo_botao(url: str) -> str:
    """Rótulo curto (máx. 20 caracteres — limite do WhatsApp) para um botão de link.

    Usa o domínio quando cabe no limite; caso contrário usa um rótulo
    genérico, para não cortar o domínio a meio de forma ilegível.
    """
    try:
        dominio = urlparse(url).netloc.removeprefix("www.")
    except ValueError:
        dominio = ""
    if dominio and len(dominio) <= 20:
        return dominio
    return "Abrir link"


def extrair_links(texto: str) -> tuple[str, list[str]]:
    """Remove URLs do texto e devolve-as à parte, para serem enviadas como
    botões nativos em vez de aparecerem como link cru no corpo da mensagem."""
    urls = URL_REGEX.findall(texto)
    sem_links = URL_REGEX.sub("", texto)
    sem_links = re.sub(r"[ \t]{2,}", " ", sem_links)
    sem_links = re.sub(r"[ \t]+\n", "\n", sem_links)
    sem_links = re.sub(r"\n[ \t]+", "\n", sem_links)
    sem_links = re.sub(r"\n{3,}", "\n\n", sem_links).strip()
    return sem_links, urls
