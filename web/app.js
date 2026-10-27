"use strict";
const byId=id=>document.getElementById(id);
let scenes=[];
let active=null;
let ready=false;
function setText(id, value){byId(id).textContent=String(value);}
function node(tag,className,content){
  const e=document.createElement(tag);
  if(className)e.className=className;
  if(content!==undefined)e.textContent=String(content);
  return e;
}
function selectScene(id){
  const item=scenes.find(s=>s.id===id);
  if(!item)return;
  active=item;
  setText("brief-artist",item.artist);
  setText("brief-city",item.city+" / cultural discovery");
  for(const b of document.querySelectorAll(".scene"))b.setAttribute("aria-pressed",String(b.dataset.id===id));
  setText("results-title","A place to start, not a guess.");
  setText("results-sub",item.mission);
}
function addScenes(list){
  scenes=list;
  const root=byId("scenes");root.replaceChildren();
  for(const s of scenes){
    const button=node("button","scene");
    button.type="button";button.dataset.id=s.id;
    button.setAttribute("aria-pressed","false");
    button.append(node("span","number",s.visual));
    const content=node("div","body");
    content.append(node("span","name",s.name),node("span","context",s.deck));
    button.append(content,node("span","arrow","↗"));
    button.addEventListener("click",()=>selectScene(s.id));
    root.append(button);
  }
  selectScene(list[0]?.id);
}
function showResponse(data){
  setText("provenance",data.provider_verified?"QLOO LIVE / VERIFIED":"SYNTHETIC REPLAY / NOT QLOO");
  setText("results-title",data.provider_verified?"Grounded in Qloo data.":"A fictional rehearsal.");
  setText("results-sub",data.provider_verified
    ?"Entities returned through real Qloo Search and Insights, with a human review boundary."
    :"The three names below are synthetic fixture data, not actual businesses or Qloo recommendations.");
  const root=byId("places");
  root.className="places-list";
  root.replaceChildren();
  for(const p of data.places){
    const card=node("article","place");
    card.append(node("span","rank",String(p.rank).padStart(2,"0")));
    const detail=node("div","details");
    detail.append(node("h4","",p.name),node("p","",p.note),node("p","id","Qloo-like entity ID: "+p.qloo_entity_id));
    card.append(detail);
    root.append(card);
  }
  const trace=byId("timeline");trace.replaceChildren();
  data.agent_steps.forEach((step,i)=>trace.append(node("div","",(i+1).toString().padStart(2,"0")+" — "+step.phase+" · "+step.status)));
  setText("review",data.limits.join(" ")+" No automatic booking, targeting or identity inference.");
  setText("status",data.provider_verified
    ?"REAL SPONSOR API PROOF · Response received and schema-validated · Manual confirmation required."
    :"SYNTHETIC REPLAY ONLY · No Qloo API call · All places are fictional · No actual recommendations.");
}
async function run(){
  if(!active||!ready)return;
  const button=byId("run");button.disabled=true;
  const live=byId("live").checked;
  setText("status",live?"Checking event key and free Qloo quota gate…":"Executing synthetic two-tool replay…");
  try{
    const resp=await fetch("/api/execute",{method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({scene_id:active.id,mode:live?"live":"mock"})});
    const result=await resp.json();
    if(!resp.ok)throw Error(result.error||"The agent could not verify this request");
    showResponse(result);
  }catch(error){
    setText("status","STOPPED · "+error.message+" · No place recommendation was generated.");
    setText("provenance","BLOCKED / NO RESULT");
    setText("results-title","The agent abstained.");
    setText("results-sub","A missing event key, ambiguous entity or invalid provider response is not a reason to invent results.");
    const root=byId("places");root.className="results-placeholder";root.replaceChildren(node("p","","Fail-closed: no unverified output is shown."));
  }finally{button.disabled=false;}
}
async function boot(){
  try{
    const r=await fetch("/api/scenes",{cache:"no-store"});
    if(!r.ok)throw Error("Cannot load independent scenarios");
    const d=await r.json();
    ready=true;addScenes(d.scenes);
    byId("live").disabled=!d.provider_ready;
    byId("provider-hint").textContent=d.provider_ready
      ?"/ event key + authorized quota gate available"
      :"/ locked until issued key and free event quota are verified";
    byId("run").addEventListener("click",run);
  }catch(e){setText("status","LOCAL DEMO UNAVAILABLE · "+e.message);}
}
boot();

let bridgeList=[];
let activeBridge=null;
let bridgeEpoch=0;
let snapshotReadyScene=null;
function chooseBridge(id){
  const b=bridgeList.find(x=>x.id===id);
  if(!b)return;
  // Invalidate any earlier in-flight response before changing the scene.
  bridgeEpoch+=1;
  activeBridge=b;
  byId("bridge-snapshot").disabled=snapshotReadyScene!==id;
  for(const button of document.querySelectorAll(".bridge-choice")){
    button.setAttribute("aria-pressed",String(button.dataset.id===id));
  }
  setText("bridge-title",b.name);
  setText("bridge-subtitle",b.artists.join(" × ")+" / "+b.city+" — "+b.objective);
  setText("bridge-provenance","NOT RUN");
  setText("bridge-source-status","NOT RUN · This selected fictional brief has no verified Qloo result.");
  setText("bridge-steps","RESOLVE A → RESOLVE B → GROUND BOTH → VERIFY → HUMAN REVIEW / NOT RUN");
  const oldChain=byId("bridge-source-chain");
  oldChain.open=false;
  oldChain.hidden=true;
  byId("bridge-source-chain-details").replaceChildren();
  const list=byId("bridge-result-list");
  list.replaceChildren(node("p","muted","Run the selected brief to examine source-bound results."));
  byId("bridge-decision-note").replaceChildren(node("p","muted",
    "No source-bound candidate has been selected for human review."));
}
function displayBridgeEvidence(result){
  if(!result || !Array.isArray(result.places) || !Array.isArray(result.artists)
      || result.artists.length!==2 || result.human_confirmation_required!==true
      || result.automatic_actions!==0)throw Error("Untrusted group evidence");
  const real=result.provider_verified===true
    && result.mode==="QLOO_HACKATHON_TWO_ARTIST_API_LIVE"
    && result.provider_api_calls===3;
  const cached=result.provider_verified===true
    && result.mode==="QLOO_HACKATHON_VERIFIED_SOURCE_SNAPSHOT"
    && result.provider_api_calls===0
    && result.source_acquisition_calls===3
    && result.source_data_is_live_per_request===false
    && result.snapshot_is_sponsor_signed===false
    && typeof result.source_acquired_at_utc==="string"
    && /^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(result.source_acquired_at_utc)
    && result.scene_id===activeBridge.id;
  const fake=result.provider_verified===false
    && result.mode==="SYNTHETIC_BRIDGE_REPLAY_NO_API"
    && result.provider_api_calls===0;
  if(!real&&!fake&&!cached)throw Error("Source provenance cannot be verified");
  // Client-side truth boundary: a real-looking response for a different
  // brief must never be rendered, even if the server or its cache is wrong.
  if(result.scene_id!==activeBridge.id || result.city!==activeBridge.city ||
     result.artists.some((source,i)=>source.artist!==activeBridge.artists[i]))
    throw Error("Source belongs to another curator brief");
  if(!Array.isArray(result.agent_steps) || result.agent_steps.length!==5 ||
      result.agent_steps.some((step,i)=>!step ||
        step.phase!==["RESOLVE_A","RESOLVE_B","GROUND_BOTH","FACT_CHECK","HUMAN_REVIEW"][i] ||
        typeof step.status!=="string"))
    throw Error("Invalid source verification trail");
  if(result.source_explainability_count!==
      result.places.filter(place=>Array.isArray(place?.source_explainability) &&
        place.source_explainability.length>0).length)
    throw Error("Contradictory source evidence count");
  const sourced=real||cached;
  setText("bridge-provenance",cached?"QLOO SOURCE SNAPSHOT / NOT LIVE":
    real?"QLOO API × 3 / VERIFIED":"FICTIONAL REPLAY / NOT QLOO");
  const chain=byId("bridge-source-chain");
  const chainDetails=byId("bridge-source-chain-details");
  chain.hidden=false;
  chainDetails.replaceChildren();
  for(const [i,artist] of result.artists.entries()){
    if(typeof artist.artist!=="string" ||
       typeof artist.source_entity_id!=="string" ||
       !/^[0-9A-F-]{36}$/i.test(artist.source_entity_id))
      throw Error("Invalid source-resolved artist");
    chainDetails.append(node("p","bridge-chain-row",
       (sourced?"Qloo Search ":"FICTIONAL Search ")+(i+1)+
       " · "+artist.artist+" · "+artist.source_entity_id));
  }
  chainDetails.append(node("p","bridge-chain-row",
    (cached?"Qloo Insights cached":real?"Qloo Insights live":"FICTIONAL Insights replay")+
    " · two resolved IDs submitted jointly · no individual preference or venue-opening claim"));
  setText("bridge-title",activeBridge.name);
  setText("bridge-subtitle",cached
    ?"Previously acquired Qloo source, reviewed at "+result.source_acquired_at_utc+". No Qloo call is made per visitor; venue facts remain unverified."
    :real?"Two independently resolved artist IDs contributed to one Qloo Insights request. A rank is NOT proof of a group preference."
    :"Every venue and attribution below is invented test data, never an actual Qloo suggestion.");
  const placeRoot=byId("bridge-result-list");
  placeRoot.replaceChildren();
  byId("bridge-decision-note").replaceChildren(node("p","muted",
    "Select one candidate to prepare a source-based human review note; no booking or personal history."));
  for(const place of result.places){
    if(!place || typeof place.name!=="string" || !Array.isArray(place.source_explainability) ||
       place.source_coverage_is_user_fit!==false)
      throw Error("Missing place provenance");
    const cited=new Set(place.source_explainability.map(x=>x.entity_id));
    const coverage=cited.size;
    const expectedState=coverage===2?"BOTH_EXPLICIT_INPUT_IDS":
      coverage===1?"ONE_EXPLICIT_INPUT_ID":"NO_INTEREST_ATTRIBUTION_PROVIDED";
    const expectedDecision=coverage===2?"SOURCE_VALUES_FOR_BOTH_REVIEW_ONLY":
      coverage===1?"SECOND_INTEREST_NOT_EVIDENCED":"ABSTAIN_NO_INTEREST_ATTRIBUTION";
    if(coverage>2 || place.source_coverage_count!==coverage ||
       place.source_coverage_state!==expectedState ||
       place.agent_decision!==expectedDecision ||
       place.agent_decision_is_automatic_approval!==false ||
       [...cited].some(id=>!result.artists.some(a=>a.source_entity_id===id)))
      throw Error("Contradictory source coverage or agent decision");
    const card=node("article","bridge-place");
    card.append(node("span","bridge-rank",String(place.rank).padStart(2,"0")));
    const body=node("div","bridge-place-body");
    body.append(node("strong","bridge-place-name",place.name),
                node("small","bridge-place-id","Source entity: "+place.entity_id));
    body.append(node("small","bridge-place-coverage",
      coverage===2?"BOTH input IDs in reported source values; NOT verified shared taste":
      coverage===1?"ONE input ID in reported source values; not enough to infer two-person fit":
      "NO interpretable interest attribution; cannot infer why this place appeared"));
    body.append(node("small","bridge-place-decision",
      coverage===2?"NEXT: Check venue facts and suitability before considering this sourced candidate.":
      coverage===1?"HOLD: Ask for independent evidence about the second public interest.":
      "ABSTAIN: No support for a two-interest cultural recommendation."));
    if(place.source_explainability.length){
      const sourceRefs=place.source_explainability.map(ref=>{
        const artist=result.artists.find(x=>x.source_entity_id===ref.entity_id);
        if(!artist || typeof ref.score!=="number" || !Number.isFinite(ref.score)
            || ref.score<=0 || ref.score>1)throw Error("Untrusted source attribution");
        return artist.artist+": "+ref.score.toFixed(2);
      });
      body.append(node("small","bridge-place-explain",
          (sourced?"Reported source values: ":"FICTIONAL test values: ")+sourceRefs.join(" · ")));
    }else{
      body.append(node("small","bridge-place-missing",
        "Source did not supply interpretable per-place attribution; none inferred."));
    }
    const choose=node("button","bridge-review-button","Prepare review note");
    choose.type="button";
    choose.addEventListener("click",()=>{
      const note=byId("bridge-decision-note");
      note.replaceChildren();
      note.append(
        node("small","bridge-note-label",cached
          ?"HUMAN REVIEW NOTE / CACHED QLOO SOURCE — NOT LIVE"
          :real?"HUMAN REVIEW NOTE / REAL QLOO SOURCE"
          :"HUMAN REVIEW NOTE / FICTIONAL TEST DATA"),
        node("strong","bridge-note-venue",place.name),
        node("p","", "City: "+result.city+" · Source entity: "+place.entity_id),
        node("p","",coverage===2
          ?"Both public input entity IDs appear in explicitly reported source values, but that does not verify suitability for either person."
          :coverage===1
          ?"Only one input entity ID appears in reported values, so a shared-taste match is not established."
          :"No interpretable interest-level attribution exists; no cultural explanation is inferred."),
        node("p","bridge-note-verify",
          "Before choosing a location, independently verify venue identity, operating hours, availability and suitability. No booking, payment or outreach is authorized."),
        node("small","bridge-note-limits",
          cached?"Previously captured Qloo source, not vendor-signed or updated for each visitor. User benefit not measured."
              :real?"Source returned by official Qloo API; user benefit not measured."
              :"Fictional rehearsal only. Never use these locations as real business leads.")
      );
    });
    body.append(choose);
    card.append(body);
    placeRoot.append(card);
  }
  setText("bridge-source-status",cached
    ?"CACHED SOURCE: three historical Qloo reads documented; zero per-visitor Qloo calls. Not sponsor-signed; real user-fit not measured."
    :real?"Qloo Search × 2 + Insights × 1 returned schema-valid source entities. Real user-fit and impact NOT measured."
    :"OFFLINE EXAMPLE ONLY: fake entities, fake influence values and zero Qloo calls.");
  setText("bridge-steps",result.agent_steps.map(s=>s.phase+" "+s.status).join(" → "));
}
async function runBridge(modeOverride=null){
  if(!activeBridge)return;
  const requestedBridge=activeBridge;
  const requestedEpoch=bridgeEpoch;
  const button=modeOverride==="snapshot"?byId("bridge-snapshot"):byId("bridge-run");
  const live=modeOverride!=="snapshot" && byId("bridge-live").checked;
  const mode=modeOverride==="snapshot"?"snapshot":live?"live":"mock";
  if(mode==="snapshot" && snapshotReadyScene!==requestedBridge.id)return;
  button.disabled=true;
  setText("bridge-source-status",mode==="snapshot"
    ?"Loading a previously acquired, approved source snapshot; no live Qloo call…"
    :live?"Checking the approved event-key and no-spend call gate…"
    :"Executing an isolated, offline 2-search + 1-insight fictional replay…");
  try{
    const response=await fetch("/api/bridge",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({bridge_id:requestedBridge.id,mode:mode})
    });
    const data=await response.json();
    // A response is valid only for its exact initiating brief, never the one
    // selected later. A browser abort cannot revoke an upstream Qloo request.
    if(requestedEpoch!==bridgeEpoch || activeBridge!==requestedBridge)return;
    if(!response.ok)throw Error(data.error||"Source check failed");
    displayBridgeEvidence(data);
  }catch(e){
    if(requestedEpoch!==bridgeEpoch || activeBridge!==requestedBridge)return;
    // A rejected response must erase any source chain or trace from this or
    // a previous attempt. Never leave trusted-looking evidence on screen.
    const rejectedChain=byId("bridge-source-chain");
    rejectedChain.open=false;
    rejectedChain.hidden=true;
    byId("bridge-source-chain-details").replaceChildren();
    setText("bridge-steps","SOURCE REJECTED → ABSTAIN / NO VERIFIED SOURCE");
    setText("bridge-provenance","SOURCE REJECTED");
    setText("bridge-title","Agent abstained.");
    setText("bridge-subtitle","No source-grounded place can be safely displayed.");
    byId("bridge-result-list").replaceChildren(node("p","muted",
      "A missing signal, source mismatch, quota issue or unsafe result failed closed."));
    byId("bridge-decision-note").replaceChildren(node("p","muted",
      "No safe decision note can be prepared from rejected source data."));
    setText("bridge-source-status","BLOCKED · No provider fallback or fabricated recommendation.");
  }finally{
    button.disabled=mode==="snapshot" &&
      (!activeBridge || activeBridge.id!==snapshotReadyScene);
  }
}
async function bootBridge(){
  try{
    const r=await fetch("/api/bridges",{cache:"no-store"});
    if(!r.ok)throw Error("No curated bridge cases");
    const doc=await r.json();
    if(!Array.isArray(doc.bridges) || doc.bridges.length<1)
      throw Error("No original bridge scenarios");
    bridgeList=doc.bridges;
    snapshotReadyScene=doc.snapshot_ready===true &&
       typeof doc.snapshot_scene_id==="string" &&
       bridgeList.some(x=>x.id===doc.snapshot_scene_id)
       ?doc.snapshot_scene_id:null;
    const holder=byId("bridge-options");
    holder.replaceChildren();
    for(const b of bridgeList){
      if(!Array.isArray(b.artists) || b.artists.length!==2)
        throw Error("Invalid taste pair");
      const btn=node("button","bridge-choice");
      btn.type="button";
      btn.dataset.id=b.id;
      btn.setAttribute("aria-pressed","false");
      btn.append(node("strong","",b.artists.join(" × ")),
        node("small","",b.city+" · "+b.objective));
      btn.addEventListener("click",()=>chooseBridge(b.id));
      holder.append(btn);
    }
    chooseBridge(bridgeList[0].id);
    byId("bridge-run").disabled=false;
    byId("bridge-live").disabled=doc.provider_ready!==true;
    byId("bridge-live").checked=doc.provider_ready===true;
    setText("bridge-hint",snapshotReadyScene
      ?"One specifically approved historical Qloo source snapshot can be reviewed. Other briefs remain fictional; no live Qloo calls are made by visitors."
      :doc.provider_ready===true
      ?"REAL QLOO LIVE: every request makes two authenticated Search GETs and one Insights GET. No cached Qloo result, no automatic retries or booking."
      :"Real key delivery is not proof of quota. Live Qloo remains locked; zero API calls.");
    byId("bridge-run").addEventListener("click",()=>runBridge(null));
    byId("bridge-snapshot").addEventListener("click",()=>runBridge("snapshot"));
  }catch(e){
    setText("bridge-source-status","OFFLINE BRIDGE MODULE UNAVAILABLE — NO PROVIDER CLAIM");
  }
}
bootBridge();
