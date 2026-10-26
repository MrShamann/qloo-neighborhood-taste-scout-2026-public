import assert from "node:assert/strict";
import test from "node:test";
import worker,{ready,authenticAgent,QlooBudget} from "./worker.mjs";

const a="d3cf323e-d045-4fb0-a67c-7e184fe56301";
const b="821f4056-9a1d-4017-9dcb-ce31fe513002";
const place="029dcf30-f509-4805-a933-601c05b2c003";
const scene={id:"bridge-new-york",city:"New York",artists:["Miles Davis","Radiohead"]};
const envReady={QLOO_API_KEY:"UNIT_TEST_DUMMY_NEVER_SENT",QLOO_CALLS_APPROVED:"YES",
  QLOO_ZERO_OVERAGE_VERIFIED:"YES",QLOO_PUBLIC_SOURCE_DISPLAY_RIGHTS_VERIFIED:"YES",
  FOUNDER_EXACT_PUBLIC_RELEASE_APPROVED:"YES",CF_WORKERS_FREE_PLAN_VERIFIED:"YES",
  QLOO_MAX_READS:"3"};
const search=(artist,id)=>({results:[{name:artist,entity_id:id,type:"urn:entity",
  subtype:"urn:entity:artist"}]});
const insights=()=>({results:[{name:"Artificial Venue One",entity_id:place,type:"urn:entity",
  subtype:"urn:entity:place",query:{explainability:{
  "signal.interests.entities":[{entity_id:a,score:.6},{entity_id:b,score:.4}]}}}]});
function sourceProvider(){
 let n=0;const urls=[];
 const handler=async(url,opts)=>{
   urls.push(url);
   assert.equal(new URL(url).origin,"https://hackathon.api.qloo.com");
   assert.equal(opts.method,"GET");
   assert.equal(opts.redirect,"error");
   assert.equal(opts.headers["X-Api-Key"],envReady.QLOO_API_KEY);
   const value=[search("Miles Davis",a),search("Radiohead",b),insights()][n++];
   if(!value)throw Error("too many sponsor calls");
   return new Response(JSON.stringify(value),{status:200,
     headers:{"content-type":"application/json","x-qloo-request-id":"test-fixture"}});
 };
 return {handler,urls};
}
// Unit tests must never depend on generated cloudflare/public assets.
 // The real generated asset pipeline is validated separately in Chromium.
const localAssets={
  async fetch(req){
    const path=new URL(req.url).pathname;
    const records={
      "/data/bridges.json":{bridges:[scene],provider_ready:false,live_call_count:0},
      "/data/scenes.json":{scenes:[],provider_ready:false},
      "/data/bridge.bridge-new-york.json":{
        scene_id:scene.id,provider_verified:false,provider_api_calls:0,
        mode:"SYNTHETIC_BRIDGE_REPLAY_NO_API",places:[]
      }
    };
    if(!Object.prototype.hasOwnProperty.call(records,path))
      return new Response("Not Found",{status:404});
    return new Response(JSON.stringify(records[path]),{status:200,
      headers:{"content-type":"application/json"}});
  }
};
const origin="http://qloo-private.test";
const post=(mode,id="bridge-new-york",headers={})=>new Request(origin+"/api/bridge",{
  method:"POST",headers:{origin,"content-type":"application/json",...headers},
  body:JSON.stringify({bridge_id:id,mode})});
function guardContext(){
 const map=new Map();let last=Promise.resolve();
 return {storage:{
   get:async k=>map.get(k),put:async(k,v)=>{map.set(k,v);}
 },blockConcurrencyWhile:fn=>{
   const previous=last;
   let finish;last=new Promise(r=>finish=r);
   return previous.then(fn).finally(finish);
 },map};
}
test("source gate is closed by default and no external calls required",async()=>{
 assert.equal(ready({}),false);
 const response=await worker.fetch(new Request(origin+"/api/bridges"),{ASSETS:localAssets});
 assert.equal(response.status,200);
 assert.equal((await response.json()).provider_ready,false);
 const noLive=await worker.fetch(post("live"),{ASSETS:localAssets});
 assert.equal(noLive.status,422);
 const replay=await worker.fetch(post("mock"),{ASSETS:localAssets});
 assert.equal(replay.status,200);
 const data=await replay.json();
 assert.equal(data.provider_verified,false);
 assert.equal(data.provider_api_calls,0);
});
test("origin and request controls refuse abuse",async()=>{
 assert.equal((await worker.fetch(post("mock",scene.id,{origin:"https://evil.test"}),
   {ASSETS:localAssets})).status,403);
 assert.equal((await worker.fetch(new Request(origin+"/api/bridge?a=1"),{
   ASSETS:localAssets})).status,400);
 assert.equal((await worker.fetch(post("snapshot"),{ASSETS:localAssets})).status,422);
 assert.equal((await worker.fetch(post("mock","unknown"),{ASSETS:localAssets})).status,422);
});
test("an authentic-shaped agent uses exactly two typed searches and one insights",async()=>{
 const {handler,urls}=sourceProvider();
 const result=await authenticAgent(scene,envReady.QLOO_API_KEY,handler);
 assert.equal(urls.length,3);
 assert.equal(new URL(urls[2]).pathname,"/v2/insights");
 assert.equal(result.provider_api_calls,3);
 assert.equal(result.provider_verified,true);
 assert.equal(result.places.length,1);
 assert.equal(result.places[0].source_coverage_count,2);
 assert.equal(result.places[0].agent_decision,"SOURCE_VALUES_FOR_BOTH_REVIEW_ONLY");
 assert.equal(result.automatic_actions,0);
});
test("ambiguous identity fails closed after first read",async()=>{
 let calls=0;
 const fake=async()=>{
   calls++;
   return new Response(JSON.stringify({results:[{name:"Miles Davis",entity_id:a}]}),{
     status:200});
 };
 await assert.rejects(authenticAgent(scene,envReady.QLOO_API_KEY,fake));
 assert.equal(calls,1);
});
test("Durable Object reserves globally, caches one source, and denies another run",async()=>{
 const ctx=guardContext();
 const api=new QlooBudget(ctx,envReady);
 const realFetch=globalThis.fetch;
 const {handler,urls}=sourceProvider();
 globalThis.fetch=handler;
 try{
   const req=()=>new Request("https://internal.invalid/run",{method:"POST",
     body:JSON.stringify(scene)});
   const first=await api.fetch(req());
   assert.equal(first.status,200);
   assert.equal((await first.json()).provider_api_calls,3);
   assert.equal(urls.length,3);
   assert.equal(ctx.map.get("reads_reserved"),3);
   const second=await api.fetch(req());
   assert.equal(second.status,200);
   const cached=await second.json();
   assert.equal(cached.provider_api_calls,0);
   assert.equal(cached.source_acquisition_calls,3);
   assert.equal(cached.source_data_is_live_per_request,false);
   assert.equal(cached.snapshot_is_sponsor_signed,false);
   assert.equal(urls.length,3);
   const exhausted=await api.fetch(new Request("https://internal.invalid/run",{
     method:"POST",body:JSON.stringify({...scene,id:"bridge-tokyo"})}));
   assert.equal(exhausted.status,429);
   assert.equal(urls.length,3);
 }finally{globalThis.fetch=realFetch;}
});

test("zero or subprecision explainability is NOT evidence for both inputs",async()=>{
  for(const rejectedScore of [0, -0.01, 0.000001, Number.NaN]){
    let count=0;
    const fake=async()=>{
      const results=[
        search("Miles Davis",a),
        search("Radiohead",b),
        insights()
      ];
      results[2].results[0].query.explainability["signal.interests.entities"][1].score=rejectedScore;
      const result=results[count++];
      return new Response(JSON.stringify(result),{status:200});
    };
    const doc=await authenticAgent(scene,envReady.QLOO_API_KEY,fake);
    assert.equal(count,3);
    assert.equal(doc.places[0].source_coverage_count,1);
    assert.equal(doc.places[0].agent_decision,"SECOND_INTEREST_NOT_EVIDENCED");
    assert.equal(doc.places[0].source_explainability.length,1);
  }
});


test("oversized provider response without Content-Length stops before further Qloo reads",async()=>{
  let count=0;
  const oversized=async(url,opts)=>{
    count++;
    assert.equal(new URL(url).pathname,"/search");
    const stream=new ReadableStream({
      start(controller){
        controller.enqueue(new Uint8Array(150000));
        controller.enqueue(new Uint8Array(60000));
        controller.close();
      }
    });
    return new Response(stream,{status:200,headers:{"content-type":"application/json"}});
  };
  await assert.rejects(authenticAgent(scene,envReady.QLOO_API_KEY,oversized),
                       /RESPONSE_TOO_LARGE/);
  assert.equal(count,1);
});
