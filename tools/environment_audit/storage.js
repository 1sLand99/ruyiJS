(async window => {
  const out={};
  const request = value => new Promise((resolve,reject)=>{value.onsuccess=()=>resolve(value.result);value.onerror=()=>reject(value.error)});
  const transaction = value => new Promise((resolve,reject)=>{value.oncomplete=resolve;value.onabort=()=>reject(value.error)});
  try {
    const name='environment-audit';await request(indexedDB.deleteDatabase(name));
    const opening=indexedDB.open(name,1);
    opening.onupgradeneeded=()=>{const store=opening.result.createObjectStore('items',{keyPath:'id'});store.createIndex('group','group')};
    const db=await request(opening);let tx=db.transaction('items','readwrite'),done=transaction(tx);
    tx.objectStore('items').put({id:1,group:'x',bytes:new Uint8Array([3,4])});tx.objectStore('items').put({id:2,group:'x',bytes:new Uint8Array([5])});await done;
    tx=db.transaction('items');done=transaction(tx);const store=tx.objectStore('items');
    const [item,count,keys]=await Promise.all([request(store.get(1)),request(store.index('group').count('x')),request(store.getAllKeys())]);await done;
    out.indexedDB={item:[item.id,item.group,Array.from(item.bytes),item.bytes instanceof Uint8Array],count,keys,names:Array.from(db.objectStoreNames),version:db.version};
    db.close();await request(indexedDB.deleteDatabase(name));
  }catch(e){out.indexedDB={error:e.name,message:e.message}}
  try {
    await caches.delete('environment-audit');const cache=await caches.open('environment-audit');
    await cache.put('/cached',new Response('cached-body',{status:201,headers:{'x-test':'yes'}}));
    const r=await cache.match('/cached');out.cache={status:r.status,body:await r.text(),header:r.headers.get('x-test'),keys:(await cache.keys()).map(r=>new URL(r.url).pathname)};
    await caches.delete('environment-audit');
  }catch(e){out.cache={error:e.name,message:e.message}}
  try {
    const root=await navigator.storage.getDirectory();const dir=await root.getDirectoryHandle('environment-audit',{create:true});
    const handle=await dir.getFileHandle('data.txt',{create:true});const writer=await handle.createWritable();await writer.write('hello');await writer.close();
    const file=await handle.getFile();out.opfs={name:file.name,size:file.size,text:await file.text(),kind:handle.kind,same:await handle.isSameEntry(await dir.getFileHandle('data.txt'))};
    await root.removeEntry('environment-audit',{recursive:true});
  }catch(e){out.opfs={error:e.name,message:e.message}}
  try {
    const calls=[];await Promise.all([navigator.locks.request('audit',async lock=>{calls.push([lock.name,lock.mode,1]);await Promise.resolve();calls.push(['release',1])}),
      navigator.locks.request('audit',lock=>calls.push([lock.name,lock.mode,2]))]);out.locks=calls;
  }catch(e){out.locks={error:e.name,message:e.message}}
  return out;
})
