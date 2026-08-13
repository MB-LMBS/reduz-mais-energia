# agent/admin.py — Painel de administração para ver e responder conversas
# Generado por AgentKit

"""
Painel web simples e protegido por password para:
- Ver todas as conversas do agente, separadas em "Em aberto" e "Tratadas"
- Alternar cada conversa entre modo "bot" (automático) e "manual" (o humano responde)
- Enviar respostas manuais (texto ou ficheiros) a partir do telemóvel
- Ver ficheiros que os clientes enviaram (fotos, PDFs, etc.)
"""

import os
import re
import html
import uuid
import secrets
import logging
import mimetypes
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse

from agent.memory import (
    listar_conversaciones, obtener_historial, obtener_modo, establecer_modo,
    obtener_estado, establecer_estado, obtener_nome_contato, obtener_categoria,
    establecer_categoria, CATEGORIAS_VALIDAS, guardar_mensaje, listar_agendamentos,
    editar_mensagem, apagar_mensagem, obtener_mensagens_novas,
    listar_alertas_nao_vistos, marcar_alerta_visto, marcar_todos_alertas_vistos,
    cancelar_agendamento,
)
from agent.agenda import formatar_slot
from agent.providers import obtener_proveedor
from agent.notificacoes import notificar_consultor, NUMERO_CONSULTOR
from agent.calendario import apagar_evento_chamada as apagar_evento_icloud
from agent.outlook_calendar import (
    apagar_evento_chamada as apagar_evento_outlook,
    outlook_configurado, esta_ligado as outlook_esta_ligado,
    gerar_url_autorizacao, concluir_autorizacao,
)
from agent.feriados import (
    feriado_de_hoje, proximos_feriados, nome_dia_semana,
    feriados_municipais_de_hoje, proximo_feriado_municipal,
)

logger = logging.getLogger("agentkit")
router = APIRouter(prefix="/admin")
security = HTTPBasic()

MEDIA_DIR = "data/media"
os.makedirs(MEDIA_DIR, exist_ok=True)

LOGO_URL = "https://reduz-mais-energia.neocities.org/Reduz+%20Energia_logo.png"
FAVICON_LINK = f'<link rel="icon" type="image/png" href="{LOGO_URL}">'

ESTILO = """
<style>
  :root {
    --verde: #0a7d4f; --verde-escuro: #086b43; --azul: #1d6fa5; --vermelho: #c0392b;
    --fundo: #f2f3f5; --fundo-card: #ffffff; --texto: #1a1a1a; --texto-secundario: #666;
    --borda: #e2e2e2;
    --sombra: 0 1px 3px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.05);
    --sombra-media: 0 4px 14px rgba(0,0,0,0.12);
    --bolha-bot-1: #e3f9d5; --bolha-bot-2: #d4f4c0;
    --bolha-humano-1: #d9ecff; --bolha-humano-2: #c9e3ff;
  }
  body.tema-azul {
    --verde: #1d6fa5; --verde-escuro: #164f79;
    --bolha-bot-1: #d9ecff; --bolha-bot-2: #c9e3ff;
    --bolha-humano-1: #e3f9d5; --bolha-humano-2: #d4f4c0;
  }
  body.tema-escuro {
    --fundo: #16181b; --fundo-card: #23262a; --texto: #eee; --texto-secundario: #9aa0a6;
    --borda: #383c41;
    --sombra: 0 1px 3px rgba(0,0,0,0.4); --sombra-media: 0 4px 16px rgba(0,0,0,0.55);
    --bolha-bot-1: #1e3a2c; --bolha-bot-2: #234730;
    --bolha-humano-1: #1c3550; --bolha-humano-2: #204066;
  }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 640px;
         margin: 0 auto; padding: 12px; background: var(--fundo); color: var(--texto);
         transition: background 0.2s ease, color 0.2s ease; }
  h1 { font-size: 1.3rem; }
  a { color: var(--verde); text-decoration: none; }
  button { font-family: inherit; cursor: pointer; -webkit-tap-highlight-color: transparent; }
  .temas { display: flex; gap: 6px; align-items: center; }
  .tema-swatch { width: 22px; height: 22px; border-radius: 50%; border: 2px solid transparent;
                  padding: 0; transition: transform 0.12s ease, border-color 0.12s ease; }
  .tema-swatch:hover { transform: scale(1.15); }
  .tema-swatch.ativo { border-color: var(--texto); }
  .tema-swatch.tema-verde { background: linear-gradient(135deg, #0a7d4f, #0f9d63); }
  .tema-swatch.tema-azul { background: linear-gradient(135deg, #1d6fa5, #2a8fd1); }
  .tema-swatch.tema-escuro { background: linear-gradient(135deg, #23262a, #0e0f11); }
  .relogio-card { background: var(--fundo-card); border-radius: 16px; padding: 16px 18px; margin-bottom: 12px;
                   box-shadow: var(--sombra); display: flex; justify-content: space-between; align-items: center;
                   flex-wrap: wrap; gap: 10px; }
  .relogio-hora { font-size: 2.4rem; font-weight: 700; letter-spacing: 0.02em; line-height: 1;
                   font-variant-numeric: tabular-nums; }
  .relogio-dia { color: var(--texto-secundario); font-size: 0.95rem; margin-top: 4px; text-transform: capitalize; }
  .feriados-info { text-align: right; font-size: 0.82rem; color: var(--texto-secundario); line-height: 1.5; }
  .feriados-info .feriado-hoje { color: var(--vermelho); font-weight: 700; display: block; }
  .feriados-info .feriado-proximo strong { color: var(--texto); }
  .feriados-info .feriado-municipal { display: block; }
  .tag-tipo { font-size: 0.68rem; padding: 1px 7px; border-radius: 8px; border: 1px solid var(--borda);
              margin-left: 4px; white-space: nowrap; }
  .tag-tipo.nacional { color: var(--verde); border-color: var(--verde); }
  .tag-tipo.local { color: var(--azul); border-color: var(--azul); }
  .tabs { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
  .tabs a { flex: 1; text-align: center; padding: 10px; border-radius: 10px; background: var(--fundo-card);
            color: var(--texto-secundario); font-size: 0.9rem; font-weight: 500; box-shadow: var(--sombra);
            transition: transform 0.12s ease, box-shadow 0.12s ease; }
  .tabs a.ativo { background: var(--verde); color: white; box-shadow: 0 2px 8px rgba(10,125,79,0.35); }
  .tabs a:active { transform: scale(0.97); }
  .conversa { background: var(--fundo-card); border-radius: 14px; padding: 12px 16px; margin-bottom: 10px;
              display: flex; gap: 10px; align-items: flex-start; box-shadow: var(--sombra);
              transition: box-shadow 0.15s ease, transform 0.15s ease; }
  .conversa:hover { box-shadow: var(--sombra-media); transform: translateY(-1px); }
  .conversa .corpo { flex: 1; min-width: 0; }
  .conversa .top { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
  .conversa .tel { font-weight: 600; }
  .avatar { flex-shrink: 0; width: 40px; height: 40px; border-radius: 50%; display: flex;
            align-items: center; justify-content: center; color: white; font-weight: 600;
            font-size: 0.95rem; box-shadow: inset 0 0 0 2px rgba(255,255,255,0.25); }
  .cabecalho { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
  .cabecalho .avatar { width: 48px; height: 48px; font-size: 1.1rem; }
  .cabecalho .nome { font-size: 1.2rem; font-weight: 600; }
  .cabecalho .tel { color: var(--texto-secundario); font-size: 0.85rem; }
  .btn-consultor { width: 100%; padding: 12px; margin-bottom: 8px; border-radius: 12px; border: none;
                    background: linear-gradient(135deg, var(--azul), #164f79); color: white; font-size: 0.9rem;
                    font-weight: 600; box-shadow: 0 3px 10px rgba(29,111,165,0.35);
                    transition: transform 0.12s ease, box-shadow 0.12s ease; }
  .btn-consultor:hover { box-shadow: 0 5px 16px rgba(29,111,165,0.45); }
  .btn-consultor:active { transform: scale(0.98); }
  .badges { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
  .badge { font-size: 0.75rem; padding: 3px 9px; border-radius: 10px; white-space: nowrap; font-weight: 600; }
  .badge.bot { background: #e3f2e9; color: var(--verde); }
  .badge.manual { background: #fdeaea; color: var(--vermelho); }
  .badge.tratada { background: #e9e9e9; color: #666; }
  .badge.interessado { background: #fdf2df; color: #a5701d; }
  .badge.ganho { background: #e3f2e9; color: var(--verde); }
  .badge.perdido { background: #fdeaea; color: var(--vermelho); }
  .filtros { display: flex; gap: 6px; margin-bottom: 12px; overflow-x: auto; padding-bottom: 2px; }
  .filtros a { flex-shrink: 0; padding: 7px 14px; border-radius: 20px; background: var(--fundo-card);
               color: var(--texto-secundario); font-size: 0.85rem; border: 1px solid var(--borda);
               transition: all 0.12s ease; }
  .filtros a.ativo { background: #1a1a1a; color: white; border-color: #1a1a1a; }
  .preview { color: var(--texto-secundario); font-size: 0.9rem; margin-top: 4px; white-space: nowrap;
             overflow: hidden; text-overflow: ellipsis; }
  .msg { padding: 9px 13px; border-radius: 16px; margin-bottom: 10px; max-width: 80%; word-break: break-word;
         box-shadow: var(--sombra); position: relative; line-height: 1.4; color: var(--texto);
         white-space: pre-wrap; }
  .msg strong { font-weight: 700; }
  .msg em { font-style: italic; }
  .msg .campo { font-weight: 600; }
  .msg .link-botao { display: inline-block; margin: 5px 6px 2px 0; padding: 7px 14px; border-radius: 20px;
                      background: var(--verde); color: #fff; text-decoration: none; font-size: 0.85rem;
                      font-weight: 600; white-space: nowrap; }
  .msg .link-botao:active { opacity: 0.85; }
  .msg.user { background: var(--fundo-card); margin-right: auto; border-bottom-left-radius: 4px; }
  .msg.assistant { background: linear-gradient(135deg, var(--bolha-bot-1), var(--bolha-bot-2)); margin-left: auto;
                    border-bottom-right-radius: 4px; }
  .msg.humano { background: linear-gradient(135deg, var(--bolha-humano-1), var(--bolha-humano-2)); margin-left: auto;
                border-bottom-right-radius: 4px; }
  .msg img { max-width: 100%; border-radius: 10px; display: block; margin-bottom: 4px; }
  .msg .ficheiro { display: block; font-size: 0.85rem; }
  .msg .remetente { display: block; font-size: 0.7rem; font-weight: 700; opacity: 0.5; margin-bottom: 3px;
                     text-transform: uppercase; letter-spacing: 0.03em; }
  .msg .hora { display: block; font-size: 0.7rem; color: #999; margin-top: 4px; text-align: right; }
  .msg-acoes { display: flex; gap: 12px; justify-content: flex-end; margin-top: 5px; }
  .msg-acoes summary, .msg-acoes .btn-apagar { font-size: 0.75rem; color: var(--texto-secundario); cursor: pointer;
                                                 background: none; border: none; padding: 0;
                                                 transition: color 0.12s ease; }
  .msg-acoes summary:hover { color: var(--verde); }
  .msg-acoes .btn-apagar { color: var(--vermelho); opacity: 0.85; }
  .msg-acoes .btn-apagar:hover { opacity: 1; }
  .form-editar { display: flex; gap: 6px; margin-top: 6px; }
  .form-editar textarea { flex: 1; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--borda);
                            resize: none; background: var(--fundo-card); color: var(--texto); }
  .form-editar button { padding: 0 12px; border-radius: 8px; border: none; background: var(--verde);
                          color: white; font-weight: 600; transition: background 0.12s ease; }
  .form-editar button:hover { background: var(--verde-escuro); }
  form.reply { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; }
  form.reply textarea { flex: 1; min-width: 140px; padding: 12px 14px; border-radius: 20px; border: 1px solid var(--borda);
                         resize: none; background: var(--fundo-card); color: var(--texto); box-shadow: var(--sombra);
                         transition: border-color 0.12s ease; }
  form.reply textarea:focus { outline: none; border-color: var(--verde); }
  form.reply button { padding: 0 22px; height: 44px; border-radius: 22px; border: none; background: var(--verde);
                       color: white; font-weight: 600; box-shadow: 0 3px 10px rgba(10,125,79,0.35);
                       transition: transform 0.12s ease, background 0.12s ease; }
  form.reply button:hover { background: var(--verde-escuro); }
  form.reply button:active { transform: scale(0.96); }
  form.reply .anexo { flex-basis: 100%; font-size: 0.85rem; color: var(--texto-secundario); }
  .toggle { display: flex; gap: 8px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
  .toggle.separador { padding-top: 8px; border-top: 1px solid var(--borda); }
  .toggle button { padding: 7px 13px; border-radius: 10px; border: 1px solid var(--borda); background: var(--fundo-card);
                    color: var(--texto); font-size: 0.85rem; font-weight: 500; transition: all 0.12s ease; }
  .toggle button:hover { border-color: #bbb; }
  .toggle button.ativo { background: var(--verde); color: white; border-color: var(--verde);
                          box-shadow: 0 2px 6px rgba(10,125,79,0.3); }
  .toggle button.tratada.ativo { background: #666; border-color: #666; box-shadow: none; }
  .toggle button.interessado.ativo { background: #a5701d; border-color: #a5701d; box-shadow: 0 2px 6px rgba(165,112,29,0.3); }
  .toggle button.ganho.ativo { background: var(--verde); border-color: var(--verde); }
  .toggle button.perdido.ativo { background: var(--vermelho); border-color: var(--vermelho); box-shadow: 0 2px 6px rgba(192,57,43,0.3); }
  .topo { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
          gap: 8px; margin-bottom: 12px; }
  .topo-direita { display: flex; align-items: center; gap: 12px; }
  .marca { display: flex; align-items: center; gap: 8px; }
  .marca .logo { width: 32px; height: 32px; border-radius: 8px; box-shadow: var(--sombra); flex-shrink: 0; }
  .marca h1 { margin: 0; font-size: 1.05rem; }
  .alertas { margin-bottom: 12px; }
  .alerta { background: linear-gradient(135deg, #fffaeb, #fff3d6); border: 1px solid #f0d78c; border-radius: 12px;
            padding: 10px 14px; margin-bottom: 8px; display: flex; justify-content: space-between;
            align-items: center; gap: 10px; font-size: 0.9rem; box-shadow: var(--sombra); color: #1a1a1a; }
  .alerta a.ver { color: #1a1a1a; text-decoration: underline; flex: 1; }
  .alerta button { flex-shrink: 0; padding: 5px 12px; border-radius: 8px; border: 1px solid #ddd;
                    background: white; font-size: 0.8rem; transition: all 0.12s ease; }
  .alerta button:hover { background: #f5f5f5; }
  .alertas-topo { display: flex; justify-content: flex-end; margin-bottom: 6px; }
  .alertas-topo button { padding: 5px 12px; border-radius: 8px; border: 1px solid var(--borda);
                          background: var(--fundo-card); color: var(--texto); font-size: 0.8rem; transition: all 0.12s ease; }
  .alertas-topo button:hover { filter: brightness(0.96); }
  .link-agenda { padding: 9px 16px; border-radius: 10px; background: var(--fundo-card); color: var(--texto-secundario);
                 font-size: 0.9rem; font-weight: 500; border: 1px solid var(--borda); box-shadow: var(--sombra);
                 transition: box-shadow 0.12s ease; }
  .link-agenda:hover { box-shadow: var(--sombra-media); }
  .agendamento { background: var(--fundo-card); border-radius: 14px; padding: 12px 16px; margin-bottom: 10px;
                 box-shadow: var(--sombra); }
  .agendamento .quando { font-weight: 700; color: var(--verde); }
  .agendamento .nome { font-weight: 600; }
  .agendamento .tel { color: var(--texto-secundario); font-size: 0.85rem; }
  .agendamento .info { margin-top: 6px; font-size: 0.9rem; white-space: pre-wrap; }
  .btn-cancelar { margin-top: 8px; padding: 7px 14px; border-radius: 8px; border: 1px solid var(--vermelho);
                   background: var(--fundo-card); color: var(--vermelho); font-size: 0.85rem; font-weight: 500;
                   transition: all 0.12s ease; }
  .btn-cancelar:hover { background: var(--vermelho); color: white; }
  .sync-ok { color: var(--verde); font-size: 0.9rem; }
  .sync-aviso { color: #a5701d; font-size: 0.9rem; background: #fff8e1; padding: 8px 12px; border-radius: 8px; }

  /* Página de conversa: cabeçalho fixo no topo, mensagens com scroll próprio,
     caixa de resposta fixa em baixo — como numa app de chat normal */
  body.conversa-page { padding: 0; height: 100vh; display: flex; flex-direction: column; overflow: hidden;
                        background: var(--fundo); }
  .cabecalho-fixo { flex-shrink: 0; background: var(--fundo-card); border-bottom: 1px solid var(--borda);
                     padding: 10px 12px; position: relative; z-index: 20; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }
  .cabecalho-linha { display: flex; align-items: center; gap: 10px; }
  .cabecalho-linha .voltar { font-size: 1.2rem; flex-shrink: 0; color: var(--texto); }
  .cabecalho-linha .avatar { width: 40px; height: 40px; font-size: 0.95rem; }
  .cabecalho-info { flex: 1; min-width: 0; }
  .cabecalho-info .nome { font-weight: 600; font-size: 1rem; white-space: nowrap; overflow: hidden;
                           text-overflow: ellipsis; color: var(--texto); }
  .cabecalho-info .tel { color: var(--texto-secundario); font-size: 0.8rem; }
  .opcoes { flex-shrink: 0; }
  .opcoes summary { list-style: none; cursor: pointer; font-size: 1.3rem; padding: 4px 10px; border-radius: 8px;
                     transition: background 0.12s ease; color: var(--texto); }
  .opcoes summary:hover { background: var(--fundo); }
  .opcoes summary::-webkit-details-marker { display: none; }
  .opcoes[open] summary { color: var(--verde); background: var(--fundo); }
  .opcoes-conteudo { position: absolute; right: 12px; top: 100%; background: var(--fundo-card); border: 1px solid var(--borda);
                      border-radius: 14px; padding: 12px; margin-top: 6px; box-shadow: var(--sombra-media);
                      min-width: 240px; max-width: calc(100vw - 24px); z-index: 30; }
  .mensagens-scroll { flex: 1; overflow-y: auto; padding: 14px 12px; }
  .reply-fixa { flex-shrink: 0; background: var(--fundo); border-top: 1px solid var(--borda); padding: 10px 12px; }
</style>
"""

# Script de tema — colocado logo a seguir à abertura do <body>, para aplicar
# o tema guardado antes do resto da página ser pintado (evita "flash").
SCRIPT_TEMA = """<script>
(function() {
  var guardado = localStorage.getItem('reduzmais-tema');
  if (guardado) document.body.classList.add(guardado);
})();
function mudarTema(tema) {
  document.body.classList.remove('tema-verde', 'tema-azul', 'tema-escuro');
  if (tema !== 'tema-verde') document.body.classList.add(tema);
  localStorage.setItem('reduzmais-tema', tema === 'tema-verde' ? '' : tema);
  document.querySelectorAll('.tema-swatch').forEach(function(el) {
    el.classList.toggle('ativo', el.classList.contains(tema));
  });
}
window.addEventListener('load', function() {
  var guardado = localStorage.getItem('reduzmais-tema') || 'tema-verde';
  document.querySelectorAll('.tema-swatch').forEach(function(el) {
    el.classList.toggle('ativo', el.classList.contains(guardado));
  });
});
</script>"""


def _swatches_tema_html() -> str:
    """Botões circulares para trocar o tema de cores do painel (guardado no browser)."""
    return "".join(
        f'<button type="button" class="tema-swatch {classe}" title="{titulo}" onclick="mudarTema(\'{classe}\')"></button>'
        for classe, titulo in [("tema-verde", "Verde"), ("tema-azul", "Azul"), ("tema-escuro", "Escuro")]
    )


def _formatar_concelhos(concelhos: list[str], limite: int = 6) -> str:
    """Formata uma lista de concelhos para exibição, cortando se for muito longa."""
    if len(concelhos) <= limite:
        return ", ".join(concelhos)
    return ", ".join(concelhos[:limite]) + f" e mais {len(concelhos) - limite}"


def _relogio_feriados_html() -> str:
    """Cartão com relógio digital (hora/dia atualizados em tempo real) e feriados atuais/próximos."""
    hoje = datetime.now(ZoneInfo("Europe/Lisbon")).date()
    feriado_hoje = feriado_de_hoje(hoje)
    concelhos_hoje = feriados_municipais_de_hoje(hoje)

    partes_feriados = ""
    if feriado_hoje:
        partes_feriados += (
            f'<span class="feriado-hoje">🎉 Hoje é feriado — {html.escape(feriado_hoje)} '
            f'<span class="tag-tipo nacional">Nacional</span></span>'
        )
    if concelhos_hoje:
        partes_feriados += (
            f'<span class="feriado-municipal">🏛️ Feriado municipal hoje '
            f'<span class="tag-tipo local">Local</span> — {html.escape(_formatar_concelhos(concelhos_hoje))}</span>'
        )

    for data_f, nome_f in proximos_feriados(hoje, quantidade=2 if feriado_hoje else 3):
        if data_f == hoje:
            continue
        partes_feriados += (
            f'<span class="feriado-proximo">{nome_dia_semana(data_f)}, {data_f.strftime("%d/%m")} — '
            f'<strong>{html.escape(nome_f)}</strong> <span class="tag-tipo nacional">Nacional</span></span><br>'
        )

    proximo_municipal = proximo_feriado_municipal(hoje)
    if proximo_municipal:
        data_m, concelhos_m = proximo_municipal
        partes_feriados += (
            f'<span class="feriado-proximo">{nome_dia_semana(data_m)}, {data_m.strftime("%d/%m")} — '
            f'<strong>Feriado municipal</strong> <span class="tag-tipo local">Local</span> — '
            f'{html.escape(_formatar_concelhos(concelhos_m))}</span><br>'
        )

    return f"""
    <div class="relogio-card">
      <div>
        <div class="relogio-hora" id="relogio-hora">--:--</div>
        <div class="relogio-dia" id="relogio-dia">a carregar…</div>
      </div>
      <div class="feriados-info">{partes_feriados}</div>
    </div>
    <script>
    (function() {{
      var dias = ['Domingo','Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira','Sexta-feira','Sábado'];
      function atualizar() {{
        var agora = new Date();
        var hh = String(agora.getHours()).padStart(2, '0');
        var mm = String(agora.getMinutes()).padStart(2, '0');
        document.getElementById('relogio-hora').textContent = hh + ':' + mm;
        document.getElementById('relogio-dia').textContent = dias[agora.getDay()] + ', ' + agora.toLocaleDateString('pt-PT');
      }}
      atualizar();
      setInterval(atualizar, 1000);
    }})();
    </script>
    """


# O WhatsApp Cloud API da Meta não disponibiliza a foto de perfil dos contactos
# por razões de privacidade — como alternativa, geramos um avatar com as
# iniciais do nome (ou os últimos dígitos do número, se o nome ainda não for
# conhecido) numa cor estável por contacto.
CORES_AVATAR = ["#0a7d4f", "#1d6fa5", "#a5521d", "#7d1da5", "#a51d4a", "#4a7d1d"]


def _avatar_html(nome: str | None, telefono: str, tamanho_classe: str = "") -> str:
    """Gera um avatar simples (iniciais em círculo colorido) para um contacto."""
    if nome:
        iniciais = "".join(p[0] for p in nome.split()[:2]).upper()
    else:
        iniciais = telefono[-2:]
    cor = CORES_AVATAR[sum(ord(c) for c in telefono) % len(CORES_AVATAR)]
    return f'<div class="avatar {tamanho_classe}" style="background:{cor}">{html.escape(iniciais)}</div>'


def verificar_password(credentials: HTTPBasicCredentials = Depends(security)):
    """Protege o painel com uma password única (ADMIN_PASSWORD no .env)."""
    password_correta = os.getenv("ADMIN_PASSWORD", "")
    if not password_correta:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD não está configurada")
    if not secrets.compare_digest(credentials.password, password_correta):
        raise HTTPException(
            status_code=401,
            detail="Password incorreta",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


NOMES_CATEGORIA = {
    "sem_categoria": "Sem categoria",
    "interessado": "Com interesse",
    "ganho": "Ganho",
    "perdido": "Perdido",
}


def _render_alertas(alertas: list[dict]) -> str:
    """Gera o HTML dos alertas pendentes (agendamentos, lembretes, escaladas)."""
    if not alertas:
        return ""
    linhas = ""
    for a in alertas:
        mensagem = html.escape(a["mensagem"])
        telefone = html.escape(a["telefono"])
        linhas += f"""
        <div class="alerta">
          <a class="ver" href="/admin/conversa/{telefone}">{mensagem}</a>
          <form method="post" action="/admin/alertas/{a['id']}/visto">
            <button type="submit">Dispensar</button>
          </form>
        </div>
        """
    return f"""
    <div class="alertas">
      <div class="alertas-topo">
        <form method="post" action="/admin/alertas/marcar-todos">
          <button type="submit">Marcar todos como lidos</button>
        </form>
      </div>
      {linhas}
    </div>
    """


@router.get("/", response_class=HTMLResponse)
async def painel(
    estado: str = "aberta", categoria: str = "todas", vista: str = "",
    auth: bool = Depends(verificar_password),
):
    """Lista as conversas do estado escolhido, com filtro opcional por categoria comercial.

    A vista "interesse" é um separador à parte dos habituais Em aberto/Tratadas —
    mostra todas as conversas marcadas como "Com interesse" (ex: pedidos vindos do
    simulador de eletricidade), independentemente de estarem abertas ou tratadas.
    """
    alertas = await listar_alertas_nao_vistos()
    alertas_html = _render_alertas(alertas)
    todas = await listar_conversaciones()
    n_abertas = sum(1 for c in todas if c["estado"] == "aberta")
    n_tratadas = sum(1 for c in todas if c["estado"] == "tratada")
    n_interesse = sum(1 for c in todas if c["categoria"] == "interessado")

    if vista == "interesse":
        conversas = [c for c in todas if c["categoria"] == "interessado"]
    else:
        do_estado = [c for c in todas if c["estado"] == estado]
        conversas = do_estado if categoria == "todas" else [c for c in do_estado if c["categoria"] == categoria]

    linhas = ""
    for c in conversas:
        preview = html.escape(c["ultimo_mensaje"][:80]) if c.get("ultimo_mensaje") else ""
        if not preview and c.get("ultimo_tipo") != "texto":
            preview = f"[{c.get('ultimo_tipo', 'ficheiro')}]"
        badge_classe = "manual" if c["modo"] == "manual" else "bot"
        badge_texto = "Manual" if c["modo"] == "manual" else "Bot"
        badges_extra = ""
        if c["categoria"] != "sem_categoria":
            badges_extra = f'<span class="badge {c["categoria"]}">{NOMES_CATEGORIA[c["categoria"]]}</span>'
        nome = c.get("nome_contato")
        titulo = html.escape(nome) if nome else html.escape(c["telefono"])
        linhas += f"""
        <a class="conversa" href="/admin/conversa/{html.escape(c['telefono'])}">
          {_avatar_html(nome, c['telefono'])}
          <div class="corpo">
            <div class="top">
              <span class="tel">{titulo}</span>
              <span class="badges"><span class="badge {badge_classe}">{badge_texto}</span>{badges_extra}</span>
            </div>
            <div class="preview">{preview}</div>
          </div>
        </a>
        """

    if not conversas:
        linhas = "<p>Sem conversas aqui.</p>"

    filtros_categoria = "".join(
        f'<a href="/admin/?estado={estado}&categoria={chave}" class="{"ativo" if categoria == chave else ""}">{nome}</a>'
        for chave, nome in [("todas", "Todas"), *NOMES_CATEGORIA.items()]
    )

    return f"""
    <html>
    <head><title>Conversas — Reduz+ Energia</title>{ESTILO}{FAVICON_LINK}
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body>
      {SCRIPT_TEMA}
      <div class="topo">
        <div class="marca">
          <img class="logo" src="{LOGO_URL}" alt="Reduz+ Energia">
          <h1>Conversas Reduz+ Energia</h1>
        </div>
        <div class="topo-direita">
          {_swatches_tema_html()}
          <a class="link-agenda" href="/admin/agenda">📅 Agenda</a>
        </div>
      </div>
      {_relogio_feriados_html()}
      {alertas_html}
      <div class="tabs">
        <a href="/admin/?estado=aberta&categoria={categoria}" class="{'ativo' if not vista and estado == 'aberta' else ''}">Em aberto ({n_abertas})</a>
        <a href="/admin/?estado=tratada&categoria={categoria}" class="{'ativo' if not vista and estado == 'tratada' else ''}">Tratadas ({n_tratadas})</a>
        <a href="/admin/?vista=interesse" class="{'ativo' if vista == 'interesse' else ''}">Interesse numa proposta ({n_interesse})</a>
      </div>
      {'' if vista == 'interesse' else f'<div class="filtros">{filtros_categoria}</div>'}
      {linhas}
      <script>setInterval(function() {{ location.reload(); }}, 20000);</script>
    </body>
    </html>
    """


@router.post("/alertas/{alerta_id}/visto")
async def dispensar_alerta(alerta_id: int, auth: bool = Depends(verificar_password)):
    """Marca um alerta como visto, para deixar de aparecer no painel."""
    await marcar_alerta_visto(alerta_id)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/alertas/marcar-todos")
async def dispensar_todos_alertas(auth: bool = Depends(verificar_password)):
    """Marca todos os alertas pendentes como vistos."""
    await marcar_todos_alertas_vistos()
    return RedirectResponse(url="/admin/", status_code=303)


@router.get("/agenda", response_class=HTMLResponse)
async def agenda(auth: bool = Depends(verificar_password)):
    """Lista as próximas chamadas agendadas pelos clientes."""
    agendamentos = await listar_agendamentos()

    linhas = ""
    for a in agendamentos:
        nome = html.escape(a["nome_cliente"]) if a.get("nome_cliente") else "(nome não indicado)"
        telefone = html.escape(a["telefono"])
        quando = formatar_slot(a["data_hora"])
        informacao = html.escape(a.get("informacao") or "")
        linhas += f"""
        <div class="agendamento">
          <div class="quando">{quando}</div>
          <div class="nome">{nome}</div>
          <div class="tel"><a href="/admin/conversa/{telefone}">{telefone}</a></div>
          <div class="info">{informacao}</div>
          <form method="post" action="/admin/agenda/{a['id']}/cancelar"
                onsubmit="return confirm('Cancelar esta chamada? Também será removida do calendário.')">
            <button type="submit" class="btn-cancelar">Cancelar chamada</button>
          </form>
        </div>
        """

    if not agendamentos:
        linhas = "<p>Sem chamadas agendadas de momento.</p>"

    estado_outlook = ""
    if outlook_configurado():
        ligado = await outlook_esta_ligado()
        if ligado:
            estado_outlook = '<p class="sync-ok">✅ Sincronizado com o Outlook Calendar</p>'
        else:
            estado_outlook = (
                '<p class="sync-aviso">⚠️ Outlook ainda não autorizado — '
                '<a href="/admin/outlook/conectar">clique aqui para ligar</a></p>'
            )

    return f"""
    <html>
    <head><title>Agenda — Reduz+ Energia</title>{ESTILO}{FAVICON_LINK}
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body>
      {SCRIPT_TEMA}
      <a href="/admin/">&larr; Conversas</a>
      <h1>Próximas chamadas agendadas</h1>
      {estado_outlook}
      {linhas}
    </body>
    </html>
    """


@router.get("/outlook/conectar")
async def outlook_conectar(auth: bool = Depends(verificar_password)):
    """Inicia a autorização OAuth com a Microsoft — o utilizador tem de fazer login e aceitar."""
    if not outlook_configurado():
        raise HTTPException(status_code=500, detail="AZURE_CLIENT_ID/SECRET/TENANT_ID não configurados")
    url = await gerar_url_autorizacao()
    return RedirectResponse(url=url, status_code=303)


@router.get("/outlook/callback", response_class=HTMLResponse)
async def outlook_callback(code: str | None = None, error: str | None = None, auth: bool = Depends(verificar_password)):
    """Recebe o redirecionamento da Microsoft depois do login/autorização."""
    if error or not code:
        return f"""
        <html><body>
          <p>Erro ao ligar ao Outlook: {html.escape(error or 'código em falta')}</p>
          <a href="/admin/agenda">&larr; Voltar à agenda</a>
        </body></html>
        """
    sucesso = await concluir_autorizacao(code)
    mensagem = "Outlook ligado com sucesso! ✅" if sucesso else "Não foi possível ligar ao Outlook. Tente novamente."
    return f"""
    <html><body>
      <p>{mensagem}</p>
      <a href="/admin/agenda">&larr; Voltar à agenda</a>
    </body></html>
    """


@router.post("/agenda/{agendamento_id}/cancelar")
async def cancelar_chamada(agendamento_id: int, auth: bool = Depends(verificar_password)):
    """Cancela uma chamada agendada e remove o evento correspondente do calendário (iCloud e/ou Outlook)."""
    cancelado = await cancelar_agendamento(agendamento_id)
    if cancelado:
        await apagar_evento_icloud(agendamento_id)
        await apagar_evento_outlook(cancelado.get("evento_outlook_id"))
        logger.info(f"Chamada cancelada: agendamento {agendamento_id}")
    return RedirectResponse(url="/admin/agenda", status_code=303)


def _formatar_hora(timestamp: datetime | None) -> str:
    """Converte um timestamp UTC guardado na base de dados para hora de Portugal, formatada."""
    if not timestamp:
        return ""
    hora_local = timestamp.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Lisbon"))
    hoje = datetime.now(ZoneInfo("Europe/Lisbon")).date()
    if hora_local.date() == hoje:
        return hora_local.strftime("%H:%M")
    return hora_local.strftime("%d/%m %H:%M")


URL_REGEX = re.compile(r'https?://[^\s<>"]+')
NEGRITO_REGEX = re.compile(r'(?<!\w)\*([^*\n]+)\*(?!\w)')
ITALICO_REGEX = re.compile(r'(?<!\w)_([^_\n]+)_(?!\w)')
RISCADO_REGEX = re.compile(r'(?<!\w)~([^~\n]+)~(?!\w)')
# "Campo: valor" no início de uma linha (ex: "Nome: João") — o rótulo antes
# dos dois pontos fica com destaque intermédio, entre o texto normal e os
# tópicos em *negrito*. Exige pelo menos uma letra, para não apanhar horas
# tipo "14:30" no início de uma linha.
CAMPO_REGEX = re.compile(r'^([^\n:]{1,40}):(?=[ \t])', re.MULTILINE)


def _substituir_campo(m: re.Match) -> str:
    rotulo = m.group(1)
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", rotulo):
        return m.group(0)
    return f'<b class="campo">{rotulo}</b>:'


def _aplicar_markdown_whatsapp(texto_escapado: str) -> str:
    """Converte a formatação do WhatsApp (*negrito*, _itálico_, ~riscado~) em
    HTML, e dá destaque intermédio aos rótulos "Campo:" no início de linha.

    Aplica-se a texto que já passou por html.escape() — os marcadores
    *_~ não são caracteres especiais de HTML, por isso não interferem. A
    deteção de "Campo:" corre primeiro, para não interferir com as tags
    <strong>/<em>/<del> já inseridas nos passos seguintes.
    """
    texto_escapado = CAMPO_REGEX.sub(_substituir_campo, texto_escapado)
    texto_escapado = NEGRITO_REGEX.sub(r"<strong>\1</strong>", texto_escapado)
    texto_escapado = ITALICO_REGEX.sub(r"<em>\1</em>", texto_escapado)
    texto_escapado = RISCADO_REGEX.sub(r"<del>\1</del>", texto_escapado)
    return texto_escapado


def _rotulo_link(url: str) -> str:
    """Rótulo curto para mostrar num botão em vez do URL completo."""
    try:
        dominio = urlparse(url).netloc.removeprefix("www.")
    except ValueError:
        dominio = ""
    return f"🔗 Abrir link ({dominio})" if dominio else "🔗 Abrir link"


def _linkificar(texto: str) -> str:
    """Escapa o texto de uma mensagem, transforma URLs em botões de link, e
    aplica a formatação do WhatsApp — para o texto aparecer no painel
    organizado tal como aparece no WhatsApp do cliente."""
    partes = []
    posicao = 0
    for m in URL_REGEX.finditer(texto):
        antes = html.escape(texto[posicao:m.start()])
        partes.append(_aplicar_markdown_whatsapp(antes))
        url_escapado = html.escape(m.group(0))
        rotulo = html.escape(_rotulo_link(m.group(0)))
        partes.append(f'<a class="link-botao" href="{url_escapado}" target="_blank" rel="noopener">{rotulo}</a>')
        posicao = m.end()
    resto = html.escape(texto[posicao:])
    partes.append(_aplicar_markdown_whatsapp(resto))
    return "".join(partes)


ROTULOS_REMETENTE = {"user": "Cliente", "humano": "Você", "assistant": "Bot"}


def _render_mensagem(msg: dict, telefono: str) -> str:
    """Gera o HTML de uma mensagem, incluindo pré-visualização de ficheiros e hora."""
    classe = "user" if msg["role"] == "user" else ("humano" if msg["role"] == "humano" else "assistant")
    rotulo = ROTULOS_REMETENTE.get(msg["role"], "")
    partes = f'<span class="remetente">{rotulo}</span>' if rotulo else ""

    if msg.get("media_path"):
        nome_arquivo = os.path.basename(msg["media_path"])
        url = f"/admin/media/{nome_arquivo}"
        if msg.get("tipo") == "imagem":
            partes += f'<a href="{url}" target="_blank"><img src="{url}" alt="imagem"></a>'
        else:
            nome_mostrar = html.escape(msg.get("nome_ficheiro") or nome_arquivo)
            partes += f'<a class="ficheiro" href="{url}" target="_blank">📎 {nome_mostrar}</a>'

    if msg["content"]:
        partes += _linkificar(msg["content"])

    partes += f'<small class="hora">{_formatar_hora(msg.get("timestamp"))}</small>'

    # Mensagens enviadas manualmente pelo painel podem ser corrigidas ou
    # apagadas do registo (não afeta o que o cliente já recebeu no WhatsApp)
    if msg["role"] == "humano" and msg.get("id"):
        conteudo_editavel = html.escape(msg["content"] or "")
        partes += f"""
        <div class="msg-acoes">
          <details>
            <summary>✏️ Editar</summary>
            <form class="form-editar" method="post" action="/admin/conversa/{telefono}/mensagem/{msg['id']}/editar">
              <textarea name="texto" rows="2">{conteudo_editavel}</textarea>
              <button type="submit">Guardar</button>
            </form>
          </details>
          <form method="post" action="/admin/conversa/{telefono}/mensagem/{msg['id']}/apagar"
                onsubmit="return confirm('Apagar esta mensagem do registo? Isto não a remove do WhatsApp do cliente, que já a recebeu.')">
            <button type="submit" class="btn-apagar">🗑️ Apagar</button>
          </form>
        </div>
        """

    return f'<div class="msg {classe}" data-msg-id="{msg["id"]}">{partes}</div>'


@router.get("/conversa/{telefono}", response_class=HTMLResponse)
async def ver_conversa(telefono: str, auth: bool = Depends(verificar_password)):
    """Mostra o histórico de uma conversa e permite responder ou trocar o modo/estado."""
    historico = await obtener_historial(telefono, limite=100)
    modo = await obtener_modo(telefono)
    estado = await obtener_estado(telefono)
    categoria = await obtener_categoria(telefono)
    nome = await obtener_nome_contato(telefono)

    mensagens_html = "".join(_render_mensagem(msg, telefono) for msg in historico)
    titulo_pagina = nome or telefono

    return f"""
    <html>
    <head><title>{html.escape(titulo_pagina)} — Reduz+ Energia</title>{ESTILO}{FAVICON_LINK}
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body class="conversa-page">
      {SCRIPT_TEMA}
      <div class="cabecalho-fixo">
        <div class="cabecalho-linha">
          <a class="voltar" href="/admin/">&larr;</a>
          {_avatar_html(nome, telefono)}
          <div class="cabecalho-info">
            <div class="nome">{html.escape(nome) if nome else html.escape(telefono)}</div>
            {f'<div class="tel">{html.escape(telefono)}</div>' if nome else ''}
          </div>
          <details class="opcoes">
            <summary>☰</summary>
            <div class="opcoes-conteudo">
              {f'''<form method="post" action="/admin/conversa/{telefono}/encaminhar"
                     onsubmit="return confirm('Encaminhar esta conversa para o consultor Luis Sequeira ({NUMERO_CONSULTOR})?')">
                <button type="submit" class="btn-consultor">📞 Encaminhar para consultor</button>
              </form>''' if NUMERO_CONSULTOR else ''}

              <div class="toggle">
                <form method="post" action="/admin/conversa/{telefono}/modo">
                  <input type="hidden" name="modo" value="bot">
                  <button type="submit" class="{'ativo' if modo == 'bot' else ''}">Bot responde</button>
                </form>
                <form method="post" action="/admin/conversa/{telefono}/modo">
                  <input type="hidden" name="modo" value="manual">
                  <button type="submit" class="{'ativo' if modo == 'manual' else ''}">Eu respondo</button>
                </form>
                <form method="post" action="/admin/conversa/{telefono}/estado">
                  <input type="hidden" name="estado" value="aberta">
                  <button type="submit" class="{'ativo' if estado == 'aberta' else ''}">Em aberto</button>
                </form>
                <form method="post" action="/admin/conversa/{telefono}/estado">
                  <input type="hidden" name="estado" value="tratada">
                  <button type="submit" class="tratada {'ativo' if estado == 'tratada' else ''}">Tratada</button>
                </form>
              </div>

              <div class="toggle separador">
                {"".join(
                    f'''<form method="post" action="/admin/conversa/{telefono}/categoria">
                          <input type="hidden" name="categoria" value="{chave}">
                          <button type="submit" class="{chave} {'ativo' if categoria == chave else ''}">{nome_cat}</button>
                        </form>'''
                    for chave, nome_cat in NOMES_CATEGORIA.items()
                )}
              </div>
            </div>
          </details>
        </div>
      </div>

      <div id="mensagens" class="mensagens-scroll">{mensagens_html}</div>

      <div class="reply-fixa">
        <form class="reply" method="post" action="/admin/conversa/{telefono}/responder" enctype="multipart/form-data">
          <textarea name="texto" rows="2" placeholder="Escrever resposta..."
                    onkeydown="if(event.key==='Enter' &amp;&amp; !event.shiftKey){{event.preventDefault(); this.form.requestSubmit();}}"></textarea>
          <button type="submit">Enviar</button>
          <input class="anexo" type="file" name="ficheiro">
        </form>
      </div>

      <script>
      (function() {{
        var telefone = {telefono!r};
        var container = document.getElementById('mensagens');

        // Abre sempre já posicionado na mensagem mais recente
        container.scrollTop = container.scrollHeight;

        function ultimoIdAtual() {{
          var nos = container.querySelectorAll('[data-msg-id]');
          if (!nos.length) return 0;
          return parseInt(nos[nos.length - 1].dataset.msgId, 10);
        }}

        var ultimoId = ultimoIdAtual();

        async function verificarNovas() {{
          try {{
            var resp = await fetch('/admin/conversa/' + telefone + '/novas?desde=' + ultimoId);
            if (!resp.ok) return;
            var html = await resp.text();
            if (html.trim()) {{
              container.insertAdjacentHTML('beforeend', html);
              ultimoId = ultimoIdAtual();
              container.scrollTop = container.scrollHeight;
            }}
          }} catch (e) {{}}
        }}

        setInterval(verificarNovas, 4000);
      }})();
      </script>
    </body>
    </html>
    """


@router.get("/conversa/{telefono}/novas", response_class=HTMLResponse)
async def mensagens_novas(telefono: str, desde: int = 0, auth: bool = Depends(verificar_password)):
    """Retorna em HTML as mensagens novas de uma conversa — usado para atualizar a página automaticamente."""
    novas = await obtener_mensagens_novas(telefono, desde)
    return "".join(_render_mensagem(msg, telefono) for msg in novas)


@router.post("/conversa/{telefono}/modo")
async def mudar_modo(telefono: str, modo: str = Form(...), auth: bool = Depends(verificar_password)):
    """Alterna entre modo 'bot' (automático) e 'manual' (respondo eu)."""
    if modo not in ("bot", "manual"):
        raise HTTPException(status_code=400, detail="Modo inválido")
    await establecer_modo(telefono, modo)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/estado")
async def mudar_estado(telefono: str, estado: str = Form(...), auth: bool = Depends(verificar_password)):
    """Alterna entre 'aberta' e 'tratada'."""
    if estado not in ("aberta", "tratada"):
        raise HTTPException(status_code=400, detail="Estado inválido")
    await establecer_estado(telefono, estado)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/encaminhar")
async def encaminhar_consultor(telefono: str, auth: bool = Depends(verificar_password)):
    """Reenvia a conversa completa para o WhatsApp do consultor, manualmente."""
    proveedor = obtener_proveedor()
    historico = await obtener_historial(telefono, limite=100)
    enviado = await notificar_consultor(proveedor, telefono, historico)
    if enviado:
        logger.info(f"Conversa {telefono} encaminhada manualmente para o consultor")
    else:
        logger.warning(f"Falha ao encaminhar conversa {telefono} para o consultor")
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/categoria")
async def mudar_categoria(telefono: str, categoria: str = Form(...), auth: bool = Depends(verificar_password)):
    """Muda a categoria comercial da conversa: sem_categoria, interessado, ganho ou perdido."""
    if categoria not in CATEGORIAS_VALIDAS:
        raise HTTPException(status_code=400, detail="Categoria inválida")
    await establecer_categoria(telefono, categoria)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/responder")
async def responder_manual(
    telefono: str,
    texto: str = Form(""),
    ficheiro: UploadFile | None = File(None),
    auth: bool = Depends(verificar_password),
):
    """Envia uma resposta manual ao cliente — texto, ficheiro, ou ambos."""
    proveedor = obtener_proveedor()

    if ficheiro is not None and ficheiro.filename:
        conteudo = await ficheiro.read()
        mime_type = ficheiro.content_type or mimetypes.guess_type(ficheiro.filename)[0] or "application/octet-stream"
        enviado = await proveedor.enviar_documento(telefono, conteudo, ficheiro.filename, mime_type, legenda=texto)
        if enviado:
            extensao = mimetypes.guess_extension(mime_type) or os.path.splitext(ficheiro.filename)[1]
            nome_local = f"{uuid.uuid4().hex}{extensao}"
            with open(os.path.join(MEDIA_DIR, nome_local), "wb") as f:
                f.write(conteudo)
            tipo = "imagem" if mime_type.startswith("image/") else "documento"
            await guardar_mensaje(
                telefono, "humano", texto, tipo=tipo,
                media_path=os.path.join(MEDIA_DIR, nome_local), nome_ficheiro=ficheiro.filename,
            )
            logger.info(f"Ficheiro enviado manualmente a {telefono}: {ficheiro.filename}")
        else:
            logger.warning(f"Falha ao enviar ficheiro manual a {telefono}")
    elif texto.strip():
        enviado = await proveedor.enviar_mensaje(telefono, texto)
        if enviado:
            await guardar_mensaje(telefono, "humano", texto)
            logger.info(f"Resposta manual a {telefono}: {texto}")
        else:
            logger.warning(f"Falha ao enviar resposta manual a {telefono}")

    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/mensagem/{mensagem_id}/editar")
async def editar_mensagem_manual(
    telefono: str, mensagem_id: int, texto: str = Form(...), auth: bool = Depends(verificar_password)
):
    """Corrige o texto de uma mensagem enviada manualmente (só no registo do painel)."""
    await editar_mensagem(mensagem_id, texto)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/mensagem/{mensagem_id}/apagar")
async def apagar_mensagem_manual(telefono: str, mensagem_id: int, auth: bool = Depends(verificar_password)):
    """Remove do registo do painel uma mensagem enviada manualmente."""
    await apagar_mensagem(mensagem_id)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.get("/media/{nome_arquivo}")
async def obter_media(nome_arquivo: str, auth: bool = Depends(verificar_password)):
    """Serve um ficheiro guardado localmente (recebido ou enviado numa conversa)."""
    caminho = os.path.join(MEDIA_DIR, nome_arquivo)
    caminho_absoluto = os.path.abspath(caminho)
    diretorio_absoluto = os.path.abspath(MEDIA_DIR)
    if not caminho_absoluto.startswith(diretorio_absoluto) or not os.path.isfile(caminho_absoluto):
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado")
    return FileResponse(caminho_absoluto)
