const $=id=>document.getElementById(id);const S={diagrams:[],diagram:null,annotations:[],paths:[],mode:'pan',scale:1,tx:0,ty:0,pending:[],point:null,drag:null,terminals:[],links:[],auto:[],graph:{run:null,edges:[],events:[],label_links:[]},selectedEdge:null,segmentation:{run:null,edges:[]},associations:{run:null,candidates:[]},selectedAssociation:null,terminalCandidates:{run:null,candidates:[]},circleCandidates:{run:null,candidates:[]},evidence:{run:null,circles:[]},independent:{run:null,circles:[]},pathMatches:{run:null,matches:[]},fuseAudit:{run:null,items:[]},localOCR:{run:null,items:[]},diagnostics:{run:null,items:[]},continuity:{run:null,items:[]},targeted:{run:null,items:[]},gapVisual:{run:null,items:[]},components:{run:null,items:[]},trace:{run:null,items:[]},selectedTrace:null};const api=async(url,opts)=>{const r=await fetch(url,opts);const j=await r.json();if(!r.ok)throw Error(j.error||'request failed');return j};const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function size(){const d=S.diagram;return {w:d.width,h:d.height}}function renderTransform(){const st=$('stage');st.style.width=S.diagram.width+'px';st.style.height=S.diagram.height+'px';st.style.transform=`translate(${S.tx}px,${S.ty}px) scale(${S.scale})`;}
function fit(){const v=$('viewport'),d=S.diagram;S.scale=Math.min((v.clientWidth-40)/d.width,(v.clientHeight-40)/d.height,1.5);S.tx=(v.clientWidth-d.width*S.scale)/2;S.ty=(v.clientHeight-d.height*S.scale)/2;renderTransform()}
function point(ev){const r=$('viewport').getBoundingClientRect();return [(ev.clientX-r.left-S.tx)/S.scale/S.diagram.width,(ev.clientY-r.top-S.ty)/S.scale/S.diagram.height].map(x=>Math.max(0,Math.min(1,x)))}
function svg(tag,attrs){const el=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));return el}
function draw(){const overlay=$('overlay');overlay.replaceChildren();overlay.setAttribute('viewBox',`0 0 ${S.diagram.width} ${S.diagram.height}`);const search=$('search').value.toLowerCase();for(const a of S.annotations){if(search&&!`${a.label} ${a.kind} ${a.notes}`.toLowerCase().includes(search))continue;const el=svg('rect',{x:a.x*S.diagram.width,y:a.y*S.diagram.height,width:Math.max(a.w*S.diagram.width,15),height:Math.max(a.h*S.diagram.height,15),rx:3,class:'box'});el.addEventListener('click',e=>{e.stopPropagation();inspect('annotations',a)});overlay.append(el)}for(const p of S.paths){if(search&&!`${p.label} ${p.notes}`.toLowerCase().includes(search))continue;const el=svg('polyline',{points:p.points.map(q=>`${q[0]*S.diagram.width},${q[1]*S.diagram.height}`).join(' '),class:'wire'});el.addEventListener('click',e=>{e.stopPropagation();inspect('paths',p)});overlay.append(el)}if($('autoOverlay').checked){for(const a of S.auto){const kind=a.kind;const visible=kind==='ocr_connector'?$('layerConnectors').checked:kind==='ocr_fuse_label'?$('layerFuses').checked:kind==='line_segment_candidate'?$('layerLines').checked:$('layerText').checked;if(!visible)continue;if(search&&!`${a.label} ${a.kind}`.toLowerCase().includes(search))continue;const box=svg('rect',{x:a.x*S.diagram.width,y:a.y*S.diagram.height,width:Math.max(a.w*S.diagram.width,3),height:Math.max(a.h*S.diagram.height,3),class:'auto-box'});box.addEventListener('click',e=>{e.stopPropagation();inspect('machine candidate',{...a,notes:'OCR/CV proposal only; connectivity not verified.'})});overlay.append(box)}}if($('layerGraph').checked){for(const e of S.graph.edges){const el=svg('line',{x1:e.x1*S.diagram.width,y1:e.y1*S.diagram.height,x2:e.x2*S.diagram.width,y2:e.y2*S.diagram.height,class:e.id===S.selectedEdge?'graph-edge selected-wire':'graph-edge'});el.addEventListener('click',ev=>{ev.stopPropagation();inspect('geometry candidate',{label:e.axis,verification:e.verification,id:e.id,notes:'Segmen visual, bukan kontinuitas listrik terverifikasi.'})});overlay.append(el)}}if(S.segmentation.edges.length){for(const e of S.segmentation.edges){if(e.classification==='candidate_wire'&&!$('layerSegmented').checked)continue;if(e.classification==='excluded_structural'&&!$('layerExcluded').checked)continue;const el=svg('line',{x1:e.x1*S.diagram.width,y1:e.y1*S.diagram.height,x2:e.x2*S.diagram.width,y2:e.y2*S.diagram.height,class:e.classification==='candidate_wire'?'segment-wire':'segment-excluded'});el.addEventListener('click',ev=>{ev.stopPropagation();inspect('segmentation',{label:e.region,kind:e.classification,verification:e.verification,notes:e.reason,id:e.id})});overlay.append(el)}}if($('layerTrace').checked){for(const a of S.trace.items){const pts=a.trace?.points||[];if(pts.length>=2){const el=svg('polyline',{points:pts.map(p=>p[0]*S.diagram.width+','+p[1]*S.diagram.height).join(' '),class:'smart-trace-line'+(S.selectedTrace===a.component_id?' smart-trace-selected':'')});el.addEventListener('click',ev=>{ev.stopPropagation();S.selectedTrace=a.component_id;renderTrace();draw();inspect('cached geometric trace',{label:a.fuse_label,kind:a.trace_status,verification:'unverified',notes:a.trace_reason,id:a.id})});overlay.append(el)}if(a.terminal_circle_id){const c=S.independent.circles.find(x=>x.id===a.terminal_circle_id);if(c){const el=svg('circle',{cx:c.x*S.diagram.width,cy:c.y*S.diagram.height,r:Math.max(5,c.r*Math.max(S.diagram.width,S.diagram.height)),class:'smart-trace-terminal'});overlay.append(el)}}}}if($('layerComponents').checked){for(const a of S.components.items){const el=svg('rect',{x:a.x*S.diagram.width-8,y:a.y*S.diagram.height-8,width:16,height:16,class:'component-candidate'});el.addEventListener('click',ev=>{ev.stopPropagation();inspect('fuse symbol candidate',{label:a.fuse_label,kind:a.component_type,verification:'unverified',notes:JSON.stringify(a.graph_preview),id:a.id})});overlay.append(el)}}if($('layerContinuity').checked){for(const a of S.continuity.items){overlay.append(svg('line',{x1:a.endpoint_x*S.diagram.width,y1:a.endpoint_y*S.diagram.height,x2:a.neighbor_x*S.diagram.width,y2:a.neighbor_y*S.diagram.height,class:'continuity-gap'}))}}if($('layerDiagnostics').checked){for(const a of S.diagnostics.items){if(a.endpoint_x===null)continue;const el=svg('circle',{cx:a.endpoint_x*S.diagram.width,cy:a.endpoint_y*S.diagram.height,r:7,class:'diagnostic-endpoint'});el.addEventListener('click',ev=>{ev.stopPropagation();inspect('terminal diagnostic',{label:a.fuse_label,kind:a.reason,verification:'unverified',notes:JSON.stringify(a.candidates.slice(0,3)),id:a.id})});overlay.append(el)}}if($('layerLocalOCR').checked){for(const a of S.localOCR.items){const el=svg('rect',{x:a.x*S.diagram.width,y:a.y*S.diagram.height,width:a.w*S.diagram.width,height:a.h*S.diagram.height,class:'local-ocr-box'});el.addEventListener('click',ev=>{ev.stopPropagation();inspect('localized OCR',{label:a.label,kind:'ocr_suggestion_unverified',verification:'unverified',notes:a.reason,id:a.id})});overlay.append(el)}}if($('layerFuseAudit').checked){for(const a of S.fuseAudit.items.filter(x=>x.status!=='already_associated')){const el=svg('circle',{cx:a.x*S.diagram.width,cy:a.y*S.diagram.height,r:10,class:'fuse-audit-label'});el.addEventListener('click',ev=>{ev.stopPropagation();inspect('fuse audit',{label:a.label,kind:a.status,verification:'unverified',notes:a.reason,id:a.id})});overlay.append(el);for(const id of a.edge_ids){const e=S.segmentation.edges.find(x=>x.source_edge_id===id);if(!e)continue;overlay.append(svg('line',{x1:e.x1*S.diagram.width,y1:e.y1*S.diagram.height,x2:e.x2*S.diagram.width,y2:e.y2*S.diagram.height,class:'fuse-audit-edge'}))}}}if($('layerPathMatches').checked){for(const m of S.pathMatches.matches.filter(m=>m.circle_id)){const c=S.independent.circles.find(x=>x.id===m.circle_id);if(!c)continue;const el=svg('circle',{cx:c.x*S.diagram.width,cy:c.y*S.diagram.height,r:Math.max(6,c.r*Math.max(S.diagram.width,S.diagram.height)+4),class:'path-match-circle'});el.addEventListener('click',ev=>{ev.stopPropagation();inspect('geometric path candidate',{label:m.fuse_label+' → '+m.terminal_text,kind:'geometric_candidate_unverified',verification:'unverified',notes:m.reason+'; distance='+m.geometric_distance,id:m.id})});overlay.append(el)}}if($('layerIndependent').checked){for(const c of S.independent.circles.filter(c=>c.ocr_text)){const el=svg('circle',{cx:c.x*S.diagram.width,cy:c.y*S.diagram.height,r:Math.max(4,c.r*Math.max(S.diagram.width,S.diagram.height)),class:'independent-read'});el.addEventListener('click',ev=>{ev.stopPropagation();inspect('independent OCR',{label:c.ocr_text,kind:'unassociated_circle_ocr',verification:'unverified',notes:c.reason+'; OCR '+Math.round(c.ocr_confidence*100)+'%',id:c.id})});overlay.append(el)}}if($('layerAllCircles').checked){for(const c of S.evidence.circles){const el=svg('circle',{cx:c.x*S.diagram.width,cy:c.y*S.diagram.height,r:Math.max(4,c.r*Math.max(S.diagram.width,S.diagram.height)),class:c.status==='ocr_match_unverified'?'evidence-match':'evidence-rejected'});el.addEventListener('click',ev=>{ev.stopPropagation();inspect('circle audit',{label:c.ocr_text||'No OCR',kind:c.status,verification:'visual_evidence_unverified',notes:c.reason,id:c.id})});overlay.append(el)}}if($('layerCircleEvidence').checked){for(const c of S.circleCandidates.candidates){overlay.append(svg('circle',{cx:c.circle_x*S.diagram.width,cy:c.circle_y*S.diagram.height,r:Math.max(5,c.circle_r*Math.max(S.diagram.width,S.diagram.height)),class:'circle-evidence'}))}}if(S.selectedAssociation){const ids=new Set(S.selectedAssociation.edge_ids);for(const e of S.segmentation.edges){if(!ids.has(e.source_edge_id))continue;overlay.append(svg('line',{x1:e.x1*S.diagram.width,y1:e.y1*S.diagram.height,x2:e.x2*S.diagram.width,y2:e.y2*S.diagram.height,class:'association-selected'}))}}if($('layerCrossings').checked){for(const ev of S.graph.events){const el=svg('circle',{cx:ev.x*S.diagram.width,cy:ev.y*S.diagram.height,r:4,class:'graph-crossing'});el.addEventListener('click',e=>{e.stopPropagation();inspect('crossing',{label:'Crossing: unknown',verification:ev.verification,id:ev.id,notes:'Persilangan ini tidak dianggap tersambung.'})});overlay.append(el)}}if(S.pending.length){overlay.append(svg('polyline',{points:S.pending.map(q=>`${q[0]*S.diagram.width},${q[1]*S.diagram.height}`).join(' '),class:'wire pending'}))}}
function inspect(type,obj){$('inspector').innerHTML=`<b>${esc(obj.label||obj.connector_label||obj.path_label)}</b><p>Jenis: ${esc(obj.kind||type)}</p><p>Status: ${esc(obj.verification)}</p><p>${esc(obj.notes||'Tanpa catatan')}</p><p class="muted">ID: ${esc(obj.id)}</p>`}
function list(id,items,type){const el=$(id);el.replaceChildren();for(const x of items){const row=document.createElement('div');row.className='item';const b=document.createElement('button');b.textContent=x.label;b.onclick=()=>inspect(type,x);const del=document.createElement('button');del.className='delete';del.textContent='×';del.title='Hapus';del.onclick=async()=>{if(!confirm(`Hapus ${x.label}?`))return;await api(`/api/${type}/${x.id}`,{method:'DELETE'});await refresh()};row.append(b,del);el.append(row)}}
async function refresh(){S.graph=await api(`/api/graph?diagram=${S.diagram.id}`);S.segmentation=await api(`/api/segmentation?diagram=${S.diagram.id}`);$('segmentInfo').textContent=S.segmentation.run?`${S.segmentation.run.candidate_wire_segments}/${S.segmentation.run.raw_segments} candidate segments • ${S.segmentation.run.excluded_structural_segments} excluded • ${S.segmentation.run.remaining_ambiguous_crossings} crossings • 0 verified connections`:'Segmentation not built';S.associations=await api(`/api/associations?diagram=${S.diagram.id}`);S.terminalCandidates=await api(`/api/terminal-candidates?diagram=${S.diagram.id}`);renderTerminalCandidates();S.circleCandidates=await api(`/api/circle-candidates?diagram=${S.diagram.id}`);renderCircleCandidates();S.evidence=await api(`/api/evidence?diagram=${S.diagram.id}`);renderEvidence();S.independent=await api(`/api/independent-ocr?diagram=${S.diagram.id}`);renderIndependent();S.pathMatches=await api(`/api/path-matches?diagram=${S.diagram.id}`);renderPathMatches();S.fuseAudit=await api(`/api/fuse-audit?diagram=${S.diagram.id}`);renderFuseAudit();S.localOCR=await api(`/api/local-ocr?diagram=${S.diagram.id}`);renderLocalOCR();S.diagnostics=await api(`/api/match-diagnostics?diagram=${S.diagram.id}`);renderDiagnostics();S.continuity=await api(`/api/continuity-audit?diagram=${S.diagram.id}`);renderContinuity();S.targeted=await api(`/api/targeted-ocr?diagram=${S.diagram.id}`);renderTargeted();S.gapVisual=await api(`/api/gap-visual?diagram=${S.diagram.id}`);renderGapVisual();S.components=await api(`/api/components?diagram=${S.diagram.id}`);renderComponents();S.trace=await api(`/api/trace?diagram=${S.diagram.id}`);renderTrace();S.selectedAssociation=null;renderAssociations();S.selectedEdge=null;renderGraph();S.auto=await api(`/api/auto-candidates?diagram=${S.diagram.id}`);const kinds={};for(const a of S.auto)kinds[a.kind]=(kinds[a.kind]||0)+1;$('autoInfo').textContent=`${S.auto.length} kandidat • ${Object.entries(kinds).map(([k,v])=>k+': '+v).join(', ')||'Belum ada'}. Tidak ada konektivitas otomatis terverifikasi.`;$('autoList').replaceChildren();for(const a of S.auto.filter(a=>a.kind==='ocr_connector'||a.kind==='ocr_fuse_label').slice(0,25)){const b=document.createElement('button');b.textContent=`${a.kind}: ${a.label} (${Math.round(a.confidence*100)}%)`;b.onclick=()=>inspect('machine candidate',{...a,notes:'Belum diverifikasi oleh teknisi'});$('autoList').append(b)}S.annotations=await api(`/api/annotations?diagram=${S.diagram.id}`);S.paths=await api(`/api/paths?diagram=${S.diagram.id}`);S.terminals=await api(`/api/terminals?diagram=${S.diagram.id}`);S.links=await api(`/api/circuit-links?diagram=${S.diagram.id}`);list('annotations',S.annotations,'annotations');list('paths',S.paths,'paths');renderMappings();draw();$('status').textContent=`${S.annotations.length} anotasi • ${S.paths.length} jalur (manual)`}
async function change(){S.diagram=S.diagrams.find(d=>d.id===$('diagram').value);$('diagramImg').src='/images/'+S.diagram.image_file;S.pending=[];fit();await refresh()}
function mode(m){S.mode=m;S.pending=[];document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===m));$('finish').hidden=m!=='path';$('cancel').hidden=m!=='path';$('viewport').style.cursor=m==='pan'?'grab':'crosshair';draw()}
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>mode(b.dataset.mode));$('search').oninput=draw;$('diagram').onchange=change;$('reset').onclick=fit;function zoom(f,at){const v=$('viewport');const x=at?.[0]??v.clientWidth/2,y=at?.[1]??v.clientHeight/2;const old=S.scale;S.scale=Math.min(8,Math.max(.08,old*f));S.tx=x-(x-S.tx)*S.scale/old;S.ty=y-(y-S.ty)*S.scale/old;renderTransform()};$('zin').onclick=()=>zoom(1.25);$('zout').onclick=()=>zoom(.8);$('viewport').onwheel=e=>{e.preventDefault();const r=$('viewport').getBoundingClientRect();zoom(e.deltaY<0?1.15:.87,[e.clientX-r.left,e.clientY-r.top])};
$('viewport').onpointerdown=e=>{if(e.button!==0)return;if(S.mode==='pan'){S.drag={x:e.clientX,y:e.clientY,tx:S.tx,ty:S.ty};$('viewport').setPointerCapture(e.pointerId)}};$('viewport').onpointermove=e=>{if(S.drag){S.tx=S.drag.tx+e.clientX-S.drag.x;S.ty=S.drag.ty+e.clientY-S.drag.y;renderTransform()}};$('viewport').onpointerup=()=>S.drag=null;
$('overlay').addEventListener('click',e=>{if(S.mode==='pan'||e.target!==$('overlay'))return;const p=point(e);if(S.mode==='annotation'){S.point=p;$('editor').showModal()}else{S.pending.push(p);draw()}});
$('close').onclick=()=>$('editor').close();$('editForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);try{await api('/api/annotations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id,kind:f.get('kind'),label:f.get('label'),notes:f.get('notes'),x:S.point[0],y:S.point[1],w:.035,h:.025})});$('editor').close();e.target.reset();await refresh()}catch(err){alert(err.message)}};
$('finish').onclick=async()=>{if(S.pending.length<2)return alert('Minimal dua titik');const label=prompt('Nama jalur (manual):');if(!label)return;try{await api('/api/paths',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id,label,points:S.pending})});S.pending=[];await refresh()}catch(err){alert(err.message)}};$('cancel').onclick=()=>{S.pending=[];draw()};
(async()=>{S.diagrams=await api('/api/diagrams');for(const d of S.diagrams){const o=document.createElement('option');o.value=d.id;o.textContent=d.title;$('diagram').append(o)}$('diagram').value='junction_block';await change()})().catch(e=>{$('status').textContent=e.message});

function options(el,items,fmt){el.replaceChildren();for(const item of items){const o=document.createElement('option');o.value=item.id;o.textContent=fmt(item);el.append(o)}}
function mappingRow(container,title,detail,type,obj){const row=document.createElement('div');row.className='item';const b=document.createElement('button');b.textContent=title;b.title=detail;b.onclick=()=>{inspect(type,{...obj,label:title,notes:detail});if(type==='circuit-links'){const p=S.paths.find(x=>x.id===obj.path_id);if(p){$('search').value='';draw();const el=[...$('overlay').querySelectorAll('polyline')][S.paths.indexOf(p)];if(el){el.classList.add('selected-wire');setTimeout(()=>el.classList.remove('selected-wire'),3500)}}}};const del=document.createElement('button');del.className='delete';del.textContent='×';del.onclick=async()=>{if(!confirm('Hapus mapping ini?'))return;try{await api(`/api/${type}/${obj.id}`,{method:'DELETE'});await refresh()}catch(e){alert(e.message)}};row.append(b,del);container.append(row)}
function renderMappings(){const t=$('terminals'),l=$('links');t.replaceChildren();l.replaceChildren();for(const x of S.terminals)mappingRow(t,`${x.connector_label} / ${x.terminal_number}`,x.signal_name||x.notes,'terminals',x);for(const x of S.links)mappingRow(l,`${x.path_label} → ${x.annotation_label}${x.terminal_number?' / '+x.terminal_number:''}`,x.notes||'Needs review','circuit-links',x)}
$('newTerminal').onclick=()=>{const connectors=S.annotations.filter(x=>x.kind==='connector');if(!connectors.length)return alert('Buat anotasi dengan jenis connector terlebih dahulu.');options($('terminalConnector'),connectors,x=>x.label);$('terminalDialog').showModal()};
$('terminalForm').onsubmit=async e=>{e.preventDefault();const v=Object.fromEntries(new FormData(e.target));v.diagram_id=S.diagram.id;try{await api('/api/terminals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(v)});$('terminalDialog').close();e.target.reset();await refresh()}catch(err){alert(err.message)}};
function terminalOptions(){const aid=$('linkAnnotation').value;const relevant=S.terminals.filter(x=>x.connector_annotation_id===aid);const sel=$('linkTerminal');sel.replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent='Tanpa terminal';sel.append(empty);for(const t of relevant){const o=document.createElement('option');o.value=t.id;o.textContent=`${t.terminal_number} — ${t.signal_name||'no signal'}`;sel.append(o)}}
$('newLink').onclick=()=>{if(!S.paths.length||!S.annotations.length)return alert('Buat minimal satu jalur dan satu anotasi terlebih dahulu.');options($('linkPath'),S.paths,x=>x.label);options($('linkAnnotation'),S.annotations,x=>`${x.label} (${x.kind})`);terminalOptions();$('linkDialog').showModal()};$('linkAnnotation').onchange=terminalOptions;
$('linkForm').onsubmit=async e=>{e.preventDefault();const v=Object.fromEntries(new FormData(e.target));v.diagram_id=S.diagram.id;try{await api('/api/circuit-links',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(v)});$('linkDialog').close();await refresh()}catch(err){alert(err.message)}};

$('autoOverlay').onchange=draw;$('autoAnalyze').onclick=async()=>{const b=$('autoAnalyze');b.disabled=true;$('autoInfo').textContent='Memproses OCR dan CV lokal...';try{const r=await api('/api/auto-analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id,ocr:true,lines:true})});await refresh();if(r.notes.length)alert(r.notes.join('\n'))}catch(e){alert(e.message)}finally{b.disabled=false}};

function renderGraph(){const g=S.graph;const info=$('graphInfo');info.textContent=g.run?`${g.run.edges} segmen • ${g.run.ambiguous_crossings} persilangan ambigu • ${g.run.nearby_labels} label terdekat • 0 koneksi terverifikasi`:'Belum ada graph. Jalankan analisis, lalu Build geometry graph.';const sel=$('graphCircuit');sel.replaceChildren();const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Pilih label kandidat...';sel.append(placeholder);for(const link of g.label_links){const o=document.createElement('option');o.value=link.edge_id;o.textContent=`${link.label} (${link.kind}; proximity ${link.distance})`;sel.append(o)}}
for(const id of ['layerConnectors','layerFuses','layerText','layerLines','layerGraph','layerCrossings'])$(id).onchange=draw;
$('buildGraph').onclick=async()=>{try{const r=await api('/api/graph-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();$('layerGraph').checked=true;draw();alert(`${r.edges} geometry segments; ${r.ambiguous_crossings} ambiguous crossings. NO verified electrical connections.`)}catch(e){alert(e.message)}};
$('traceGraph').onclick=()=>{S.selectedEdge=$('graphCircuit').value||null;if(!S.selectedEdge)return alert('Pilih label kandidat terlebih dahulu');$('layerGraph').checked=true;draw();$('graphInfo').textContent='Highlighted nearest geometric segment ONLY — not an electrically traced circuit.'};
$('exportGraph').onclick=async()=>{const g=await api(`/api/graph-export?diagram=${S.diagram.id}`);const blob=new Blob([JSON.stringify(g,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`autowiring-${S.diagram.id}-graph-candidates.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};

$('buildSegments').onclick=async()=>{try{const r=await api('/api/segment-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();$('layerGraph').checked=false;draw();alert(`${r.candidate_wire_segments} candidate segments, ${r.excluded_structural_segments} excluded, ${r.remaining_ambiguous_crossings} ambiguous crossings. Not electrically verified.`)}catch(e){alert(e.message)}};
for(const id of ['layerSegmented','layerExcluded'])$(id).onchange=draw;
$('graphCircuit').addEventListener('change',()=>{const link=S.graph.label_links.find(x=>x.edge_id===$('graphCircuit').value);if(link)inspect('candidate label',{label:link.label,kind:link.kind,verification:link.verification,notes:'Nearest segment only, not electrical continuity',id:link.label_candidate_id})});

function renderAssociations(){
 const sel=$('associationSelect');sel.replaceChildren();const p=document.createElement('option');p.value='';p.textContent='Pilih fuse candidate...';sel.append(p);
 for(const c of S.associations.candidates){const o=document.createElement('option');o.value=c.id;o.textContent=`${c.label} • ${c.edge_ids.length} segment(s)${c.terminal_text?' • terminal OCR '+c.terminal_text:''}`;sel.append(o)}
 $('associationInfo').textContent=S.associations.run?`${S.associations.run.candidate_circuits} fuse candidates • ${S.associations.run.terminal_text_candidates} nearby terminal OCR candidates • 0 verified connections`:'Run segmentation first, then find candidate circuits.';
}
$('buildAssociations').onclick=async()=>{try{const r=await api('/api/association-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();alert(`${r.candidate_circuits} candidate circuits; ${r.terminal_text_candidates} terminal OCR candidates. NONE electrically verified.`)}catch(e){alert(e.message)}};
$('highlightAssociation').onclick=()=>{const c=S.associations.candidates.find(x=>x.id===$('associationSelect').value);if(!c)return alert('Pilih kandidat fuse terlebih dahulu');S.selectedAssociation=c;draw();inspect('candidate circuit',{label:c.label,kind:'visual_association',verification:c.verification,notes:`${c.reason} OCR terminal: ${c.terminal_text||'not detected'}. NOT a verified connector pin or continuous circuit.`,id:c.id})};
$('associationSelect').onchange=()=>{const c=S.associations.candidates.find(x=>x.id===$('associationSelect').value);if(c)inspect('candidate circuit',{label:c.label,kind:'visual_association',verification:c.verification,notes:`${c.reason} Terminal OCR: ${c.terminal_text||'not detected'}`,id:c.id})};
$('exportAssociations').onclick=()=>{const blob=new Blob([JSON.stringify(S.associations,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`autowiring-${S.diagram.id}-candidate-circuits-v035.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};

function renderTerminalCandidates(){
 const d=S.terminalCandidates;const el=$('terminalCandidateList');el.replaceChildren();
 $('terminalCandidateInfo').textContent=d.run?`${d.run.terminal_candidates} terminal OCR candidates • ${d.run.connector_column_candidates} connector-column candidates • 0 verified electrical connections`:'Run Find candidate circuits first.';
 for(const c of d.candidates){const b=document.createElement('button');b.textContent=`${c.fuse_label} → terminal ${c.terminal_text||'?'} → connector ${c.connector_label||'?'} (UNVERIFIED)`;b.onclick=()=>inspect('terminal OCR candidate',{label:c.fuse_label,kind:'endpoint_ocr_proximity',verification:c.verification,notes:c.reason+` • OCR confidence ${c.ocr_confidence}`,id:c.id});el.append(b)}
}
$('detectTerminals').onclick=async()=>{const b=$('detectTerminals');b.disabled=true;try{const r=await api('/api/terminal-detect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();alert(`${r.terminal_candidates} terminal OCR candidates, ${r.connector_column_candidates} connector-column candidates. No verified electrical connections.`)}catch(e){alert(e.message)}finally{b.disabled=false}};
$('exportTerminalCandidates').onclick=()=>{const blob=new Blob([JSON.stringify(S.terminalCandidates,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`autowiring-${S.diagram.id}-terminal-candidates-v036.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};

function renderCircleCandidates(){
 const d=S.circleCandidates;const el=$('circleList');el.replaceChildren();
 $('circleInfo').textContent=d.run?`${d.run.detected_circles} detected circles • ${d.run.matched_terminal_candidates} OCR matches • ${d.run.rejected_or_unmatched} rejected/unmatched • 0 verified connections`:'Run terminal OCR first, then circle detection.';
 for(const c of d.candidates){const b=document.createElement('button');b.textContent=`${c.fuse_label} → circle terminal ${c.terminal_text} (OCR ${Math.round(c.ocr_confidence*100)}%, UNVERIFIED)`;b.onclick=()=>inspect('circle OCR evidence',{label:c.fuse_label,kind:'circle_terminal_candidate',verification:c.verification,notes:c.reason,id:c.id});el.append(b)}
}
$('layerCircleEvidence').onchange=draw;
$('detectCircles').onclick=async()=>{const b=$('detectCircles');b.disabled=true;try{const r=await api('/api/circle-detect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();alert(`${r.detected_circles} circles, ${r.matched_terminal_candidates} strict OCR matches, ${r.rejected_or_unmatched} rejected/unmatched. NOT verified electrical connections.`)}catch(e){alert(e.message)}finally{b.disabled=false}};
$('exportCircles').onclick=()=>{const blob=new Blob([JSON.stringify(S.circleCandidates,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`autowiring-${S.diagram.id}-circle-evidence-v037.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};

function renderEvidence(){
 const d=S.evidence;const el=$('evidenceList');el.replaceChildren();
 $('evidenceInfo').textContent=d.run?`${d.run.detected_circles} circles audited • ${d.run.ocr_matches} OCR matches • 0 verified connections`:'Run circle-first OCR, then audit all detected circles.';
 if(!d.run)return;
 const counts=d.run.status_counts||{};const p=document.createElement('p');p.className='muted';p.textContent=Object.entries(counts).map(([k,v])=>k+': '+v).join(' • ');el.append(p);
 for(const c of d.circles.filter(c=>c.status==='ocr_match_unverified')){const b=document.createElement('button');b.textContent=`${c.nearest_fuse} → OCR ${c.ocr_text} (${Math.round(c.ocr_confidence*100)}%, unverified)`;b.onclick=()=>inspect('circle audit',{label:c.ocr_text,kind:c.status,verification:'visual_evidence_unverified',notes:c.reason,id:c.id});el.append(b)}
}
$('layerAllCircles').onchange=draw;
$('buildEvidence').onclick=async()=>{const b=$('buildEvidence');b.disabled=true;try{const r=await api('/api/evidence-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();$('layerAllCircles').checked=true;draw();alert(`${r.detected_circles} circles audited; ${r.ocr_matches} OCR matches. All unverified.`)}catch(e){alert(e.message)}finally{b.disabled=false}};
$('exportEvidence').onclick=()=>{const blob=new Blob([JSON.stringify(S.evidence,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`autowiring-${S.diagram.id}-evidence-v038.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};

function renderIndependent(){
 const d=S.independent;const el=$('independentList');el.replaceChildren();
 $('independentInfo').textContent=d.run?`${d.run.detected_circles} circles • ${d.run.ocr_read} OCR reads • ${d.run.ocr_unread} unread • 0 verified connections`:'Run independent circle OCR to inspect missed terminal numbers.';
 for(const c of d.circles.filter(c=>c.ocr_text)){const b=document.createElement('button');b.textContent=`Circle ${c.ocr_text} (${Math.round(c.ocr_confidence*100)}% OCR, UNASSOCIATED)`;b.onclick=()=>inspect('independent OCR',{label:c.ocr_text,kind:c.status,verification:'unverified',notes:`x=${c.x.toFixed(4)} y=${c.y.toFixed(4)}; ${c.reason}`,id:c.id});el.append(b)}
}
$('layerIndependent').onchange=draw;
$('scanIndependent').onclick=async()=>{const b=$('scanIndependent');b.disabled=true;$('independentInfo').textContent='Scanning all circles; this may take a while...';try{const r=await api('/api/independent-ocr-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();$('layerIndependent').checked=true;draw();alert(`${r.detected_circles} circles, ${r.ocr_read} OCR reads, ${r.ocr_unread} unread. No electrical connections verified.`)}catch(e){alert(e.message)}finally{b.disabled=false}};
$('exportIndependent').onclick=()=>{const blob=new Blob([JSON.stringify(S.independent,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`autowiring-${S.diagram.id}-independent-ocr-v039.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};

function renderPathMatches(){
 const d=S.pathMatches;const el=$('pathMatchList');el.replaceChildren();
 $('pathMatchInfo').textContent=d.run?`${d.run.fuse_candidates} fuse paths • ${d.run.geometric_matches} geometric candidates • ${d.run.unmatched} unmatched • 0 verified`:'Run independent OCR and then geometric path matching.';
 for(const m of d.matches){const b=document.createElement('button');b.textContent=`${m.fuse_label} → ${m.terminal_text||'unmatched'} (${m.reason}, UNVERIFIED)`;b.onclick=()=>inspect('geometric match',{label:m.fuse_label+' → '+(m.terminal_text||'?'),kind:m.status,verification:'unverified',notes:m.reason,id:m.id});el.append(b)}
}
$('layerPathMatches').onchange=draw;
$('buildPathMatches').onclick=async()=>{const b=$('buildPathMatches');b.disabled=true;try{const r=await api('/api/path-match-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();alert(`${r.geometric_matches} geometric matches / ${r.fuse_candidates} fuse paths; ${r.unmatched} unmatched. No verified electrical connections.`)}catch(e){alert(e.message)}finally{b.disabled=false}};
$('exportPathMatches').onclick=()=>{const blob=new Blob([JSON.stringify(S.pathMatches,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`autowiring-${S.diagram.id}-path-matches-v0310.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};

function renderFuseAudit(){
 const d=S.fuseAudit;const el=$('fuseAuditList');el.replaceChildren();
 $('fuseAuditInfo').textContent=d.run?`${d.run.labels_audited} labels • ${d.run.missing_association_candidates} missing association candidates • ${d.run.without_nearby_wire} without nearby wire • 0 verified`:'Audit missing fuse labels after segmentation and candidate circuit discovery.';
 for(const a of d.items){const b=document.createElement('button');b.textContent=`${a.label} [${a.source_text}] — ${a.status} (${a.edge_ids.length} segments)`;b.onclick=()=>inspect('fuse audit',{label:a.label,kind:a.status,verification:'unverified',notes:a.reason,id:a.id});el.append(b)}
}
$('layerFuseAudit').onchange=draw;
$('buildFuseAudit').onclick=async()=>{const b=$('buildFuseAudit');b.disabled=true;try{const r=await api('/api/fuse-audit-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();alert(`${r.labels_audited} labels audited, ${r.missing_association_candidates} missing association candidates. No electrical connections verified.`)}catch(e){alert(e.message)}finally{b.disabled=false}};
$('exportFuseAudit').onclick=()=>{const blob=new Blob([JSON.stringify(S.fuseAudit,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`autowiring-${S.diagram.id}-fuse-audit-v0311.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};

function renderLocalOCR(){
 const d=S.localOCR;const el=$('localOCRList');el.replaceChildren();
 $('localOCRInfo').textContent=d.run?`${d.run.ocr_suggestions} A/B OCR suggestions • 0 verified connections`:'Scan A/B CONT in overlapping image tiles.';
 for(const a of d.items){const b=document.createElement('button');b.textContent=`${a.label} — OCR ${Math.round(a.confidence*100)}% at (${a.x.toFixed(3)}, ${a.y.toFixed(3)})`;b.onclick=()=>inspect('localized OCR',{label:a.label,kind:'ocr_suggestion_unverified',verification:'unverified',notes:a.reason,id:a.id});el.append(b)}
}
$('layerLocalOCR').onchange=draw;
$('buildLocalOCR').onclick=async()=>{const b=$('buildLocalOCR');b.disabled=true;try{const r=await api('/api/local-ocr-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();alert(`${r.ocr_suggestions} localized A/B OCR suggestions. No verified connections.`)}catch(e){alert(e.message)}finally{b.disabled=false}};
$('exportLocalOCR').onclick=()=>{const blob=new Blob([JSON.stringify(S.localOCR,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`autowiring-${S.diagram.id}-local-ocr-v0312.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};

function renderDiagnostics(){
 const d=S.diagnostics;const el=$('diagnosticList');el.replaceChildren();
 $('diagnosticInfo').textContent=d.run?`${d.run.fuse_candidates} paths • ${d.run.geometric_candidates} eligible • ${d.run.rejected_or_ambiguous} rejected/ambiguous • 0 verified`:'Run diagnostics after independent OCR and fuse association.';
 for(const a of d.items){const b=document.createElement('button');const nearest=a.candidates[0];b.textContent=`${a.fuse_label}: ${a.reason}; nearest OCR ${nearest?nearest.terminal_text+' (dy='+nearest.vertical_offset+', gap='+nearest.horizontal_gap+')':'none'}`;b.onclick=()=>inspect('terminal diagnostic',{label:a.fuse_label,kind:a.reason,verification:'unverified',notes:JSON.stringify(a.candidates.slice(0,5)),id:a.id});el.append(b)}
}
$('layerDiagnostics').onchange=draw;
$('buildDiagnostics').onclick=async()=>{const b=$('buildDiagnostics');b.disabled=true;try{const r=await api('/api/match-diagnostics-build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();alert(`${r.geometric_candidates} geometric candidates / ${r.fuse_candidates} fuse paths; ${r.rejected_or_ambiguous} rejected or ambiguous. No verified connections.`)}catch(e){alert(e.message)}finally{b.disabled=false}};
$('exportDiagnostics').onclick=()=>{const blob=new Blob([JSON.stringify(S.diagnostics,null,2)],{type:'application/json'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`autowiring-${S.diagram.id}-match-diagnostics-v0313.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};

function renderContinuity(){const d=S.continuity,el=$('continuityList');el.replaceChildren();$('continuityInfo').textContent=d.run?`${d.run.visual_gap_suggestions} nearby collinear gaps; 0 verified`:'Run after Find candidate circuits.';for(const a of d.items){const b=document.createElement('button');b.textContent=`${a.fuse_label}: gap=${a.gap}, dy=${a.vertical_offset} (UNVERIFIED)`;b.onclick=()=>inspect('visual gap',{label:a.fuse_label,kind:a.status,verification:'unverified',notes:a.reason,id:a.id});el.append(b)}}
function renderTargeted(){const d=S.targeted,el=$('targetedList');el.replaceChildren();$('targetedInfo').textContent=d.run?`${d.run.ocr_attempts} OCR attempts; ${d.run.nonempty_reads} nonempty; 0 verified`:'Run Diagnose terminal matches first.';for(const a of d.items){const b=document.createElement('button');b.textContent=`${a.fuse_label} psm=${a.psm} scale=${a.scale}: ${a.raw_text.slice(0,65)||'(empty)'}`;b.onclick=()=>inspect('raw targeted OCR',{label:a.fuse_label,kind:'unverified_ocr',verification:'unverified',notes:a.raw_text,id:a.id});el.append(b)}}
$('layerContinuity').onchange=draw;
async function runAudit(button,path){const b=$(button);b.disabled=true;try{const r=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({diagram_id:S.diagram.id})});await refresh();$('status').textContent=Object.entries(r).filter(([k])=>k!=='warning'&&k!=='run_id').map(([k,v])=>k+': '+v).join(' • ')}catch(e){alert(e.message)}finally{b.disabled=false}}
$('buildContinuity').onclick=()=>runAudit('buildContinuity','/api/continuity-audit-build');
$('buildTargetedOCR').onclick=()=>runAudit('buildTargetedOCR','/api/targeted-ocr-build');
function exportAudit(data,suffix){const u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;const versions={'component-graph':'v0316','gap-visual':'v0315'};a.download=`autowiring-${S.diagram.id}-${suffix}-${versions[suffix]||'v0314'}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
$('exportContinuity').onclick=()=>exportAudit(S.continuity,'continuity-audit');
$('exportTargetedOCR').onclick=()=>exportAudit(S.targeted,'targeted-ocr');

function renderGapVisual(){
 const d=S.gapVisual,el=$('gapVisualList');el.replaceChildren();
 $('gapVisualInfo').textContent=d.run?`${d.run.gaps_inspected} source-image crops inspected; 0 verified connections`:'Run Audit collinear segment gaps first.';
 for(const a of d.items){
  const wrap=document.createElement('div');wrap.className='gap-visual-card';
  const title=document.createElement('div');title.textContent=`${a.fuse_label} — ${a.classification}; center ink ${a.centerline_ink_fraction}; UNVERIFIED`;
  const img=document.createElement('img');img.src='data:image/png;base64,'+a.crop_base64;img.alt='Original diagram crop around candidate gap';img.style.maxWidth='100%';img.style.imageRendering='pixelated';
  wrap.append(title,img);el.append(wrap);
 }
}
$('buildGapVisual').onclick=()=>runAudit('buildGapVisual','/api/gap-visual-build');
$('exportGapVisual').onclick=()=>exportAudit(S.gapVisual,'gap-visual');

function renderComponents(){const d=S.components,el=$('componentList');el.replaceChildren();$('componentInfo').textContent=d.run?`${d.run.fuse_symbol_candidates} fuse symbol hypotheses / ${d.run.component_hypotheses} candidates; 0 confirmed; 0 electrically verified`:'Run Inspect gap image crops first.';for(const a of d.items){const b=document.createElement('button');b.textContent=`${a.fuse_label}: ${a.component_type} (REVIEW REQUIRED)`;b.onclick=()=>inspect('component graph preview',{label:a.fuse_label,kind:a.component_type,verification:'unverified',notes:JSON.stringify(a.graph_preview,null,2),id:a.id});el.append(b)}}
$('layerComponents').onchange=draw;
$('buildComponents').onclick=()=>runAudit('buildComponents','/api/components-build');
$('exportComponents').onclick=()=>exportAudit(S.components,'component-graph');


// v0.3.17 is intentionally ONE click after v0.3.16. Never call old builders here.
function renderTrace(){
 const data=S.trace,box=$('traceList');box.replaceChildren();
 const r=data.run;
 const count=r?.component_hypotheses_reused||0;
 $('traceInfo').textContent=r
   ? count+' saved components reused • '+r.ratings_ocr_candidates+' rating OCR leads • '
     +r.geometric_terminal_leads+' geometric terminal leads • '
     +r.older_stages_rerun+' previous analysis stages rerun • 0 electrically verified connections.'
   :'Belum ada v0.3.17 trace. Klik Continue saved analysis SEKALI; hasil v0.3.16 akan dipakai tanpa proses ulang.';
 $('exportTrace').disabled=!r;
 for(const item of data.items){
   const card=document.createElement('div');card.className='trace-review-card'+(S.selectedTrace===item.component_id?' focused':'');
   const head=document.createElement('button');head.className='trace-review-focus';
   head.textContent=item.fuse_label+' • '+(item.display_rating||'rating unknown')
     +' • '+(item.terminal_text?'terminal OCR '+item.terminal_text:'terminal belum terbaca')
     +' • UNVERIFIED';
   head.onclick=()=>{S.selectedTrace=item.component_id;renderTrace();draw();inspect('saved trace',{label:item.fuse_label,kind:item.trace_status,verification:'unverified',notes:item.trace_reason+' / '+JSON.stringify(item.trace),id:item.id})};
   const details=document.createElement('div');details.className='muted';
   details.textContent='Shape: '+item.shape_status
     +' | Rating: '+item.rating_status
     +' | Trace: '+item.trace_status
     +' | Symbol reviewed: '+item.human_review
     +' | Pinout: NOT VERIFIED';
   card.append(head,details);
   const original=S.components.items.find(c=>c.id===item.component_id);
   const crop=original&&S.gapVisual.items.find(g=>g.source_gap_id===original.source_gap_id);
   if(crop){
     const pic=document.createElement('img');
     pic.src='data:image/png;base64,'+crop.crop_base64;
     pic.alt='Previous gap crop, annotated; manually verify fuse shape';
     pic.className='trace-preview';
     card.append(pic);
   }
   const controls=document.createElement('div');controls.className='trace-review-controls';
   const visual=document.createElement('select');
   visual.setAttribute('aria-label','Visual symbol review for '+item.fuse_label);
   for(const [val,label] of [['needs_review','Belum dikonfirmasi'],['confirmed_fuse_symbol','✓ Simbol fuse terlihat'],['rejected_not_fuse','✕ Bukan fuse']]){
     const opt=document.createElement('option');opt.value=val;opt.textContent=label;visual.append(opt);
   }
   visual.value=item.human_review;
   const rating=document.createElement('select');
   rating.setAttribute('aria-label','Manual fuse rating for '+item.fuse_label);
   for(const v of ['','5A','7.5A','10A','15A','20A','25A','30A','40A','50A','60A','70A','80A','100A']){
     const opt=document.createElement('option');opt.value=v;opt.textContent=v||'Rating tidak diketahui';rating.append(opt);
   }
   rating.value=item.human_rating||'';
   const save=document.createElement('button');save.textContent='Simpan review visual';
   save.onclick=async()=>{
     save.disabled=true;
     try{
       await api('/api/trace-review',{method:'POST',headers:{'Content-Type':'application/json'},
         body:JSON.stringify({diagram_id:S.diagram.id,component_id:item.component_id,
           review_status:visual.value,rating_override:rating.value||null})});
       S.trace=await api('/api/trace?diagram='+encodeURIComponent(S.diagram.id));
       renderTrace();draw();
       $('traceInfo').textContent='Review visual '+item.fuse_label+' disimpan. Tidak ada analisis atau konektivitas listrik yang dihitung ulang.';
     }catch(err){$('traceInfo').textContent='Error: '+err.message;save.disabled=false;}
   };
   controls.append(visual,rating,save);card.append(controls);box.append(card);
 }
}
$('layerTrace').onchange=draw;
$('buildTrace').onclick=async()=>{
 const b=$('buildTrace');b.disabled=true;
 $('traceInfo').textContent='Menggunakan hasil v0.3.16 yang tersimpan; hanya OCR rating lokal jika diperlukan...';
 try{
   const result=await api('/api/trace-build',{method:'POST',headers:{'Content-Type':'application/json'},
     body:JSON.stringify({diagram_id:S.diagram.id})});
   S.trace=await api('/api/trace?diagram='+encodeURIComponent(S.diagram.id));
   renderTrace();draw();
   $('traceInfo').textContent=(result.cache_hit?'CACHE HIT: hasil lama langsung dipakai. ':'ANALISIS LANJUTAN SELESAI. ')
     +result.component_hypotheses_reused+' komponen reused, '
     +result.ratings_ocr_candidates+' rating OCR candidate, '
     +result.geometric_terminal_leads+' terminal geometric candidate, '
     +result.older_stages_rerun+' proses lama diulang, 0 verified electrical connections.';
 }catch(err){$('traceInfo').textContent='Tidak berhasil: '+err.message;}
 finally{b.disabled=false;}
};
$('exportTrace').onclick=()=>{
 if(!S.trace.run)return;
 const u=URL.createObjectURL(new Blob([JSON.stringify(S.trace,null,2)],{type:'application/json'}));
 const a=document.createElement('a');a.href=u;
 a.download='autowiring-'+S.diagram.id+'-trace-review-v0317.json';
 a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);
};
