# agent/meta_templates.py — Gestão de templates de mensagem da Meta (WhatsApp)
# Generado por AgentKit

"""
Consulta e cria templates de mensagem no WhatsApp Business (via Graph API),
usados para o negócio poder iniciar uma conversa fora da janela de 24h —
como as mensagens diárias de motivação à equipa (agent/motivacao.py).

A Meta não aprova templates cujo conteúdo seja maioritariamente uma
variável em aberto (ver histórico no Manual de Operação) — por isso cada
mensagem individual é o seu próprio template, com o primeiro nome como
única variável, e o resto do texto fixo.
"""

import os
import re
import logging
import httpx

logger = logging.getLogger("agentkit")

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_WABA_ID = os.getenv("META_WABA_ID", "")
GRAPH = "https://graph.facebook.com/v21.0"


def configurado() -> bool:
    return bool(META_ACCESS_TOKEN and META_WABA_ID)


async def listar_templates(prefixo: str = "") -> list[dict]:
    """Lista todos os templates (qualquer estado) cujo nome começa por `prefixo`."""
    if not configurado():
        return []
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{GRAPH}/{META_WABA_ID}/message_templates",
            params={"access_token": META_ACCESS_TOKEN, "fields": "name,status", "limit": 200},
        )
        if r.status_code != 200:
            logger.error(f"Erro Meta (listar templates): {r.status_code} — {r.text}")
            return []
        dados = r.json().get("data", [])
        if prefixo:
            dados = [t for t in dados if t["name"].startswith(prefixo)]
        return dados


async def listar_templates_aprovados(prefixo: str) -> list[str]:
    """Nomes dos templates aprovados com este prefixo, ordenados."""
    templates = await listar_templates(prefixo)
    nomes = sorted(t["name"] for t in templates if t["status"] == "APPROVED")
    return nomes


async def proximo_indice_livre(prefixo: str) -> int:
    """Próximo número livre a seguir ao maior já usado (aprovado, pendente ou rejeitado) com este prefixo."""
    templates = await listar_templates(prefixo)
    maior = 0
    for t in templates:
        m = re.search(r"_(\d+)$", t["name"])
        if m:
            maior = max(maior, int(m.group(1)))
    return maior + 1


async def criar_template(nome: str, texto_corpo: str, categoria: str = "MARKETING") -> bool:
    """Submete um novo template à revisão da Meta. Retorna True se aceite (fica PENDING)."""
    if not configurado():
        logger.warning("META_WABA_ID não configurado — não é possível criar templates")
        return False
    payload = {
        "name": nome,
        "language": "pt_PT",
        "category": categoria,
        "components": [{"type": "BODY", "text": texto_corpo}],
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{GRAPH}/{META_WABA_ID}/message_templates",
            headers={"Authorization": f"Bearer {META_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code != 200:
            logger.error(f"Erro Meta (criar template {nome}): {r.status_code} — {r.text}")
            return False
        logger.info(f"Template {nome} submetido à Meta: {r.json()}")
        return True
