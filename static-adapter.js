/* Strict static review adapter: only local generated SYNTHETIC JSON.
No backend, Qloo key, real API call, booking or external network. */
'use strict';
(()=>{
  const realFetch=window.fetch.bind(window);
  const allowedScenes=new Set(['jazz-new-york','jazz-tokyo','jazz-paris']);
  const allowedBridges=new Set(['bridge-new-york','bridge-tokyo','bridge-paris']);
  const rejected=(code,error)=>new Response(JSON.stringify({error}),
    {status:code,headers:{'Content-Type':'application/json'}});
  const exactKeys=(val,keys)=>val && typeof val==='object' &&
    !Array.isArray(val) &&
    Object.keys(val).sort().join('|')===keys.slice().sort().join('|');
  const local=(name)=>realFetch('./data/'+name,{cache:'no-store'});
  window.QLOO_STATIC_OFFLINE_ONLY=true;
  window.fetch=(url,options={})=>{
    if(typeof url!=='string' || !url.startsWith('/api/'))
      return Promise.resolve(rejected(403,'STATIC_EXTERNAL_FETCH_BLOCKED'));
    const method=(options.method||'GET').toUpperCase();
    if(method==='GET'){
      if(url==='/api/scenes')return local('scenes.json');
      if(url==='/api/bridges')return local('bridges.json');
      return Promise.resolve(rejected(404,'NOT_FOUND'));
    }
    if(method!=='POST')return Promise.resolve(rejected(405,'METHOD_NOT_ALLOWED'));
    let body;
    try{body=JSON.parse(options.body)}catch(_){
      return Promise.resolve(rejected(400,'INVALID_JSON'));
    }
    if(url==='/api/bridge'){
      if(!exactKeys(body,['bridge_id','mode']) ||
          body.mode!=='mock' || !allowedBridges.has(body.bridge_id))
        return Promise.resolve(rejected(422,'SYNTHETIC_ONLY'));
      return local('bridge.'+body.bridge_id+'.json');
    }
    if(url==='/api/execute'){
      if(!exactKeys(body,['scene_id','mode']) ||
          body.mode!=='mock' || !allowedScenes.has(body.scene_id))
        return Promise.resolve(rejected(422,'SYNTHETIC_ONLY'));
      return local('scene.'+body.scene_id+'.json');
    }
    return Promise.resolve(rejected(403,'UNSUPPORTED'));
  };
})();