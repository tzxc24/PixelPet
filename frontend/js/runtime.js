/* Real PC audio and unified local effects. Never read a model credential in the browser. */
(() => {
  const $=selector=>document.querySelector(selector),ui=window.petUI;
  let prefs={},lastReply={reply:'你好呀！我是小星，是你的像素小伙伴。'},recording=false,recognizing=false,opening=false,playing=false;
  let recorder=null,stream=null,audioContext=null,analyser=null,timer=null,started=0,chunks=[],total=0,cancelRecording=false;
  let asrAbort=null,captureGeneration=0,micPermissionTimer=null,lastEffects=[],holdTimer=null,tapTimer=null,held=false,down=false;
  let notificationQueue=Promise.resolve(),pollingNotifications=false,notificationGeneration=0;
  let voiceStoppedAt=null;
  const metrics={asr_ms:null,llm_first_token_ms:null,llm_total_ms:null,tts_ms:null,voice_to_first_text_ms:null,voice_to_playing_ms:null};
  const authHeaders=extra=>window.pixelPetAuth?.headers(extra)||extra||{};
  const note=text=>{$('#voice-status').textContent=text;};
  const json=async(path,options={})=>{
    const response=await fetch(path,{...options,headers:authHeaders(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),signal:options.signal||AbortSignal.timeout(15000)});
    if(!response.ok){let body={};try{body=await response.json();}catch{}throw new Error(body.detail?.message||body.detail?.[0]?.msg||(typeof body.detail==='string'?body.detail:`请求失败 ${response.status}`));}
    return response.json();
  };
  function quiet(){
    if(!prefs.quiet_start||prefs.quiet_start===prefs.quiet_end)return false;
    const now=new Date().toLocaleTimeString('en-GB',{hour12:false,hour:'2-digit',minute:'2-digit',timeZone:prefs.time_zone||'Asia/Shanghai'});
    return prefs.quiet_start<prefs.quiet_end?now>=prefs.quiet_start&&now<prefs.quiet_end:now>=prefs.quiet_start||now<prefs.quiet_end;
  }
  async function event(type,payload={}){
    try{
      const result=await json('/api/events',{method:'POST',body:JSON.stringify({version:1,type,device_id:'browser-pixelpet',event_id:crypto.randomUUID(),timestamp:new Date().toISOString(),payload})});
      lastEffects=result.effects||[];
      for(const effect of lastEffects){
        if(effect.type==='haptic.pattern'||effect.type==='haptic.pulse'){
          $('#haptic-status').textContent=`模拟震动：${effect.payload.name||'pulse'} / ${effect.payload.strength}`;
          $('#haptic-status').classList.add('active');setTimeout(()=>$('#haptic-status').classList.remove('active'),500);
        }
      }
      return result;
    }catch(exc){note('事件未送达：'+exc.message);return null;}
  }
  async function configureEffects(){
    const quietMode=quiet();
    window.pixelPet.setSleepSchedule(quietMode);
    await json('/api/events/configure',{method:'PATCH',body:JSON.stringify({quiet_mode:quietMode})}).catch(()=>{});
  }
  const previewText='你好呀，我是小星！今天也很开心见到你，嘿嘿，要不要陪我聊聊天？';
  let audioState='IDLE',speechStarted=false;
  const audioPlayer=new window.PixelPetAudioPlayer({
    onState(state,metadata){
      audioState=state;playing=['GENERATING_AUDIO','PLAYING_AUDIO','STOPPING_AUDIO'].includes(state);
      $('#audio-state').textContent=state;
      if(state==='GENERATING_AUDIO'){window.pixelPetWake?.suspend();ui.renderAnimation('THINKING');note('正在生成自然语音…');}
      if(state==='PLAYING_AUDIO')note(`正在播放 · ${metadata.provider||'未知提供方'} · ${metadata.voice||''}${metadata.fallback&&metadata.fallback!=='none'&&metadata.fallback!=='false'?' · 已降级到离线声音':''}`);
      if(state==='IDLE'||state==='AUDIO_ERROR'){
        if(speechStarted){speechStarted=false;event('audio.speak_end');}
        if(!recording&&!opening&&!recognizing)ui.renderAnimation('IDLE');
        if(state==='IDLE')note('语音播放完成。');
      }
    },
    onPlaying(metadata,options){
      if(speechStarted)return;
      speechStarted=true;
      if(metadata.synthesis_ms!=null)metrics.tts_ms=Number(metadata.synthesis_ms);
      if(options.voiceStoppedAt!=null)metrics.voice_to_playing_ms=Math.round(performance.now()-options.voiceStoppedAt);
      event('audio.speak_start');
      ui.renderAnimation('SPEAKING',options.emotion);
    },
    onProgress(_progress,active,pose){window.pixelPet.setMouth(active?pose?.mouth??'closed':'closed');}
  });
  function stopSpeech(){audioPlayer.stop();}
  function speechControls(){const form=$('#settings-form');return {tts_provider:form.elements.tts_provider.value,voice:form.elements.voice.value,rate:Number(form.elements.rate.value),volume:Number(form.elements.volume.value),pitch_hz:Number(form.elements.pitch_hz.value)};}
  async function speak(text,manual=false,overrides=null,emotion='normal',stoppedAt=null){
    if(recording||recognizing||opening){note('录音和播放互斥，请先结束录音。');return;}
    if(manual&&window.pixelPetChat?.isResponding()){note('小星正在回复，请稍候再试听。');return;}
    if(!manual&&(quiet()||Number(prefs.volume)===0)){note('安静时段或音量为零，回复仅显示文字。');return;}
    const settings=overrides||prefs,provider=settings.tts_provider||'edge';
    const options={provider,voice:settings.voice||(provider==='edge'?'zh-CN-XiaoyiNeural':null),rate:settings.rate??1,volume:settings.volume??1,pitch_hz:settings.pitch_hz??0,allow_fallback:false,emotion,voiceStoppedAt:stoppedAt};
    try{
      if(manual)await audioPlayer.speak(text,options);
      else await audioPlayer.enqueue(text,options);
    }
    catch(error){note(error.message);}
  }
  function captureButtons(value){
    $('#voice-start').disabled=value;
    $('#voice-stop').disabled=!recording;
    $('#chat-form button').disabled=value||!!window.pixelPetChat?.isBusy();
    const touch=$('#touch-record');
    touch.disabled=recognizing;
    touch.setAttribute('aria-pressed',String(recording||opening));
    touch.textContent=recording?'点按结束并发送':opening?'点按取消麦克风请求':'点按录音，再点发送';
  }
  function releaseCapture(){
    clearInterval(timer);timer=null;stream?.getTracks().forEach(track=>track.stop());stream=null;
    audioContext?.close().catch(()=>{});audioContext=null;analyser=null;$('#voice-level').value=0;
  }
  async function startRecording({handsFree=false}={}){
    if(recording||recognizing||opening)return;
    if(window.pixelPetChat?.isBusy()){note('小星正在回复，请稍候再录音。');return;}
    if(prefs.asr_provider==='disabled'){note('语音识别已关闭，请在设置中开启。');return;}
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){note('此浏览器不支持录音，请使用新版 Edge/Chrome 或文字输入。');return;}
    window.pixelPetWake?.suspend();
    stopSpeech();voiceStoppedAt=null;const generation=++captureGeneration;opening=true;captureButtons(true);note('请允许使用麦克风…');
    try{
      const constraints={echoCancellation:true,noiseSuppression:true,channelCount:1};if(prefs.microphone_id)constraints.deviceId={exact:prefs.microphone_id};
      micPermissionTimer=setTimeout(()=>{
        if(generation!==captureGeneration||!opening)return;
        cancelCapture();
        note('等待麦克风授权超时。请检查地址栏权限后重新点按。');
      },20000);
      const acquired=await navigator.mediaDevices.getUserMedia({audio:constraints});
      if(generation!==captureGeneration){acquired.getTracks().forEach(track=>track.stop());return;}
      clearTimeout(micPermissionTimer);
      micPermissionTimer=null;
      stream=acquired;
      const mime=['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
      recorder=new MediaRecorder(stream,mime?{mimeType:mime}:{});chunks=[];total=0;cancelRecording=false;
      audioContext=new AudioContext();audioContext.resume().catch(()=>{});analyser=audioContext.createAnalyser();analyser.fftSize=256;audioContext.createMediaStreamSource(stream).connect(analyser);
      const format=stream.getAudioTracks()[0]?.getSettings()||{};
      const activeRecorder=recorder;
      recorder.ondataavailable=evt=>{if(generation!==captureGeneration)return;if(evt.data.size){chunks.push(evt.data);total+=evt.data.size;if(total>10*1024*1024){cancelCapture();note('录音超过 10MB，已取消。');}}};
      recorder.onstop=async()=>{
        if(generation!==captureGeneration)return;
        const stoppedAt=voiceStoppedAt??performance.now();
        const duration=stoppedAt-started,type=activeRecorder.mimeType||mime||'audio/webm',blob=new Blob(chunks,{type});chunks=[];recorder=null;recording=false;recognizing=true;captureButtons(true);releaseCapture();await event('audio.record_stop');
        if(generation!==captureGeneration)return;
        if(cancelRecording||blob.size===0){opening=recognizing=false;captureButtons(false);ui.renderAnimation('IDLE');return;}
        recognizing=true;captureButtons(true);ui.renderAnimation('THINKING');note('录音已结束，正在本机识别中文…');
        try{
          const form=new FormData();form.append('audio',blob,'pixelpet-recording.webm');form.append('duration_ms',String(Math.round(duration)));if(format.sampleRate)form.append('sample_rate',String(format.sampleRate));if(format.channelCount)form.append('channels',String(format.channelCount));
          const controller=new AbortController();asrAbort=controller;
          const deadline=setTimeout(()=>controller.abort(),130000);
          let result;
          try{result=await json('/api/audio/transcribe',{method:'POST',body:form,signal:controller.signal});}finally{clearTimeout(deadline);if(asrAbort===controller)asrAbort=null;}
          if(generation!==captureGeneration||cancelRecording)return;
          metrics.asr_ms=result.elapsed_ms??null;
          note(`识别：${result.text}（${result.elapsed_ms}ms）`);recognizing=false;captureButtons(false);await window.pixelPetChat.send(result.text,{voiceStoppedAt:stoppedAt});
        }catch(exc){if(generation===captureGeneration){note('识别未完成：'+exc.message);ui.renderAnimation('ERROR');}}
        finally{if(generation===captureGeneration){recognizing=false;captureButtons(false);}}
      };
      recorder.onerror=()=>{if(generation===captureGeneration){cancelCapture();note('录音设备发生错误，请检查麦克风后重试。');}};
      recorder.start(250);started=performance.now();recording=true;opening=false;captureButtons(true);ui.renderAnimation('LISTENING');
      let lastSpeech = null;
      const levels = new Float32Array(analyser.fftSize);
      timer=setInterval(()=>{
        const elapsed=performance.now()-started;
        $('#voice-time').textContent=`00:${String(Math.floor(elapsed/1000)).padStart(2,'0')}`;
        if(analyser){
          analyser.getFloatTimeDomainData(levels);
          const rms=Math.sqrt(levels.reduce((sum,value)=>sum+value*value,0)/levels.length);
          $('#voice-level').value=Math.min(1,rms*4);
          if(rms>=.012)lastSpeech=elapsed;
        }
        if(handsFree&&window.pixelPetWake.shouldFinish(elapsed,lastSpeech)){
          if(lastSpeech===null){cancelCapture();note('没有听到后续说话，可以再叫一次「小星」。');}
          else stopRecording();
        }else if(elapsed>=59000)stopRecording();
      },100);
      await event('audio.record_start');if(generation!==captureGeneration||!recording)return;note(handsFree?'正在聆听，停顿后自动发送。':'正在真实录音，结束后才识别；59 秒自动停止。');
      await microphones();
    }catch(exc){if(generation===captureGeneration){cancelCapture();note(exc.name==='NotAllowedError'?'麦克风权限被拒绝，请在地址栏允许麦克风后重试。':'无法打开麦克风：'+exc.message);}}
  }
  function stopRecording(){
    if(recorder&&recorder.state!=='inactive'){
      voiceStoppedAt=performance.now();
      recorder.stop();
    }
  }
  function cancelCapture(){
    clearTimeout(micPermissionTimer);
    micPermissionTimer=null;
    captureGeneration++;cancelRecording=true;asrAbort?.abort();asrAbort=null;
    const active=recording||opening||recognizing;
    stopRecording();recorder=null;chunks=[];total=0;opening=recording=recognizing=false;releaseCapture();captureButtons(false);
    if(active){event('audio.record_stop');ui.renderAnimation('IDLE');}
  }
  function applyPreferences(value){
    prefs=value;window.pixelPetSettings=value;$('#pet').style.filter=`brightness(${value.brightness})`;
    document.querySelector('.pet-caption .name').textContent=value.name+' ✦';
    for(const input of $('#settings-form').elements){if(!input.name||value[input.name]===undefined)continue;if(input.type==='checkbox')input.checked=value[input.name];else input.value=value[input.name];}
    refreshSpeechLabels();configureEffects();
  }
  async function microphones(){
    const select=$('#settings-form [name="microphone_id"]');select.replaceChildren(new Option('系统默认麦克风',''));
    const devices=await navigator.mediaDevices?.enumerateDevices().catch(()=>[])||[];
    for(const device of devices.filter(item=>item.kind==='audioinput'))select.append(new Option(device.label||'麦克风（需授权显示名称）',device.deviceId));select.value=prefs.microphone_id||'';
  }
  let voiceGeneration=0;
  async function voices(preferred){
    const generation=++voiceGeneration,select=$('#settings-form [name="voice"]'),provider=$('#settings-form [name="tts_provider"]').value||'edge';
    const wanted=preferred??select.value??prefs.voice;
    let list=[];
    try{list=provider==='browser'?(window.speechSynthesis?.getVoices()||[]).map(v=>({name:v.name,label:v.name+' · '+v.lang,available:true})):await json('/api/audio/voices?provider='+encodeURIComponent(provider));}
    catch(error){note('声音列表加载失败：'+error.message);}
    if(generation!==voiceGeneration)return;
    select.replaceChildren();
    for(const voice of list){const option=new Option(voice.label||voice.name,voice.name);option.disabled=voice.available===false;option.title=voice.reason||'';select.append(option);}
    if(!select.options.length)select.append(new Option(provider==='mock'?'Mock 测试声音':'没有可用声音',''));
    const available=Array.from(select.options).filter(o=>!o.disabled);select.value=available.some(o=>o.value===wanted)?wanted:available[0]?.value||'';
  }
  let speechSaveTimer=null,speechSaveSequence=0,speechSaveQueue=Promise.resolve();
  function refreshSpeechLabels(){const value=speechControls();$('#rate-value').textContent=`${value.rate.toFixed(2)} × (${Math.round((value.rate-1)*100)>=0?'+':''}${Math.round((value.rate-1)*100)}%)`;$('#volume-value').textContent=Math.round(value.volume*100)+'%';$('#pitch-value').textContent=(value.pitch_hz>=0?'+':'')+value.pitch_hz+' Hz';}
  function saveSpeech(){
    clearTimeout(speechSaveTimer);const sequence=++speechSaveSequence;refreshSpeechLabels();
    speechSaveTimer=setTimeout(()=>{
      const changes=speechControls();
      speechSaveQueue=speechSaveQueue.catch(()=>{}).then(async()=>{
        const result=await json('/api/pet/settings',{method:'PATCH',body:JSON.stringify(changes)});
        if(sequence===speechSaveSequence){prefs={...prefs,...changes};window.pixelPetSettings={...window.pixelPetSettings,...changes};$('#settings-status').textContent='语音设置已自动保存';}
      }).catch(error=>{$('#settings-status').textContent='保存失败：'+error.message;});
    },450);
  }
  async function diagnostics(){
    const data=await json('/api/diagnostics');
    const browser={...metrics,pet_state:window.pixelPet.state,behavior:window.pixelPet.behavior,audio_state:audioState,queued_audio:audioPlayer.queueLength};
    $('#diagnostics-output').textContent=JSON.stringify({...data,browser},null,2);
  }
  async function reminders(){
    const rows=await json('/api/reminders');$('#reminder-list').replaceChildren();
    for(const row of rows){const div=document.createElement('div');div.className='reminder-row';const text=document.createElement('span');text.textContent=`${row.text} · ${new Date(row.due_at).toLocaleString()} · ${row.status}`;const remove=document.createElement('button');remove.type='button';remove.textContent='删除';remove.onclick=()=>guard(async()=>{await json('/api/reminders/'+row.id,{method:'DELETE'});await reminders();});div.append(text,remove);$('#reminder-list').append(div);}
  }
  async function guard(operation){try{await operation();}catch(exc){note(exc.message);}}
  function speakReply(manual){
    return speak(lastReply.reply,manual,null,lastReply.emotion,manual?null:lastReply.voiceStoppedAt);
  }
  $('#voice-start').onclick=startRecording;$('#voice-stop').onclick=stopRecording;$('#voice-play').onclick=()=>speakReply(true);
  $('#voice-cancel').onclick=()=>{notificationGeneration++;cancelCapture();stopSpeech();window.pixelPetChat?.cancel?.();note('已停止播放或取消录音。');};
  window.addEventListener('pixelpet-reply',evt=>{
    lastReply=evt.detail;
    metrics.llm_first_token_ms=lastReply.timings?.llm_first_token_ms??null;
    metrics.llm_total_ms=lastReply.timings?.llm_total_ms??null;
    if(lastReply.voiceStoppedAt!=null){
      metrics.voice_to_first_text_ms=Math.round(lastReply.firstTextAt-lastReply.voiceStoppedAt);
      metrics.voice_to_playing_ms=null;
    }
    if($('#auto-speak').checked)speakReply(false);
  });
  $('#settings-toggle').onclick=()=>{$('#settings-panel').hidden=!$('#settings-panel').hidden;};$('#close-settings').onclick=()=>$('#settings-panel').hidden=true;
  $('#diagnostics-toggle').onclick=()=>guard(async()=>{$('#diagnostics-panel').hidden=!$('#diagnostics-panel').hidden;if(!$('#diagnostics-panel').hidden){await diagnostics();await reminders();}});$('#refresh-diagnostics').onclick=()=>guard(diagnostics);
  $('#settings-form').onsubmit=evt=>{evt.preventDefault();guard(async()=>{const changes={};for(const input of evt.target.elements){if(!input.name)continue;changes[input.name]=input.type==='checkbox'?input.checked:['range','number'].includes(input.type)?Number(input.value):input.value;}const result=await json('/api/pet/settings',{method:'PATCH',body:JSON.stringify(changes)});applyPreferences(result);$('#settings-status').textContent='设置已保存到 SQLite';await voices(prefs.voice);});};
  $('#settings-form [name="tts_provider"]').onchange=()=>guard(async()=>{stopSpeech();await voices('');saveSpeech();});
  for(const name of ['voice','rate','volume','pitch_hz'])$('#settings-form').elements[name].addEventListener('input',saveSpeech);
  $('#voice-preview').onclick=()=>speak(previewText,true,speechControls());
  $('#voice-defaults').onclick=()=>guard(async()=>{stopSpeech();const form=$('#settings-form');form.elements.tts_provider.value='edge';form.elements.rate.value='1';form.elements.volume.value='1';form.elements.pitch_hz.value='0';await voices('zh-CN-XiaoyiNeural');saveSpeech();});
  $('#reminder-form').onsubmit=evt=>{evt.preventDefault();guard(async()=>{await json('/api/reminders',{method:'POST',body:JSON.stringify({text:$('#reminder-text').value,due_at:new Date($('#reminder-time').value).toISOString()})});$('#reminder-text').value='';await reminders();});};
  $('#reminder-time').title='提醒时间使用本机时区：'+Intl.DateTimeFormat().resolvedOptions().timeZone;
  $('#reminder-time').setAttribute('aria-label','提醒时间（本机时区）');
  $('#clear-all-memories').onclick=()=>{if(confirm('清空全部长期记忆？聊天记录仍然保留。'))guard(async()=>{await json('/api/memories',{method:'DELETE'});$('#all-memories').click();});};
  async function respondToTouch(gesture){
    const result=await event('touch.'+gesture);
    if(!result||recording||opening||recognizing)return;
    if(!playing&&!window.pixelPetChat?.isBusy())ui.renderAnimation(window.pixelPet.touch(gesture==='double_tap'));
    window.dispatchEvent(new CustomEvent('pixelpet-touch',{detail:gesture}));
  }
  document.querySelectorAll('[data-touch]').forEach(button=>button.onclick=()=>guard(()=>respondToTouch(button.dataset.touch)));
  document.querySelectorAll('[data-haptic]').forEach(button=>button.onclick=()=>event('haptic.pattern',{name:button.dataset.haptic}));
  const pad=$('#touch-pad');
  $('#touch-record').onclick=()=>{
    if(opening)cancelCapture();
    else if(recording)stopRecording();
    else startRecording();
  };
  pad.onpointerdown=evt=>{if(down)return;down=true;held=false;pad.setPointerCapture(evt.pointerId);event('touch.touch_down');holdTimer=setTimeout(async()=>{held=true;await startRecording();if(recording)event('touch.long_press');},650);};
  pad.onpointerup=()=>{
    if(!down)return;
    down=false;
    clearTimeout(holdTimer);
    event('touch.touch_up');
    if(held){if(opening)cancelCapture();else stopRecording();return;}
    if(tapTimer){
      clearTimeout(tapTimer);
      tapTimer=null;
      guard(()=>respondToTouch('double_tap'));
    }else{
      tapTimer=setTimeout(()=>{tapTimer=null;guard(()=>respondToTouch('tap'));},250);
    }
  };
  pad.onpointercancel=()=>{down=false;clearTimeout(holdTimer);cancelCapture();event('touch.touch_up');};
  $('#export-frame').onclick=()=>guard(async()=>{const canvas=$('#pet'),context=canvas.getContext('2d');const response=await fetch('/api/assets/rgb565',{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify({width:240,height:240,rgba:Array.from(context.getImageData(0,0,240,240).data)})});if(!response.ok)throw new Error('像素导出失败');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download='pixelpet-240x240-rgb565-le.bin';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  window.pixelPetRuntime={speak,stopSpeech,startRecording,stopRecording,isCapturing:()=>recording||recognizing||opening,get speaking(){return playing;},get audioState(){return audioState;},get audioMetadata(){return audioPlayer.metadata;},event};
  guard(async()=>{
    applyPreferences(await json('/api/pet/settings'));await Promise.all([voices(prefs.voice),microphones()]);
    const [speech,status]=await Promise.all([json('/api/audio/status'),json('/api/status')]);
    $('#llm-ready').textContent=status.mode==='mock'?'Mock · 离线测试':'DeepSeek Live · '+status.model;
    $('#asr-ready').textContent=speech.asr.ready?'ASR Ready · '+speech.asr.model:'ASR Not Ready · 可用文字';
    $('#tts-ready').textContent=speech.tts.ready?'TTS Ready · '+(prefs.tts_provider||'edge'):'TTS Not Ready · 检查声音';
  });
  function showNotification(item){
    let history=$('#notification-history');
    if(!history){history=document.createElement('div');history.id='notification-history';history.setAttribute('role','log');history.setAttribute('aria-label','已触发提醒记录');$('#diagnostics-panel').append(history);}
    const entry=document.createElement('p');entry.textContent=`${new Date().toLocaleString()} · ${item.text}`;history.append(entry);
    while(history.children.length>100)history.firstElementChild.remove();
  }
  setInterval(()=>guard(async()=>{
    if(pollingNotifications)return;pollingNotifications=true;
    try{
      await configureEffects();const notices=await json('/api/notifications/poll');
      for(const item of notices){
        showNotification(item);const generation=notificationGeneration;
        notificationQueue=notificationQueue.catch(()=>{}).then(async()=>{
          while(generation===notificationGeneration&&(playing||recording||recognizing||opening||window.pixelPetChat?.isBusy()))await new Promise(resolve=>setTimeout(resolve,250));
          if(generation!==notificationGeneration)return;
          ui.setSpeech(item.text);note('提醒：'+item.text);if(!quiet())await speak(item.text);
        });
      }
    }finally{pollingNotifications=false;}
  }),15000);
})();
