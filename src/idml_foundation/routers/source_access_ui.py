# ruff: noqa: E501
from fastapi import APIRouter, Response

router = APIRouter(tags=["interface"])

HTML = """<section id="sources" class="view card" hidden><h1>Fontes públicas do artigo</h1>
<p>Administradores e operadores habilitados pela empresa podem autorizar consultas ao Crossref, ORCID e cadastro SciELO para validar este artigo. A autorização permite armazenar os registros consultados na VPS durante sua vigência. Não autoriza alterar o XML nem publicar o artigo.</p>
<label>Artigo<select id="source-article"><option value="">Selecione um artigo</option></select></label>
<p id="source-status" role="status"></p><label>Validade<select id="source-days"><option value="7">7 dias</option><option value="30">30 dias</option></select></label>
<button id="source-grant" disabled>Autorizar / renovar consultas</button> <button id="source-revoke" disabled>Revogar autorização</button>
<p id="source-message" role="alert"></p><p>Converta primeiro o IDML no perfil habilitado. Ao trocar o arquivo de origem, será necessária uma nova autorização. Avisos editoriais e identidades não confirmadas permanecem para revisão.</p></section>"""

JS = r"""(()=>{
let selected=null, generation=0;
const disable=()=>{selected=null;$('#source-grant').disabled=true;$('#source-revoke').disabled=true};
const labels={not_authorized:'Sem autorização',active:'Autorização ativa',revoked:'Autorização revogada',inactive:'Autorização inativa: verifique validade, origem e administrador'};
async function status(){const ticket=++generation;disable();const resource=$('#source-article').value,org=state.org;if(!resource){$('#source-status').textContent='Selecione um artigo.';return}try{const r=await api(`/v1/resources/${encodeURIComponent(resource)}/public-sources`);if(ticket!==generation||org!==state.org)return;selected={org,resource,sequence:r.sequence};$('#source-status').textContent=labels[r.status]+(r.expires_at?' · validade: '+new Date(r.expires_at).toLocaleString('pt-BR'):'');$('#source-grant').disabled=!r.can_manage;$('#source-revoke').disabled=!r.can_manage||(!r.sequence && r.status!=='active')}catch(e){if(ticket===generation&&org===state.org)message($('#source-message'),e.message)}}
async function load(){const ticket=++generation,org=state.org;disable();$('#source-article').innerHTML='<option value="">Selecione um artigo</option>';$('#source-status').textContent='';$('#source-message').textContent='';try{const articles=await api('/v1/resources');if(ticket!==generation||org!==state.org)return;for(const a of articles){const option=document.createElement('option');option.value=a.id;option.textContent=a.title;$('#source-article').append(option)}}catch(e){if(ticket===generation&&org===state.org)message($('#source-message'),e.message)}}
async function decide(action){const current=selected;if(!current||current.org!==state.org)return;const ticket=++generation;const stillCurrent=()=>ticket===generation&&current.org===state.org&&current.resource===$("#source-article").value;disable();try{await api(`/v1/resources/${encodeURIComponent(current.resource)}/public-sources`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:crypto.randomUUID(),expected_sequence:current.sequence,action,days:Number($('#source-days').value)})});if(!stillCurrent())return;message($('#source-message'),action==='grant'?'Consultas autorizadas. Gere um novo pacote para obter a validação atualizada.':'Autorização revogada. Relatórios anteriores permanecem no histórico.',true);await status()}catch(e){if(!stillCurrent())return;message($('#source-message'),e.message);await status()}}
$('#source-article').addEventListener('change',status);$('#source-grant').addEventListener('click',()=>decide('grant'));$('#source-revoke').addEventListener('click',()=>decide('revoke'));document.querySelector('[data-view="sources"]').addEventListener('click',load);$('#organization').addEventListener('change',()=>{generation++;disable();if(!$('#sources').hidden)load()});
})();"""


@router.get("/app/assets/sources.js")
def javascript() -> Response:
    return Response(JS, media_type="text/javascript")
