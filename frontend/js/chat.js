/* SQLite-backed history and validated SSE; localStorage stores only the selected ID. */
(() => {
  const $=selector=>document.querySelector(selector);
  let cid=null,busy=false,mode='unknown',editId=null,chatAbort=null,chatTimer=null;
  let syncing=false,lastSessions='',lastMessages='',lastMemories='',historyGeneration=0;
  const categories={basic:'基本信息',interest:'兴趣爱好',work:'学习工作',project:'长期项目',event:'重要事件',preference:'个人偏好',explicit:'明确记住'};
  const ui=window.petUI;
  const key='pixelpet-conversation';
  function remember(){try{if(cid)localStorage.setItem(key,cid);else localStorage.removeItem(key);}catch{/* Private browsing may disallow storage. */}}
  function saved(){try{return localStorage.getItem(key);}catch{return null;}}
  function error(message){$('#chat-error').textContent=message;$('#chat-error').hidden=false;}
  function lock(value){busy=value;if(value)historyGeneration++;document.querySelectorAll('#chat-form button,#conversation-select,#new-chat,#delete-chat,#clear-chat,[data-message]').forEach(button=>button.disabled=value);}
  async function api(path,options={}){
    const response=await fetch(path,{...options,headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(10000)});
    if(!response.ok){
      let body;try{body=await response.json();}catch{body={};}
      const detail=body.detail;
      throw new Error(typeof detail==='string'?detail:detail?.message||`请求失败（${response.status}），请稍后重试。`);
    }
    return response.json();
  }
  function append(text,role='assistant',meta=''){
    const article=document.createElement('article');article.className=`message${role==='user'?' user':''}`;
    const avatar=document.createElement('span');avatar.className='avatar';avatar.textContent=role==='user'?'你':'✦';avatar.setAttribute('aria-hidden','true');
    const content=document.createElement('div');content.className='message-content';
    const label=document.createElement('span');label.className='message-meta';label.textContent=role==='user'?'主人':`小星${meta?' · '+meta:''}`;
    const p=document.createElement('p');p.textContent=text;content.append(label,p);article.append(avatar,content);$('#chat-log').append(article);scroll();return {p,label,article};
  }
  function scroll(){$('#chat-log').scrollTop=$('#chat-log').scrollHeight;}
  function empty(){append('主人，我在呢。说点今天的事情吧，重要的信息我会收进记忆本。','assistant','欢迎').article.classList.add('welcome-message');}
  async function sessions(expected=null){
    const rows=await api('/api/conversations');
    if(expected!==null&&expected!==historyGeneration)return rows;
    const signature=JSON.stringify(rows);
    if(signature===lastSessions)return rows;
    lastSessions=signature;$('#conversation-select').replaceChildren();
    for(const row of rows){const option=document.createElement('option');option.value=row.id;option.textContent=row.title;$('#conversation-select').append(option);}
    if(cid)$('#conversation-select').value=cid;
    return rows;
  }
  async function load(id,expected=null){
    const messages=await api(`/api/conversations/${encodeURIComponent(id)}/messages`);
    if(expected!==null&&(expected!==historyGeneration||busy))return;
    const signature=JSON.stringify(messages);
    if(cid===id&&lastMessages===signature)return;
    lastMessages=signature;
    cid=id;remember();$('#conversation-select').value=id;$('#chat-log').replaceChildren();
    for(const message of messages){
      const meta=message.mode==='legacy'?'历史':responseMode(message.mode);
      const node=append(message.content,message.role,meta);
      if(message.status!=='complete'){node.label.textContent+=message.status==='pending'?' · 正在回复':' · 回复未完成，可重发';node.article.classList.add('failed-message');}
    }
    if(!messages.length)empty();
  }
  async function create(){const result=await api('/api/conversations',{method:'POST'});await sessions();await load(result.id);}
  function responseMode(value){return value==='mock'?'Mock 离线':value==='deepseek'?'DeepSeek':'AI';}
  async function send(text,{fromTouch=false,voiceStoppedAt=null}={}){
    if(busy||window.pixelPetRuntime?.isCapturing())return;
    window.pixelPetRuntime?.stopSpeech();
    text=text.trim().slice(0,2000);if(!text)return;
    lock(true);$('#chat-error').hidden=true;
    let node=null,done=false;
    try{
      if(!cid)await create();
      $('#chat-log .welcome-message')?.remove();
      append(text,'user');$('#message').value='';
      node=append('小星正在思考…','assistant',responseMode(mode));
      ui.renderAnimation('THINKING','thinking');
      chatAbort=new AbortController();
      chatTimer=setTimeout(()=>chatAbort?.abort(),310000);
      const response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,conversation_id:cid}),signal:chatAbort.signal});
      if(!response.ok){let body;try{body=await response.json();}catch{body={};}throw new Error(body.detail?.message||body.detail||`请求失败（${response.status}）`);}
      const reader=response.body.getReader();const decoder=new TextDecoder();let buffer='',reply='',firstTextAt=null;
      function event(block){
        let name='',data='';
        for(const line of block.split('\n')){if(line.startsWith('event:'))name=line.slice(6).trim();if(line.startsWith('data:'))data+=line.slice(5).trim();}
        if(!data)return;const item=JSON.parse(data);
        if(name==='meta'){cid=item.conversation_id;remember();node.label.textContent='小星 · '+responseMode(item.mode);}
        if(name==='delta'){firstTextAt??=performance.now();reply+=item.text;node.p.textContent=reply;ui.renderAnimation('THINKING','thinking');scroll();}
        if(name==='done'){
          done=true;
          node.p.textContent=item.reply;
          ui.renderAnimation(item.state==='SPEAKING'?'IDLE':item.state,item.emotion);
          ui.setSpeech(item.reply);
          scroll();
          window.dispatchEvent(new CustomEvent('pixelpet-reply',{detail:{...item,fromTouch,voiceStoppedAt,firstTextAt:firstTextAt??performance.now()}}));
        }
        if(name==='error')throw new Error(item.message||'模型暂时不可用，请稍后再试。');
      }
      try{
        while(true){const chunk=await reader.read();if(chunk.done)break;buffer+=decoder.decode(chunk.value,{stream:true}).replace(/\r\n/g,'\n');let boundary;while((boundary=buffer.indexOf('\n\n'))!==-1){event(buffer.slice(0,boundary));buffer=buffer.slice(boundary+2);}}
        if(!done)throw new Error('回复连接中断，用户消息已保存，请稍后重试。');
      }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
      await sessions();
      if(!$('#memory-panel').hidden)await memories();
    }catch(exc){
      if(done){error('回复已保存，但历史或记忆列表刷新失败。请稍后刷新页面。');}
      else{
        if(node){node.p.textContent='这次回复没有完成。';node.label.textContent='小星 · 未完成';node.article.classList.add('failed-message');}
        ui.renderAnimation('IDLE','normal');error(exc.message||'暂时无法聊天，请检查本地服务。');
      }
    }finally{clearTimeout(chatTimer);chatAbort=null;lock(false);$('#message').focus();}
  }
  async function memories(query){
    const rows=await api('/api/memories'+(query?'?q='+encodeURIComponent(query):''));
    const status=$('#memory-sync-status');if(status)status.textContent=`已同步 ${rows.length} 条长期记忆 · ${new Date().toLocaleTimeString('zh-CN')} · 完整聊天另行保存`;
    const signature=JSON.stringify(rows);if(lastMemories===signature)return;
    lastMemories=signature;$('#memory-list').replaceChildren();
    if(!rows.length){const p=document.createElement('p');p.className='memory-hint';p.textContent='还没有相关记忆。你可以告诉我“请记住…”，或者在下面手动新增。';$('#memory-list').append(p);}
    for(const memory of rows){
      const row=document.createElement('article');row.className='memory-card';row.dataset.memoryId=memory.id;
      const label=document.createElement('small');label.textContent=`${categories[memory.category]||memory.category} · 重要度 ${memory.importance.toFixed(2)} · ${memory.confirmed?'已确认':'待确认'} · 置信度 ${Math.round((memory.confidence??.9)*100)}% · ${new Date(memory.updated_at).toLocaleString('zh-CN')}`;
      const p=document.createElement('p');p.textContent=memory.content;
      const source=document.createElement('small');source.textContent='来源：'+memory.source;
      const tools=document.createElement('div');tools.className='memory-actions';
      const edit=document.createElement('button');edit.type='button';edit.textContent='编辑';edit.addEventListener('click',()=>{editId=memory.id;$('#memory-category').value=memory.category;$('#memory-content').value=memory.content;$('#memory-form button').textContent='✓';$('#memory-content').focus();});
      const remove=document.createElement('button');remove.type='button';remove.textContent='删除';remove.addEventListener('click',()=>safe(async()=>{await api('/api/memories/'+memory.id,{method:'DELETE'});if(editId===memory.id)resetEdit();await memories();}));
      if(!memory.confirmed){const confirm=document.createElement('button');confirm.type='button';confirm.textContent='确认';confirm.onclick=()=>safe(async()=>{await api('/api/memories/'+memory.id,{method:'PATCH',body:JSON.stringify({confirmed:true})});await memories();});tools.append(confirm);}
      tools.append(edit,remove);row.append(label,p,source,tools);$('#memory-list').append(row);
    }
  }
  function resetEdit(){editId=null;$('#memory-content').value='';$('#memory-form button').textContent='＋';}
  async function safe(operation){try{$('#chat-error').hidden=true;await operation();}catch(exc){error(exc.message);}}
  async function conversationOperation(operation){
    if(busy)return;lock(true);$('#chat-error').hidden=true;
    try{await operation();}
    catch(exc){$('#conversation-select').value=cid||'';error(exc.message);}
    finally{lock(false);}
  }
  $('#chat-form').addEventListener('submit',event=>{event.preventDefault();send($('#message').value);});
  document.querySelectorAll('[data-message]').forEach(button=>button.addEventListener('click',()=>send(button.dataset.message)));
  $('#new-chat').addEventListener('click',()=>{$('#follow-device-chat').checked=false;conversationOperation(create);});
  $('#conversation-select').addEventListener('change',()=>{$('#follow-device-chat').checked=false;conversationOperation(()=>load($('#conversation-select').value));});
  $('#clear-chat').addEventListener('click',()=>conversationOperation(async()=>{if(cid){await api(`/api/conversations/${cid}/messages`,{method:'DELETE'});$('#chat-log').replaceChildren();empty();await sessions();await load(cid);}}));
  $('#delete-chat').addEventListener('click',()=>conversationOperation(async()=>{if(cid)await api('/api/conversations/'+cid,{method:'DELETE'});cid=null;remember();$('#chat-log').replaceChildren();const rows=await sessions();if(rows.length)await load(rows[0].id);else await create();}));
  $('#open-memories').addEventListener('click',()=>safe(async()=>{$('#memory-panel').hidden=false;await memories();$('#memory-panel').scrollIntoView({behavior:'auto',block:'start'});}));
  $('#close-memories').addEventListener('click',()=>{$('#memory-panel').hidden=true;});
  $('#search-memories').addEventListener('click',()=>safe(()=>memories($('#memory-query').value.trim())));
  $('#all-memories').addEventListener('click',()=>{$('#memory-query').value='';safe(()=>memories());});
  $('#memory-form').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{const content=$('#memory-content').value.trim();if(!content)return;const body={content,category:$('#memory-category').value};await api('/api/memories'+(editId?'/'+editId:''),{method:editId?'PATCH':'POST',body:JSON.stringify(body)});resetEdit();await memories();});});
  window.addEventListener('pixelpet-touch',event=>{
    const touch=event.detail==='double_tap'?'主人轻轻点了小星两下':'主人轻轻摸了摸小星';
    send(`[触摸互动] ${touch}，请自然回应。`,{fromTouch:true});
  });
  window.pixelPetChat={send,isBusy:()=>busy,isResponding:()=>chatAbort!==null,cancel:()=>chatAbort?.abort()};
  async function syncHistory(){
    if(syncing||busy||document.hidden)return;
    syncing=true;
    try{
      const generation=historyGeneration;
      const rows=await sessions(generation);let selected=cid;
      if($('#follow-device-chat').checked){
        const status=await api('/api/devices/voice/status');
        const device=status.devices.filter(item=>rows.some(row=>row.id===item.conversation_id))
          .sort((a,b)=>String(b.last_heartbeat||b.connected_at).localeCompare(String(a.last_heartbeat||a.connected_at)))[0];
        if(device)selected=device.conversation_id;
      }
      if(!busy&&generation===historyGeneration&&selected&&rows.some(row=>row.id===selected))await load(selected,generation);
      if(!$('#memory-panel').hidden&&!editId&&!$('#memory-content').value.trim()&&
          !document.activeElement?.closest('#memory-list'))await memories($('#memory-query').value.trim());
      $('#history-sync-status').textContent=' · 已同步 '+new Date().toLocaleTimeString('zh-CN');
    }catch(exc){$('#history-sync-status').textContent=' · 同步失败，点刷新重试';}
    finally{syncing=false;}
  }
  $('#refresh-chat-history').addEventListener('click',syncHistory);
  $('#follow-device-chat').addEventListener('change',syncHistory);
  setInterval(syncHistory,3000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)syncHistory();});
  lock(true);
  safe(async()=>{
    const status=await api('/api/status');mode=status.mode;
    $('#chat-mode').textContent=mode==='mock'?'MOCK · 当前为离线规则测试模式':`${mode==='deepseek'?'DeepSeek':'AI'} · ${status.model} · 聊天和记忆保存在本机`;
    const rows=await sessions();const id=saved();
    if(rows.length)await load(rows.some(row=>row.id===id)?id:rows[0].id);else await create();
  }).finally(()=>lock(false));
})();
