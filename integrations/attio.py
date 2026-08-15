# integrations/attio.py — Sincronização de leads do WhatsApp com o Attio CRM

"""
Regista no Attio (CRM da Reduz+ Energia) os leads que pedem para falar com
um consultor via WhatsApp: garante uma Person (por número de telefone) e um
Deal na etapa QUALIFICADO na primeira vez, e só acrescenta uma nota nas
escaladas seguintes do mesmo número — nunca duplica o Deal.

Ligação direta e independente do Make: usa um token de acesso dedicado
(ATTIO_API_KEY), separado do usado pelo Make, com os scopes Records
(Read-write), Object Configuration (Read) e Notes (Read-write). Gerar em
Attio → Settings → Developers → Access tokens.

Nunca levanta exceção para fora deste módulo — uma falha do Attio não deve
quebrar o fluxo do WhatsApp, só fica registada no log.
"""

import os
import logging
import httpx

from agent.memory import obter_config, definir_config

logger = logging.getLogger("agentkit")

ATTIO_API_KEY = os.getenv("ATTIO_API_KEY", "")
ATTIO_URL = "https://api.attio.com/v2"

# Workspace member definido como owner de todos os Deals criados por esta
# integração — "owner" é um campo obrigatório nos Deals deste workspace.
ATTIO_OWNER_ACTOR_ID = os.getenv("ATTIO_OWNER_ACTOR_ID", "f2163400-ecc1-4b39-a270-9295ad78ffc3")

# Etapa inicial do pipeline para leads vindos do WhatsApp — já houve
# interação direta (o cliente escreveu e pediu um consultor), por isso
# salta as etapas NOVO/CONTACTADO.
ETAPA_INICIAL = "QUALIFICADO"

_PREFIXO_CHAVE_DEAL = "attio_deal_"


def attio_configurado() -> bool:
    """Se a integração com o Attio está configurada (token presente)."""
    return bool(ATTIO_API_KEY)


def _normalizar_telefone(telefone: str) -> str:
    """Garante o prefixo '+' exigido pelo Attio (o agente guarda os números sem ele)."""
    telefone = (telefone or "").strip()
    if telefone and not telefone.startswith("+"):
        telefone = f"+{telefone}"
    return telefone


async def _attio_request(method: str, caminho: str, corpo: dict | None = None) -> dict | None:
    """Chamada genérica à API do Attio. Retorna None (e regista o erro) se falhar."""
    headers = {
        "Authorization": f"Bearer {ATTIO_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.request(method, f"{ATTIO_URL}{caminho}", headers=headers, json=corpo)
    if r.status_code >= 400:
        logger.error(f"Erro Attio API ({method} {caminho}): {r.status_code} — {r.text}")
        return None
    return r.json() if r.content else {}


async def _encontrar_pessoa_por_telefone(telefone: str) -> str | None:
    """Procura uma Person já existente com este telefone. Retorna o record_id, ou None."""
    resultado = await _attio_request(
        "POST", "/objects/people/records/query",
        corpo={"filter": {"phone_numbers": {"$eq": telefone}}, "limit": 1},
    )
    registos = (resultado or {}).get("data") or []
    if not registos:
        return None
    return registos[0]["id"]["record_id"]


async def _criar_pessoa(telefone: str, nome: str | None) -> str | None:
    """Cria uma nova Person no Attio. Retorna o record_id criado, ou None se falhou."""
    valores = {"phone_numbers": [telefone]}
    if nome:
        valores["name"] = [{"first_name": nome, "last_name": "", "full_name": nome}]
    resultado = await _attio_request(
        "POST", "/objects/people/records",
        corpo={"data": {"values": valores}},
    )
    if not resultado:
        return None
    return resultado["data"]["id"]["record_id"]


async def _obter_ou_criar_pessoa(telefone: str, nome: str | None) -> str | None:
    """Encontra a Person por telefone, ou cria uma nova se não existir."""
    pessoa_id = await _encontrar_pessoa_por_telefone(telefone)
    if pessoa_id:
        return pessoa_id
    return await _criar_pessoa(telefone, nome)


async def _criar_deal(pessoa_id: str, nome: str | None, motivo: str | None) -> str | None:
    """Cria um novo Deal em QUALIFICADO, associado à Person. Retorna o record_id, ou None."""
    titulo = f"WhatsApp - {nome}" if nome else "WhatsApp - Lead sem nome"
    valores = {
        "name": titulo,
        "stage": ETAPA_INICIAL,
        "owner": {
            "referenced_actor_type": "workspace-member",
            "referenced_actor_id": ATTIO_OWNER_ACTOR_ID,
        },
        "associated_people": [{"target_object": "people", "target_record_id": pessoa_id}],
    }
    resultado = await _attio_request(
        "POST", "/objects/deals/records",
        corpo={"data": {"values": valores}},
    )
    if not resultado:
        return None
    return resultado["data"]["id"]["record_id"]


async def _adicionar_nota(deal_id: str, titulo: str, conteudo: str):
    """Acrescenta uma nota ao Deal (histórico de escaladas seguintes do mesmo lead)."""
    await _attio_request(
        "POST", "/notes",
        corpo={
            "data": {
                "parent_object": "deals",
                "parent_record_id": deal_id,
                "title": titulo,
                "format": "plaintext",
                "content": conteudo,
            }
        },
    )


async def sincronizar_lead_attio(telefone: str, nome: str | None, motivo: str | None):
    """
    Sincroniza um lead do WhatsApp com o Attio — chamado quando o cliente
    pede para falar com um consultor (ferramenta escalar_a_consultor).

    Na primeira vez que este número escala, cria a Person (se ainda não
    existir) e um Deal em QUALIFICADO. Nas vezes seguintes, só acrescenta
    uma nota ao Deal já existente (guardado localmente por telefone) —
    nunca duplica o Deal.
    """
    if not attio_configurado():
        logger.info("ATTIO_API_KEY não configurada — sincronização com o Attio ignorada")
        return

    try:
        telefone_norm = _normalizar_telefone(telefone)
        chave = f"{_PREFIXO_CHAVE_DEAL}{telefone}"
        deal_id = await obter_config(chave)

        if deal_id:
            await _adicionar_nota(
                deal_id, "Nova escalada via WhatsApp",
                f"Cliente pediu novamente para falar com um consultor.\n"
                f"Motivo: {motivo or '(não indicado)'}",
            )
            logger.info(f"Attio: nota acrescentada ao Deal {deal_id} ({telefone})")
            return

        pessoa_id = await _obter_ou_criar_pessoa(telefone_norm, nome)
        if not pessoa_id:
            logger.warning(f"Attio: não foi possível obter/criar a Person para {telefone}")
            return

        deal_id = await _criar_deal(pessoa_id, nome, motivo)
        if not deal_id:
            logger.warning(f"Attio: não foi possível criar o Deal para {telefone}")
            return

        await definir_config(chave, deal_id)
        if motivo:
            await _adicionar_nota(deal_id, "Escalada via WhatsApp", f"Motivo: {motivo}")

        logger.info(
            f"Attio: lead sincronizado — Deal {deal_id} criado em {ETAPA_INICIAL} "
            f"para {telefone} ({nome or 'sem nome'})"
        )
    except Exception as e:
        logger.error(f"Erro ao sincronizar lead com o Attio ({telefone}): {e}")
