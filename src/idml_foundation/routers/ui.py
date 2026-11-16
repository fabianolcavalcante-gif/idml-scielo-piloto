# ruff: noqa: E501

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from idml_foundation.routers.edit_evaluation_ui import HTML as EVALUATION_HTML
from idml_foundation.routers.input_workspace_ui import HTML as INPUT_HTML
from idml_foundation.routers.input_workspace_ui import JS as INPUT_JS
from idml_foundation.routers.source_access_ui import HTML as SOURCE_ACCESS_HTML

router = APIRouter(tags=["interface"])

_HTML = (
    """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IDML → SciELO</title><link rel="stylesheet" href="/app/assets/app.css"></head>
<body><header><div><strong>IDML → SciELO</strong><small> revisão editorial auditável</small></div>
<div id="identity"></div></header><main>
<p role="status">Ambiente de desenvolvimento/homologação. Pacote gerado e aprovação editorial não significam validação formal nem autorização de publicação. Consulte o diagnóstico de validação em Jobs.</p>
<section id="login-panel" class="card narrow"><h1 id="login-title">Entrar</h1><form id="login-form">
<label>E-mail<input id="email" type="email" required autocomplete="username"></label>
<label>Senha<input id="password" type="password" minlength="14" required autocomplete="current-password"></label>
<label>Código MFA<input id="mfa-code" inputmode="numeric" pattern="[0-9]{6}" autocomplete="one-time-code"></label>
<label><span><input id="trust-browser" type="checkbox"> Confiar neste navegador pessoal para recuperar minha senha por 30 dias</span></label>
<button>Entrar</button></form><button id="show-recovery" class="link">Recuperar senha</button>
<form id="recovery-form" hidden><p>Use o navegador que você marcou como confiável ao entrar. Se for seu primeiro acesso neste aparelho, peça um link de recuperação ao responsável pelo sistema.</p>
<label>E-mail cadastrado<input id="recovery-email" type="email" autocomplete="username" required></label><button>Continuar</button></form>
<form id="new-password-form" hidden>
<label>Nova senha (ao menos 14 caracteres)<input id="new-password" type="password" autocomplete="new-password" minlength="14" maxlength="1024" required></label>
<label>Confirme a nova senha<input id="confirm-password" type="password" autocomplete="new-password" minlength="14" maxlength="1024" required></label>
<button>Salvar nova senha</button></form>
<button type="button" id="cancel-recovery" class="link" hidden>Voltar para entrar</button>
<p id="login-message" role="alert"></p></section>
<section id="workspace" hidden><nav><select id="organization" aria-label="Empresa"></select>
<button data-view="dashboard">Jobs</button><button data-view="uploads">Uploads</button>
<button data-view="reviews">Revisões</button><button data-view="members">Usuários</button>
<button data-view="identity-view">Identidade</button><button data-view="releases">Aprovações</button>
<button data-view="audit">Auditoria</button><button id="logout">Sair</button></nav>
<section id="dashboard" class="view card"><h1>Dashboard de jobs</h1><button class="refresh" data-target="jobs">Atualizar</button><p id="job-message"></p><div id="jobs"></div><article id="validation-diagnosis" aria-live="polite"></article><div id="timeline"></div></section>
"""
    + INPUT_HTML
    + """
<section id="reviews" class="view card" hidden><h1>Review Queue</h1><details><summary>Criar pendência a partir do resultado do job</summary><form id="review-create-form"><label>ID do artigo<input id="review-resource" required></label><label>ID do snapshot canônico<input id="review-snapshot" required></label><label>ID do job<input id="review-job"></label><label>Categoria<select id="review-category"><option value="semantic">Semântica</option><option value="missing-source">Fonte ausente</option><option value="source-conflict">Conflito de fonte</option><option value="deterministic">Determinística</option><option value="system">Sistema</option></select></label><label>Código da regra<input id="review-rule" required></label><label>Caminho canônico<input id="review-path" placeholder="/front/titles/0/text/value" required></label><label>Mensagem<textarea id="review-message" required></textarea></label><button>Criar pendência</button></form><p id="review-create-message"></p></details><button class="refresh" data-target="review-list">Atualizar</button><div class="split"><div id="review-list"></div><article id="review-detail"><p>Selecione uma pendência.</p></article></div></section>
<section id="members" class="view card" hidden><h1>Empresa e usuários</h1><form id="invite-form"><input id="invite-email" type="email" placeholder="E-mail" required><select id="invite-role"><option value="operator">Operador</option><option value="reviewer">Revisor</option><option value="release_manager">Release manager</option></select><button>Convidar</button></form><p id="invite-message"></p><div id="member-list"></div>
<form id="support-link-form" hidden><h2>Recuperação de senha</h2>
<p>Confirme a identidade do titular antes de compartilhar o link pelo canal privado combinado. O link vale por 30 minutos.</p>
<label>E-mail do titular<input id="support-email" type="email" required></label>
<button>Gerar link de recuperação</button>
<label id="support-result" hidden>Link de uso único<input id="support-link" readonly></label>
<p id="support-message" role="status"></p></form></section>
<section id="identity-view" class="view card" hidden><h1>Identidade, MFA e sessões</h1><p id="mfa-status"></p><form id="mfa-setup"><label>Senha atual<input id="mfa-password" type="password" minlength="14" required></label><button>Configurar MFA</button></form><div id="mfa-confirmation" hidden><p>Cadastre esta chave no autenticador: <code id="mfa-secret"></code></p><label>Código TOTP<input id="mfa-confirm-code" inputmode="numeric" pattern="[0-9]{6}"></label><button id="mfa-confirm">Confirmar MFA</button></div><pre id="recovery-codes" hidden></pre><h2>Sessões</h2><div id="session-list"></div></section>
<section id="releases" class="view card" hidden><h1>Aprovação editorial</h1><p>A aprovação de duas pessoas não substitui o Gate técnico de release.</p><form id="release-form"><input id="release-resource" placeholder="ID do recurso" required><input id="release-snapshot" placeholder="ID do snapshot canônico" required><input id="release-sha" placeholder="SHA-256 do pacote" pattern="[0-9a-f]{64}" required><button>Solicitar aprovação</button></form><p id="release-message"></p><div id="release-list"></div></section>
<section id="audit" class="view card" hidden><h1>Auditoria</h1><a id="audit-export" href="/v1/audit/export">Download controlado</a><div id="audit-list"></div></section>
</section></main><script src="/app/assets/app.js" defer></script></body></html>"""
)

_CSS = """:root{color-scheme:light;font-family:Inter,system-ui,sans-serif;background:#f3f5f7;color:#17202a}*{box-sizing:border-box}body{margin:0}header{height:64px;padding:0 24px;background:#102a43;color:#fff;display:flex;align-items:center;justify-content:space-between}header small{color:#9fb3c8}main{max-width:1280px;margin:24px auto;padding:0 18px}.card{background:#fff;border:1px solid #d9e2ec;border-radius:10px;padding:20px;box-shadow:0 3px 12px #102a4310}.narrow{max-width:430px;margin:70px auto}h1{font-size:1.25rem;margin-top:0}label{display:grid;gap:6px;margin:12px 0}input,select,textarea,button{font:inherit;padding:9px 11px;border:1px solid #bcccdc;border-radius:6px}button{background:#0b7285;color:#fff;border:0;cursor:pointer}button:hover{background:#095c6b}.link{background:none;color:#0b7285;padding-left:0}nav{display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap}nav select{min-width:250px}.view{min-height:430px}.split{display:grid;grid-template-columns:minmax(280px,36%) 1fr;gap:18px}.item{border:1px solid #d9e2ec;border-radius:7px;padding:10px;margin:8px 0;cursor:pointer}.item:hover{border-color:#0b7285}.badge{display:inline-block;background:#e6fcf5;color:#087f5b;border-radius:999px;padding:2px 8px;font-size:.78rem}pre{white-space:pre-wrap;overflow:auto;background:#f8f9fa;border:1px solid #e9ecef;padding:10px;max-height:320px}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{text-align:left;border-bottom:1px solid #e9ecef;padding:8px;font-size:.9rem}.error{color:#c92a2a}.success{color:#087f5b}@media(max-width:800px){.split{grid-template-columns:1fr}header small{display:none}}"""

_JS = (
    r"""const state={token:sessionStorage.getItem('idml_token'),org:sessionStorage.getItem('idml_org'),me:null};
const $=s=>document.querySelector(s); const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,options={}){const headers=new Headers(options.headers||{});if(state.token)headers.set('Authorization',`Bearer ${state.token}`);if(state.org)headers.set('X-Organization-ID',state.org);const r=await fetch(path,{...options,headers});if(r.status===204)return null;const type=r.headers.get('content-type')||'';const body=type.includes('json')?await r.json():await r.text();if(!r.ok)throw new Error(body.detail||body||`HTTP ${r.status}`);return body}
function message(node,text,ok=false){node.textContent=text;node.className=ok?'success':'error'}
async function boot(){if(!state.token)return showLogin();try{state.me=await api('/v1/auth/me');$('#support-link-form').hidden=!state.me.is_platform_admin;const orgs=await api('/v1/organizations');if(!orgs.length)throw new Error('Usuário sem empresa ativa');$('#organization').innerHTML=orgs.map(o=>`<option value="${esc(o.id)}" data-role="${esc(o.role)}">${esc(o.name)} — ${esc(o.role)}</option>`).join('');state.org=orgs.some(o=>o.id===state.org)?state.org:orgs[0].id;$('#organization').value=state.org;sessionStorage.setItem('idml_org',state.org);$('#identity').textContent=state.me.email;$('#login-panel').hidden=true;$('#workspace').hidden=false;await Promise.allSettled([loadJobs(),loadReviews(),loadArtifacts(),loadResources()])}catch(e){sessionStorage.clear();state.token=null;showLogin();message($('#login-message'),e.message)}}
function showLogin(){$('#login-panel').hidden=false;$('#workspace').hidden=true}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const payload={email:$('#email').value,password:$('#password').value,trust_browser:$('#trust-browser').checked};if($('#mfa-code').value)payload.mfa_code=$('#mfa-code').value;try{const r=await api('/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});state.token=r.access_token;sessionStorage.setItem('idml_token',state.token);await boot()}catch(err){message($('#login-message'),err.message)}});
let resetToken = '';
function recoveryScreen(screen) {
  $('#login-title').textContent = {login:'Entrar', request:'Recuperar senha', reset:'Escolha sua nova senha'}[screen];
  $('#login-form').hidden = $('#show-recovery').hidden = screen !== 'login';
  $('#recovery-form').hidden = screen !== 'request';
  $('#new-password-form').hidden = screen !== 'reset';
  $('#cancel-recovery').hidden = screen === 'login';
  message($('#login-message'), '');
  $('#new-password-form').reset();
  if (screen !== 'reset') resetToken = '';
  $(screen === 'login' ? '#email' : screen === 'request' ? '#recovery-email' : '#new-password').focus();
}
$('#show-recovery').addEventListener('click', () => {
  $('#recovery-email').value = $('#email').value;
  recoveryScreen('request');
});
$('#cancel-recovery').addEventListener('click', () => recoveryScreen('login'));
async function recoveryPost(path, payload) {
  const response = await fetch('/v1/auth/recovery/'+path, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload), cache:'no-store'
  });
  if (response.status === 429) {
    const minutes = Math.max(1, Math.ceil(Number(response.headers.get('retry-after') || 3600)/60));
    throw Error('Limite de tentativas atingido. Tente novamente em '+minutes+' min.');
  }
  if (response.status === 400) throw Error('Este link expirou ou já foi usado. Solicite um novo link ao responsável.');
  if (!response.ok) throw Error('O portal não conseguiu concluir o pedido. Tente novamente.');
  return response.status === 204 ? null : response.json();
}
$('#recovery-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  try {
    const result = await recoveryPost('request', {email:$('#recovery-email').value});
    if (result.reset_token) {
      resetToken = result.reset_token;
      recoveryScreen('reset');
    } else {
      message($('#login-message'), 'Não foi possível confirmar a conta neste navegador. Use o navegador confiável ou peça um link de recuperação ao responsável pelo sistema.');
    }
  } catch (err) { message($('#login-message'), err.message); }
  finally { button.disabled = false; }
});
$('#new-password-form').addEventListener('submit', async event => {
  event.preventDefault();
  if ($('#new-password').value !== $('#confirm-password').value) {
    message($('#login-message'), 'As senhas estão diferentes. Confira a confirmação.');
    $('#confirm-password').focus();
    return;
  }
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  try {
    await recoveryPost('complete', {token:resetToken, new_password:$('#new-password').value});
    $('#login-form').reset();
    $('#email').value = $('#recovery-email').value;
    recoveryScreen('login');
    message($('#login-message'), 'Senha salva. Entre com a nova senha.', true);
  } catch (err) { message($('#login-message'), err.message); }
  finally { button.disabled = false; }
});
function openRecoveryLink() {
  const token = new URLSearchParams(location.hash.slice(1)).get('recuperar');
  if (token === null) return false;
  history.replaceState(null, '', location.pathname + location.search);
  showLogin();
  if (!/^[a-zA-Z0-9_-]{32,200}$/.test(token)) {
    recoveryScreen('request');
    message($('#login-message'), 'Link incompleto. Abra novamente o link de recuperação.');
  } else {
    resetToken = token;
    recoveryScreen('reset');
  }
  return true;
}
window.addEventListener('hashchange', openRecoveryLink);
$('#support-link-form').addEventListener('submit', async event => {
  event.preventDefault();
  $('#support-result').hidden = true;
  $('#support-link').value = '';
  try {
    const data = await api('/v1/auth/recovery/support', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email:$('#support-email').value})});
    const url = new URL('/app', location.origin);
    url.hash = 'recuperar='+data.reset_token;
    $('#support-link').value = url.href;
    $('#support-result').hidden = false;
    $('#support-link').select();
    message($('#support-message'), 'Copie o link e entregue ao titular.', true);
  } catch (err) { message($('#support-message'), 'Confira o e-mail e entre novamente como administrador da plataforma com MFA.'); }
});
$('#logout').addEventListener('click',async()=>{try{await api('/v1/auth/logout',{method:'POST'})}finally{sessionStorage.clear();location.reload()}});$('#organization').addEventListener('change',async e=>{state.org=e.target.value;sessionStorage.setItem('idml_org',state.org);await Promise.allSettled([loadJobs(),loadReviews(),loadArtifacts(),loadResources()])});
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',async()=>{document.querySelectorAll('.view').forEach(v=>v.hidden=true);$(`#${b.dataset.view}`).hidden=false;if(b.dataset.view==='uploads')await Promise.allSettled([loadArtifacts(),loadResources()]);if(b.dataset.view==='members')await loadMembers();if(b.dataset.view==='identity-view')await loadIdentity();if(b.dataset.view==='releases')await loadReleases();if(b.dataset.view==='audit')await loadAudit()}));document.querySelectorAll('.refresh').forEach(b=>b.addEventListener('click',()=>b.dataset.target==='jobs'?loadJobs():loadReviews()));
let diagnosisRequest=0,jobsRequest=0;
function resultDownload(job){
 if(job.state!=='succeeded')return '';
 const id=job.kind==='scielo.package'?job.result?.package_artifact_id:job.kind==='idml.process'?job.result?.xml_artifact_id:null;
 if(typeof id!=='string'||!/^[a-f0-9-]{36}$/i.test(id))return '';
 const label=job.kind==='scielo.package'?'Baixar ZIP de avaliação':'Baixar XML da conversão';
 return `<a href="/v1/artifacts/${encodeURIComponent(id)}/download" data-result-download="${esc(id)}">${label}</a> `;
}
async function loadJobs(){const request=++jobsRequest,org=state.org,token=state.token;diagnosisRequest++;$('#validation-diagnosis').replaceChildren();$('#jobs').replaceChildren();try{const rows=await api('/v1/jobs');if(request!==jobsRequest||org!==state.org||token!==state.token)return;$('#jobs').innerHTML=`<table><tr><th>ID / tipo</th><th>Estado</th><th>Tentativas</th><th>Resultado</th><th>Ações</th></tr>${rows.map(j=>`<tr><td><code>${esc(j.id)}</code><br>${esc(j.kind)}</td><td><span class="badge">${esc(j.state)}</span>${j.error_code?`<br><small>${esc(j.error_code)}</small>`:''}</td><td>${j.attempt_count}</td><td>${resultDownload(j)}<button data-diagnosis="${esc(j.id)}">Diagnóstico de validação</button><details><summary>Resultado técnico salvo</summary><pre>${esc(JSON.stringify(j.result,null,2))}</pre></details></td><td><button data-job="${esc(j.id)}">Timeline</button> ${j.state==='queued'?`<button data-cancel-job="${esc(j.id)}" data-version="${j.version}">Cancelar</button>`:''} ${j.state==='failed_retryable'?`<button data-retry-job="${esc(j.id)}" data-version="${j.version}">Repetir</button>`:''}</td></tr>`).join('')}</table>`;document.querySelectorAll('[data-result-download]').forEach(a=>a.addEventListener('click',downloadAuthorized));document.querySelectorAll('[data-diagnosis]').forEach(b=>b.addEventListener('click',()=>loadDiagnosis(b.dataset.diagnosis)));document.querySelectorAll('[data-job]').forEach(b=>b.addEventListener('click',()=>loadTimeline(b.dataset.job)));document.querySelectorAll('[data-cancel-job]').forEach(b=>b.addEventListener('click',()=>controlJob(b,'cancel')));document.querySelectorAll('[data-retry-job]').forEach(b=>b.addEventListener('click',()=>controlJob(b,'retry')))}catch(e){if(request===jobsRequest&&org===state.org&&token===state.token)message($('#jobs'),e.message)}}
function renderDiagnosis(d,id){
 const groups={xml:'XML e pacote',tool:'Validadores e consultas',editorial:'Homologação e entrega'};
 const statuses={'action-required':'Ação necessária',observed:'Resultado registrado','known-limitation':'Limitação conhecida',unavailable:'Evidência indisponível','separate-workflow':'Decisão separada'};
 const counts={blocking:'Bloqueantes',critical:'Críticos',error:'Erros',warning:'Avisos',blocking_errors:'Bloqueantes',fatal_errors:'Fatais',errors:'Erros',warnings:'Avisos'};
 return `<h2>Diagnóstico de validação</h2><p>Job <code>${esc(id)}</code></p><p>${esc(d.notice)}</p>${Object.entries(groups).map(([key,label])=>`<section><h3>${label}</h3>${d.items.filter(i=>i.category===key).map(i=>`<div class="item"><strong>${esc(i.title)}</strong><p>${esc(statuses[i.status]||'Evidência indisponível')} — ${esc(i.detail)}</p>${i.next_action?`<p><strong>Próxima ação:</strong> ${esc(i.next_action)}</p>`:''}${i.identifier_sha256?`<details><summary>Alvo da consulta (SHA-256)</summary><code>${esc(i.identifier_sha256)}</code></details>`:''}${i.counts?`<dl>${Object.entries(i.counts).map(([k,v])=>`<dt>${esc(counts[k]||k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`:''}${i.report_sha256?`<details><summary>Identificador da evidência</summary><code>${esc(i.report_sha256)}</code></details>`:''}</div>`).join('')}</section>`).join('')}<p>Este diagnóstico não concede aprovação nem altera o resultado original.</p>`;
}
async function loadDiagnosis(id){const request=++diagnosisRequest,org=state.org,token=state.token;const current=()=>request===diagnosisRequest&&org===state.org&&token===state.token;const node=$('#validation-diagnosis');node.textContent='Carregando diagnóstico…';try{const d=await api(`/v1/jobs/${encodeURIComponent(id)}/validation-diagnosis`);if(!current())return;node.innerHTML=renderDiagnosis(d,id)}catch(e){if(current())message(node,e.message)}}
async function controlJob(button,action){try{await api(`/v1/jobs/${button.dataset.cancelJob||button.dataset.retryJob}/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:Number(button.dataset.version)})});message($('#job-message'),action==='cancel'?'Job cancelado.':'Retry enfileirado.',true);await loadJobs()}catch(e){message($('#job-message'),e.message)}}
async function loadTimeline(id){try{const rows=await api(`/v1/jobs/${id}/events`);$('#timeline').innerHTML=`<h2>Timeline</h2><ol>${rows.map(x=>`<li>${esc(x.created_at)} — ${esc(x.from_state)} → ${esc(x.to_state)}</li>`).join('')}</ol>`}catch(e){message($('#timeline'),e.message)}}
let artifactRequest=0;
async function loadArtifacts(){
 const generation=++artifactRequest, org=state.org, token=state.token;
 const current=()=>generation===artifactRequest&&org===state.org&&token===state.token;
 const list=$('#artifacts');list.replaceChildren();
 const labels={clamav_clean:'Verificado',policy_only:'Sem varredura',generated:'Gerado pelo sistema',malware_detected:'Em quarentena',scan_unavailable:'Varredura indisponível',integrity_failure:'Falha de integridade'};
 try{
  const rows=await api('/v1/artifacts');if(!current())return;
  list.innerHTML=`<table><tr><th>Arquivo / ID</th><th>Tipo</th><th>SHA-256</th><th>Antivírus</th></tr>${rows.map(a=>`<tr><td><a href="/v1/artifacts/${esc(a.id)}/download" data-download="${esc(a.id)}">${esc(a.original_name)}</a><br><code>${esc(a.id)}</code></td><td>${esc(a.media_type)}</td><td><code>${esc(a.sha256)}</code></td><td>${esc(labels[a.scanner_status]||'Sem confirmação')} ${['generated','malware_detected'].includes(a.scanner_status)?'':`<button data-scan="${esc(a.id)}">Verificar arquivo</button>`}</td></tr>`).join('')}</table>`;
  list.querySelectorAll('[data-download]').forEach(a=>a.addEventListener('click',downloadAuthorized));
  list.querySelectorAll('[data-scan]').forEach(b=>b.addEventListener('click',async()=>{
   if(!current())return;b.disabled=true;message($('#upload-message'),'Verificação em andamento…',true);
   try{await api('/v1/artifacts/'+encodeURIComponent(b.dataset.scan)+'/rescan',{method:'POST'});
    if(current())message($('#upload-message'),'Arquivo verificado pelo antivírus.',true);
   }catch(e){if(current())message($('#upload-message'),e.message)}
   if(current())await Promise.allSettled([loadArtifacts(),loadInputContext(inputRevision.value)]);
  }));
 }catch(e){if(current())message(list,e.message)}
}
async function downloadAuthorized(e){e.preventDefault();try{const r=await fetch(e.currentTarget.href,{headers:{Authorization:`Bearer ${state.token}`,'X-Organization-ID':state.org}});if(!r.ok)throw new Error('Download negado');const blob=await r.blob();const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;const disposition=r.headers.get('Content-Disposition')||'';const match=/filename="([^"]+)"/i.exec(disposition);a.download=match?match[1].split(/[\\/]/).pop()||'artifact':'artifact';a.click();URL.revokeObjectURL(u)}catch(err){alert(err.message)}}
$('#upload-form').addEventListener('submit',async e=>{e.preventDefault();const org=state.org;const f=$('#upload-file').files[0];if(!f)return;const data=new FormData();data.append('upload',f);try{await api(`/v1/artifacts/${$('#upload-kind').value}`,{method:'POST',body:data});message($('#upload-message'),'Upload concluído.',true);await loadArtifacts()}catch(err){message($('#upload-message'),err.message)}});
"""
    + INPUT_JS
    + r"""
$('#review-create-form').addEventListener('submit',async e=>{e.preventDefault();try{const payload={resource_id:$('#review-resource').value,base_snapshot_id:$('#review-snapshot').value,category:$('#review-category').value,rule_code:$('#review-rule').value,field_path:$('#review-path').value,message:$('#review-message').value,evidence:[],alternatives:[]};if($('#review-job').value)payload.job_id=$('#review-job').value;const r=await api('/v1/reviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});message($('#review-create-message'),`Pendência criada: ${r.id}`,true);await loadReviews()}catch(err){message($('#review-create-message'),err.message)}});
async function loadReviews(){try{const rows=await api('/v1/reviews');$('#review-list').innerHTML=rows.map(r=>`<div class="item" data-review="${esc(r.id)}"><span class="badge">${esc(r.state)}</span><strong>${esc(r.rule_code)}</strong><p>${esc(r.message)}</p><small>v${r.version} · ${esc(r.field_path)}</small></div>`).join('')||'<p>Fila vazia.</p>';document.querySelectorAll('[data-review]').forEach(n=>n.addEventListener('click',()=>showReview(n.dataset.review)))}catch(e){message($('#review-list'),e.message)}}
async function showReview(id){try{const r=await api(`/v1/reviews/${id}`);const snap=await api(`/v1/snapshots/${r.base_snapshot_id}`);const history=await api(`/v1/reviews/${id}/history`);$('#review-detail').innerHTML=`<h2>${esc(r.rule_code)}</h2><p>${esc(r.message)}</p><h3>Evidências IDML/PDF</h3><pre>${esc(JSON.stringify(r.evidence,null,2))}</pre><h3>Alternativas</h3><pre>${esc(JSON.stringify(r.alternatives,null,2))}</pre><details><summary>Modelo canônico</summary><pre>${esc(JSON.stringify(snap.payload,null,2))}</pre></details><details><summary>Histórico</summary><pre>${esc(JSON.stringify(history,null,2))}</pre></details><button id="claim-review">Assumir</button><form id="decision-form"><label>Caminho<input id="patch-path" value="${esc(r.field_path)}" required></label><label>Valor JSON<textarea id="patch-value" required></textarea></label><label>Justificativa<textarea id="justification" minlength="10" required></textarea></label><button>Aplicar patch e revalidar</button><button type="button" id="reject-review">Encerrar sem alteração</button></form><div id="decision-result"></div>`;$('#claim-review').addEventListener('click',async()=>{try{const claimed=await api(`/v1/reviews/${id}/claim`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:r.version})});await showReview(claimed.id);await loadReviews()}catch(e){message($('#decision-result'),e.message)}});$('#reject-review').addEventListener('click',async()=>{try{const latest=await api(`/v1/reviews/${id}`);const result=await api(`/v1/reviews/${id}/decisions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:latest.version,action:'reject',patch:[],justification:$('#justification').value})});message($('#decision-result'),`Pendência encerrada: ${result.state}`,true);await loadReviews()}catch(err){message($('#decision-result'),err.message)}});$('#decision-form').addEventListener('submit',async e=>{e.preventDefault();try{const latest=await api(`/v1/reviews/${id}`);const value=JSON.parse($('#patch-value').value);const result=await api(`/v1/reviews/${id}/decisions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:latest.version,action:'apply_patch',patch:[{op:'replace',path:$('#patch-path').value,value}],justification:$('#justification').value})});const build=await api(`/v1/review-builds/${result.build_id}`);const diff=await api(`/v1/snapshots/${r.base_snapshot_id}/diff/${result.result_snapshot_id}`);$('#decision-result').innerHTML=`<p class="success">Nova versão: ${esc(result.result_snapshot_id)} · XML ${esc(result.xml_sha256)} · válido: ${result.validation_valid}</p><a href="/v1/review-builds/${esc(result.build_id)}/xml" data-build-download>Baixar XML</a><h3>Validação</h3><pre>${esc(JSON.stringify(build.validation,null,2))}</pre><h3>Diff</h3><pre>${esc(JSON.stringify(diff,null,2))}</pre>`;$('#decision-result [data-build-download]').addEventListener('click',downloadAuthorized);await loadReviews()}catch(err){message($('#decision-result'),err.message)}})}catch(e){message($('#review-detail'),e.message)}}
async function loadMembers(){try{const rows=await api(`/v1/organizations/${state.org}/members`);$('#member-list').innerHTML=`<table><tr><th>E-mail</th><th>Papel</th><th>Ativo</th></tr>${rows.map(m=>`<tr><td>${esc(m.email)}</td><td>${esc(m.role)}</td><td>${m.is_active?'sim':'não'}</td></tr>`).join('')}</table>`}catch(e){message($('#member-list'),e.message)}}
$('#invite-form').addEventListener('submit',async e=>{e.preventDefault();try{const r=await api(`/v1/organizations/${state.org}/invitations`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('#invite-email').value,role:$('#invite-role').value})});message($('#invite-message'),r.development_token?`Convite criado. Token: ${r.development_token}`:'Convite criado.',true);await loadMembers()}catch(err){message($('#invite-message'),err.message)}});
async function loadIdentity(){message($('#mfa-status'),state.me.mfa_enabled?'MFA habilitada.':'MFA ainda não habilitada.',state.me.mfa_enabled);const rows=await api('/v1/auth/sessions');$('#session-list').innerHTML=`<table><tr><th>Criada</th><th>MFA</th><th></th></tr>${rows.map(s=>`<tr><td>${esc(s.created_at)}</td><td>${s.mfa_verified_at?'sim':'não'}</td><td><button data-session="${esc(s.id)}">Revogar</button></td></tr>`).join('')}</table>`;document.querySelectorAll('[data-session]').forEach(b=>b.addEventListener('click',async()=>{await api(`/v1/auth/sessions/${b.dataset.session}`,{method:'DELETE'});await loadIdentity()}))}
$('#mfa-setup').addEventListener('submit',async e=>{e.preventDefault();try{const r=await api('/v1/auth/mfa/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('#mfa-password').value})});$('#mfa-secret').textContent=r.secret;$('#mfa-confirmation').hidden=false;message($('#mfa-status'),'Configuração iniciada.',true)}catch(err){message($('#mfa-status'),err.message)}});$('#mfa-confirm').addEventListener('click',async()=>{try{const r=await api('/v1/auth/mfa/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('#mfa-confirm-code').value})});$('#recovery-codes').textContent=`Códigos de recuperação (guarde agora):\n${r.recovery_codes.join('\n')}\n\nFaça login novamente com MFA.`;$('#recovery-codes').hidden=false;sessionStorage.removeItem('idml_token')}catch(err){message($('#mfa-status'),err.message)}});
async function loadReleases(){try{const rows=await api('/v1/releases');$('#release-list').innerHTML=`<table><tr><th>Pacote</th><th>Estado</th><th>Versão</th><th></th></tr>${rows.map(r=>`<tr><td><code>${esc(r.package_sha256.slice(0,16))}</code></td><td>${esc(r.state)}</td><td>${r.version}</td><td>${r.state==='pending'?`<button data-release="${esc(r.id)}" data-version="${r.version}">Aprovar</button>`:''}</td></tr>`).join('')}</table>`;document.querySelectorAll('[data-release]').forEach(b=>b.addEventListener('click',async()=>{const justification=prompt('Justificativa (mínimo 20 caracteres)');const evidence=prompt('SHA-256 da evidência');if(!justification||!evidence)return;try{await api(`/v1/releases/${b.dataset.release}/approvals`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:Number(b.dataset.version),justification,evidence_sha256:evidence})});await loadReleases()}catch(err){message($('#release-message'),err.message)}}))}catch(e){message($('#release-list'),e.message)}}
$('#release-form').addEventListener('submit',async e=>{e.preventDefault();try{await api('/v1/releases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resource_id:$('#release-resource').value,snapshot_id:$('#release-snapshot').value,package_sha256:$('#release-sha').value})});message($('#release-message'),'Solicitação criada. São necessárias duas aprovações distintas.',true);await loadReleases()}catch(err){message($('#release-message'),err.message)}});
async function loadAudit(){try{const rows=await api('/v1/audit');$('#audit-list').innerHTML=`<table><tr><th>Data</th><th>Ação</th><th>Ator</th><th>Resultado</th></tr>${rows.map(x=>`<tr><td>${esc(x.created_at)}</td><td>${esc(x.action)}</td><td>${esc(x.actor_user_id)}</td><td>${esc(x.outcome)}</td></tr>`).join('')}</table>`}catch(e){message($('#audit-list'),e.message)}}$('#audit-export').addEventListener('click',downloadAuthorized);if (!openRecoveryLink()) boot();"""
)


@router.get("/app", response_class=HTMLResponse)
def application_shell() -> str:
    return (
        _HTML.replace(
            '<button data-view="reviews">',
            '<button data-view="evaluations">Avaliação do XML</button><button data-view="reviews">',
        )
        .replace('<section id="reviews"', EVALUATION_HTML + '<section id="reviews"')
        .replace("</body>", '<script src="/app/assets/evaluation.js" defer></script></body>')
        .replace(
            '<button data-view="audit">',
            '<button data-view="sources">Fontes públicas</button><button data-view="audit">',
        )
        .replace('<section id="audit"', SOURCE_ACCESS_HTML + '<section id="audit"')
        .replace("</body>", '<script src="/app/assets/sources.js" defer></script></body>')
    )


@router.get("/app/assets/app.css")
def application_css() -> Response:
    return Response(_CSS, media_type="text/css")


@router.get("/app/assets/app.js")
def application_javascript() -> Response:
    return Response(_JS, media_type="text/javascript")
