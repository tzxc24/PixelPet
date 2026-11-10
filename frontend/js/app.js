/* Single local simulator: serialized API writes and clearly labelled demo chat. */
(() => {
  const $ = selector => document.querySelector(selector);
  const states = {IDLE:'待机',HAPPY:'开心',LISTENING:'聆听',THINKING:'思考',SPEAKING:'说话',SHY:'害羞',SLEEP:'睡觉',SURPRISED:'惊讶',ANNOYED:'气鼓鼓',ERROR:'出错'};
  const emotions = {normal:'平静',happy:'开心',curious:'好奇',thinking:'思考',shy:'害羞',sleepy:'困倦',surprised:'惊讶',sad:'低落',angry:'生气'};
  const stateEmotions = {IDLE:'normal',HAPPY:'happy',LISTENING:'curious',THINKING:'thinking',SPEAKING:'happy',SHY:'shy',SLEEP:'sleepy',SURPRISED:'surprised',ANNOYED:'angry',ERROR:'sad'};
  const speech = {IDLE:'嗨，主人！今天想做点什么？',HAPPY:'被你摸摸，就充满电啦！',LISTENING:'耳朵准备好了，正在模拟聆听～',THINKING:'嗯……让我认真想一想。',SPEAKING:'叽里咕噜，模拟说话中！',SHY:'哎呀，有一点点不好意思……',SLEEP:'星星也需要充电，呼噜～',SURPRISED:'哇！发生什么新鲜事啦？'};
  let queue = Promise.resolve();
  function clock(){const now=new Date(),prefs=window.pixelPetSettings||{};const options={hour12:prefs.time_format==='12',timeZone:prefs.time_zone||'Asia/Shanghai'};$('#clock').textContent=now.toLocaleTimeString('zh-CN',options);$('#date').textContent=now.toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long',timeZone:options.timeZone});}
  clock();setInterval(clock,1000);
  function renderAnimation(state,emotion=stateEmotions[state]){
    window.pixelPet.setState(state);
    $('#state-label').textContent=states[state];$('#state-code').textContent=state;
    $('#emotion').textContent=`${emotions[emotion]||emotion} · ${emotion}`;
    $('#pet-speech').textContent=speech[state]||'小星正在调整一下状态…';
    $('#pet').setAttribute('aria-label',`小星：${states[state]}`);
    document.querySelectorAll('[data-state]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.state===state)));
  }
  function apply(snapshot){
    if(!liveVoiceBusy())renderAnimation(snapshot.state,snapshot.emotion);
    $('#recording').textContent=snapshot.recording?'● 正在模拟录音':'录音模拟未开始';
    $('#audio-start').disabled=snapshot.recording;$('#audio-end').disabled=!snapshot.recording;
    for(const [id,key] of [['wifi','wifi_connected'],['ble','ble_connected']]){
      $(`#${id} span`).textContent=snapshot[key]?'已模拟连接':'未模拟连接';
      $(`#${id}`).classList.toggle('connected',snapshot[key]);
    }
    if(snapshot.last_event)$('#event-log').textContent=`${new Date().toLocaleTimeString('zh-CN',{hour12:false})} / ${snapshot.last_event}`;
  }
  async function request(path,payload){
    const response=await fetch(path,{method:payload?'POST':'GET',headers:payload?{'Content-Type':'application/json'}:{},body:payload?JSON.stringify(payload):undefined,signal:AbortSignal.timeout(5000)});
    if(!response.ok)throw new Error(`本地服务返回 ${response.status}，请检查服务后重试。`);
    return response.json();
  }
  function report(error){$('#connection').textContent='服务暂不可用';$('#error').hidden=false;$('#error').textContent=`连接失败：${error.message} 请确认本地服务正在运行，再点击表情或互动按钮重试。`;} 
  function online(){$('#connection').textContent='本地服务已连接';$('#error').hidden=true;}
  function liveVoiceBusy(){
    return window.pixelPetRuntime?.isCapturing()||window.pixelPetRuntime?.speaking||window.pixelPetChat?.isBusy();
  }
  function update(path,payload){
    // Continue after failed requests without poisoning subsequent button interactions.
    queue=queue.then(async()=>{try{apply(await request(path,payload));online();}catch(error){report(error);}});
    return queue;
  }
  document.querySelectorAll('[data-state]').forEach(button=>button.addEventListener('click',()=>{
    if(liveVoiceBusy())return;
    // Animation previews remain usable even when the backend is offline.
    renderAnimation(button.dataset.state);
    update('/api/simulator/preview',{state:button.dataset.state});
  }));
  document.querySelectorAll('[data-event]').forEach(button=>button.addEventListener('click',()=>{
    update('/api/simulator/events',{event:button.dataset.event}).then(()=>{
      if(button.dataset.event==='touch_start')window.dispatchEvent(new Event('pixelpet-touch'));
    });
  }));
  window.petUI={renderAnimation,setSpeech(text){$('#pet-speech').textContent=text;$('#pet-speech').title=text;}};
  update('/api/pet/state');
})();
