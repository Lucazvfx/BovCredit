/* Orkavyn UI — dashboard: tema, formulário do ciclo/estresse e parecer em abas.
   Regra da skill orkavyn-ui: NENHUM innerHTML com dado vindo da API ou do
   usuário. Tudo aqui é montado com createElement/textContent. */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const CAMPOS_ESTRESSE = [
    ["preco_arroba_base", "preço da arroba"],
    ["custo_reposicao_anual", "custo de reposição"],
    ["custo_suplementacao_anual", "custo de suplementação"],
  ];
  const CENARIOS = [
    ["queda_arroba", "Queda da arroba"],
    ["alta_reposicao", "Alta da reposição"],
    ["alta_suplementacao", "Alta da suplementação"],
    ["seca_severa", "Seca severa"],
    ["tesoura_margem_moderada", "Tesoura de margem (moderada)"],
    ["tesoura_margem_severa", "Tesoura de margem (severa)"],
  ];
  const VEREDITO = {
    aprovar: ["APROVAR", "approve"],
    ressalva: ["APROVAR COM RESSALVA", "warn"],
    negar: ["NEGAR", "reject"],
  };

  // ── utilidades ─────────────────────────────────────────────────────────
  const fmtBRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
  const fmtBRL2 = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtCompact = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
  const fmtNum2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtNum1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  const num = (v) => (v === null || v === undefined || v === "" ? null : (Number.isFinite(Number(v)) ? Number(v) : null));
  const brl = (v) => (num(v) === null ? "—" : fmtBRL.format(num(v)));
  const brl2 = (v) => (num(v) === null ? "—" : fmtBRL2.format(num(v)));
  const dscr = (v) => (num(v) === null ? "—" : fmtNum2.format(num(v)));

  function el(tag, opts, children) {
    const n = document.createElement(tag);
    const o = opts || {};
    if (o.cls) n.className = o.cls;
    if (o.text !== undefined && o.text !== null) n.textContent = String(o.text);
    if (o.attrs) Object.keys(o.attrs).forEach((k) => n.setAttribute(k, String(o.attrs[k])));
    (children || []).forEach((c) => { if (c) n.appendChild(c); });
    return n;
  }
  function svg(tag, attrs, text) {
    const n = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach((k) => n.setAttribute(k, String(attrs[k])));
    if (text !== undefined) n.textContent = String(text);
    return n;
  }
  function card(titulo, filhos) {
    return el("section", { cls: "od-card" }, [el("h3", { cls: "od-card__title", text: titulo })].concat(filhos));
  }

  // ── tema ───────────────────────────────────────────────────────────────
  const TEMA_CHAVE = "orkavyn_theme";
  function temaAtual() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  function aplicarTema(tema, persistir) {
    document.documentElement.setAttribute("data-theme", tema);
    if (persistir) { try { localStorage.setItem(TEMA_CHAVE, tema); } catch (e) { /* modo privado */ } }
    document.querySelectorAll("img.ork-brand__mark").forEach((img) => {
      img.setAttribute("src", tema === "dark" ? "/static/img/logo-dark.svg" : "/static/img/logo-light.svg");
    });
    const btn = document.getElementById("od-theme-toggle");
    if (btn) {
      btn.setAttribute("aria-pressed", tema === "dark" ? "true" : "false");
      const rotulo = tema === "dark" ? "Claro" : "Escuro";
      btn.replaceChildren(
        el("span", { cls: "od-theme-toggle__label", text: rotulo })
      );
    }
  }
  function iniciarTema() {
    const hdr = document.querySelector(".ork-context-header .hdr-r");
    if (hdr && !document.getElementById("od-theme-toggle")) {
      const btn = el("button", { cls: "od-theme-toggle", attrs: { id: "od-theme-toggle", type: "button", "aria-label": "Alternar tema claro/escuro" } });
      btn.addEventListener("click", () => aplicarTema(temaAtual() === "dark" ? "light" : "dark", true));
      // Ordem da topbar: cotações, tema, menu do usuário.
      hdr.insertBefore(btn, hdr.querySelector(".od-user"));
    }
    aplicarTema(temaAtual(), false);
  }

  // ── menus popover (usuário na topbar, "Mais" no dock) ──────────────────
  function fecharMenus(exceto) {
    document.querySelectorAll("[data-od-menu]").forEach((b) => {
      const menu = document.getElementById(b.dataset.odMenu);
      if (!menu || menu === exceto) return;
      menu.hidden = true;
      b.setAttribute("aria-expanded", "false");
    });
  }
  function iniciarMenus() {
    document.querySelectorAll("[data-od-menu]").forEach((b) => {
      const menu = document.getElementById(b.dataset.odMenu);
      if (!menu) return;
      b.addEventListener("click", () => {
        const abrir = menu.hidden;
        fecharMenus(menu);
        menu.hidden = !abrir;
        b.setAttribute("aria-expanded", abrir ? "true" : "false");
      });
      // Escolher um item (ou clicar fora do botão) fecha o menu.
      menu.addEventListener("click", (e) => { if (e.target.closest(".od-menu__item")) fecharMenus(null); });
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest("[data-od-menu], .od-menu")) fecharMenus(null);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const aberto = document.querySelector("[data-od-menu][aria-expanded='true']");
      fecharMenus(null);
      if (aberto) aberto.focus();
    });
  }

  // ── saudação por hora do dia (o nome vem renderizado no servidor) ──────
  function iniciarSaudacao() {
    const alvo = document.getElementById("od-greeting");
    if (!alvo) return;
    const h = new Date().getHours();
    alvo.textContent = h < 12 ? "Bom dia" : (h < 18 ? "Boa tarde" : "Boa noite");
  }

  // ── formulário: sistema produtivo (4 cards, desmarcável) ───────────────
  function definirSistema(valor) {
    const sel = document.getElementById("sistema_produtivo");
    if (sel) sel.value = valor;
    document.querySelectorAll(".od-sys").forEach((b) => {
      b.setAttribute("aria-pressed", b.dataset.valor === valor ? "true" : "false");
    });
    const limpar = document.getElementById("od-sys-clear");
    if (limpar) limpar.hidden = !valor;
    if (valor) revelarCampo("sistema_produtivo");
    atualizarBlocos();
    ["frequencia_pagamento", "capital_giro_inicial"].forEach((id) => {
      const campo = document.getElementById(id);
      if (!campo) return;
      campo.disabled = !valor;
      const wrap = campo.closest(".field");
      if (wrap) wrap.classList.toggle("od-field-off", !valor);
    });
  }
  function iniciarSistemas() {
    document.querySelectorAll(".od-sys").forEach((b) => {
      b.addEventListener("click", () => {
        const atual = document.getElementById("sistema_produtivo").value;
        definirSistema(atual === b.dataset.valor ? "" : b.dataset.valor);
      });
    });
    const limpar = document.getElementById("od-sys-clear");
    if (limpar) limpar.addEventListener("click", () => definirSistema(""));
    definirSistema(document.getElementById("sistema_produtivo")
      ? document.getElementById("sistema_produtivo").value : "");
  }

  // ── "Mais opções ▾" da composição por faixa etária ─────────────────────
  function iniciarMaisOpcoes() {
    const d = document.getElementById("od-more-faixa");
    if (!d) return;
    d.addEventListener("click", (e) => {
      if (e.target.closest(".od-more__item")) { d.open = false; d.querySelector("summary").focus(); }
    });
    d.addEventListener("focusout", (e) => { if (d.open && e.relatedTarget && !d.contains(e.relatedTarget)) d.open = false; });
    document.addEventListener("click", (e) => { if (d.open && !d.contains(e.target)) d.open = false; });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && d.open && d.contains(document.activeElement)) { d.open = false; d.querySelector("summary").focus(); }
    });
  }

  // ── aviso do desembolso padrão (GEP) some quando o produtor já informou ─
  function iniciarAvisoGep() {
    const campo = document.getElementById("c-desemb");
    const aviso = document.getElementById("aviso-gep-padrao");
    if (!campo || !aviso) return;
    const atualizar = () => { aviso.hidden = campo.value.trim() !== ""; };
    campo.addEventListener("input", atualizar);
    atualizar();
  }

  // ── blocos opcionais: recolhíveis, com estado na própria barra ─────────
  // Aberto de saída se já houver dado; recolhido (e anunciado) se vazio.
  const BLOCOS_OPCIONAIS = {
    "od-b2": () => {
      const sis = (document.getElementById("sistema_produtivo") || {}).value || "";
      return sis ? { n: 1, de: 1, txt: "Informado" } : { n: 0, de: 1, txt: "Não informado" };
    },
    "od-b3": () => {
      const n = CAMPOS_ESTRESSE.filter(([id]) => {
        const e = document.getElementById(id);
        return e && e.value.trim() !== "";
      }).length;
      const de = CAMPOS_ESTRESSE.length;
      return { n, de, txt: n === 0 ? "Não informado" : (n === de ? "Completo" : "Incompleto " + n + "/" + de) };
    },
  };
  function definirBloco(bloco, aberto) {
    const corpo = document.getElementById(bloco.id + "-body");
    const btn = bloco.querySelector(".od-block__toggle");
    if (!corpo || !btn) return;
    corpo.hidden = !aberto;
    btn.setAttribute("aria-expanded", aberto ? "true" : "false");
    btn.querySelector(".od-block__caret").textContent = aberto ? "▴" : "▾";
  }
  function atualizarEstresse() {
    const campos = CAMPOS_ESTRESSE.map(([id, rotulo]) => ({ e: document.getElementById(id), rotulo }));
    const vazios = campos.filter((c) => c.e && c.e.value.trim() === "");
    const parcial = vazios.length > 0 && vazios.length < campos.length;
    campos.forEach((c) => {
      if (!c.e) return;
      const wrap = c.e.closest(".field");
      const falta = parcial && c.e.value.trim() === "";
      const ok = c.e.value.trim() !== "";
      if (wrap) {
        wrap.classList.toggle("od-field--missing", falta);
        wrap.classList.toggle("od-field--ok", ok && parcial);
      }
      if (falta) c.e.setAttribute("aria-invalid", "true"); else c.e.removeAttribute("aria-invalid");
    });
    const aviso = document.getElementById("od-estresse-status");
    if (aviso) {
      aviso.hidden = !parcial;
      aviso.textContent = parcial ? "Faltam " + vazios.length + " de " + campos.length + ": " + vazios.map((c) => c.rotulo).join(", ") + "." : "";
    }
  }
  function atualizarBlocos() {
    Object.keys(BLOCOS_OPCIONAIS).forEach((id) => {
      const bloco = document.getElementById(id);
      const chip = bloco && bloco.querySelector(".od-block__status");
      if (!chip) return;
      const st = BLOCOS_OPCIONAIS[id]();
      chip.textContent = st.txt;
      chip.classList.toggle("is-ok", st.n === st.de);
      chip.classList.toggle("is-warn", st.n > 0 && st.n < st.de);
    });
    atualizarEstresse();
  }
  function iniciarBlocosOpcionais() {
    Object.keys(BLOCOS_OPCIONAIS).forEach((id) => {
      const bloco = document.getElementById(id);
      const head = bloco && bloco.querySelector(".od-block__head");
      if (!head || !document.getElementById(id + "-body")) return;
      const btn = el("button", { cls: "od-block__toggle", attrs: { type: "button", "aria-controls": id + "-body", "aria-expanded": "true", "aria-describedby": id + "-title" } }, [
        el("span", { cls: "od-block__status" }),
        el("span", { text: "▴", cls: "od-block__caret", attrs: { "aria-hidden": "true" } }),
      ]);
      btn.addEventListener("click", () => definirBloco(bloco, btn.getAttribute("aria-expanded") !== "true"));
      head.appendChild(btn);
      bloco.addEventListener("input", atualizarBlocos);
      bloco.addEventListener("click", () => setTimeout(atualizarBlocos, 0));
    });
    atualizarBlocos();
    Object.keys(BLOCOS_OPCIONAIS).forEach((id) => {
      const bloco = document.getElementById(id);
      if (bloco) definirBloco(bloco, BLOCOS_OPCIONAIS[id]().n > 0);
    });
  }
  // Campo com erro dentro de bloco recolhido: abre antes de rolar/focar.
  function revelarCampo(id) {
    const campo = document.getElementById(id);
    const bloco = campo && campo.closest(".od-block--opt");
    if (bloco) definirBloco(bloco, true);
  }

  // ── payload: tipagem estrita, vazios omitidos ──────────────────────────
  // Devolve {campos} para o corpo de /api/classificar ou {erro, campo}.
  // Número vira Number(); campo vazio não entra no JSON; o trio do estresse
  // só vai completo (o servidor recusa envio parcial com 400).
  function lerCamposNovos() {
    const campos = {};
    const sistema = (document.getElementById("sistema_produtivo") || {}).value || "";
    if (sistema) {
      campos.sistema_produtivo = sistema;
      campos.frequencia_pagamento = document.getElementById("frequencia_pagamento").value || "mensal";
      const giroEl = document.getElementById("capital_giro_inicial");
      if (giroEl && giroEl.validity && giroEl.validity.badInput) {
        return { erro: "Capital de giro inicial: valor numérico inválido.", campo: "capital_giro_inicial" };
      }
      const giroRaw = giroEl ? giroEl.value.trim() : "";
      if (giroRaw !== "") {
        const giro = Number(giroRaw);
        if (!Number.isFinite(giro) || giro < 0) {
          return { erro: "Capital de giro inicial deve ser um número maior ou igual a zero.", campo: "capital_giro_inicial" };
        }
        campos.capital_giro_inicial = giro;
      }
    }
    for (const [id, rotulo] of CAMPOS_ESTRESSE) {
      const e = document.getElementById(id);
      if (e && e.validity && e.validity.badInput) {
        return { erro: "Estresse do boi: " + rotulo + " inválido.", campo: id };
      }
    }
    const brutos = CAMPOS_ESTRESSE.map(([id, rotulo]) => {
      const e = document.getElementById(id);
      return { id, rotulo, raw: e ? e.value.trim() : "" };
    });
    const preenchidos = brutos.filter((b) => b.raw !== "");
    if (preenchidos.length && preenchidos.length < brutos.length) {
      const faltam = brutos.filter((b) => b.raw === "");
      return {
        erro: "Estresse do boi: preencha os três campos juntos (faltando " + faltam.map((b) => b.rotulo).join(", ") + ").",
        campo: faltam[0].id,
      };
    }
    for (const b of preenchidos) {
      const n = Number(b.raw);
      const minimoOk = b.id === "preco_arroba_base" ? n > 0 : n >= 0;
      if (!Number.isFinite(n) || !minimoOk) {
        return { erro: "Estresse do boi: " + b.rotulo + " inválido.", campo: b.id };
      }
      campos[b.id] = n;
    }
    return { campos };
  }

  // ── parecer: hero + banner + abas ──────────────────────────────────────
  function kpi(label, valor, sub, vazio) {
    return el("div", { cls: "od-kpi" + (vazio ? " od-kpi--empty" : "") }, [
      el("div", { cls: "od-kpi__label", text: label }),
      el("div", { cls: "od-kpi__value", text: valor }),
      el("div", { cls: "od-kpi__sub", text: sub }),
    ]);
  }
  function rotuloMes(ciclo, mes) {
    const m = (ciclo.meses || []).find((r) => r.mes === mes);
    return m && m.rotulo ? String(m.rotulo) : String(mes);
  }

  // Principais ressalvas na primeira dobra: justificativa da conclusão +
  // avisos do estresse (máx. 3). O detalhe completo continua nas abas.
  function ressalvasHero(parecer) {
    const c = parecer.conclusao || {};
    const est = parecer.estresse_pecuario || null;
    const itens = [];
    if (c.justificativa && c.recomendacao !== "aprovar") itens.push(String(c.justificativa));
    if (est && est.disponivel && Array.isArray(est.avisos)) est.avisos.forEach((t) => itens.push(String(t)));
    if (!itens.length && !c.recomendacao) return null;
    return el("div", { cls: "od-hero__notes" }, [
      el("div", { cls: "od-hero__notes-title", text: "Principais ressalvas" }),
      itens.length
        ? el("ul", { cls: "od-hero__notes-list" }, itens.slice(0, 3).map((t) => el("li", { text: t })))
        : el("div", { cls: "od-hero__notes-empty", text: "—" }),
    ]);
  }

  function montarHero(parecer) {
    const c = parecer.conclusao || {};
    const ciclo = parecer.ciclo_pecuario || null;
    const est = parecer.estresse_pecuario || null;
    const v = VEREDITO[c.recomendacao];
    const dscrMin = c.dscr_minimo !== undefined && c.dscr_minimo !== null ? c.dscr_minimo : c.dscr;
    const credMax = num(c.capacidade_maxima);

    const badge = el("span", {
      cls: "od-badge od-badge--" + (v ? v[1] : "neutral"),
      text: c.nivel_recomendacao_label || (v ? v[0] : "Sem solicitação de crédito"),
    });

    // Mini-KPI 1 — ponto de ruptura (DSCR 1,00)
    let k1;
    const rup = est && est.disponivel && est.ponto_ruptura_arroba ? est.ponto_ruptura_arroba.ressalva : null;
    if (rup && rup.status === "sem_divida") {
      k1 = kpi("Ponto de ruptura (@)", "—", "Sem dívida: não se aplica", true);
    } else if (rup && num(rup.preco_minimo) !== null) {
      k1 = kpi("Ponto de ruptura (@)", brl2(rup.preco_minimo) + "/@",
        rup.em_ruptura ? "Já em ruptura na base" : "DSCR 1,00 · base " + brl2(rup.preco_base) + "/@", false);
    } else {
      k1 = kpi("Ponto de ruptura (@)", "—", "Informe o estresse do boi", true);
    }
    // Mini-KPI 2 — vale de caixa 12m
    let k2;
    if (ciclo && ciclo.disponivel && num(ciclo.vale_caixa) !== null) {
      const vale = num(ciclo.vale_caixa);
      k2 = kpi("Vale de caixa (12m)", brl(vale),
        vale < 0 && ciclo.mes_vale !== null && ciclo.mes_vale !== undefined
          ? "Pior ponto em " + rotuloMes(ciclo, ciclo.mes_vale) : "Sem saldo negativo", false);
    } else {
      k2 = kpi("Vale de caixa (12m)", "—", "Informe o sistema produtivo", true);
    }
    // Mini-KPI 3 — prazo: quantos anos do prazo foram avaliados e qual o crítico
    const nAnos = num(c.anos_avaliados);
    const k4 = nAnos !== null && nAnos > 0
      ? kpi("Prazo avaliado", nAnos + (nAnos === 1 ? " ano" : " anos"),
        c.ano_critico ? "Ano crítico: " + c.ano_critico : "Sem ano crítico", false)
      : kpi("Prazo avaliado", "—", "Indisponível para este parecer", true);

    // Sem crédito ativo (recomendacao nula) não há DSCR, crédito máximo, ruptura
    // nem prazo: o card vazio com "—" só ocupa a primeira dobra.
    const creditoAtivo = !!c.recomendacao;
    const kpis = creditoAtivo ? [k1, k2, k4] : [];

    return el("section", { cls: "od-hero", attrs: { "aria-label": "Resumo do parecer de crédito" } }, [
      el("div", { cls: "od-hero__top" }, [el("span", { cls: "od-eyebrow", text: "Parecer de crédito" }), badge]),
      creditoAtivo ? el("div", { cls: "od-hero__figures" }, [
        el("div", {}, [
          el("div", { cls: "od-fig__label", text: "DSCR mínimo" }),
          el("div", { cls: "od-fig__value", text: dscr(dscrMin) }),
          el("div", { cls: "od-fig__sub", text: c.ano_critico ? "ano crítico " + c.ano_critico : "ano 1" }),
        ]),
        el("div", {}, [
          el("div", { cls: "od-fig__label", text: "Crédito máximo" }),
          el("div", { cls: "od-fig__value", text: credMax !== null && credMax > 0 ? brl(credMax) : "—" }),
          el("div", { cls: "od-fig__sub", text: "capacidade de pagamento" }),
        ]),
      ]) : null,
      kpis.length ? el("div", { cls: "od-kpis" }, kpis) : null,
      ressalvasHero(parecer),
    ]);
  }

  function montarBanners(parecer) {
    const out = [];
    const ciclo = parecer.ciclo_pecuario || null;
    const est = parecer.estresse_pecuario || null;
    const rup = est && est.disponivel && est.ponto_ruptura_arroba ? est.ponto_ruptura_arroba.ressalva : null;

    if (rup && rup.em_ruptura === true && num(rup.preco_minimo) !== null) {
      out.push(el("div", { cls: "od-banner od-banner--reject", attrs: { role: "alert" } }, [
        el("div", { cls: "od-banner__title", text: "Operação já em ruptura na base" }),
        el("div", {
          cls: "od-banner__text",
          text: "Com a arroba a " + brl2(rup.preco_base) + ", o DSCR já está no ou abaixo de " + dscr(rup.dscr_alvo) +
            " (mínimo de " + brl2(rup.preco_minimo) + "/@). Veja a aba Estresse do Boi.",
        }),
      ]));
    }
    if (ciclo && ciclo.disponivel && ciclo.quebra_caixa_com_dscr_ok === true) {
      const rec = ciclo.recomendacao;
      let texto;
      if (rec && rec.melhora_vale) {
        texto = "Pagamento " + rec.estrutura_recomendada + " nos meses de pico de entrada " +
          (rec.elimina_vale ? "elimina" : "reduz") + " o vale (de " + brl(rec.vale_mensal) +
          "), com o mesmo serviço anual e sem juros adicionais — cotar a nova taxa com o credor.";
      } else if (rec) {
        texto = "Nenhuma estrutura semestral/anual melhora o vale: manter mensal e cobrir o vale com capital de giro.";
      } else {
        texto = "A parcela neste calendário gera meses de déficit que a operação sozinha não teria.";
      }
      out.push(el("div", { cls: "od-banner od-banner--warn", attrs: { role: "alert" } }, [
        el("div", { cls: "od-banner__title", text: "DSCR anual aprovado, mas o caixa quebra na entressafra" }),
        el("div", { cls: "od-banner__text", text: texto }),
      ]));
    }
    return out;
  }

  // gráfico de barras do saldo acumulado (verde ≥ 0, vermelho < 0)
  function graficoSaldo(meses) {
    const W = 720, H = 240, padL = 62, padR = 10, padT = 14, padB = 28;
    const vals = meses.map((m) => num(m.saldo_acumulado) || 0);
    const max = Math.max(0, ...vals), min = Math.min(0, ...vals);
    const span = max - min || 1;
    const y = (v) => padT + ((max - v) / span) * (H - padT - padB);
    const slot = (W - padL - padR) / meses.length;
    const bw = slot * 0.6;
    const s = svg("svg", { class: "od-chart", viewBox: "0 0 " + W + " " + H, role: "img",
      "aria-label": "Saldo de caixa acumulado nos 12 meses; meses negativos em vermelho" });
    [max, 0, min].filter((v, i, a) => a.indexOf(v) === i).forEach((v) => {
      s.appendChild(svg("line", { class: v === 0 ? "od-axis" : "od-grid-line", x1: padL, x2: W - padR, y1: y(v), y2: y(v) }));
      s.appendChild(svg("text", { x: padL - 8, y: y(v) + 4, "text-anchor": "end" }, fmtCompact.format(v)));
    });
    meses.forEach((m, i) => {
      const v = vals[i];
      const x = padL + i * slot + (slot - bw) / 2;
      const top = Math.min(y(v), y(0));
      const bar = svg("rect", { class: v < 0 ? "od-bar-neg" : "od-bar-pos", x, y: top, width: bw, height: Math.max(Math.abs(y(v) - y(0)), 1), rx: 2 });
      bar.appendChild(svg("title", {}, (m.rotulo || m.mes) + ": " + brl(v) + (v < 0 ? " (déficit)" : "")));
      s.appendChild(bar);
      s.appendChild(svg("text", { x: x + bw / 2, y: H - 8, "text-anchor": "middle" }, m.rotulo || m.mes));
    });
    return s;
  }

  function tabelaCiclo(meses) {
    const cab = ["Mês", "Entradas", "Saídas", "Parcela", "Saldo do mês", "Saldo acumulado"];
    const thead = el("thead", {}, [el("tr", {}, cab.map((t) => el("th", { text: t, attrs: { scope: "col" } })))]);
    const tbody = el("tbody", {}, meses.map((m) => {
      const acum = num(m.saldo_acumulado) || 0;
      const mesSaldo = num(m.saldo_mensal) || 0;
      return el("tr", {}, [
        el("td", { text: m.rotulo || m.mes }),
        el("td", { text: brl(m.entradas) }),
        el("td", { text: brl(m.saidas_operacionais) }),
        el("td", { text: brl(m.servico_divida) }),
        el("td", { text: brl(mesSaldo), cls: mesSaldo < 0 ? "od-neg" : "" }),
        el("td", { text: brl(acum), cls: acum < 0 ? "od-neg" : "" }),
      ]);
    }));
    return el("div", { cls: "od-table-wrap" }, [el("table", { cls: "od-table" }, [thead, tbody])]);
  }

  function painelCiclo(parecer) {
    const c = parecer.ciclo_pecuario;
    if (!c) {
      return [el("div", { cls: "od-card od-empty", text: "Ciclo pecuário não informado. Escolha o sistema produtivo no formulário (bloco 2) para projetar o caixa mês a mês." })];
    }
    if (!c.disponivel) {
      return [el("div", { cls: "od-card od-empty", text: c.motivo || "Fluxo sazonal indisponível." })];
    }
    const meses = Array.isArray(c.meses) ? c.meses : [];
    const defMeses = (Array.isArray(c.meses_deficit) ? c.meses_deficit : []).map((m) => rotuloMes(c, m));
    const chips = el("div", { cls: "od-chips" }, [
      el("span", {}, [document.createTextNode("Sistema: "), el("strong", { text: c.sistema || "—" }), document.createTextNode(" · pagamento " + (c.frequencia || "—"))]),
      el("span", {}, [document.createTextNode("Pior vale: "), el("strong", { text: brl(c.vale_caixa) })]),
      el("span", {}, [document.createTextNode("Meses em déficit: "), el("strong", { text: defMeses.length ? defMeses.join(", ") : "nenhum" })]),
      el("span", {}, [document.createTextNode("DSCR ano " + (c.ano_referencia || "") + ": "), el("strong", { text: dscr(c.dscr_anual) })]),
    ]);
    const justificativa = Array.isArray(c.justificativa) && c.justificativa.length
      ? el("ul", { cls: "od-list" }, c.justificativa.map((t) => el("li", { text: t }))) : null;
    return [
      card("Saldo de caixa acumulado — 12 meses", [chips, graficoSaldo(meses)]),
      card("Fluxo mensal", [tabelaCiclo(meses)]),
      justificativa ? card("Leitura do fluxo", [justificativa]) : null,
      el("p", { cls: "od-muted", text: "Perfis sazonais são premissas estilizadas de referência (calendário típico do Brasil Central), não série medida da propriedade. Alternativas semestral/anual mantêm o mesmo serviço anual, sem juros adicionais de repactuação." }),
    ];
  }

  function painelEstresse(parecer) {
    const e = parecer.estresse_pecuario;
    if (!e) {
      return [el("div", { cls: "od-card od-empty", text: "Estresse do boi não informado. Preencha preço da arroba, reposição e suplementação (bloco 3) para comparar os cenários." })];
    }
    if (!e.disponivel) {
      return [el("div", { cls: "od-card od-empty", text: e.motivo || "Estresse pecuário indisponível." })];
    }
    const lim = e.limiares_dscr || {};
    const limA = num(lim.aprovar && lim.aprovar.valor !== undefined ? lim.aprovar.valor : lim.aprovar) || 1.3;
    const limR = num(lim.ressalva && lim.ressalva.valor !== undefined ? lim.ressalva.valor : lim.ressalva) || 1.0;
    const cen = e.cenarios || {};
    const linhas = CENARIOS.filter(([k]) => cen[k]).map(([k, nome]) => ({ k, nome, d: cen[k] }));
    const maxD = Math.max(2, limA * 1.25, ...linhas.map((l) => num(l.d.dscr) || 0));
    const pos = (v) => Math.max(0, Math.min(100, (v / maxD) * 100));
    const CLS = { aprovar: "aprovar", ressalva: "ressalva", negar: "negar" };
    const CLS_TXT = { aprovar: "aprova", ressalva: "ressalva", negar: "nega" };

    const barras = linhas.map(({ nome, d }) => {
      const v = num(d.dscr);
      const cls = CLS[d.classificacao] || "neutro";
      const bar = el("div", { cls: "od-scn__bar od-scn__bar--" + cls, attrs: { style: "width:" + (v === null ? 0 : pos(Math.max(v, 0))).toFixed(1) + "%" } });
      const track = el("div", { cls: "od-scn__track" }, [
        bar,
        el("span", { cls: "od-scn__mark", attrs: { style: "left:" + pos(limR).toFixed(1) + "%" } }),
        el("span", { cls: "od-scn__mark", attrs: { style: "left:" + pos(limA).toFixed(1) + "%" } }),
      ]);
      const nomeEl = el("div", { cls: "od-scn__name", text: nome });
      if (d.descricao) nomeEl.setAttribute("title", String(d.descricao));
      return el("div", {
        cls: "od-scn__row",
        attrs: { role: "group", "aria-label": nome + ": DSCR " + dscr(v) + (CLS_TXT[d.classificacao] ? " (" + CLS_TXT[d.classificacao] + ")" : "") },
      }, [nomeEl, track, el("div", { cls: "od-scn__val", text: dscr(v) })]);
    });
    const eixo = el("div", { cls: "od-scn__axis", attrs: { "aria-hidden": "true" } }, [
      el("span"),
      el("div", { cls: "od-scn__axis-track" }, [
        el("span", { text: "0", attrs: { style: "left:0%" } }),
        el("span", { text: dscr(limR), attrs: { style: "left:" + pos(limR).toFixed(1) + "%" } }),
        el("span", { text: dscr(limA), attrs: { style: "left:" + pos(limA).toFixed(1) + "%" } }),
      ]),
      el("span"),
    ]);
    const base = e.base || {};
    const chips = el("div", { cls: "od-chips" }, [
      el("span", {}, [document.createTextNode("Base: DSCR "), el("strong", { text: dscr(base.dscr) }), document.createTextNode(" · arroba "), el("strong", { text: brl2(base.preco_arroba) })]),
      el("span", { text: "Cores: verde ≥ " + dscr(limA) + " · âmbar " + dscr(limR) + " a " + dscr(limA) + " · vermelho < " + dscr(limR) }),
    ]);

    const itemRup = (r) => {
      if (!r) return null;
      if (r.status === "sem_divida" || num(r.preco_minimo) === null) {
        return el("div", { cls: "od-rupt__item" }, [
          el("div", { cls: "od-rupt__label", text: "Para DSCR " + dscr(r.dscr_alvo) }),
          el("div", { cls: "od-rupt__value", text: "—" }),
          el("div", { cls: "od-rupt__sub", text: r.status === "sem_divida" ? "Sem dívida: a ruptura não se aplica." : "Sem volume de venda: ruptura não calculável." }),
          el("span", { cls: "od-badge od-badge--neutral", text: r.status === "sem_divida" ? "Não se aplica" : "Indisponível" }),
        ]);
      }
      const queda = num(r.queda_maxima_suportada_pct);
      const sub = r.em_ruptura
        ? "Já em ruptura" + (queda !== null ? ": a arroba precisaria subir " + fmtNum1.format(Math.abs(queda)) + "%" : "")
        : "Folga" + (queda !== null ? ": suporta queda de " + fmtNum1.format(queda) + "%" : "");
      return el("div", { cls: "od-rupt__item" }, [
        el("div", { cls: "od-rupt__label", text: "Para DSCR " + dscr(r.dscr_alvo) }),
        el("div", { cls: "od-rupt__value", text: brl2(r.preco_minimo) + "/@" }),
        el("div", { cls: "od-rupt__sub", text: sub + " · base " + brl2(r.preco_base) + "/@" }),
        el("span", { cls: "od-badge od-badge--" + (r.em_ruptura ? "reject" : "approve"), text: r.em_ruptura ? "Em ruptura" : "Com folga" }),
      ]);
    };
    const pr = e.ponto_ruptura_arroba || {};
    const avisos = Array.isArray(e.avisos) && e.avisos.length
      ? el("div", { cls: "od-note od-note--warn" }, e.avisos.map((t) => el("div", { text: t }))) : null;

    return [
      card("DSCR por cenário de estresse", [chips, el("div", { cls: "od-scn" }, barras.concat([eixo])), avisos]),
      card("Ponto de ruptura da arroba", [el("div", { cls: "od-rupt" }, [itemRup(pr.ressalva), itemRup(pr.aprovar)])]),
      e.premissas_base ? el("p", { cls: "od-muted", text: e.premissas_base }) : null,
    ];
  }

  function montarAbas(resumoNodes, parecer) {
    const defs = [
      ["resumo", "Resumo / Base"],
      ["ciclo", "Ciclo 12m"],
      ["estresse", "Estresse do Boi"],
    ];
    const painelEl = {};
    painelEl.resumo = el("div", { cls: "od-panel", attrs: { id: "od-panel-resumo", role: "tabpanel", "aria-labelledby": "od-tab-resumo" } }, resumoNodes);
    painelEl.ciclo = el("div", { cls: "od-panel", attrs: { id: "od-panel-ciclo", role: "tabpanel", "aria-labelledby": "od-tab-ciclo", hidden: "" } }, painelCiclo(parecer));
    painelEl.estresse = el("div", { cls: "od-panel", attrs: { id: "od-panel-estresse", role: "tabpanel", "aria-labelledby": "od-tab-estresse", hidden: "" } }, painelEstresse(parecer));

    const botoes = defs.map(([id, rotulo], i) => el("button", {
      cls: "od-tab", text: rotulo,
      attrs: { id: "od-tab-" + id, type: "button", role: "tab", "aria-controls": "od-panel-" + id, "aria-selected": i === 0 ? "true" : "false", tabindex: i === 0 ? "0" : "-1" },
    }));
    const ativar = (idx, foco) => {
      botoes.forEach((b, i) => {
        const on = i === idx;
        b.setAttribute("aria-selected", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;
        painelEl[defs[i][0]].hidden = !on;
      });
      if (foco) botoes[idx].focus();
    };
    botoes.forEach((b, i) => {
      b.addEventListener("click", () => ativar(i, false));
      b.addEventListener("keydown", (ev) => {
        if (ev.key === "ArrowRight") { ev.preventDefault(); ativar((i + 1) % botoes.length, true); }
        if (ev.key === "ArrowLeft") { ev.preventDefault(); ativar((i + botoes.length - 1) % botoes.length, true); }
      });
    });
    return [el("div", { cls: "od-tabs", attrs: { role: "tablist", "aria-label": "Seções do parecer" } }, botoes)]
      .concat(defs.map(([id]) => painelEl[id]));
  }

  // Reorganiza #result-wrap: hero + banners + abas. O conteúdo legado (resumo,
  // SHAP assíncrono, proveniência, PDF) é MOVIDO para a aba Resumo, não
  // recriado — ids e handlers continuam os mesmos.
  function renderParecer(data) {
    const wrap = document.getElementById("result-wrap");
    const parecer = data && data.parecer;
    if (!wrap || !parecer || !parecer.conclusao) return;
    const legado = Array.from(wrap.childNodes);
    const raiz = el("div", { cls: "od-result" });
    raiz.appendChild(montarHero(parecer));
    montarBanners(parecer).forEach((b) => raiz.appendChild(b));
    montarAbas(legado, parecer).forEach((n) => raiz.appendChild(n));
    wrap.appendChild(raiz);
  }

  // Impressão: <details> fechado não sai no papel; abre antes e restaura depois.
  window.addEventListener("beforeprint", () => {
    document.querySelectorAll("details.ork-fold:not([open])").forEach((d) => { d.dataset.pr = "1"; d.open = true; });
  });
  window.addEventListener("afterprint", () => {
    document.querySelectorAll("details.ork-fold[data-pr]").forEach((d) => { d.open = false; delete d.dataset.pr; });
  });

  window.OrkavynDash = { lerCamposNovos, renderParecer, definirSistema, aplicarTema, revelarCampo, atualizarBlocos };

  document.addEventListener("DOMContentLoaded", () => {
    iniciarTema();
    iniciarMenus();
    iniciarSaudacao();
    iniciarSistemas();
    iniciarMaisOpcoes();
    iniciarAvisoGep();
    iniciarBlocosOpcionais();
  });
})();
