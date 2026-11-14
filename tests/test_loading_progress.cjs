/* Node-only test of the global progress indicator. No browser deps. */
const test=require("node:test");
const assert=require("node:assert/strict");
const vm=require("node:vm");
const fs=require("node:fs");
function create(offline=false){
  const events={};
  const nodes={};
  function element(id){
    return nodes[id]||(nodes[id]={id,hidden:true,textContent:"",
       dataset:{},setAttribute(){},removeAttribute(){}});
  }
  const doc={
    getElementById:element,
    documentElement:{setAttribute(k,v){this[k]=v},removeAttribute(k){delete this[k]}},
    addEventListener(type,fn,capture){events[type]=fn}
  };
  const context={
    document:doc,
    window:{fetch:()=>offline?Promise.reject(new Error('offline')):
      new Promise(resolve=>setTimeout(()=>resolve({ok:true,status:200}),85))},
    setTimeout,clearTimeout,setInterval,clearInterval,
    requestAnimationFrame:fn=>setTimeout(fn,0),
    performance:{now:()=>Date.now()},Promise,
  };
  vm.runInNewContext(fs.readFileSync("web/loading.js","utf8"),context);
  return {context,events,nodes,progress:context.window.ActionProgress};
}
test("visible spinner starts for EVERY button click and stops only after request+paint",async()=>{
  const {context,events,nodes,progress}=create();
  // Simulate any existing/legacy button without changing its click handler.
  events.click({target:{closest:()=>({
    disabled:false,dataset:{},textContent:"Find candidate circuits",
    getAttribute:()=>null,closest:()=>false})}});
  assert.equal(nodes.diagramLoading.hidden,false);
  assert.equal(progress.snapshot().active,true);
  const pending=context.window.fetch("/api/test-circuit-build");
  assert.equal(progress.snapshot().requests,1);
  await pending;
  // We cannot claim finished on only fetch resolution: still wait for paint.
  await progress.whenIdle();
  assert.equal(nodes.diagramLoading.hidden,true);
  assert.equal(nodes.activityResult.hidden,false);
  assert.match(nodes.activityResult.textContent,/Selesai:/);
  assert.equal(progress.snapshot().requests,0);
});
test("image decode hold keeps loading visible after network resolves",async()=>{
  const {context,events,nodes,progress}=create();
  events.change({target:{id:"diagram",matches:()=>false}});
  let release;
  const image=new Promise(resolve=>release=resolve);
  const tracked=progress.hold(image,"Memuat gambar diagram");
  await context.window.fetch("/api/diagrams");
  assert.equal(progress.snapshot().holds,1);
  assert.equal(nodes.diagramLoading.hidden,false);
  release();
  await tracked;
  await progress.whenIdle();
  assert.equal(nodes.diagramLoading.hidden,true);
  assert.equal(progress.snapshot().holds,0);
});
test("network error reports failure and never silently shows success",async()=>{
  const {context,progress,nodes}=create(true);
  await assert.rejects(context.window.fetch("/api/diagram"),/offline/);
  await progress.whenIdle();
  assert.equal(nodes.activityResult.dataset.state,"error");
  assert.match(nodes.activityResult.textContent,/offline/);
});
