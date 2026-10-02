const $ = id => document.getElementById(id);
const names = {'1':'1 · Gemini vision','3':'3 · OCR + Gemini','4':'4 · PaddleOCR-VL','5':'5 · Hybrid'};
let jobId = sessionStorage.getItem('eastcoJob'), timer = null;
const groups = {
 connections: [
  ['GEMINI_API_KEY','AI Studio API key','password'],['GEMINI_VLM_MODEL','Vision model','text','gemini-3.8-flash'],['GEMINI_LLM_MODEL','Text model','text','gemini-3.8-flash'],
  ['PADDLE_OCR_URL','PaddleOCR Cloud Run URL','url'],['PADDLE_OCR_TOKEN','PaddleOCR ID token','password'],['PADDLE_VL_URL','PaddleOCR-VL Cloud Run URL','url'],['PADDLE_VL_TOKEN','PaddleOCR-VL ID token','password']],
 rates: [['COST_CURRENCY','Currency','text','USD'],['VLM_INPUT_PER_MILLION','Vision input / million tokens','number'],['VLM_OUTPUT_PER_MILLION','Vision output / million tokens','number'],['LLM_INPUT_PER_MILLION','Text input / million tokens','number'],['LLM_OUTPUT_PER_MILLION','Text output / million tokens','number'],['OCR_ACTIVE_PER_SECOND','OCR active compute / second','number'],['VL_ACTIVE_PER_SECOND','OCR-VL active compute / second','number']],
 overhead: [['IDLE_COST','Idle capacity'],['STORAGE_COST','Storage'],['NETWORK_COST','Network'],['LOGGING_COST','Logging'],['BUILD_COST','Build / deployment'],['OTHER_COST','Other allocated costs'],['TAX_COST','Allocated tax']].map(x=>[...x,'number']),
 billing: [['BILLING_TABLE','Billing export table','text',''],['BILLING_QUERY_PROJECT','BigQuery execution project'],['BILLING_PROJECT_IDS','Billed project IDs (comma separated)'],['BILLING_LOCATION','BigQuery location','text','US'],['BILLING_ACCESS_TOKEN','Google billing access token','password'],['BILLING_SCOPE','Project allocation','select','shared',['shared','dedicated']],['BILLING_ALLOCATION_FRACTION','Shared-project fraction (0–1)','number'],['BILLING_START','Billing start (ISO timestamp)'],['BILLING_END','Billing end (ISO timestamp)'],['BILLING_AUTO_REFRESH','Refresh after live run','select','false',['false','true']],['BILLING_MAX_BYTES','Maximum query bytes','number','1000000000']],
 advanced: [['VERIFIED_DATES','Verified reference dates','text','20260801'],['MAX_RETRIES','Retries per API request','number','2'],['REQUEST_TIMEOUT','Request timeout (seconds)','number','180'],['HYBRID_THRESHOLD','Completeness threshold','number','1']]
};
for (const [section, fields] of Object.entries(groups)) {
 for (const [key,label,type='text',initial='',choices] of fields) {
  const wrap=document.createElement('label'); wrap.append(document.createTextNode(label));
  const input=document.createElement(type==='select'?'select':'input'); input.id=key; input.dataset.setting='1';
  if(type==='select') for(const choice of choices) { const option=document.createElement('option'); option.value=choice; option.textContent=choice; input.append(option); }
  else {input.type=type;input.autocomplete='off'; if(type==='number'){input.min='0';input.step='any';}}
  input.value=initial; if(!initial) input.placeholder=type==='number'?'Unknown':type==='password'?'Not configured':'';
  if(key==='BILLING_TABLE')input.placeholder='project.dataset.gcp_billing_export_v1_…';
  if(key.endsWith('_URL'))input.placeholder='https://service-region.run.app';
  wrap.append(input); $(section).append(wrap);
 }
}
function settings(){return Object.fromEntries([...document.querySelectorAll('[data-setting]')].map(i=>[i.id,i.value]));}
function notice(message){$('notice').textContent=message;$('notice').hidden=!message;}
function view(name){document.querySelectorAll('.view').forEach(x=>x.hidden=x.id!=='view-'+name);document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.view===name));}
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>view(b.dataset.view)));
async function api(path,body,method='POST',headers={}){
 const response=await fetch(path,{method,headers:{'X-Eastco-Request':'1',...(body instanceof Blob?{}:{'Content-Type':'application/json'}),...headers},body:method==='GET'?undefined:body instanceof Blob?body:JSON.stringify(body||{})});
 const data=await response.json(); if(!response.ok){const error=Error(data.error||'Request failed');error.status=response.status;throw error;} return data;
}
async function init(){
 try {const data=await api('/api/config',null,'GET');for(const [k,v] of Object.entries(data.values))if($(k)&&v)$(k).value=v;for(const k of data.configured_secrets)if($(k))$(k).placeholder='Configured on server';$('login').hidden=true;$('workspace').hidden=false;}
 catch(err) {if(err.status!==401){notice(err.message);return;}try {await api('/api/login',{password:''});const data=await api('/api/config',null,'GET');for(const [k,v]of Object.entries(data.values))if($(k)&&v)$(k).value=v;for(const k of data.configured_secrets)if($(k))$(k).placeholder='Configured on server';}catch{$('login').hidden=false;$('workspace').hidden=true;}}
}
$('loginForm').addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/login',{password:$('password').value});$('password').value='';await init();notice('');}catch(err){alert(err.message);}});
$('dataset').addEventListener('change',()=>{const f=$('dataset').files[0];$('fileMeta').textContent=f?`${(f.size/1048576).toFixed(1)} MB`:'No file selected';});
$('runForm').addEventListener('submit',async e=>{
 e.preventDefault();notice('');const file=$('dataset').files[0];if(!file)return;
 $('runButton').disabled=true;$('progress').hidden=false;$('status').textContent='Uploading';
 try {
  const created=await api('/api/uploads',{size:file.size});jobId=created.id;sessionStorage.setItem('eastcoJob',jobId);
  for(let offset=0;offset<file.size;offset+=8*1024*1024){await api(`/api/jobs/${jobId}/chunk`,file.slice(offset,offset+8*1024*1024),'PUT',{'X-Upload-Offset':String(offset)});const percent=Math.min(100,100*(offset+8*1024*1024)/file.size);$('progress').value=percent;$('progressText').textContent=`Uploading ${Math.round(percent)}%`;}
  const options={mode:$('mode').value,method:$('method').value,date:$('date').value,limit:Number($('limit').value),repeat:Number($('repeat').value),concurrency:Number($('concurrency').value)};
  await api(`/api/jobs/${jobId}/run`,{settings:settings(),options});
  for(const input of document.querySelectorAll('input[type=password]')) input.value='';
  $('progressText').textContent='Processing submissions…';poll();
 }catch(err){notice(err.message);$('runButton').disabled=false;$('status').textContent='Needs attention';}
});
async function poll(){
 try{const job=await api(`/api/jobs/${jobId}`,null,'GET');$('status').textContent=job.status;
  if(job.status==='complete'){render(job.summary);view('results');$('runButton').disabled=false;$('progress').hidden=true;$('progressText').textContent='Completed';return;}
  if(job.status==='uploading'){await api(`/api/jobs/${jobId}/delete`,{});sessionStorage.removeItem('eastcoJob');throw Error('The upload was interrupted. Select the ZIP and start again.');}
  if(job.status==='failed')throw Error(job.error);timer=setTimeout(poll,1200);
 }catch(err){if(err.status===404)sessionStorage.removeItem('eastcoJob');notice(err.message);$('runButton').disabled=false;$('progressText').textContent='';}
}
function cell(tr,text,tag='td'){const td=document.createElement(tag);td.textContent=text;tr.append(td);}
function money(value,currency){return value==null?'Unknown':`${currency} ${Number(value).toFixed(6)}`;}
function render(summary){
 $('empty').hidden=true;$('report').hidden=false;
 const cost=summary.cost_report, currency=cost.currency, methods=Object.entries(summary.methods);
 $('runMeta').textContent=`${summary.mode==='dry'?'DRY RUN · No provider measurements':'LIVE RUN'} · ${summary.dataset.length} tenant/date groups · ${summary.repeat} repeat(s) · concurrency ${summary.concurrency}`;
 $('total').textContent=money(cost.estimated_total,currency);$('count').textContent=methods[0][1].submissions;$('images').textContent=summary.dataset.reduce((n,s)=>n+s.images,0);$('coverage').textContent=cost.status==='estimate_complete'?'Complete estimate':summary.mode==='dry'?'Dry run':'Incomplete';
 $('costState').className='costState'+(cost.status==='estimate_complete'?'':' warning');
 $('costState').textContent=summary.mode==='dry'?'Dry run: no APIs called. Cost, accuracy and provider speed are not measured.':cost.status==='estimate_complete'?'Estimate includes the configured processing rates and allocated overhead. Billing charges are reported separately below.':`Total remains unknown until usage rates and all overhead categories are supplied. Missing overhead: ${cost.missing_overhead.join(', ')||'none; check processing prices or unreported usage'}.`;
 $('comparison').replaceChildren();for(const [method,m]of methods){const tr=document.createElement('tr');const c=cost.methods[method];for(const val of [names[method],money(c.estimated_total,currency),money(c.estimated_per_submission,currency),m.latency_p50_ms==null?'—':`${m.latency_p50_ms.toFixed(1)} ms`,m.latency_p95_ms==null?'—':`${m.latency_p95_ms.toFixed(1)} ms`,m.accuracy==null?'Not scored':`${(m.accuracy*100).toFixed(1)}% (${m.scored_submissions})`,m.failures,m.fallbacks])cell(tr,val);$('comparison').append(tr);}
 $('costBreakdown').replaceChildren();for(const [label,value]of Object.entries(cost.overhead_for_entire_run)){const div=document.createElement('div');div.className='costRow';const name=document.createElement('span');name.textContent=label.replaceAll('_',' ');const amount=document.createElement('span');amount.textContent=money(value,currency);div.append(name,amount);$('costBreakdown').append(div);}
 $('usage').textContent=JSON.stringify(summary.methods,null,2);$('summaryDownload').href=`/api/jobs/${jobId}/summary`;$('detailsDownload').href=`/api/jobs/${jobId}/details`;
 $('refreshBilling').disabled=summary.mode==='dry';renderBilling(summary.billing);
}
function renderBilling(billing){$('billingTable').replaceChildren();$('billingState').textContent=billing?`${billing.status}: ${billing.message||''}`:'Not queried. Set billing export details to retrieve delayed charges.';if(!billing?.services?.length)return;const table=document.createElement('table');const head=document.createElement('tr');['Service','Currency','Before credits','Credits','Net'].forEach(x=>cell(head,x,'th'));table.append(head);for(const row of billing.services){const tr=document.createElement('tr');[row.service,row.currency,row.gross.toFixed(6),row.credits.toFixed(6),row.net.toFixed(6)].forEach(x=>cell(tr,x));table.append(tr);}$('billingTable').append(table);const p=document.createElement('p');p.className='hint';p.textContent=`Window: ${billing.start} → ${billing.end}. Allocated net: ${JSON.stringify(billing.allocated_net_by_currency)||'Unallocated'}.`;$('billingTable').append(p);}
$('refreshBilling').addEventListener('click',async()=>{$('refreshBilling').disabled=true;try{renderBilling(await api(`/api/jobs/${jobId}/billing`,{settings:settings()}));}catch(err){notice(err.message);}finally{$('BILLING_ACCESS_TOKEN').value='';$('refreshBilling').disabled=false;}});
$('deleteRun').addEventListener('click',async()=>{try{await api(`/api/jobs/${jobId}/delete`,{});jobId=null;sessionStorage.removeItem('eastcoJob');$('report').hidden=true;$('empty').hidden=false;$('status').textContent='Ready';}catch(err){notice(err.message);}});
$('envDownload').addEventListener('click',()=>{const text=Object.entries(settings()).map(([k,v])=>`${k}='${v.replaceAll("'", "'\\''")}'`).join('\n')+'\nBENCHMARK_MODE=dry\nINPUT_ZIP=/REPLACE_WITH_PATH/SampleData.zip\n';const url=URL.createObjectURL(new Blob([text],{type:'text/plain'}));const a=document.createElement('a');a.href=url;a.download='.env';a.click();URL.revokeObjectURL(url);});
init().then(()=>{if(jobId&&$('login').hidden){$('runButton').disabled=true;poll();}});
