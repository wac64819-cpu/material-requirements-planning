'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const schema = {
  materials: [['material_id','编号','text'],['name','名称','text'],['supply_type','类型','type'],['unit','单位','text'],['lead_time_days','提前期 / 天','number'],['min_purchase_qty','最小采购量','number'],['purchase_multiple','采购倍数','number']],
  bom: [['parent_id','父项编号','text'],['child_id','子项编号','text'],['qty_per','单件用量','number']],
  stocks: [['material_id','物料编号','text'],['on_hand','账面库存','number'],['reserved','已占用','number'],['snapshot_date','快照日期','date']],
  tasks: [['task_id','任务编号','text'],['product_id','成品编号','text'],['required_qty','需求数量','number'],['due_date','交货日期','date'],['priority','优先级','priority']]
};
const names = {materials:'物料',bom:'BOM',stocks:'库存',tasks:'生产任务'};
const tips = {materials:'自制件必须有 BOM，外购件作为叶子。采购参数仅对外购件生效。',bom:'单件用量表示生产一件父项需要多少子项。编号须与物料表一致。',stocks:'可用库存 = 账面库存 − 已占用。每个参与计算的物料都需要库存记录。',tasks:'需求数量按交付量计算，可先用成品库存抵扣。在“计划计算”中勾选本次参与的任务。'};
let data = null, active = 'materials', selected = new Set(), version = 0, dirty = false, busy = false;
let savedRevision = null, saving = false, historyOffset = null, historyRows = [], viewToken = 0;
let csvCandidate=null, csvToken=0, csvWorking=false, exportBatch=null;
let currentView='data';
const viewCopy={
  data:['基础数据','01 / DATA FOUNDATION','把数据准备好，<span>让计划有据可依。</span>','维护物料、结构与库存，构建本次生产计划的数据基础。'],
  planning:['计划计算','02 / REQUIREMENTS PLANNING','从生产需求，<span>到可执行的计划。</span>','按任务优先级分配库存，展开多层需求并生成生产与采购建议。'],
  history:['历史记录','03 / PLAN ARCHIVE','留存每次计算，<span>追溯每一项决策。</span>','查看历史快照、核对需求来源，随时导出已保存的计划。']
};
function showView(view,focus=true){
  if(!viewCopy[view])return;
  currentView=view;
  document.querySelectorAll('.view').forEach(panel=>{panel.hidden=panel.id!=='view-'+view;});
  document.querySelectorAll('[data-view]').forEach(button=>{
    if(button.dataset.view===view)button.setAttribute('aria-current','page');
    else button.removeAttribute('aria-current');
  });
  const [label,eyebrow,title,description]=viewCopy[view];
  $('#breadcrumb-current').textContent=label;$('#page-eyebrow').textContent=eyebrow;
  $('#page-title').innerHTML=title;$('#page-description').textContent=description;
  if(focus){$('#page-title').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
}
function updateOverview(){
  if(!data)return;
  Object.keys(schema).forEach(kind=>{$('#count-'+kind).textContent=data.sources[kind].length;});
  $('#selected-count').textContent=selected.size+' / '+data.sources.tasks.length;
}

function clearCsvPreview(){if(csvCandidate)$('#csv-message').textContent='数据或文件已改变，请重新校验。';csvCandidate=null;csvToken++;$('#apply-csv').disabled=true;}
function setExport(id){exportBatch=id;$('#export-controls').hidden=!id;$('#export-status').textContent='';}

function invalidate() {
  updateOverview();
  clearCsvPreview();setExport(null);
  version++; dirty = true;
  viewToken++; $('#history-meta').hidden = true;
  $('#edit-state').textContent = '有编辑 · 尚未保存';
  $('#save-status').textContent = '有未保存的修改';
  $('#result-badge').textContent = '待重新计算';
  $('#results').innerHTML = '<div class="empty">数据已改变，请重新生成计划。<small>旧结果已清除，避免混用不同版本的数据。</small></div>';
  $('#status').textContent = '数据已更新，尚未重新计算。';
}

function renderEditor() {
  updateOverview();
  document.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === active)));
  $('#table-help').textContent = tips[active];
  const rows = data.sources[active];
  const cells = rows.map((row, i) => '<tr>' + schema[active].map(([key,label,type]) => {
    const attrs = `data-row="${i}" data-key="${key}" aria-label="${names[active]}第${i+1}行 ${label}"`;
    const disabled = active === 'materials' && row.supply_type === 'MAKE' && ['min_purchase_qty','purchase_multiple'].includes(key);
    if (type === 'type' || type === 'priority') {
      const choices = type === 'type' ? [['MAKE','自制'],['BUY','外购']] : [[1,'1 · 高'],[2,'2 · 中'],[3,'3 · 低']];
      return '<td><select '+attrs+'>'+choices.map(([v,l])=>`<option value="${v}" ${String(row[key])===String(v)?'selected':''}>${l}</option>`).join('')+'</select></td>';
    }
    return `<td><input ${attrs} type="${type}" value="${esc(disabled ? '' : row[key])}" ${type==='number'?'step="1" min="0"':''} ${disabled?'disabled placeholder="不适用"':''}></td>`;
  }).join('')+`<td><button class="delete" data-delete="${i}" aria-label="删除${names[active]}第${i+1}行">删除</button></td></tr>`).join('');
  $('#editor').innerHTML = `<table><thead><tr>${schema[active].map(([,label])=>'<th>'+label+'</th>').join('')}<th>操作</th></tr></thead><tbody>${cells}</tbody></table>` + (rows.length?'':'<p class="empty">暂无数据，点击下方新增一行。</p>');
}

function renderSelection() {
  updateOverview();
  $('#task-selection').innerHTML = data.sources.tasks.map((t,i)=>{
    const unit=data.sources.materials.find(m=>m.material_id.trim()===t.product_id.trim())?.unit || '';
    return `<label class="task-check"><input type="checkbox" data-select="${i}" ${selected.has(i)?'checked':''}><span>${esc(t.task_id || '未填写编号')}<small>${esc(t.product_id || '未填写成品')} · ${esc(t.required_qty ?? '—')} ${esc(unit==='pcs'?'件':unit)} · 优先级 ${esc(t.priority)}<br>交期 ${esc(t.due_date || '未填写')}</small></span></label>`;
  }).join('') || '<p class="muted">请先在生产任务表新增任务。</p>';
}

async function loadExample(confirmReplace = true) {
  if (confirmReplace && dirty && !window.confirm('载入示例将替换当前页面的数据，是否继续？')) return;
  $('#load').disabled = true;
  try {
    const response = await fetch('/api/example/' + $('#example').value);
    if (!response.ok) throw new Error('示例读取失败，请确认本地服务正在运行。');
    const incoming = await response.json();
    data = incoming; selected = new Set(data.sources.tasks.map((_,i)=>i));
    version++; viewToken++; dirty = confirmReplace; $('#baseline').value = data.request.baseline_date;
    clearCsvPreview();setExport(null);
    $('#history-meta').hidden=true;
    $('#save-status').textContent = '示例尚未保存，点击“保存数据”可保留';
    renderEditor(); renderSelection();
    $('#edit-state').textContent = '示例已载入'; $('#result-badge').textContent = '尚未计算';
    $('#results').innerHTML = '<div class="empty">准备好数据后，点击“生成计划”。<small>可以直接计算示例，也可以先编辑任意表格。</small></div>';
    $('#status').textContent = '已选择 '+selected.size+' 个任务。';
  } catch (error) { $('#status').textContent = error.message; $('#save-status').textContent=error.message; }
  finally { $('#load').disabled = false; }
}

function table(headers, rows) {
  if (!rows.length) return '<p class="muted">本次没有相关记录。</p>';
  return '<div class="table-wrap"><table><thead><tr>'+headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(v=>'<td>'+esc(v ?? '—')+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
}

const messages = {SCHEMA:'输入记录格式有误。',REQUIRED_TEXT:'必填内容不能为空。',INTEGER:'数量须为符合范围的整数，不能填写小数或负数；用量和采购倍数必须大于零。',DATE:'请填写有效的日期。',SUPPLY_TYPE:'请选择自制或外购。',PRIORITY:'优先级须为1、2或3。',SNAPSHOT_DATE:'库存快照日期必须与计划基准日一致。',RESERVED_EXCEEDS_STOCK:'已占用数量不能超过账面库存。',DUPLICATE_ID:'编号重复，请修改。',DUPLICATE_EDGE:'同一父项与子项的BOM关系重复。',UNKNOWN_MATERIAL:'引用的物料编号不存在，请核对物料表。',UNKNOWN_TASK:'选中的任务不存在。',MISSING_STOCK:'参与计算的物料缺少库存记录。',MISSING_BOM:'自制物料缺少BOM，即使库存足够也必须补充。',BUY_HAS_CHILDREN:'外购物料不能有下层BOM。',BOM_CYCLE:'BOM存在循环引用，请检查父项与子项关系。',SELECTION:'请至少选择一个生产任务。',DUPLICATE_SELECTION:'选中的任务编号重复。',DATE_RANGE:'提前期倒推超出可表示的日期范围。',RULE_VERSION:'计算规则版本不匹配，请重新载入页面。'};

function locationLabel(location) {
  const match = /^(materials|bom|stocks|tasks)\[(\d+)\](?:\.(\w+))?/.exec(location);
  if (!match) return location === 'request.selected_task_ids' ? '本次任务选择' : location === 'request.baseline_date' ? '计划基准日' : location;
  const field = schema[match[1]].find(([key])=>key===match[3]);
  return names[match[1]]+'第'+(Number(match[2])+1)+'行'+(field?' · '+field[1]:'');
}

function showOutcome(outcome,reveal=true) {
  if(reveal)showView('planning',false);
  setExport(null);
  $('#history-meta').hidden=true;
  if (outcome.status !== 'VALID') {
    $('#result-badge').textContent = '校验未通过';
    $('#status').textContent = '未生成计划，请先修正下方问题。';
    $('#results').innerHTML = '<div class="error-box"><strong>发现 '+outcome.errors.length+' 项问题，本次未生成有效计划</strong><ul>'+outcome.errors.map(e=>'<li><strong>'+esc(locationLabel(e.source_location))+'</strong>：'+esc(messages[e.code] || e.message)+(/^(materials|bom|stocks|tasks)\[/.test(e.source_location)?`<button data-locate="${esc(e.source_location)}">定位</button>`:'')+(e.code==='BOM_CYCLE'?'<br><small>'+esc(e.message)+'</small>':'')+'</li>').join('')+'</ul></div>';
    return;
  }
  const r = outcome.result, n = r.net_bundle, s = r.summary;
  $('#result-badge').textContent = r.risks.length ? '已生成 · 存在交期风险' : '已生成';
  $('#status').textContent = '计算完成。未扣减实际库存。';
  const metrics = [['参与任务',s.task_count],['生产计划行',s.make_line_count],['采购建议行',s.purchase_line_count],['交期风险',s.risk_count]];
  let html = '<div class="metrics">'+metrics.map(([l,v])=>'<div class="metric"><strong>'+v+'</strong><span>'+l+'</span></div>').join('')+'</div><p class="muted">实际处理顺序：'+esc(n.context.ordered_task_ids.join(' → '))+'</p>';
  html += '<h3>新增生产计划</h3>'+table(['任务','物料','毛需求','抵扣库存','新增生产','开始日期','需要日期'],n.make_lines.map(x=>[x.task_id,x.material_id,x.gross_qty,x.allocated_qty,x.make_qty,x.start_date,x.needed_date]));
  html += '<h3>采购建议与余量</h3><p class="muted">采购量为0表示由早期计划余量满足，不产生采购建议。</p>'+table(['物料','需要日期','库存后缺口','使用余量','剩余缺口','采购量','下单日期','本期后余量'],r.purchase_buckets.map(x=>[x.material_id,x.needed_date,x.gross_shortage,x.surplus_used,x.remaining_gap,x.purchase_qty,x.order_date,x.surplus_after]));
  html += '<details><summary>查看库存分配明细</summary>'+table(['任务','物料','需要日期','分配前','本次分配','分配后'],n.allocations.map(x=>[x.task_id,x.material_id,x.needed_date,x.before_qty,x.allocated_qty,x.after_qty]))+'</details>';
  html += '<details><summary>查看需求来源与 BOM 路径</summary>'+table(['任务','物料','需要日期','来源路径','贡献数量'],n.demands.flatMap(x=>x.demand.origins.map(o=>[x.demand.task_id,x.demand.material_id,x.demand.needed_date,o.bom_path.join(' → '),o.contribution_qty])))+'</details>';
  if (r.risks.length) html += '<div class="risk"><h3>交期风险：建议日期早于基准日</h3>'+table(['任务','物料','原计算日期','早于基准日 / 天'],r.risks.map(x=>[x.task_id,x.material_id,x.computed_date,x.days_before_baseline]))+'</div>';
  $('#results').innerHTML = html;
}

async function calculate() {
  if (!data || busy || saving) return;
  const unsafe=inputErrors();
  if(unsafe.length){showOutcome({status:'INVALID',errors:unsafe});return;}
  const current = version;
  const payload = currentPayload();
  viewToken++; $('#history-meta').hidden=true;setExport(null);
  busy = true; $('#calculate').disabled = true; $('#calculate').textContent = '计算中…';
  $('#status').textContent = '正在校验、计算并保存计划，请稍候。';
  $('#result-badge').textContent = '计算中'; $('#results').innerHTML = '<div class="empty">正在计算…</div>';
  try {
    const response = await fetch('/api/calculate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const outcome = await response.json();
    if (!response.ok) throw new Error(outcome.message || '计算服务暂不可用，请重试。');
    if(outcome.saved_batch) refreshHistory();
    if (version !== current) { $('#status').textContent = '输入已改变，请重新生成计划；刚才提交的快照如已计算成功，可在历史中查看。'; $('#result-badge').textContent = '待重新计算'; $('#results').innerHTML='<div class="empty">输入已改变，本次返回结果已丢弃。</div>'; return; }
    showOutcome(outcome,false);
    if(outcome.saved_batch){setExport(outcome.saved_batch.batch_id);$('#history-meta').hidden=false;$('#history-meta').textContent='已保存计划 '+outcome.saved_batch.batch_id.slice(0,8)+' · '+formatTime(outcome.saved_batch.created_at);}
    if(currentView==='planning')$('#result-section').scrollIntoView({behavior:'smooth',block:'start'});
  } catch (error) {
    const message=error instanceof TypeError?'无法连接服务，未确认计划是否保存。请恢复连接后刷新历史列表。':error.message;
    $('#status').textContent = message; $('#result-badge').textContent = '计算失败';
    $('#results').innerHTML = '<div class="error-box">'+esc(message)+'</div>';
  } finally { busy = false; $('#calculate').disabled = false; $('#calculate').textContent = '生成计划'; }
}

function inputErrors() {
  const unsafe=[];
  for(const [table,fields] of Object.entries(schema)) {
    data.sources[table].forEach((row,i)=>fields.forEach(([key,,type])=>{
      if(type==='number' && Number.isInteger(row[key]) && !Number.isSafeInteger(row[key]))
        unsafe.push({code:'UI_INTEGER_RANGE',message:'页面输入须在安全整数范围内（不超过 9007199254740991），请减小数量。',source_location:`${table}[${i}].${key}`});
    }));
  }
  return unsafe;
}

function currentPayload() {
  const payload = structuredClone(data);
  payload.request.baseline_date = $('#baseline').value;
  payload.request.selected_task_ids = [...selected].sort((a,b)=>a-b).map(i=>data.sources.tasks[i].task_id);
  return payload;
}

function formatTime(value){return new Date(value).toLocaleString('zh-CN',{hour12:false});}

function installSaved(record) {
  clearCsvPreview();setExport(null);
  data=record.payload; savedRevision=record.revision_id;
  selected=new Set(data.sources.tasks.map((t,i)=>data.request.selected_task_ids.includes(t.task_id)?i:-1).filter(i=>i>=0));
  version++; viewToken++; dirty=false; $('#baseline').value=data.request.baseline_date;
  renderEditor();renderSelection();$('#edit-state').textContent='已保存';
  $('#save-status').textContent='已保存 · '+formatTime(record.created_at);
  $('#history-meta').hidden=true;$('#result-badge').textContent='尚未计算';
  $('#results').innerHTML='<div class="empty">已载入保存的数据，可继续编辑或生成计划。</div>';
}

async function loadSaved(initial=false) {
  if(saving || busy)return;
  if(!initial && dirty && !confirm('载入已保存数据将替换当前未保存的编辑，是否继续？'))return;
  const current=version;$('#reload-saved').disabled=true;
  try {
    const response=await fetch('/api/workspace');const record=await response.json();
    if(!response.ok)throw new Error(record.message || '读取已保存数据失败');
    if(current!==version){$('#save-status').textContent='读取期间有新编辑，未替换当前内容';return;}
    savedRevision=record.revision_id;
    if(record.payload)installSaved(record);
    else if(initial)await loadExample(false);
    else $('#save-status').textContent='尚无已保存数据，当前编辑保留';
  } catch(error){$('#save-status').textContent=error.message;}
  finally{$('#reload-saved').disabled=false;}
}

async function saveData() {
  if(!data || saving || busy)return;
  viewToken++;
  const unsafe=inputErrors();if(unsafe.length){showOutcome({status:'INVALID',errors:unsafe});return;}
  const current=version; saving=true;$('#save-data').disabled=true;$('#save-status').textContent='正在校验并保存…';
  try {
    const response=await fetch('/api/workspace',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({payload:currentPayload(),expected_revision:savedRevision})});
    const record=await response.json();
    if(!response.ok)throw new Error(record.message || '保存失败，未确认成功，请重试');
    if(record.status==='INVALID'){showOutcome(record);$('#save-status').textContent='校验未通过，已保存版本保持不变';return;}
    savedRevision=record.revision_id;
    if(current===version)installSaved(record);
    else $('#save-status').textContent='已保存提交时的数据；当前新修改尚未保存';
  } catch(error){$('#save-status').textContent=error instanceof TypeError?'连接中断，未确认保存成功。请重新连接后载入已保存数据核对。':error.message;}
  finally{saving=false;$('#save-data').disabled=false;}
}

async function refreshHistory(more=false) {
  const offset=more?historyOffset:0;if(offset===null)return;
  $('#refresh-history').disabled=true;$('#more-history').disabled=true;
  try {
    const response=await fetch('/api/history?offset='+offset);const result=await response.json();
    if(!response.ok)throw new Error(result.message || '历史读取失败');
    historyRows=more?[...historyRows,...result.items]:result.items;historyOffset=result.next_offset;
    $('#history-list').innerHTML=historyRows.length?'<div class="table-wrap"><table><thead><tr><th>计划编号</th><th>保存时间</th><th>基准日</th><th>任务</th><th>生产 / 采购 / 风险</th><th></th></tr></thead><tbody>'+historyRows.map(r=>`<tr><td>${esc(r.batch_id.slice(0,8))}</td><td>${esc(formatTime(r.created_at))}</td><td>${esc(r.baseline_date)}</td><td>${esc(r.task_ids.join('、'))}</td><td>${r.summary.make_line_count} / ${r.summary.purchase_line_count} / ${r.summary.risk_count}</td><td><button data-history="${esc(r.batch_id)}">查看</button></td></tr>`).join('')+'</tbody></table></div>':'<div class="empty">还没有历史计划<small>在“计划计算”中生成第一份计划，系统会自动保存到这里。</small></div>';
    $('#more-history').hidden=historyOffset===null;
  } catch(error){$('#history-list').textContent=error.message;}
  finally{$('#refresh-history').disabled=false;$('#more-history').disabled=false;}
}

async function viewHistory(id) {
  if(busy)return;
  $('#history-message').textContent='正在读取计划…';
  const token=++viewToken;
  try {
    const response=await fetch('/api/history/'+encodeURIComponent(id));const record=await response.json();
    if(!response.ok)throw new Error(record.message || '历史读取失败');
    if(token!==viewToken)return;
    showOutcome(record.outcome);setExport(id);$('#result-badge').textContent='历史计划 · 只读';
    $('#status').textContent='正在查看历史计划，基础数据中的编辑未改变。';
    $('#history-message').textContent='';
    $('#history-meta').hidden=false;$('#history-meta').textContent='历史计划 '+id.slice(0,8)+' · '+formatTime(record.saved_batch.created_at)+' · 使用当时保存的输入和结果';
    const context=record.outcome.result.net_bundle.context;
    $('#results').insertAdjacentHTML('beforeend','<details id="historical-input"><summary>查看本次输入快照</summary><p class="muted">基准日 '+esc(context.request.baseline_date)+'</p>'+Object.entries(schema).map(([kind,fields])=>'<h3>'+names[kind]+'</h3>'+table(fields.map(f=>f[1]),context.sources[kind].map(row=>fields.map(([key])=>row[key])))).join('')+'</details>');
    $('#result-section').scrollIntoView({behavior:'smooth',block:'start'});
  } catch(error){if(token===viewToken)$('#history-message').textContent=error.message;}
}

document.querySelectorAll('[data-view],[data-go]').forEach(button=>button.addEventListener('click',()=>{
  viewToken++;$('#history-message').textContent='';showView(button.dataset.view || button.dataset.go);
}));
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{if(data){active=b.dataset.tab;renderEditor();}}));
$('#editor').addEventListener('input',event=>{
  const control = event.target, key = control.dataset.key;
  if (!key) return;
  const row = data.sources[active][Number(control.dataset.row)];
  row[key] = control.type==='number' ? (control.value===''?null:Number(control.value)) : key==='priority'?Number(control.value):control.value;
  if (key==='supply_type' && row[key]==='BUY') {row.min_purchase_qty ??= 0; row.purchase_multiple ??= 1;}
  invalidate();
  if (active==='tasks' || active==='materials') renderSelection();
  if (key==='supply_type') renderEditor();
});
$('#editor').addEventListener('click',event=>{
  const button = event.target.closest('[data-delete]'); if (!button) return;
  const i = Number(button.dataset.delete); data.sources[active].splice(i,1);
  if(active==='tasks') selected=new Set([...selected].filter(v=>v!==i).map(v=>v>i?v-1:v));
  invalidate();renderEditor();renderSelection();
});
$('#add').addEventListener('click',()=>{
  if(!data)return;
  const defaults={materials:{material_id:'',name:'',supply_type:'BUY',unit:'pcs',lead_time_days:0,min_purchase_qty:0,purchase_multiple:1},bom:{parent_id:'',child_id:'',qty_per:1},stocks:{material_id:'',on_hand:0,reserved:0,snapshot_date:$('#baseline').value},tasks:{task_id:'',product_id:'',required_qty:1,due_date:$('#baseline').value,priority:2}};
  data.sources[active].push(defaults[active]);invalidate();renderEditor();renderSelection();
  $('#editor tbody tr:last-child input')?.focus();
});
$('#task-selection').addEventListener('change',event=>{const i=Number(event.target.dataset.select);if(event.target.checked)selected.add(i);else selected.delete(i);invalidate();});
$('#select-all').addEventListener('click',()=>{if(!data)return;selected=new Set(data.sources.tasks.map((_,i)=>i));invalidate();renderSelection();});
$('#baseline').addEventListener('input',()=>{if(data)invalidate();});
$('#load').addEventListener('click',()=>loadExample());
$('#calculate').addEventListener('click',calculate);
$('#results').addEventListener('click',event=>{
  const button=event.target.closest('[data-locate]');if(!button)return;
  const m=/^(materials|bom|stocks|tasks)\[(\d+)\](?:\.(\w+))?/.exec(button.dataset.locate);if(!m)return;
  showView('data',false);active=m[1];renderEditor();
  const input=$(`#editor [data-row="${m[2]}"]${m[3]?`[data-key="${m[3]}"]`:''}`);
  if(input){input.classList.add('invalid-field');input.focus();input.scrollIntoView({block:'center'});}
});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
$('#save-data').addEventListener('click',saveData);
$('#reload-saved').addEventListener('click',()=>loadSaved());
$('#refresh-history').addEventListener('click',()=>refreshHistory());
$('#more-history').addEventListener('click',()=>refreshHistory(true));
$('#history-list').addEventListener('click',event=>{const button=event.target.closest('[data-history]');if(button)viewHistory(button.dataset.history);});
async function previewCsv(){
  if(!data || csvWorking)return;
  clearCsvPreview();const current=version, token=csvToken;csvWorking=true;$('#preview-csv').disabled=true;
  $('#csv-message').textContent='正在读取和校验文件…';
  try{
    const files={};
    for(const input of document.querySelectorAll('[data-csv]')){
      const file=input.files[0];if(!file)continue;
      if(file.size>500000)throw new Error(file.name+' 超过500KB，请拆分或缩小文件。');
      try{files[input.dataset.csv]=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());}
      catch{throw new Error(file.name+' 不是有效的UTF-8文件，请另存为CSV UTF-8后重试。');}
    }
    if(!Object.keys(files).length)throw new Error('请至少选择一个CSV文件。');
    const response=await fetch('/api/csv/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({payload:currentPayload(),files})});
    const result=await response.json();if(!response.ok)throw new Error(result.message || 'CSV校验服务不可用。');
    if(current!==version || token!==csvToken){$('#csv-message').textContent='校验期间数据或文件已改变，请重新校验。';return;}
    if(result.status!=='READY'){$('#csv-message').innerHTML='未应用导入，原数据保持不变。<ul>'+result.errors.map(e=>'<li>'+esc(e.source_location)+'：'+esc(messages[e.code] || e.message)+'</li>').join('')+'</ul>';return;}
    csvCandidate={payload:result.payload,version:current,token};$('#apply-csv').disabled=false;
    $('#csv-message').textContent='校验通过，将替换：'+Object.entries(result.counts).map(([k,v])=>names[k]+' '+v+' 行').join('、')+'。请核对后点击应用。';
  }catch(error){$('#csv-message').textContent=error instanceof TypeError?'无法连接校验服务，请保持启动窗口运行后重试。':error.message;}
  finally{csvWorking=false;$('#preview-csv').disabled=false;}
}

function applyCsv(){
  if(busy || saving){$('#csv-message').textContent='请等待当前保存或计算完成后再应用。';return;}
  if(!csvCandidate || csvCandidate.version!==version || csvCandidate.token!==csvToken){clearCsvPreview();$('#csv-message').textContent='预览已失效，请重新校验。';return;}
  data=csvCandidate.payload;selected=new Set(data.sources.tasks.map((t,i)=>data.request.selected_task_ids.includes(t.task_id)?i:-1).filter(i=>i>=0));
  invalidate();renderEditor();renderSelection();$('#baseline').value=data.request.baseline_date;
  $('#csv-message').textContent='已应用到编辑区，请核对任务勾选并点击“保存数据”。';
}

async function downloadCsv(){
  if(!exportBatch)return;
  const id=exportBatch, kind=$('#export-kind').value;$('#export-csv').disabled=true;
  try{
    const response=await fetch('/api/history/'+encodeURIComponent(id)+'/csv/'+kind);
    if(!response.ok){const problem=await response.json();throw new Error(problem.message || '导出失败。');}
    const blob=await response.blob(), url=URL.createObjectURL(blob), link=document.createElement('a');
    link.href=url;link.download='plan-'+id+'-'+kind+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    if(exportBatch===id)$('#export-status').textContent='已导出计划 '+id.slice(0,8);
  }catch(error){$('#export-status').textContent=error instanceof TypeError?'连接失败，请重新连接后导出。':error.message;}
  finally{$('#export-csv').disabled=false;}
}

document.querySelectorAll('[data-csv]').forEach(input=>input.addEventListener('change',()=>{clearCsvPreview();$('#csv-message').textContent='文件已选择，请校验后应用。';}));
$('#preview-csv').addEventListener('click',previewCsv);$('#apply-csv').addEventListener('click',applyCsv);$('#export-csv').addEventListener('click',downloadCsv);
loadSaved(true);refreshHistory();
