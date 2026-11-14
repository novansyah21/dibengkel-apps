/* AutoWiring v0.3.21 — honest, global, indeterminate activity UI.
 * Every button/select action immediately exposes visible state; actual API
 * requests and image decoding keep it active. No fabricated progress percent.
 * Runs BEFORE app.js to see all initial and legacy requests, too.
 */
(function(){
  "use strict";
  const overlay=document.getElementById("diagramLoading");
  const title=document.getElementById("loadingTitle");
  const detail=document.getElementById("loadingDetail");
  const elapsed=document.getElementById("loadingElapsed");
  const state={active:false,requests:0,holds:0,completed:0,
    startAt:0,lastRequestAt:0,action:"Memuat diagram",error:"",
    idleTimer:null,clock:null,generation:0};
  const paint=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  function update(){
    if(!overlay)return;
    title.textContent=state.error
      ? "⚠ Proses selesai dengan kendala"
      : (state.requests+state.holds>0?"Sedang memproses…":"Menerapkan hasil pada gambar…");
    detail.textContent=state.action+" • "+state.completed+
      " permintaan selesai"+
      (state.requests>0?" • "+state.requests+" masih berjalan":"")+
      (state.holds>0?" • menunggu gambar":"")+
      (state.error?" • "+state.error:"");
    elapsed.textContent=((performance.now()-state.startAt)/1000).toFixed(1)+" detik";
  }
  function begin(label){
    clearTimeout(state.idleTimer);
    if(!state.active){
      state.active=true;state.startAt=performance.now();
      state.completed=0;state.error="";
      overlay.hidden=false;overlay.dataset.state="loading";
      state.clock=setInterval(update,150);
      document.documentElement.setAttribute("aria-busy","true");
    }
    state.action=String(label||"Memuat diagram").trim().slice(0,90);
    state.generation++;
    update();
    scheduleEnd();
  }
  function finish(){
    if(!state.active)return;
    clearTimeout(state.idleTimer);
    state.active=false;
    clearInterval(state.clock);
    document.documentElement.removeAttribute("aria-busy");
    const message=state.error
      ?"⚠ "+state.action+" — "+state.error
      :"✓ Selesai: "+state.action;
    const badge=document.getElementById("activityResult");
    if(badge){
      badge.textContent=message;
      badge.dataset.state=state.error?"error":"done";
      badge.hidden=false;
      clearTimeout(finish.badgeTimer);
      finish.badgeTimer=setTimeout(()=>{badge.hidden=true},3500);
    }
    overlay.hidden=true;overlay.dataset.state="idle";
  }
  function scheduleEnd(){
    clearTimeout(state.idleTimer);
    if(!state.active||state.requests||state.holds)return;
    const generation=state.generation;
    // A short delay lets sequences such as POST -> GET -> render stay in a
    // single activity without flickering or prematurely claiming completion.
    const wait=Math.max(330-(performance.now()-state.startAt),220);
    state.idleTimer=setTimeout(async()=>{
      if(state.generation!==generation||state.requests||state.holds)return;
      await paint();
      if(state.generation===generation&&!state.requests&&!state.holds)finish();
    },wait);
  }
  function addHold(promise,description){
    if(!state.active)begin(description||"Menyiapkan gambar");
    state.holds++;
    if(description)state.action=description;
    state.generation++;update();
    return Promise.resolve(promise).catch(error=>{
      state.error=error?.message||"Gambar gagal dimuat";
      update();throw error;
    }).finally(()=>{state.holds=Math.max(0,state.holds-1);state.generation++;update();scheduleEnd()});
  }
  function reportError(message){
    if(!state.active)begin("Permintaan");
    state.error=String(message||"Permintaan gagal").slice(0,130);
    update();scheduleEnd();
  }
  const originalFetch=window.fetch.bind(window);
  window.fetch=function(...args){
    const request=args[0],url=typeof request==="string"?request:(request?.url||"");
    const route=String(url).split("?")[0].split("/").pop();
    const actionName=route?route.replaceAll("-"," "):"Memuat data diagram";
    if(!state.active)begin("Memuat data diagram");
    // Do not replace a meaningful button label with a generic API endpoint;
    // initial load still gets a usable explicit status.
    if(!state.action||state.action==="Memuat diagram")state.action=actionName;
    state.requests++;state.generation++;update();
    return Promise.resolve().then(()=>originalFetch(...args))
      .then(response=>{
        if(!response.ok)reportError("HTTP "+response.status+" pada "+actionName);
        return response;
      }).catch(err=>{
        reportError(err?.message||"Koneksi ke aplikasi gagal");
        throw err;
      }).finally(()=>{
        state.requests=Math.max(0,state.requests-1);
        state.completed++;state.generation++;update();scheduleEnd();
      });
  };
  document.addEventListener("click",event=>{
    const button=event.target.closest?.("button");
    if(!button||button.disabled||button.closest("#diagramLoading"))return;
    const action=button.dataset.loadingLabel||
      button.textContent.replace(/\s+/g," ").trim()||
      button.getAttribute("aria-label")||"Menerapkan perubahan";
    begin(action);
  },true);
  document.addEventListener("change",event=>{
    if(event.target.id==="diagram"){
      begin("Mengganti diagram & memuat gambar");
    }else if(event.target.matches?.("input[type='checkbox']")){
      begin("Memperbarui layer pada gambar");
    }
  },true);
  document.addEventListener("submit",event=>{
    const target=event.target;
    if(target?.tagName==="FORM")begin("Menyimpan: "+(target.id||"form"));
  },true);
  window.ActionProgress={
    begin,hold:addHold,reportError,
    snapshot:()=>({active:state.active,requests:state.requests,holds:state.holds,
      completed:state.completed,action:state.action,error:state.error}),
    // For browser verification/debug, never intended as the application API.
    whenIdle:()=>new Promise(resolve=>{
      if(!state.active)return resolve();
      const timer=setInterval(()=>{if(!state.active){clearInterval(timer);resolve()}},25);
    })
  };
  // Show a meaningful indicator on initial page load, including first image.
  begin("Memuat AutoWiring & diagram");
})();
