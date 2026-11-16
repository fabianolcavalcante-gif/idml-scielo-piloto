# ruff: noqa: E501
"""Named inputs for conversion and revision-bound packaging in the portal."""

HTML = """
<section id="uploads" class="view card" hidden><h1>Artigos e arquivos</h1>
<label>Artigo<select id="input-article"></select></label>
<details id="input-create" hidden><summary>Criar artigo</summary>
<form id="resource-form"><label>Título operacional<input id="resource-title" required></label>
<button>Criar artigo</button></form></details><p id="resource-message" role="status"></p>
<div id="input-upload" hidden><h2>Enviar arquivo</h2>
<form id="upload-form"><label>Tipo<select id="upload-kind"><option value="idml">IDML</option>
<option value="assets">PDF/JPG/PNG</option></select></label>
<input aria-label="Arquivo para envio" id="upload-file" type="file" required><button>Enviar</button></form>
<p id="upload-message" role="status"></p>
<details><summary>Arquivos e verificações da empresa</summary><div id="artifacts"></div></details></div>
<div id="input-context" hidden>
<form id="process-form" hidden><h2>Converter IDML</h2><label>Arquivo IDML<select id="process-idml" required></select></label>
<button>Enfileirar conversão</button></form><p id="process-message" role="status"></p>
<h2>Revisão e pacote SciELO</h2><label>Revisão do artigo<select id="package-snapshot"></select></label>
<button type="button" id="input-refresh">Atualizar revisões e pacote</button>
<p id="input-source"></p><p id="input-receipt"></p>
<form id="package-form" hidden><label>PDF do artigo<select id="package-pdf" required></select></label>
<fieldset><legend>Imagens do artigo</legend><div id="package-assets"></div></fieldset>
<button>Enfileirar pacote</button></form><p id="package-message" role="status"></p>
</div></section>"""

JS = r"""
const inputArticle=$('#input-article'), inputRevision=$('#package-snapshot');
let inputGeneration=0, articleGeneration=0, inputOrg=null, inputData=null;
const canWriteInputs=()=>
    ['operator','org_admin'].includes($('#organization').selectedOptions[0]?.dataset.role);
function inputOptions(select, rows, placeholder, value=''){
    select.replaceChildren(new Option(placeholder,''), ...rows.map(([id,label])=>new Option(label,id)));
    select.value=value||'';
}
function clearInputContext(){
    inputGeneration++; inputData=null;
    $('#input-context').hidden=true;
    for(const id of ['process-message','package-message','input-source','input-receipt']){
        $('#'+id).replaceChildren();
    }
}
async function loadResources(preferred){
    const generation=++articleGeneration, org=state.org;
    if(inputOrg!==org){
        inputOrg=org; clearInputContext(); inputArticle.replaceChildren();
        $('#upload-form').reset(); $('#resource-form').reset();
        $('#resource-message').replaceChildren(); $('#upload-message').replaceChildren();
    }
    $('#input-create').hidden=$('#input-upload').hidden=!canWriteInputs();
    try{
        const rows=await api('/v1/resources');
        if(generation!==articleGeneration || state.org!==org)return;
        const selected=preferred??inputArticle.value;
        const counts=new Map();
        for(const row of rows)counts.set(row.title,(counts.get(row.title)||0)+1);
        inputOptions(inputArticle,rows.map(r=>[r.id,counts.get(r.title)>1?r.title+' · '+r.id.slice(0,8):r.title]),'Escolha um artigo',selected);
        await loadInputContext(inputData?.selected);
    }catch(e){if(generation===articleGeneration){clearInputContext();message($('#resource-message'),e.message)}}
}
async function loadInputContext(revision){
    const resource=inputArticle.value, org=state.org;
    clearInputContext(); const generation=inputGeneration;
    if(!resource)return;
    try{
        const query=revision?'?snapshot_id='+encodeURIComponent(revision):'';
        const data=await api('/v1/resources/'+encodeURIComponent(resource)+'/input-workspace'+query);
        if(org!==state.org || generation!==inputGeneration)return;
        inputData=data;
        const files=new Map(data.files.map(f=>[f.id,f]));
        const label=f=>f.original_name+' · '+f.sha256.slice(0,8);
        const options=type=>data.files.filter(f=>f.media_type===type).map(f=>[f.id,label(f)]);
        inputOptions(inputRevision,data.revisions.map(r=>[r.id,'Revisão '+r.revision+(r.id===data.current?' (atual)':'')]),'Escolha uma revisão',data.selected);
        const source=data.revisions.find(r=>r.id===data.selected)?.source_artifact_id;
        inputOptions($('#process-idml'),options('application/vnd.adobe.indesign-idml-package'),'Escolha o IDML',source);
        $('#process-form').hidden=!data.can_start;
        $('#input-source').textContent=data.selected?(files.has(source)?'IDML da revisão — '+label(files.get(source)):'O IDML desta revisão precisa de verificação.'):'A revisão aparecerá após a conclusão da conversão. Use Atualizar revisões e pacote.';
        inputOptions($('#package-pdf'),options('application/pdf'),'Escolha o PDF',data.pdf);
        const images=$('#package-assets'); images.replaceChildren();
        // Preserve the recorded package order, also for names whose lexical order differs.
        const prior=new Set(data.images);
        const choices=[...data.images.map(id=>files.get(id)).filter(Boolean),
            ...data.files.filter(f=>f.media_type.startsWith('image/')&&!prior.has(f.id))];
        for(const file of choices){
            const item=document.createElement('label'), box=document.createElement('input');
            box.type='checkbox';box.value=file.id;box.checked=prior.has(file.id);
            item.append(box,document.createTextNode(label(file)));images.append(item);
        }
        const receipt=$('#input-receipt');
        if(data.package_job){
            receipt.append('Último pacote desta revisão. PDF: '+(files.get(data.pdf)?.original_name||'indisponível')+
                '. Imagens: '+(data.images.map(id=>files.get(id)?.original_name||'indisponível').join(', ')||'nenhuma')+'. ');
            if(data.package_artifact){
                const a=document.createElement('a');a.href='/v1/artifacts/'+encodeURIComponent(data.package_artifact)+'/download';
                a.textContent='Baixar ZIP de avaliação';a.addEventListener('click',downloadAuthorized);receipt.append(a,' ');
            }
            const b=document.createElement('button');b.type='button';b.textContent='Ver diagnóstico do pacote';
            b.onclick=()=>{$('[data-view="dashboard"]').click();loadDiagnosis(data.package_job)};receipt.append(b);
        }
        $('#package-form').hidden=!data.can_start || !files.has(source);
        if(data.images.some(id=>!files.has(id))){
            $('#package-form').hidden=true;
            message($('#package-message'),'Verifique as imagens indisponíveis do pacote anterior antes de repetir.');
        }
        $('#input-context').hidden=false;
    }catch(e){if(generation===inputGeneration)message($('#resource-message'),e.message)}
}
inputArticle.onchange=()=>loadInputContext();
inputRevision.onchange=()=>loadInputContext(inputRevision.value);
$('#input-refresh').onclick=()=>loadInputContext();
$('#resource-form').onsubmit=async e=>{
    e.preventDefault();const org=state.org,button=e.target.querySelector('button');button.disabled=true;
    try{
        const r=await api('/v1/resources',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('#resource-title').value})});
        if(state.org!==org)return;
        clearInputContext();await loadResources(r.id);
        $('#resource-form').reset();message($('#resource-message'),'Artigo criado.',true);
    }catch(err){if(state.org===org)message($('#resource-message'),err.message)}finally{button.disabled=false}
};
async function enqueueInput(e){
    e.preventDefault();const form=e.target, convert=form.id==='process-form', data=inputData;
    if(!data?.can_start || !inputArticle.value)return;
    const org=state.org,generation=inputGeneration;
    const payload={resource_id:inputArticle.value};
    if(convert)payload.idml_artifact_id=$('#process-idml').value;
    else{
        payload.canonical_snapshot_id=data.selected;
        payload.idml_artifact_id=data.revisions.find(r=>r.id===data.selected).source_artifact_id;
        payload.pdf_artifact_id=$('#package-pdf').value;
        payload.asset_artifact_ids=Array.from($('#package-assets').querySelectorAll('input:checked'),b=>b.value);
    }
    const kind=convert?'idml.process':'scielo.package';
    const intent='input:'+JSON.stringify([org,state.me.id,kind,payload]);
    const button=form.querySelector('button'),status=$(convert?'#process-message':'#package-message');
    button.disabled=true;
    try{
        const bytes=crypto.getRandomValues(new Uint8Array(16));
        const key=sessionStorage.getItem(intent)||Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
        sessionStorage.setItem(intent,key);
        await api('/v1/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,idempotency_key:key,payload})});
        sessionStorage.removeItem(intent);
        if(org!==state.org || generation!==inputGeneration)return;
        message(status,(convert?'Conversão enfileirada.':'Pacote enfileirado.')+' Acompanhe em Jobs e atualize a revisão ao concluir.',true);
        await loadJobs();
    }catch(err){if(generation===inputGeneration)message(status,err.message)}finally{button.disabled=false}
}
$('#process-form').onsubmit=enqueueInput;
$('#package-form').onsubmit=enqueueInput;
"""
