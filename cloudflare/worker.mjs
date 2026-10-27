/* Qloo contest-only FREE Worker live agent. Original code, no Qloo output cache.
 * Real provider calls require exact rights, free-plan, key and Founder gates.
 * A Durable Object reserves a global max before 3 GETs; never retries.
 */
const HOST="https://hackathon.api.qloo.com";
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const IDS=["bridge-new-york","bridge-tokyo","bridge-paris"];
const currentUTC=()=>new Date().toISOString().replace(/\.\d{3}Z$/,"Z");
const json=(v,status=200)=>new Response(JSON.stringify(v),{status,headers:{
  "content-type":"application/json; charset=utf-8","cache-control":"no-store",
  "x-content-type-options":"nosniff","referrer-policy":"no-referrer"}});
const fail=(status,message)=>json({error:message},status);
const object=v=>v!==null&&typeof v==="object"&&!Array.isArray(v);
const keys=(v,needed)=>object(v)&&Object.keys(v).sort().join()===needed.slice().sort().join();
const id=v=>typeof v==="string"&&UUID.test(v);
export const ready=e=>!!e.QLOO_API_KEY&&e.QLOO_API_KEY.length>=12&&
  e.QLOO_CALLS_APPROVED==="YES"&&e.QLOO_ZERO_OVERAGE_VERIFIED==="YES"&&
  e.QLOO_PUBLIC_SOURCE_DISPLAY_RIGHTS_VERIFIED==="YES"&&
  e.FOUNDER_EXACT_PUBLIC_RELEASE_APPROVED==="YES"&&
  e.CF_WORKERS_FREE_PLAN_VERIFIED==="YES";
const artistID=(data,name)=>{
  const rows=data?.results??data?.entities;
  if(data?.success===false||!Array.isArray(rows)||rows.length>100)throw Error("BAD_SEARCH");
  const hits=rows.filter(r=>object(r)&&r.name?.trim().toLowerCase()===name.trim().toLowerCase()&&
    id(r.entity_id??r.id)&&["urn:entity","urn:entity:artist",undefined].includes(r.type)&&
    [undefined,"urn:entity:artist"].includes(r.subtype)&&
    (r.types===undefined||(Array.isArray(r.types)&&r.types.includes("urn:entity:artist")))&&
    (r.type==="urn:entity:artist"||r.subtype==="urn:entity:artist"||
     r.types?.includes("urn:entity:artist"))).map(r=>r.entity_id??r.id);
  const unique=[...new Set(hits)];
  if(unique.length!==1)throw Error("AMBIGUOUS_ARTIST");
  return unique[0];
};
const places=(data,ids)=>{
  let rows=data?.results;
  if(object(rows))rows=rows.entities;
  if(data?.success===false||!Array.isArray(rows)||rows.length>200)throw Error("BAD_INSIGHTS");
  const out=[], seen=new Set();
  for(const r of rows){
    if(out.length===3)break;
    if(!object(r)||!id(r.entity_id??r.id)||typeof r.name!=="string"||
      !r.name.length||r.name.length>130||seen.has(r.entity_id??r.id)||
      !["urn:entity","urn:entity:place",undefined].includes(r.type)||
      ![undefined,"urn:entity:place"].includes(r.subtype)||
      (r.types!==undefined&&(!Array.isArray(r.types)||!r.types.includes("urn:entity:place")))||
      !(r.type==="urn:entity:place"||r.subtype==="urn:entity:place"||
       r.types?.includes("urn:entity:place")))continue;
    const eid=r.entity_id??r.id;seen.add(eid);
    const attribution=r.query?.explainability?.["signal.interests.entities"];
    const values=[], used=new Set();
    if(Array.isArray(attribution))for(const x of attribution.slice(0,8)){
      if(!object(x)||!ids.includes(x.entity_id)||used.has(x.entity_id)||
        typeof x.score!=="number"||!Number.isFinite(x.score)||x.score<=0||x.score>1||Math.round(x.score*1000)<=0)continue;
      used.add(x.entity_id);values.push({entity_id:x.entity_id,score:Math.round(x.score*1000)/1000});
    }
    const n=values.length;
    out.push({name:r.name,entity_id:eid,rank:out.length+1,source_explainability:values,
      source_attribution_state:n?"EXPLICIT_SOURCE_VALUES_ONLY":"UNAVAILABLE_NOT_INFERRED",
      source_coverage_count:n,source_coverage_state:n===2?"BOTH_EXPLICIT_INPUT_IDS":
        n===1?"ONE_EXPLICIT_INPUT_ID":"NO_INTEREST_ATTRIBUTION_PROVIDED",
      source_coverage_is_user_fit:false,
      agent_decision:n===2?"SOURCE_VALUES_FOR_BOTH_REVIEW_ONLY":
        n===1?"SECOND_INTEREST_NOT_EVIDENCED":"ABSTAIN_NO_INTEREST_ATTRIBUTION",
      agent_decision_is_automatic_approval:false});
  }
  if(!out.length)throw Error("NO_SUPPORTED_VENUE");
  return out;
};
async function qlooGET(path,params,key,fetcher){
  const url=new URL(path,HOST);
  if(url.origin!==HOST||!["/search","/v2/insights"].includes(url.pathname))throw Error("EGRESS");
  for(const [k,v] of Object.entries(params))url.searchParams.set(k,String(v));
  const r=await fetcher(url.toString(),{method:"GET",redirect:"error",
    headers:{"X-Api-Key":key,"Accept":"application/json"},signal:AbortSignal.timeout(18000)});
  if(r.status!==200||r.redirected)throw Error("PROVIDER_READ_FAILED");
  const size=Number(r.headers.get("content-length")??0);
  if(size>196608)throw Error("RESPONSE_TOO_LARGE");
  // Content-Length can be omitted or forged. Bound bytes DURING streaming
  // rather than allocating an unbounded arrayBuffer before validation.
  if(!r.body)throw Error("EMPTY_PROVIDER_BODY");
  const reader=r.body.getReader();
  const chunks=[];
  let total=0;
  try{
    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      total+=value.byteLength;
      if(total>196608){
        await reader.cancel().catch(()=>{});
        throw Error("RESPONSE_TOO_LARGE");
      }
      chunks.push(value);
    }
  }finally{reader.releaseLock();}
  const bytes=new Uint8Array(total);
  let offset=0;
  for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
  const result=JSON.parse(new TextDecoder().decode(bytes));
  if(!object(result))throw Error("BAD_JSON");
  return result;
}
export async function authenticAgent(scene,key,fetcher=fetch){
  if(!object(scene)||!IDS.includes(scene.id)||!["New York","Tokyo","Paris"].includes(scene.city)||
     !Array.isArray(scene.artists)||scene.artists.length!==2||
     scene.artists.some(a=>typeof a!=="string"||a.length<2||a.length>60))
    throw Error("INVALID_SCENE");
  const ids=[];
  for(const artist of scene.artists){
    const r=await qlooGET("/search",{query:artist,types:"urn:entity:artist",take:3,sort_by:"match"},key,fetcher);
    ids.push(artistID(r,artist));
  }
  if(ids[0]===ids[1])throw Error("DUPLICATE_ENTITY");
  const data=await qlooGET("/v2/insights",{"filter.type":"urn:entity:place",
    "signal.interests.entities":ids.join(","),"filter.location.query":scene.city,
    "filter.location.radius":0,take:3,"feature.explainability":"true"},key,fetcher);
  const rows=places(data,ids);
  return {mode:"QLOO_HACKATHON_TWO_ARTIST_API_LIVE",provider_verified:true,provider_api_calls:3,
    scene_id:scene.id,city:scene.city,
    artists:scene.artists.map((artist,i)=>({artist,source_entity_id:ids[i]})),
    places:rows,source_explainability_count:rows.filter(x=>x.source_explainability.length).length,
    agent_steps:[{phase:"RESOLVE_A",status:"LIVE"},{phase:"RESOLVE_B",status:"LIVE"},
      {phase:"GROUND_BOTH",status:"LIVE"},{phase:"FACT_CHECK",status:"PASS"},
      {phase:"HUMAN_REVIEW",status:"REQUIRED"}],
    automatic_actions:0,human_confirmation_required:true,
    comparison:{measured_user_benefit_proven:false,cross_taste_lift_proven:false},
    limits:["Aggregate public tastes only","Venue facts unverified","Missing attribution never inferred"]};
}
// Organizer confirms: event calls are free/no paid overage and judges must
// interact with LIVE source results. Never serve an old real Qloo snapshot.
// The Durable Object persists budget/lease only, not raw response data.
export class QlooBudget{
  constructor(ctx,env){this.ctx=ctx;this.env=env;}
  async fetch(request){
    if(request.method!=="POST"||new URL(request.url).pathname!=="/run")
      return fail(404,"NOT_FOUND");
    if(!ready(this.env))return fail(403,"LIVE_EVENT_ACCESS_NOT_AUTHORIZED");
    let scene;
    try{scene=await request.json();}catch{return fail(400,"BAD_JSON");}
    if(!object(scene)||!IDS.includes(scene.id)||!Array.isArray(scene.artists)||
       scene.artists.length!==2||typeof scene.city!=="string")
      return fail(422,"INVALID_SCENE");
    let reserved=false, reason="";
    try{
      await this.ctx.blockConcurrencyWhile(async()=>{
        const now=Date.now();
        const active=Number(await this.ctx.storage.get("active_until")||0);
        if(active>now){reason="BUSY";return;}
        const max=Number(this.env.QLOO_MAX_READS||3);
        if(!Number.isInteger(max)||max<3||max>300){reason="INVALID_BUDGET";return;}
        const used=Number(await this.ctx.storage.get("reads_reserved")||0);
        if(!Number.isInteger(used)||used<0||used+3>max){
          reason="EXHAUSTED";return;
        }
        // Reserve full worst-case quota BEFORE network, with no automatic
        // retries/refunds even if only the first read succeeds.
        await this.ctx.storage.put("reads_reserved",used+3);
        await this.ctx.storage.put("active_until",now+59000);
        reserved=true;
      });
    }catch{return fail(503,"PERSISTENT_BUDGET_GUARD_FAILED");}
    if(!reserved){
      if(reason==="BUSY")return fail(409,"A_LIVE_QLOO_RUN_IS_IN_PROGRESS");
      if(reason==="EXHAUSTED")return fail(429,"FIXED_EVENT_READ_BUDGET_EXHAUSTED");
      return fail(503,"EVENT_BUDGET_CONFIGURATION_INVALID");
    }
    try{
      const source=await authenticAgent(scene,this.env.QLOO_API_KEY);
      // Do not save source to Durable Object, KV, file or public repository.
      return json(source);
    }catch{
      // Provider errors abstain. We never turn failed live requests into mocks.
      return fail(502,"QLOO_LIVE_SOURCE_FAILED_NO_RETRY");
    }finally{
      // On a crash, the 59-second lease expires rather than silently replaying
      // a prior response. The consumed call budget is never refunded.
      try{await this.ctx.storage.delete("active_until");}catch{}
    }
  }
}
async function asset(env,request,path){
  const u=new URL(path,request.url);
  const r=await env.ASSETS.fetch(new Request(u.toString()));
  if(r.status!==200)return fail(503,"STATIC_SOURCE_MISSING");
  return json(await r.json());
}
export default {async fetch(request,env){
  const url=new URL(request.url);
  if(!url.pathname.startsWith("/api/"))return env.ASSETS.fetch(request);
  if(url.search)return fail(400,"QUERY_NOT_ALLOWED");
  if(request.method==="GET"){
    if(url.pathname==="/api/scenes")return asset(env,request,"/data/scenes.json");
    if(url.pathname==="/api/bridges"){
      const data=await asset(env,request,"/data/bridges.json");
      const doc=await data.json();
      return json({...doc,provider_ready:!!ready(env)&&!!env.QLOO_BUDGET});
    }
    return fail(404,"NOT_FOUND");
  }
  if(request.method!=="POST"||!["/api/bridge","/api/execute"].includes(url.pathname))
    return fail(405,"METHOD_NOT_ALLOWED");
  if(request.headers.get("origin")!==url.origin)return fail(403,"ORIGIN_REQUIRED");
  if(!request.headers.get("content-type")?.startsWith("application/json"))return fail(415,"JSON_REQUIRED");
  let input;
  try{const s=await request.text();if(s.length>512)return fail(413,"BODY_TOO_LARGE");input=JSON.parse(s);}
  catch{return fail(400,"BAD_JSON");}
  if(url.pathname==="/api/execute"){
    if(!keys(input,["scene_id","mode"])||input.mode!=="mock"||
      !["jazz-new-york","jazz-tokyo","jazz-paris"].includes(input.scene_id))
      return fail(422,"SYNTHETIC_ONLY");
    return asset(env,request,"/data/scene."+input.scene_id+".json");
  }
  if(!keys(input,["bridge_id","mode"])||!IDS.includes(input.bridge_id))
    return fail(422,"UNSUPPORTED_BRIEF");
  if(input.mode==="mock")return asset(env,request,"/data/bridge."+input.bridge_id+".json");
  if(input.mode!=="live")return fail(422,"UNSUPPORTED_MODE");
  if(!ready(env)||!env.QLOO_BUDGET)return fail(422,"NO_LIVE_ACCESS");
  const catalogue=await (await asset(env,request,"/data/bridges.json")).json();
  const scene=catalogue.bridges?.find(x=>x.id===input.bridge_id);
  if(!scene)return fail(422,"UNKNOWN_SCENE");
  const stub=env.QLOO_BUDGET.get(env.QLOO_BUDGET.idFromName("global-qloo-agent-budget"));
  return stub.fetch(new Request("https://internal.invalid/run",{method:"POST",body:JSON.stringify(scene)}));
}};
