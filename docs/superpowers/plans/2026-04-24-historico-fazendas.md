# Histórico de Análises por Fazenda — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar painel "Minhas Fazendas" com histórico de análises por propriedade, criação inline de fazenda no dropdown, e pré-seleção automática por nome ao carregar PDF.

**Architecture:** O backend já está 100% implementado (`GET/POST /api/fazendas` e `GET /api/fazendas/<id>/historico`). O trabalho é inteiramente frontend em `templates/index.html`. Três adições independentes: (1) criação inline no dropdown, (2) painel de histórico, (3) pré-seleção automática no upload de PDF.

**Tech Stack:** JavaScript vanilla, Flask/Jinja2, CSS variables existentes no app.

---

## Arquivos Modificados

| Arquivo | O que muda |
|---|---|
| `templates/index.html` | Todas as alterações — dropdown, painel, JS |

---

### Task 1: Dropdown — Criar Nova Fazenda Inline

**Files:**
- Modify: `templates/index.html`
  - HTML: select de fazendas (~linha 367–372) + mini-form inline
  - JS: `carregarFazenda()` (~linha 1004) + nova função `criarFazenda()`

**Contexto:** O select `f_sel_faz` já tem `-- Nova Fazenda --` (value="") como opção padrão. Precisamos: (a) renomear para "— Sem vínculo —", (b) adicionar opção `__nova` no final, (c) mostrar mini-form quando `__nova` for selecionado, (d) implementar `criarFazenda()` que faz POST e insere a nova opção no select.

- [ ] **Step 1: Atualizar o HTML do select e adicionar mini-form**

Localizar:
```html
          <select id="f_sel_faz" onchange="carregarFazenda(this.value)">
            <option value="">-- Nova Fazenda --</option>
            {% for f in fazendas %}
              <option value="{{ f.id }}">{{ f.nome }} ({{ f.municipio }})</option>
            {% endfor %}
          </select>
```

Substituir por:
```html
          <select id="f_sel_faz" onchange="carregarFazenda(this.value)">
            <option value="">— Sem vínculo —</option>
            {% for f in fazendas %}
              <option value="{{ f.id }}">{{ f.nome }} ({{ f.municipio }})</option>
            {% endfor %}
            <option value="__nova">＋ Nova Fazenda...</option>
          </select>
```

Em seguida, logo depois do `</div>` que fecha o `fgrid` (após a linha `<input type="hidden" id="f_id_faz" value="">`), adicionar o mini-form. Localizar:

```html
        <input type="hidden" id="f_id_faz" value="">
      </div>
      <div class="field" style="margin-top:14px"><label>Proprietário</label>
```

Substituir por:
```html
        <input type="hidden" id="f_id_faz" value="">
      </div>
      <div id="nova-faz-form" style="display:none;grid-column:1/-1;background:var(--c2);border:1px solid var(--b2);border-radius:var(--rs);padding:14px;margin-top:4px;gap:10px;align-items:flex-end" class="fgrid">
        <div class="field" style="grid-column:1/3">
          <label>Nome da Nova Fazenda</label>
          <input type="text" id="nova-faz-nome" placeholder="Ex: Fazenda Santa Cruz" onkeydown="if(event.key==='Enter')criarFazenda()">
        </div>
        <div style="display:flex;gap:8px;align-items:flex-end;padding-bottom:2px">
          <button class="btn-sm" style="border-color:var(--g);color:var(--g)" onclick="criarFazenda()">＋ Criar</button>
          <button class="btn-sm" onclick="document.getElementById('f_sel_faz').value='';carregarFazenda('');document.getElementById('nova-faz-form').style.display='none'">✕</button>
        </div>
      </div>
      <div class="field" style="margin-top:14px"><label>Proprietário</label>
```

- [ ] **Step 2: Atualizar `carregarFazenda()` para lidar com `__nova`**

Localizar:
```javascript
async function carregarFazenda(fid){
  if(!fid){
    document.getElementById('f_faz').value='';
    document.getElementById('f_mun').value='';
    document.getElementById('f_prop').value='';
    document.getElementById('f_id_faz').value='';
    return;
  }
```

Substituir por:
```javascript
async function carregarFazenda(fid){
  const nff=document.getElementById('nova-faz-form');
  if(fid==='__nova'){nff.style.display='flex';document.getElementById('nova-faz-nome').focus();return}
  nff.style.display='none';
  if(!fid){
    document.getElementById('f_faz').value='';
    document.getElementById('f_mun').value='';
    document.getElementById('f_prop').value='';
    document.getElementById('f_id_faz').value='';
    return;
  }
```

- [ ] **Step 3: Adicionar função `criarFazenda()` logo após `carregarFazenda()`**

Inserir após o `}` de fechamento de `carregarFazenda`:
```javascript
async function criarFazenda(){
  const nome=document.getElementById('nova-faz-nome').value.trim();
  if(!nome){toast('Digite o nome da fazenda',true);return}
  showLoading('Criando fazenda...');
  try{
    const res=await fetch('/api/fazendas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nome,municipio:document.getElementById('f_mun').value,proprietario:document.getElementById('f_prop').value})});
    const data=await res.json();
    if(data.erro){toast(data.erro,true);return}
    const sel=document.getElementById('f_sel_faz');
    const opt=document.createElement('option');
    opt.value=data.id;
    const mun=document.getElementById('f_mun').value;
    opt.textContent=nome+(mun?' ('+mun+')':'');
    sel.insertBefore(opt,sel.lastElementChild);
    sel.value=data.id;
    document.getElementById('f_id_faz').value=data.id;
    document.getElementById('f_faz').value=nome;
    document.getElementById('nova-faz-form').style.display='none';
    document.getElementById('nova-faz-nome').value='';
    toast('Fazenda "'+nome+'" criada');
  }finally{hideLoading()}
}
```

- [ ] **Step 4: Verificar no browser**

1. Iniciar o servidor: `python app.py` em `c:/Users/Lucas/Downloads/boviml_python/boviml/`
2. Abrir `http://localhost:5050`
3. No painel "Inserir Dados", clicar no select "Selecionar Fazenda" e escolher "＋ Nova Fazenda..."
4. O mini-form deve aparecer. Digitar um nome e clicar "＋ Criar"
5. A nova fazenda deve aparecer selecionada no dropdown
6. Escolher "— Sem vínculo —" deve limpar os campos

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat: criação inline de fazenda no dropdown"
```

---

### Task 2: Painel "Minhas Fazendas" com Histórico

**Files:**
- Modify: `templates/index.html`
  - HTML: botão na tab-bar + `<div class="panel" id="panel-fazendas">` (~após panel-custos)
  - JS: funções `abrirFazendas()`, `verHistoricoFazenda(id, nome)`, `recarregarAnalise(valores, natPct)`

**Contexto:** A tab-bar tem 4 botões (linha ~349–354). Os painéis existem como `<div class="panel">` dentro de `<main>`. A função `showTab(id, btn)` ativa/desativa painéis pelo id. As constantes `TC`, `TL`, `TE` e a função `fN` existem no escopo global.

- [ ] **Step 1: Adicionar botão na tab-bar**

Localizar:
```html
  <button class="tab-btn" onclick="showTab('custos',this)">Custo/Cab.</button>
</div>
```

Substituir por:
```html
  <button class="tab-btn" onclick="showTab('custos',this)">Custo/Cab.</button>
  <button class="tab-btn" onclick="showTab('fazendas',this);abrirFazendas()">🏡 Fazendas</button>
</div>
```

- [ ] **Step 2: Adicionar panel HTML antes das tags `<script>`**

O panel-custos é o último painel antes das tags `<script>`. Localizar o trecho:

```html
    </div>
  </div>
</div>

<script>
 // ==================== PREÇOS (CORRIGIDO) ====================
```

Substituir por:
```html
    </div>
  </div>
</div>

<!-- ═══ MINHAS FAZENDAS ═══ -->
<div class="panel" id="panel-fazendas">
  <div class="ptitle">Minhas <em>Fazendas</em></div>
  <p class="psub">Histórico de análises por propriedade.</p>
  <div id="faz-lista-wrap"></div>
  <div id="faz-hist-wrap" style="display:none"></div>
</div>

<script>
 // ==================== PREÇOS (CORRIGIDO) ====================
```

- [ ] **Step 3: Adicionar funções JS**

Localizar a função `resetApp` (linha ~2042):
```javascript
function resetApp(){
```

Inserir ANTES dela:
```javascript
// ── MINHAS FAZENDAS
async function abrirFazendas(){
  const lw=document.getElementById('faz-lista-wrap');
  const hw=document.getElementById('faz-hist-wrap');
  hw.style.display='none';hw.innerHTML='';
  lw.style.display='block';
  lw.innerHTML='<p style="color:var(--mu);padding:20px 0">Carregando...</p>';
  try{
    const res=await fetch('/api/fazendas');
    const data=await res.json();
    if(data.erro){lw.innerHTML='<p style="color:var(--rd)">Erro ao carregar fazendas.</p>';return}
    const fzs=data.fazendas;
    if(!fzs.length){lw.innerHTML='<p style="color:var(--mu);padding:20px 0">Nenhuma fazenda cadastrada ainda. Classifique um rebanho vinculando a uma fazenda para começar.</p>';return}
    lw.innerHTML='<div style="display:grid;gap:12px">'+fzs.map(f=>`
      <div class="card">
        <div class="ch">
          <div class="ct"><div class="cd"></div>${f.nome}</div>
          <button class="btn-sm" onclick="verHistoricoFazenda(${f.id},'${f.nome.replace(/\\/g,'\\\\').replace(/'/g,"\\'")}')">Ver histórico</button>
        </div>
        <div class="cb" style="padding:12px 22px;font-size:.84rem;color:var(--sb)">
          ${f.municipio||'—'} · <strong style="color:var(--tx)">${f.total_analises}</strong> análise${f.total_analises!==1?'s':''} · Última: ${f.ultima_analise?f.ultima_analise.slice(0,10):'—'}
        </div>
      </div>`).join('')+'</div>';
  }catch(e){lw.innerHTML='<p style="color:var(--rd)">Erro: '+e.message+'</p>'}
}

async function verHistoricoFazenda(id,nome){
  const lw=document.getElementById('faz-lista-wrap');
  const hw=document.getElementById('faz-hist-wrap');
  lw.style.display='none';
  hw.style.display='block';
  hw.innerHTML='<p style="color:var(--mu);padding:20px 0">Carregando histórico...</p>';
  try{
    const res=await fetch(`/api/fazendas/${id}/historico`);
    const data=await res.json();
    if(data.erro){hw.innerHTML='<p style="color:var(--rd)">Erro: '+data.erro+'</p>';return}
    const hist=data.historico;
    hw.innerHTML=`
      <button class="btn-sm" style="margin-bottom:18px" onclick="abrirFazendas()">← Voltar</button>
      <div class="ptitle" style="font-size:1.8rem;margin-bottom:6px;margin-top:4px">${nome}</div>
      ${!hist.length
        ?'<p style="color:var(--mu);padding:20px 0">Nenhuma análise salva ainda para esta fazenda.</p>'
        :`<div class="card"><table class="ytbl">
          <thead><tr><th>Data</th><th>Tipo</th><th class="r">Animais</th><th class="r">Confiança</th><th></th></tr></thead>
          <tbody>${hist.map(r=>`<tr>
            <td style="color:var(--sb);font-family:var(--fm);font-size:.78rem">${r.created_at.slice(0,10)}</td>
            <td><span style="font-family:var(--fn);font-weight:700;font-size:.85rem;color:${TC[r.class_ml]}">${TE[r.class_ml]||''} ${TL[r.class_ml]||r.class_ml}</span></td>
            <td class="r">${fN(r.valores.reduce((a,b)=>a+b,0))}</td>
            <td class="r" style="color:var(--sb)">${r.confianca}%</td>
            <td style="text-align:right"><button class="btn-sm" onclick="recarregarAnalise(${JSON.stringify(r.valores)},${r.nat_pct||75})">↩ Recarregar</button></td>
          </tr>`).join('')}</tbody>
        </table></div>`}`;
  }catch(e){hw.innerHTML='<p style="color:var(--rd)">Erro: '+e.message+'</p>'}
}

function recarregarAnalise(valores,natPct){
  FAIXAS.forEach((f,i)=>{
    document.getElementById(f.key+'_F').value=valores[i*2];
    document.getElementById(f.key+'_M').value=valores[i*2+1];
  });
  if(natPct)document.getElementById('c-nat').value=natPct;
  upd();
  showTab('entrada',document.querySelectorAll('.tab-btn')[0]);
  toast('Análise recarregada no formulário');
}

```

- [ ] **Step 4: Verificar no browser**

1. Clicar em "🏡 Fazendas" na tab-bar
2. Lista de fazendas deve aparecer (ou mensagem "Nenhuma fazenda")
3. Clicar "Ver histórico" de uma fazenda com análises
4. Tabela de análises aparece com data, tipo (badge colorido), animais, confiança, botão "↩ Recarregar"
5. Clicar "↩ Recarregar" deve preencher o formulário e voltar para a aba "Inserir Dados"
6. Clicar "← Voltar" deve retornar à lista de fazendas

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat: painel Minhas Fazendas com histórico e recarregar análise"
```

---

### Task 3: Auto-Preselect de Fazenda ao Carregar PDF

**Files:**
- Modify: `templates/index.html` — função `lerPDFInserir()` (~linha 1088)

**Contexto:** Quando um PDF é carregado em "Inserir Dados", `lerPDFInserir()` preenche `f_faz`, `f_mun`, `f_prop`. Se o nome da fazenda do PDF (campo `data.fazenda`) coincidir (case-insensitive) com alguma opção no select `f_sel_faz`, deve pré-selecionar essa opção e atualizar `f_id_faz` — sem chamar `carregarFazenda()` (que sobrescreveria os valores do PDF com a última análise salva).

- [ ] **Step 1: Adicionar auto-preselect em `lerPDFInserir()`**

Localizar dentro de `lerPDFInserir`, logo após a linha `upd();`:
```javascript
    upd();
    const _np=data.pdfs_processados||1;
    toast(
```

Substituir por:
```javascript
    upd();
    const _sel=document.getElementById('f_sel_faz');
    const _nomePDF=(data.fazenda||'').trim().toLowerCase();
    if(_nomePDF&&_sel){
      let _found='';
      for(const _o of _sel.options){
        if(_o.value&&_o.value!=='__nova'&&_o.textContent.toLowerCase().includes(_nomePDF)){_found=_o.value;break}
      }
      if(_found){_sel.value=_found;document.getElementById('f_id_faz').value=_found}
    }
    const _np=data.pdfs_processados||1;
    toast(
```

- [ ] **Step 2: Verificar no browser**

1. No painel "Inserir Dados", criar uma fazenda sintética de teste
2. Resetar o formulário (botão ✕ Limpar)
3. Clicar "📂 Ler PDF" e selecionar um PDF integralmente sintético
4. O dropdown deve pré-selecionar a fazenda sintética automaticamente
5. Os valores do PDF devem estar corretos (não sobrescritos pela última análise)

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: pré-selecionar fazenda por nome ao carregar PDF"
```
