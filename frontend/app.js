var d=document;
var curConv=null, convs={}, curAgent="", CK="aiagent_convos";
var abortCtrl=null, streaming=false;

marked.setOptions({
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  }
});

function H(t,c){
  var e=d.createElement(t);
  if(c)e.className=c;
  return e;
}
function T(e,v){
  if(v!==undefined)e.textContent=v;
  return e;
}
function scrollMsgs(){
  var m=d.getElementById("msgs");
  setTimeout(function(){m.scrollTop=m.scrollHeight},50);
}

// api
function api(url,opts){
  return fetch(url,opts).then(function(r){
    if(!r.ok)return r.text().then(function(t){throw new Error(t.slice(0,200))});
    return r;
  });
}

// conversations
function saveC(){try{localStorage.setItem(CK,JSON.stringify(convs))}catch(e){}}
function loadC(){
  try{var v=localStorage.getItem(CK);if(v)convs=JSON.parse(v)}catch(e){convs={}}
  Object.keys(convs).forEach(function(id){if(!Array.isArray(convs[id].msgs))convs[id].msgs=[]});
}

function newConv(){
  var id="c"+Date.now();
  convs[id]={name:"Dialogue "+(Object.keys(convs).length+1),msgs:[],created:new Date().toISOString(),agentId:curAgent};
  saveC();switchConv(id);
}
function switchConv(id){
  curConv=id;d.getElementById("msgs").innerHTML="";showEmpty();flushTL();
  var c=convs[id];
  if(c&&c.msgs)c.msgs.forEach(function(m){
    if(m.role==="user"){addMsgU(m.content)}
    else if(m.role==="assistant"&&m.content){addMsgA(m.content)}
  });
  if(c&&c.agentId!==undefined){curAgent=c.agentId;d.getElementById("agentSel").value=c.agentId}
  renderC();
}
function delConv(id,e){
  e.stopPropagation();
  if(!confirm("Delete?"))return;
  delete convs[id];saveC();
  if(curConv===id){var ks=Object.keys(convs);ks.length?switchConv(ks[0]):(curConv=null,d.getElementById("msgs").innerHTML="",showEmpty())}
  renderC();
}
function clearCur(){
  if(!curConv||!convs[curConv])return;
  convs[curConv].msgs=[];saveC();
  d.getElementById("msgs").innerHTML="";showEmpty();flushTL();
}
function renameConv(id){
  var c=convs[id];
  if(!c)return;
  var row=d.querySelector('.conv-row[data-cid="'+id+'"]');
  if(!row)return;
  var sn=row.firstChild,inp=d.createElement("input");
  inp.value=c.name||"";
  inp.style.cssText="background:var(--input);border:1px solid var(--cyan);color:var(--text);border-radius:var(--r);padding:2px 4px;font-size:12px;width:100%;outline:none;font-family:inherit;";
  row.replaceChild(inp,sn);inp.focus();inp.select();
  var saving=false;
  function done(save){
    if(saving)return;saving=true;
    if(save){var v=inp.value.trim();if(v)c.name=v;saveC();}
    renderC();
  }
  inp.onkeydown=function(e){
    if(e.key==="Enter")done(true);
    else if(e.key==="Escape")done(false);
  };
  inp.onblur=function(){done(true)};
}
function renderC(){
  var sel=d.getElementById("convSel"),box=d.getElementById("convBox");
  sel.innerHTML="";box.innerHTML="";
  var opt=d.createElement("option");opt.value="";opt.textContent="-- Switch --";sel.appendChild(opt);
  var ids=Object.keys(convs).sort(function(a,b){return new Date(convs[b].created)-new Date(convs[a].created)});
  if(!ids.length){var no=H("span","");no.textContent="No conversations";no.style.cssText="color:var(--text3);font-size:11px;";box.appendChild(no);return}
  ids.forEach(function(id){
    var c=convs[id];
    opt=d.createElement("option");opt.value=id;opt.textContent=c.name||"";if(id===curConv)opt.selected=true;sel.appendChild(opt);
    var row=H("div","conv-row");row.dataset.cid=id;
    var sn=H("span","");sn.textContent=c.name||"";
    var sr=H("span","crename");sr.textContent="✎";
    var sd=H("span","cdel");sd.textContent="x";
    row.appendChild(sn);row.appendChild(sr);row.appendChild(sd);
    sn.onclick=function(){switchConv(id)};
    sr.onclick=function(e){e.stopPropagation();renameConv(id)};
    sd.onclick=function(e){delConv(id,e)};
    box.appendChild(row);
  });
}

// agents
function showAgForm(){d.getElementById("agForm").classList.add("show");d.getElementById("agName").focus()}
function hideAgForm(){d.getElementById("agForm").classList.remove("show")}
function selectAgent(id){curAgent=id;if(curConv&&convs[curConv]){convs[curConv].agentId=id;saveC()}}
function createAgent(){
  var n=d.getElementById("agName").value.trim(),p=d.getElementById("agPrompt").value.trim();
  if(!n||!p){alert("Fill all fields");return}
  api("/api/agents",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n,prompt:p})}).then(function(){
    d.getElementById("agName").value="";d.getElementById("agPrompt").value="";hideAgForm();loadAgents();
  }).catch(function(e){alert("Failed: "+e.message)});
}
function delAgent(id){if(!confirm("Delete?"))return;api("/api/agents/"+id,{method:"DELETE"}).then(function(){loadAgents()}).catch(function(){})}
function loadAgents(){
  api("/api/agents").then(function(r){return r.json()}).then(function(agents){
    var sel=d.getElementById("agentSel"),box=d.getElementById("agentBox");
    sel.innerHTML="";box.innerHTML="";
    var def=d.createElement("option");def.value="";def.textContent="Default";sel.appendChild(def);
    if(!agents.length){var s=H("span","");s.textContent="No agents";s.style.cssText="color:var(--text3);font-size:11px;";box.appendChild(s);return}
    agents.forEach(function(a){
      var o=d.createElement("option");o.value=a.id;o.textContent="* "+a.name;if(a.id===curAgent)o.selected=true;sel.appendChild(o);
      var row=H("div","agent-row");
      var an=H("span","ag-name");an.textContent="* "+a.name;var ad=H("span","ag-del");ad.textContent="x";row.appendChild(an);row.appendChild(ad);
      row.querySelector(".ag-name").onclick=function(){curAgent=a.id;d.getElementById("agentSel").value=a.id};
      row.querySelector(".ag-del").onclick=function(){delAgent(a.id)};
      box.appendChild(row);
    });
  }).catch(function(){});
}

// chat
function setStreaming(on){
  streaming=on;
  var btn=d.getElementById("sendBtn");
  if(on){
    btn.textContent="■ 停止";
    btn.style.background="var(--rose)";
    btn.style.color="#fff";
    btn.style.border="none";
  }else{
    btn.textContent="发送";
    btn.style.background="var(--cyan)";
    btn.style.color="#000";
    btn.style.border="none";
  }
}

function stopGeneration(){
  if(abortCtrl){abortCtrl.abort();abortCtrl=null;}
}

function finishStreaming(ok){
  var nameTxt=arguments.length>1?arguments[1]:"";
  streaming=false;abortCtrl=null;setStreaming(false);setMascotIdle();
  if(ok&&nameTxt&&convs[curConv]&&convs[curConv].name&&convs[curConv].name.indexOf("Dialogue ")===0){
    convs[curConv].name=nameTxt.slice(0,20)+(nameTxt.length>20?"...":"");
    saveC();renderC();
  }
}

function handleFetchCatch(e,isAbort){
  if(isAbort||(e&&e.name==="AbortError")){finishBubble(pendingRaw);}
  else {addMsgA("Failed: "+(e.message||e));}
  finishStreaming(false);
}

function consumeResponse(resp,nameTxt){
  var reader=resp.body.getReader(),dec=new TextDecoder(),buf="";
  (function pump(){
    reader.read().then(function(r){
      if(r.done){finishStreaming(true,nameTxt);return}
      buf+=dec.decode(r.value,{stream:true});
      var parts=buf.split("\n\n");buf=parts.pop();
      parts.forEach(function(p){
        var ls=p.split("\n"),ev="",data="";
        ls.forEach(function(l){if(l.indexOf("event:")===0)ev=l.slice(7).trim();if(l.indexOf("data:")===0)data=l.slice(6).trim()});
        if(!data)return;
        try{var o=JSON.parse(data)}catch(e){return}
        if(ev==="tool_call"){showTC(o);logTL(o)}
        else if(ev==="token"){streamToken(o.token)}
        else if(ev==="done"){finishBubble(o.answer)}
      });
      pump();
    }).catch(function(e){handleFetchCatch(e,true)});
  })();
}

function send(){
  if(streaming){stopGeneration();return;}
  if(!curConv)newConv();
  var inp=d.getElementById("inp"),txt=inp.value.trim();
  if(!txt)return;inp.value="";
  setStreaming(true);setMascotThinking();
  addMsgU(txt);convs[curConv].msgs.push({role:"user",content:txt});saveC();
  var body={message:txt};if(curAgent)body.agent_id=curAgent;
  abortCtrl=new AbortController();
  fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body),signal:abortCtrl.signal})
    .then(function(resp){if(!resp.ok)return resp.text().then(function(t){throw new Error(t)});consumeResponse(resp,txt);})
    .catch(function(e){handleFetchCatch(e,false)});
}

function showEmpty(){
  var box=H("div","mt"),icon=H("span","mticon");icon.textContent="<>";
  icon.style.display="block";box.appendChild(icon);
  var txt=H("span","");txt.textContent="Enter a message to start";box.appendChild(txt);
  d.getElementById("msgs").appendChild(box);
}
function addMsgU(txt){
  var z=d.querySelector("#msgs .mt");if(z)z.remove();
  // Remove old regenerate buttons: only the latest AI response should have one
  var oldRgn=d.querySelectorAll(".msg-regen");oldRgn.forEach(function(el){el.remove()});
  var b=H("div","msg u");
  var t=H("span","");t.textContent=txt;b.appendChild(t);
  var cp=H("span","msg-cp");cp.textContent="⧉";cp.onclick=function(){copyMsg(txt,cp)};b.appendChild(cp);
  d.getElementById("msgs").appendChild(b);scrollMsgs();
}
function regenerate(){
  if(streaming)return;
  var msgsEl=d.getElementById("msgs");
  // Remove last AI message and preceding tool-call blocks from DOM
  var ais=msgsEl.querySelectorAll(".msg.a");
  if(ais.length>0){
    var lastAi=ais[ais.length-1];
    var prev=lastAi.previousElementSibling;
    while(prev&&prev.classList.contains("tc")){var tr=prev;prev=prev.previousElementSibling;tr.remove();}
    lastAi.remove();
  }
  // Remove last AI message from local store
  if(convs[curConv]&&convs[curConv].msgs.length){
    var ms=convs[curConv].msgs;
    for(var i=ms.length-1;i>=0;i--){if(ms[i].role==="assistant"){ms.splice(i,1);break;}}
    saveC();
  }
  setStreaming(true);setMascotThinking();
  abortCtrl=new AbortController();
  var regBody={};if(curAgent)regBody.agent_id=curAgent;
  fetch("/api/chat/regenerate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(regBody),signal:abortCtrl.signal})
    .then(function(resp){if(!resp.ok)return resp.text().then(function(t){throw new Error(t)});consumeResponse(resp,"");})
    .catch(function(e){handleFetchCatch(e,false)});
}
var pendingBubble=null,pendingRaw="";
function streamToken(tok){
  pendingRaw+=tok;
  var z=d.querySelector("#msgs .mt");if(z)z.remove();
  if(!pendingBubble){
    pendingBubble=H("div","msg a");
    var t=H("div","msg-body");pendingBubble.appendChild(t);
    d.getElementById("msgs").appendChild(pendingBubble);
  }
  pendingBubble.querySelector(".msg-body").innerHTML=marked.parse(pendingRaw);
  scrollMsgs();
}
function addRegenBtn(bubble){
  var rgn=H("span","msg-regen");rgn.textContent="↻";
  rgn.title="重新生成";
  rgn.onclick=function(e){e.stopPropagation();regenerate();};
  bubble.appendChild(rgn);
}

function finishBubble(fullText){
  if(!fullText){pendingBubble=null;pendingRaw="";return}
  var raw=fullText||pendingRaw;
  if(!pendingBubble){
    addMsgA(raw);return;
  }
  pendingBubble.querySelector(".msg-body").innerHTML=marked.parse(raw);
  var cp=H("span","msg-cp");cp.textContent="⧉";cp.onclick=function(){copyMsg(raw,cp)};
  pendingBubble.appendChild(cp);
  addRegenBtn(pendingBubble);
  convs[curConv].msgs.push({role:"assistant",content:raw});saveC();
  pendingBubble=null;pendingRaw="";
  scrollMsgs();
}
function addMsgA(txt){
  if(!txt)return;
  var z=d.querySelector("#msgs .mt");if(z)z.remove();
  var b=H("div","msg a");
  var t=H("div","msg-body");t.innerHTML=marked.parse(txt);b.appendChild(t);
  var cp=H("span","msg-cp");cp.textContent="⧉";cp.onclick=function(){copyMsg(txt,cp)};b.appendChild(cp);
  addRegenBtn(b);
  d.getElementById("msgs").appendChild(b);scrollMsgs();
}
function copyMsg(txt,el){
  navigator.clipboard.writeText(txt).then(function(){
    var orig=el.textContent;
    el.textContent="✓";
    setTimeout(function(){el.textContent=orig},1000);
  }).catch(function(){});
}

function showTC(info){
  var z=d.querySelector("#msgs .mt");if(z)z.remove();
  var tc=H("div","tc"),hd=H("div","tch"),bd=H("div","tcb");
  hd.textContent="* "+info.tool_name+" OK #"+info.iteration;
  hd.onclick=function(){bd.classList.toggle("open")};
  var p1=H("pre","");p1.textContent="Args: "+JSON.stringify(info.arguments||{},null,2);
  var p2=H("pre","");p2.textContent="Result: "+String(info.result||"").slice(0,800);
  p2.style.cssText="max-height:100px;overflow-y:auto;";
  bd.appendChild(p1);bd.appendChild(p2);
  tc.appendChild(hd);tc.appendChild(bd);
  d.getElementById("msgs").appendChild(tc);scrollMsgs();
}

var _mascotExcitedTimer=null;
function logTL(info){
  var m=d.getElementById("mascot");
  var bubble=d.getElementById("mascotBubble");
  var status=d.getElementById("mascotStatus");
  m.className="mascot excited";
  bubble.textContent="调用 "+info.tool_name+" ...";
  bubble.classList.add("show");
  status.textContent="已调用 "+info.tool_name;
  if(_mascotExcitedTimer)clearTimeout(_mascotExcitedTimer);
  _mascotExcitedTimer=setTimeout(function(){m.classList.remove("excited");bubble.classList.remove("show")},2200);
}
function flushTL(){
  var m=d.getElementById("mascot"),bubble=d.getElementById("mascotBubble"),status=d.getElementById("mascotStatus");
  m.className="mascot idle";bubble.classList.remove("show");bubble.textContent="";
  status.textContent=mascotIdleMsg();
}
var _mascotMsgs=["有什么我可以帮忙的？","今天也是个好日子~","加油！","我在听着呢~","随时准备帮忙！","(´･ω･`)","喵~ 有什么需要吗？"];
function mascotIdleMsg(){return _mascotMsgs[Math.floor(Math.random()*_mascotMsgs.length)]}
function setMascotThinking(){var m=d.getElementById("mascot");m.className="mascot thinking";d.getElementById("mascotStatus").textContent="思考中...";d.getElementById("mascotBubble").classList.remove("show")}
function setMascotIdle(){var m=d.getElementById("mascot");m.className="mascot idle";d.getElementById("mascotStatus").textContent=mascotIdleMsg()}

// skills
function loadSkills(){
  api("/api/skills").then(function(r){return r.json()}).then(function(data){
    var box=d.getElementById("skillsBox");box.innerHTML="";
    if(!data.skills||!data.skills.length){var s=H("span","");s.textContent="None";s.style.cssText="color:var(--text3);font-size:11px;";box.appendChild(s);return}
    data.skills.forEach(function(sk){
      var row=H("div","skill-row");
      var nm=H("span","sname");nm.textContent=sk.name;row.appendChild(nm);
      var ds=H("span","sdesc");ds.textContent=(sk.description||"").slice(0,60);row.appendChild(ds);
      var detail=H("div","skill-detail");detail.textContent="Loading...";
      row.onclick=function(){
        var was=row.classList.contains("open");row.classList.toggle("open");
        if(!was&&detail.textContent==="Loading..."){
          api("/api/skills/"+sk.name).then(function(r){return r.json()}).then(function(dd){
            detail.textContent=(dd.content||"").slice(0,2500)||"(empty)";
          }).catch(function(){detail.textContent="Failed to load"});
        }
      };
      box.appendChild(row);box.appendChild(detail);
    });
  }).catch(function(){d.getElementById("skillsBox").innerHTML="";var s=H("span","");s.textContent="Failed";s.style.color="var(--rose)";d.getElementById("skillsBox").appendChild(s)});
}

function loadSystem(){
  Promise.all([
    api("/api/config").then(function(r){return r.json()}),
    api("/api/skills").then(function(r){return r.json()})
  ]).then(function(v){
    var cfg=v[0],sd=v[1],box=d.getElementById("sysBox");box.innerHTML="";
    [{k:"Model",v:cfg.model},{k:"Token",v:cfg.max_tokens},{k:"Skills",v:sd.total}].forEach(function(item){
      var row=H("div","sys-row"),sk=H("span","sk"),sv=H("span","sv");
      sk.textContent=item.k;sv.textContent=item.v;
      row.appendChild(sk);row.appendChild(sv);box.appendChild(row);
    });
  }).catch(function(){});
}

function showConfig(){
  api("/api/config").then(function(r){return r.json()}).then(function(cfg){
    var tbl=d.getElementById("cfgTable");tbl.innerHTML="";
    Object.keys(cfg).forEach(function(k){
      var tr=d.createElement("tr"),td1=d.createElement("td"),td2=d.createElement("td");
      td1.textContent=k;td2.textContent=cfg[k];tr.appendChild(td1);tr.appendChild(td2);tbl.appendChild(tr);
    });
    d.getElementById("cfgOverlay").classList.add("show");
  }).catch(function(){});
}

// init
d.addEventListener("DOMContentLoaded",function(){
  api("/api/health").then(function(r){return r.json()}).then(function(data){d.getElementById("stat").textContent="model: "+data.model}).catch(function(){});
  loadC();renderC();loadSkills();loadSystem();loadAgents();setInterval(function(){var m=d.getElementById("mascot");if(m&&m.classList.contains("idle")){d.getElementById("mascotStatus").textContent=mascotIdleMsg()}},8000);
  var ids=Object.keys(convs);if(ids.length){ids.sort(function(a,b){return new Date(convs[b].created)-new Date(convs[a].created)});switchConv(ids[0])}
  else showEmpty();
});
