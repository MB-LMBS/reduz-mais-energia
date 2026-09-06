// agent/static/webchat.js — Widget de chat da Reduz+ Energia
//
// Ficheiro único servido pelo servidor (Railway) e incluído em todas as
// páginas do site com uma linha:
//   <script src="https://reduz-mais-energia-production.up.railway.app/static/webchat.js" defer></script>
//
// Vantagem de estar aqui em vez de colado em cada página: qualquer ajuste
// (cores, espaçamento, texto, comportamento) só precisa de uma alteração
// neste ficheiro + deploy, em vez de editar o HTML de cada página do site.
//
// Fala diretamente com o mesmo agente de IA que responde no WhatsApp
// (config/prompts.yaml), através do endpoint /webchat.

(function () {
  var API_URL = "https://reduz-mais-energia-production.up.railway.app/webchat";

  var style = document.createElement("style");
  style.textContent = `
    #reduzmais-chat-wrap, #reduzmais-chat-painel, #reduzmais-chat-painel * {
      font-family: Poppins, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      box-sizing: border-box;
    }
    @keyframes rm-pulso {
      0%   { box-shadow: 0 8px 22px rgba(6,26,85,.4), 0 0 0 0 rgba(53,255,156,.6); }
      70%  { box-shadow: 0 8px 22px rgba(6,26,85,.4), 0 0 0 18px rgba(53,255,156,0); }
      100% { box-shadow: 0 8px 22px rgba(6,26,85,.4), 0 0 0 0 rgba(53,255,156,0); }
    }
    @keyframes rm-baloico {
      0%, 100% { transform: rotate(0deg) translateY(0); }
      20%      { transform: rotate(-9deg) translateY(-2px); }
      40%      { transform: rotate(7deg) translateY(0); }
      60%      { transform: rotate(-4deg) translateY(-1px); }
      80%      { transform: rotate(0deg) translateY(0); }
    }
    @keyframes rm-badge-pulso {
      0%, 100% { transform: scale(1); }
      50%      { transform: scale(1.18); }
    }
    #reduzmais-chat-wrap {
      position: fixed; bottom: 92px; right: 20px; width: 62px; height: 62px; z-index: 999999;
    }
    #reduzmais-chat-bolha {
      position: relative; width: 100%; height: 100%; border-radius: 50%;
      background: linear-gradient(135deg, #35FF9C, #00C2FF);
      border: 3px solid #fff;
      color: #061A55; display: flex; align-items: center; justify-content: center;
      cursor: pointer; transition: transform .15s ease;
      animation: rm-pulso 2.6s ease-out infinite, rm-baloico 4.2s ease-in-out infinite;
      animation-delay: 0s, 1s;
    }
    #reduzmais-chat-bolha:hover { transform: scale(1.08); }
    #reduzmais-chat-wrap.rm-sem-pulso #reduzmais-chat-bolha { animation: none; box-shadow: 0 8px 22px rgba(6,26,85,.4); }
    #reduzmais-chat-badge {
      position: absolute; top: -3px; left: -3px; width: 18px; height: 18px; border-radius: 50%;
      background: #FF3B5C; border: 2px solid #fff; color: #fff; font-size: 10px; font-weight: 700;
      display: flex; align-items: center; justify-content: center; line-height: 1;
      animation: rm-badge-pulso 1.5s ease-in-out infinite;
    }
    #reduzmais-chat-wrap.rm-sem-pulso #reduzmais-chat-badge { display: none; }
    #reduzmais-chat-painel {
      display: none; position: fixed; bottom: 164px; right: 20px;
      width: 370px; max-width: calc(100vw - 40px);
      height: 520px; max-height: calc(100vh - 200px);
      background: #fff; border-radius: 18px;
      box-shadow: 0 12px 40px rgba(6, 26, 85, .35);
      z-index: 999999; flex-direction: column; overflow: hidden;
    }
    #reduzmais-chat-cabecalho {
      background: radial-gradient(circle at 20% 20%, #2F6BE8 0%, #1A47B8 35%, #0C2C86 70%, #061A55 100%);
      color: #fff; padding: 16px 18px; display: flex; justify-content: space-between; align-items: center;
    }
    #reduzmais-chat-titulo { display: flex; flex-direction: column; line-height: 1.2; }
    #reduzmais-chat-titulo strong { font-size: 15px; font-weight: 700; letter-spacing: .3px; }
    #reduzmais-chat-acoes { display: flex; align-items: center; gap: 12px; }
    #reduzmais-chat-nova {
      background: none; border: 1px solid rgba(255,255,255,.5); color: #fff; opacity: .9;
      border-radius: 20px; padding: 5px 12px; font-size: 11px; font-weight: 600; cursor: pointer;
    }
    #reduzmais-chat-nova:hover { opacity: 1; background: rgba(255,255,255,.12); }
    #reduzmais-chat-titulo span { font-size: 10px; font-weight: 600; letter-spacing: 1.5px; color: #35FF9C; }
    #reduzmais-chat-fechar {
      cursor: pointer; font-size: 20px; line-height: 1; color: #fff; opacity: .8; background: none; border: none;
    }
    #reduzmais-chat-fechar:hover { opacity: 1; }
    #reduzmais-chat-mensagens { flex: 1; overflow-y: auto; padding: 18px 16px; font-size: 14.5px; background: #F4F7FB; }
    #reduzmais-chat-opcoes { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 16px 14px; background: #F4F7FB; }
    .rm-chip {
      border: 1.5px solid #00C2FF; color: #0C2C86; background: #fff; border-radius: 20px;
      padding: 7px 15px; font-size: 13px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block;
    }
    .rm-chip:hover { background: #E8FBFF; }
    #reduzmais-chat-form { display: flex; border-top: 1px solid #E5E9F0; background: #fff; }
    #reduzmais-chat-input {
      flex: 1; border: none; padding: 16px; font-size: 14.5px; outline: none; color: #061A55; background: transparent;
    }
    #reduzmais-chat-input::placeholder { color: #9AA5B8; }
    #reduzmais-chat-enviar {
      background: linear-gradient(90deg, #35FF9C, #00C2FF); color: #061A55; border: none;
      padding: 0 22px; cursor: pointer; font-size: 14px; font-weight: 700;
    }
    .rm-balao { max-width: 84%; margin: 10px 0; padding: 12px 16px; border-radius: 14px; line-height: 1.65; white-space: pre-wrap; }
    .rm-balao.user { margin-left: auto; background: linear-gradient(135deg, #35FF9C, #00C2FF); color: #061A55; font-weight: 500; }
    .rm-balao.bot { background: #fff; border: 1px solid #E5E9F0; color: #17213D; }
    .rm-a-escrever { color: #9AA5B8; font-size: 13px; margin: 10px 0; }
  `;
  document.head.appendChild(style);

  document.body.insertAdjacentHTML("beforeend", `
    <div id="reduzmais-chat-wrap">
      <button id="reduzmais-chat-bolha" aria-label="Abrir chat da Reduz+ Energia">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M4 4h16v12H7.2L4 19.2V4z" fill="#061A55"/>
        </svg>
      </button>
      <div id="reduzmais-chat-badge">1</div>
    </div>

    <div id="reduzmais-chat-painel">
      <div id="reduzmais-chat-cabecalho">
        <div id="reduzmais-chat-titulo"><strong>REDUZ+</strong><span>ENERGIA</span></div>
        <div id="reduzmais-chat-acoes">
          <button type="button" id="reduzmais-chat-nova" aria-label="Iniciar nova conversa">Nova conversa</button>
          <button id="reduzmais-chat-fechar" aria-label="Fechar chat">&times;</button>
        </div>
      </div>
      <div id="reduzmais-chat-mensagens"></div>
      <div id="reduzmais-chat-opcoes"></div>
      <form id="reduzmais-chat-form">
        <input id="reduzmais-chat-input" type="text" placeholder="Escreva a sua pergunta..." autocomplete="off">
        <button type="submit" id="reduzmais-chat-enviar">Enviar</button>
      </form>
    </div>
  `);

  var wrap = document.getElementById("reduzmais-chat-wrap");
  var bolha = document.getElementById("reduzmais-chat-bolha");
  var painel = document.getElementById("reduzmais-chat-painel");
  var fechar = document.getElementById("reduzmais-chat-fechar");
  var novaConversaBtn = document.getElementById("reduzmais-chat-nova");
  var mensagensEl = document.getElementById("reduzmais-chat-mensagens");
  var opcoesEl = document.getElementById("reduzmais-chat-opcoes");
  var form = document.getElementById("reduzmais-chat-form");
  var input = document.getElementById("reduzmais-chat-input");

  var HISTORICO_URL = "https://reduz-mais-energia-production.up.railway.app/webchat/historico";

  var aberto = false;
  var MENSAGEM_BOAS_VINDAS =
    "\u{1F44B} Olá! Sou o assistente virtual da Reduz+ Energia. Posso ajudar a poupar na " +
    "fatura de eletricidade, gás natural, solar ou armazenamento de energia. Em " +
    "que posso ajudar?";

  function pararPulso() {
    wrap.classList.add("rm-sem-pulso");
  }

  // Enquanto o painel está com display:none (escondido), o browser não
  // calcula a altura do conteúdo — por isso scrollTop=scrollHeight não
  // tem efeito nenhum nessa altura. Chamar isto sempre que o painel abre
  // (depois do display passar a "flex") garante que a última mensagem
  // fica sempre visível, sem o visitante ter de arrastar a barra.
  function rolarParaFim() {
    requestAnimationFrame(function () {
      mensagensEl.scrollTop = mensagensEl.scrollHeight;
    });
  }

  function abrirPainel() {
    aberto = true;
    painel.style.display = "flex";
    rolarParaFim();
  }

  function abrirComBoasVindas() {
    abrirPainel();
    pararPulso();
    adicionarMensagem(MENSAGEM_BOAS_VINDAS, "bot");
  }

  function obterSessionId() {
    try {
      var id = localStorage.getItem("reduzmais_chat_session");
      if (!id) {
        id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
        localStorage.setItem("reduzmais_chat_session", id);
      }
      return id;
    } catch (e) {
      return String(Date.now()) + Math.random().toString(16).slice(2);
    }
  }

  function gerarNovoSessionId() {
    var id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
    try { localStorage.setItem("reduzmais_chat_session", id); } catch (e) {}
    return id;
  }

  function iniciarNovaConversa() {
    sessionId = gerarNovoSessionId();
    mensagensEl.innerHTML = "";
    limparOpcoes();
    abrirComBoasVindas();
  }

  var sessionId = obterSessionId();

  // Ao carregar a página, tenta restaurar a conversa já guardada no
  // servidor para esta sessão — sem isto, o ecrã "esquecia" a conversa a
  // cada refresh, mas o bot (no servidor) continuava a lembrar-se de tudo,
  // o que confundia o visitante.
  fetch(HISTORICO_URL + "?session_id=" + encodeURIComponent(sessionId))
    .then(function (r) { return r.json(); })
    .then(function (dados) {
      var mensagens = (dados && dados.mensagens) || [];
      if (mensagens.length > 0) {
        mensagens.forEach(function (m) {
          adicionarMensagem(m.content, m.role === "user" ? "user" : "bot");
        });
        return;
      }
      mostrarBoasVindasAutomaticas();
    })
    .catch(function () {
      mostrarBoasVindasAutomaticas();
    });

  function mostrarBoasVindasAutomaticas() {
    try {
      if (sessionStorage.getItem("reduzmais_chat_aberto_automaticamente")) return;
      sessionStorage.setItem("reduzmais_chat_aberto_automaticamente", "1");
    } catch (e) {}
    setTimeout(function () {
      if (!aberto) abrirComBoasVindas();
    }, 3000);
  }

  function adicionarMensagem(texto, autor) {
    var balao = document.createElement("div");
    balao.textContent = texto;
    balao.className = "rm-balao " + (autor === "user" ? "user" : "bot");
    mensagensEl.appendChild(balao);
    mensagensEl.scrollTop = mensagensEl.scrollHeight;
    rolarParaFim();
  }

  function limparOpcoes() {
    opcoesEl.innerHTML = "";
  }

  function mostrarOpcoes(opcoes) {
    limparOpcoes();
    (opcoes || []).forEach(function (texto) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = texto;
      btn.className = "rm-chip";
      btn.onclick = function () { enviarMensagem(texto); };
      opcoesEl.appendChild(btn);
    });
  }

  function mostrarLinkBotao(linkBotao) {
    limparOpcoes();
    if (!linkBotao) return;
    var a = document.createElement("a");
    a.href = linkBotao.url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = linkBotao.texto_botao;
    a.className = "rm-chip";
    opcoesEl.appendChild(a);
  }

  function mostrarLinksMultiplos(links) {
    limparOpcoes();
    (links || []).forEach(function (link) {
      var a = document.createElement("a");
      a.href = link.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = link.texto_botao;
      a.className = "rm-chip";
      opcoesEl.appendChild(a);
    });
  }

  function enviarMensagem(texto) {
    texto = (texto || "").trim();
    if (!texto) return;

    adicionarMensagem(texto, "user");
    limparOpcoes();
    input.value = "";

    var aEscrever = document.createElement("div");
    aEscrever.id = "reduzmais-chat-a-escrever";
    aEscrever.className = "rm-a-escrever";
    aEscrever.textContent = "A escrever...";
    mensagensEl.appendChild(aEscrever);
    mensagensEl.scrollTop = mensagensEl.scrollHeight;

    fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, mensagem: texto }),
    })
      .then(function (r) { return r.json(); })
      .then(function (dados) {
        var el = document.getElementById("reduzmais-chat-a-escrever");
        if (el) el.remove();

        adicionarMensagem(dados.resposta || "Desculpe, não consegui responder agora.", "bot");
        if (dados.opcoes) mostrarOpcoes(dados.opcoes);
        else if (dados.link_botao) mostrarLinkBotao(dados.link_botao);
        else if (dados.links_multiplos) mostrarLinksMultiplos(dados.links_multiplos);
      })
      .catch(function () {
        var el = document.getElementById("reduzmais-chat-a-escrever");
        if (el) el.remove();
        adicionarMensagem("Não foi possível ligar ao assistente. Tente novamente dentro de instantes.", "bot");
      });
  }

  bolha.addEventListener("click", function () {
    if (!aberto && !mensagensEl.hasChildNodes()) {
      abrirComBoasVindas();
    } else if (!aberto) {
      abrirPainel();
      pararPulso();
    } else {
      aberto = false;
      painel.style.display = "none";
    }
    if (aberto) input.focus();
  });

  fechar.addEventListener("click", function () {
    aberto = false;
    painel.style.display = "none";
  });

  novaConversaBtn.addEventListener("click", function () {
    iniciarNovaConversa();
    input.focus();
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    enviarMensagem(input.value);
  });
})();
