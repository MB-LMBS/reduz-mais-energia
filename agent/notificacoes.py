# agent/notificacoes.py — Encaminhamento de conversas para o consultor humano
# Generado por AgentKit

"""
Envía una conversación completa por WhatsApp al número personal del
consultor. Se usa tanto automáticamente (cuando el bot detecta un pedido
de consultor) como manualmente (botón "Encaminhar para consultor" en /admin).
"""

import os
import logging

from agent.agenda import formatar_slot
from agent.formatacao_whatsapp import negrito_campos

logger = logging.getLogger("agentkit")

# Número personal a donde se reenvía la conversación
NUMERO_CONSULTOR = os.getenv("NUMERO_CONSULTOR", "")

# URL pública do painel — usada para que os links nas notificações sejam
# clicáveis diretamente a partir do WhatsApp (ex: no telemóvel, fora do escritório)
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://reduz-mais-energia-production.up.railway.app")


async def notificar_consultor(
    proveedor, telefono_cliente: str, historial: list[dict],
    mensaje_actual: str | None = None, motivo: str | None = None,
) -> bool:
    """
    Envía la conversación completa al WhatsApp personal del consultor.
    Retorna True si se envió con éxito.
    """
    if not NUMERO_CONSULTOR:
        logger.warning("NUMERO_CONSULTOR no configurado — no se puede notificar")
        return False

    lineas = [f"🔔 *Pedido de consultor* — {telefono_cliente}"]
    if motivo:
        lineas.append(f"_{motivo}_")
    lineas.append("")
    for msg in historial:
        etiqueta = "Cliente" if msg["role"] == "user" else "Reduz+"
        contenido = msg["content"] or f"[ficheiro: {msg.get('nome_ficheiro') or msg.get('tipo')}]"
        lineas.append(f"*{etiqueta}:* {negrito_campos(contenido)}")
    if mensaje_actual:
        lineas.append(f"*Cliente:* {negrito_campos(mensaje_actual)}")

    enviado = await proveedor.enviar_mensaje(NUMERO_CONSULTOR, "\n".join(lineas))
    await proveedor.enviar_botao_link(
        NUMERO_CONSULTOR, "Responder diretamente ao cliente:", "Abrir conversa",
        f"{APP_BASE_URL}/admin/conversa/{telefono_cliente}",
    )
    return enviado


async def notificar_lembrete_chamada(proveedor, agendamento: dict) -> bool:
    """
    Envía un recordatorio al WhatsApp personal del consultor unos minutos
    antes de una chamada agendada. Retorna True si se envió con éxito.
    """
    if not NUMERO_CONSULTOR:
        logger.warning("NUMERO_CONSULTOR no configurado — no se puede enviar lembrete")
        return False

    nome = agendamento.get("nome_cliente") or "(nome não indicado)"
    telefone = agendamento["telefono"]
    slot = formatar_slot(agendamento["data_hora"])
    informacao = agendamento.get("informacao") or "(sem informação adicional)"

    lineas = [
        "⏰ *Lembrete: chamada daqui a poucos minutos*",
        "",
        f"*Cliente:* {nome}",
        f"*Telefone:* {telefone}",
        f"*Quando:* {slot}",
        "",
        f"*Informação registada:*\n{informacao}",
        "",
        f"Ver conversa: {APP_BASE_URL}/admin/conversa/{telefone}",
    ]

    return await proveedor.enviar_mensaje(NUMERO_CONSULTOR, "\n".join(lineas))


async def notificar_cliente_lembrete(proveedor, agendamento: dict) -> bool:
    """
    Envía um lembrete diretamente ao próprio cliente, pouco antes da chamada
    agendada. Retorna True se enviado com sucesso.
    """
    telefone = agendamento["telefono"]
    nome = agendamento.get("nome_cliente")
    hora = agendamento["data_hora"].strftime("%Hh%M")
    saudacao = f"Olá, {nome}!" if nome else "Olá!"

    mensagem = (
        f"{saudacao} 📞 Só a lembrar que tem uma chamada agendada com a "
        f"Reduz+ Energia hoje às **{hora}**. Vamos ligar-lhe daqui a poucos "
        "minutos — até já! 😊"
    )

    return await proveedor.enviar_mensaje(telefone, mensagem)


async def notificar_cancelamento(proveedor, agendamento: dict, motivo: str | None = None) -> bool:
    """
    Envía un alerta al WhatsApp personal del consultor cuando o próprio
    cliente cancela uma chamada agendada, via WhatsApp.
    Retorna True si se envió con éxito.
    """
    if not NUMERO_CONSULTOR:
        logger.warning("NUMERO_CONSULTOR no configurado — no se puede notificar cancelamento")
        return False

    nome = agendamento.get("nome_cliente") or "(nome não indicado)"
    telefone = agendamento["telefono"]
    slot = formatar_slot(agendamento["data_hora"])

    lineas = [
        "❌ *Chamada cancelada pelo cliente*",
        "",
        f"*Cliente:* {nome}",
        f"*Telefone:* {telefone}",
        f"*Era às:* {slot}",
    ]
    if motivo:
        lineas.append(f"*Motivo:* {negrito_campos(motivo)}")
    lineas.append("")
    lineas.append(f"Ver conversa: {APP_BASE_URL}/admin/conversa/{telefone}")

    return await proveedor.enviar_mensaje(NUMERO_CONSULTOR, "\n".join(lineas))


TITULOS_POR_FORMATO = {
    "presencial": "Reunião presencial agendada",
    "telefonica": "Chamada agendada",
    "teams": "Reunião Teams agendada",
    "deslocacao": "Deslocação agendada",
    "recordatorio": "Recordatório agendado",
}


def _titulo_notificacao(agendamento: dict) -> str:
    """Título da notificação — reflete o formato real do compromisso (agenda pessoal) em vez de assumir sempre 'chamada'."""
    formato = agendamento.get("formato")
    if formato in TITULOS_POR_FORMATO:
        return TITULOS_POR_FORMATO[formato]
    if agendamento.get("tipo_evento"):
        return "Compromisso agendado"
    return "Chamada agendada"


# Desativado a 14/08/2026: 5 tentativas de template (v1 a v5, variando
# categoria, número de variáveis e conteúdo) foram todas rejeitadas pela
# Meta com o mesmo motivo (INVALID_FORMAT) — mesmo a versão mais simples
# possível (uma única variável curta, sem texto livre). A causa pode ser
# específica desta conta/WABA, não só o texto. Decisão do Luis: desistir
# por agora em vez de continuar a tentar variações. Para retomar mais
# tarde, contactar o suporte da Meta com o histórico de rejeições, ou
# tentar de novo a partir daqui.
CONVITE_CONVIDADOS_ATIVO = False


async def notificar_convidados(
    proveedor, convidados: list[str], descricao: str, data_str: str, hora_str: str, nota: str = "",
) -> int:
    """
    Avisa cada convidado por WhatsApp de um compromisso da agenda pessoal do
    consultor, via template pré-aprovado — necessário para o negócio
    iniciar a conversa fora da janela de 24h. Ver CONVITE_CONVIDADOS_ATIVO
    acima: atualmente desativado (nenhum template passou na revisão da
    Meta). `nota` fica só na descrição do evento, nunca é reenviada ao
    convidado. Retorna quantos convites foram enviados com sucesso.
    """
    if not CONVITE_CONVIDADOS_ATIVO:
        return 0

    quando = f"{data_str} às {hora_str}"
    sucesso = 0
    for numero in convidados:
        ok = await proveedor.enviar_template(
            numero, "convite_reuniao_convidado_v5", [f"{descricao}, {quando}"],
        )
        if ok:
            sucesso += 1
        else:
            logger.warning(f"Falha ao enviar convite de compromisso a {numero}")
    return sucesso


async def notificar_agendamento(proveedor, agendamento: dict) -> bool:
    """
    Envía un alerta al WhatsApp personal del consultor cuando se marca una
    chamada, con toda la información que el cliente registró.
    Retorna True si se envió con éxito.
    """
    if not NUMERO_CONSULTOR:
        logger.warning("NUMERO_CONSULTOR no configurado — no se puede notificar agendamento")
        return False

    nome = agendamento.get("nome_cliente") or "(nome não indicado)"
    telefone = agendamento["telefono"]
    slot = formatar_slot(agendamento["data_hora"])
    informacao = agendamento.get("informacao") or "(sem informação adicional)"

    lineas = [
        f"📅 *{_titulo_notificacao(agendamento)}*",
        "",
        f"*Cliente:* {nome}",
        f"*Telefone:* {telefone}",
        f"*Quando:* {slot}",
        "",
        f"*Informação registada:*\n{informacao}",
        "",
        f"Ver conversa: {APP_BASE_URL}/admin/conversa/{telefone}",
    ]

    return await proveedor.enviar_mensaje(NUMERO_CONSULTOR, "\n".join(lineas))
