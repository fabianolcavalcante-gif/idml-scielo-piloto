# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(tags=["interface"])
HTML = """<section id="evaluations" class="view card" hidden>
<h1>Avaliação do XML</h1>
<label>Artigo<select id="eval-article"></select></label>
<label>Revisão canônica<select id="eval-revision" disabled></select></label>
<button id="eval-start" disabled>Iniciar avaliação</button>
<button id="eval-authorize" hidden disabled>Autorizar correção por IA</button>
<button id="eval-restore" hidden disabled>Reverter correção</button>
<button id="eval-refresh" disabled>Atualizar resultado</button>
<p id="eval-message" role="status"></p><div id="eval-result" aria-live="polite"></div>
</section>"""

JS = r"""(()=>{
const panel=$('#evaluations'), article=$('#eval-article'), revision=$('#eval-revision');
const start=$('#eval-start'), refresh=$('#eval-refresh'), status=$('#eval-message'), result=$('#eval-result');
const restore=$('#eval-restore'), authorize=$('#eval-authorize');
let generation=0, selection=null, timer=0, submitting=false;
const labels={already_corrected_use_recovery:'A correção já existe. Use Recuperar revisão corrigida e revalidar.',revision_package_required:'Gere o pacote desta revisão com o PDF e as figuras em Uploads.',operator_authorization_required:'O pedido exige um operador ativo nesta empresa.',authorization_expired:'A autorização venceu. Envie uma nova solicitação.',operation_outside_web_scope:'A operação exige avaliação editorial.',queued:'Na fila',running:'Em andamento',succeeded:'Concluída',failed_permanent:'Falha',failed_retryable:'Aguardando nova tentativa',staged:'Candidato separado',applied:'Correção aplicada ao rascunho',blocked:'Bloqueada',refused:'Recusada',abstained:'Abstenção','revalidated-working-draft':'Revisão recuperada e revalidada',snapshot:'Registro de revisão',restore:'Restauração','autocorrection-promotion':'Aplicação ao rascunho',batch_authorization_required:'Falta autorização de edição para esta revisão.',provider_window_closed:'O candidato está preparado. A janela do provedor está fechada.',no_eligible_field:'Nenhum campo tem evidência suficiente para correção.',decision_already_used:'Essa autorização já foi utilizada.',native_validation:'Validação nativa concluída.',candidate_requires_full_revalidation:'O candidato requer revalidação formal.'};
function text(parent,tag,value){const el=document.createElement(tag);el.textContent=value;parent.append(el);return el}
function reset(){generation++;clearTimeout(timer);selection=null;submitting=false;authorize.hidden=authorize.disabled=true;restore.hidden=restore.disabled=true;start.disabled=refresh.disabled=true;result.replaceChildren();status.textContent=''}
function active(ticket,org){return ticket===generation && org===state.org && !panel.hidden}
function option(select,value,label){const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o)}
function showFormal(row,parent){text(parent,'p','SHA-256 do XML · '+row.xml_sha256);for(const item of row.items){text(parent,'p',item.title+' — '+item.detail)}
 for(const [id,label] of [[row.xml_id,'Baixar XML de avaliação'],[row.zip_id,'Baixar ZIP de avaliação']]){
  if(!id)continue;
  const link=document.createElement('a');link.href='/v1/artifacts/'+encodeURIComponent(id)+'/download';
  link.textContent=label;link.addEventListener('click',downloadAuthorized);parent.append(link,' ');
 }
}
function render(data){
 result.replaceChildren();
 const section=(title)=>{const el=document.createElement('section');result.append(el);text(el,'h2',title);return el};
 const jobs=section('Avaliações solicitadas');
 if(!data.jobs.length)text(jobs,'p','Nenhuma avaliação registrada nesta revisão.');
 for(const job of data.jobs){
  text(jobs,'p',[labels[job.state]||job.state,labels[job.result]||job.result,labels[job.reason]||job.reason,
   job.provider_calls==null?'':'Chamadas de IA: '+job.provider_calls,
   job.cost_microusd==null?'':'Custo estimado: US$ '+(job.cost_microusd/1000000).toLocaleString('pt-BR',{maximumFractionDigits:6})].filter(Boolean).join(' · '));
 }
 const diffs=section('Diferenças no XML');
 if(!data.candidates.length)text(diffs,'p','Nenhum candidato registrado para comparação.');
 for(const c of data.candidates){
  for(const d of c.diff){text(diffs,'h3','Antes da avaliação');text(diffs,'pre',d.before);text(diffs,'h3','XML candidato');text(diffs,'pre',d.after)}
  if(!c.validations.length)text(diffs,'p','Sem revalidação formal registrada para este candidato.');
  for(const v of c.validations)showFormal(v,diffs);
 }
 const hist=section('Histórico e restaurações');
 for(const e of data.transitions)text(hist,'p','Evento '+e.sequence+' · '+(labels[e.action]||e.action));
 for(const r of data.restorations){text(hist,'h3',labels[r.state]||r.state);showFormal(r,hist)}
 if(!data.restorations.length)text(hist,'p','Nenhuma restauração para esta revisão.');
}
async function detail(){
 clearTimeout(timer); const ticket=++generation,org=state.org;
 const id=article.value,rev=revision.value; start.disabled=true;refresh.disabled=true;result.replaceChildren();
 if(!selection||!rev)return;
 try{
  const path='/v1/resources/'+encodeURIComponent(id)+'/edit-revisions';
  const [data,latest]=await Promise.all([api(path+'/'+encodeURIComponent(rev)),api(path)]);
  if(!active(ticket,org))return;selection=latest;revision.replaceChildren();for(const row of latest.revisions)option(revision,row.id,'Revisão '+row.revision+(row.id===latest.current?' · atual':'')+' · '+row.sha256.slice(0,12));revision.value=rev;render(data);
  restore.hidden=!latest.can_start || !latest.restore_action || latest.current!==rev;
  restore.textContent=latest.restore_action==='recover'?'Recuperar revisão corrigida e revalidar':'Reverter correção e revalidar';
  const pending=data.jobs.some(j=>['queued','running','failed_retryable'].includes(j.state));
  authorize.hidden=!latest.can_start||latest.current!==rev;authorize.disabled=authorize.hidden||submitting||pending;restore.disabled=restore.hidden||submitting||pending;refresh.disabled=false;start.disabled=submitting||pending||!selection.can_start||selection.current!==rev;
  status.textContent=pending?'Aguardando o worker. O resultado será atualizado automaticamente.':
   selection.current!==rev?'Revisão histórica disponível para consulta.':!selection.can_start?'Perfil de consulta.':'Revisão atual selecionada.';
  if(pending)timer=setTimeout(detail,2500);
 }catch(e){if(active(ticket,org)){refresh.disabled=false;status.textContent=e.message}}
}
async function loadRevisions(){
 reset();revision.replaceChildren();revision.disabled=true;
 if(!article.value)return;const ticket=generation,org=state.org;
 try{
  const r=await api('/v1/resources/'+encodeURIComponent(article.value)+'/edit-revisions');
  if(!active(ticket,org))return;selection=r;
  for(const row of r.revisions)option(revision,row.id,'Revisão '+row.revision+(row.id===r.current?' · atual':'')+' · '+row.sha256.slice(0,12));
  if(!r.current){status.textContent='Converta o IDML deste artigo para criar uma revisão.';return}
  revision.disabled=false;revision.value=r.current;await detail();
 }catch(e){if(active(ticket,org))status.textContent=e.message}
}
async function load(){
 reset();article.replaceChildren();revision.replaceChildren();revision.disabled=true;option(article,'','Selecione um artigo');
 const ticket=generation,org=state.org;
 try{const rows=await api('/v1/resources');if(!active(ticket,org))return;for(const r of rows)option(article,r.id,r.title);if(!rows.length)status.textContent='Nenhum artigo cadastrado nesta empresa.'}
 catch(e){if(active(ticket,org))status.textContent=e.message}
}
start.addEventListener('click',async()=>{
 if(!selection||start.disabled||revision.value!==selection.current)return;
 const org=state.org,ticket=generation;submitting=true;start.disabled=refresh.disabled=true;
 try{await api('/v1/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
  kind:'autocorrection.evaluate',idempotency_key:crypto.randomUUID(),payload:{resource_id:article.value,canonical_snapshot_id:revision.value,review_version:selection.review_version}})});
  if(active(ticket,org)){submitting=false;await detail()}
 }catch(e){if(active(ticket,org)){submitting=false;status.textContent=e.message;refresh.disabled=false}}
});
authorize.addEventListener('click',async()=>{
 if(submitting||authorize.disabled||!selection||revision.value!==selection.current)return;
 if(!window.confirm('Autorizar o envio ao OpenClaw do trecho de afiliação comprovado no IDML desta revisão? A correção do rascunho depende da revalidação do pacote.'))return;
 const org=state.org,ticket=generation,payload={resource_id:article.value,canonical_snapshot_id:revision.value,review_version:selection.review_version};
 const intent='authorize:'+JSON.stringify([org,state.me.id,payload]);
 submitting=true;authorize.disabled=start.disabled=restore.disabled=refresh.disabled=true;
 try{const key=sessionStorage.getItem(intent)||crypto.randomUUID();sessionStorage.setItem(intent,key);
  await api('/v1/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'autocorrection.authorize',idempotency_key:key,payload})});
  sessionStorage.removeItem(intent);if(active(ticket,org)){submitting=false;await detail()}
 }catch(e){if(active(ticket,org)){submitting=false;authorize.disabled=false;refresh.disabled=false;status.textContent=e.message}}
});
restore.addEventListener('click',async()=>{
 if(submitting||restore.disabled||!selection?.restore_action||revision.value!==selection.current)return;
 const action=selection.restore_action, org=state.org, ticket=generation;
 if(!window.confirm(action==='undo'?'Voltar à revisão anterior e revalidar o pacote?':'Recuperar a revisão corrigida e revalidar o pacote?'))return;
 const payload={resource_id:article.value,canonical_snapshot_id:revision.value,review_version:selection.review_version,action};
 const intent='restore:'+JSON.stringify([org,state.me.id,payload]);
 submitting=true;restore.disabled=start.disabled=refresh.disabled=true;
 try{
  const key=sessionStorage.getItem(intent)||crypto.randomUUID();sessionStorage.setItem(intent,key);
  const job=await api('/v1/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'autocorrection.restore',idempotency_key:key,payload})});
  sessionStorage.removeItem(intent);
  if(!active(ticket,org))return;
  status.textContent='Revalidação enfileirada. Acompanhe também em Jobs.';
  for(let i=0;i<180;i++){
   await new Promise(resolve=>setTimeout(resolve,2000));
   if(!active(ticket,org))return;
   const j=await api('/v1/jobs/'+encodeURIComponent(job.id));
   if(!active(ticket,org))return;
   if(['queued','running','failed_retryable'].includes(j.state))continue;
   if(j.state==='succeeded' && j.result?.active_snapshot_changed){await loadRevisions();return}
   throw new Error(j.result?.reason==='restore_validation_unavailable'?'Validação incompleta. A revisão anterior continua selecionada. Verifique as fontes e tente novamente.':'Restauração recusada. Atualize a revisão e consulte o job.');
  }
  throw new Error('O processamento continua. Consulte Jobs e atualize a revisão ao concluir.');
 }catch(e){if(active(ticket,org)){submitting=false;status.textContent=e.message;refresh.disabled=false;restore.disabled=false}}
});
article.addEventListener('change',loadRevisions);revision.addEventListener('change',detail);refresh.addEventListener('click',detail);
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>b.dataset.view==='evaluations'?load():reset()));
$('#organization').addEventListener('change',()=>{reset();if(!panel.hidden)load()});
})();"""


@router.get("/app/assets/evaluation.js")
def javascript() -> Response:
    return Response(JS, media_type="text/javascript")
