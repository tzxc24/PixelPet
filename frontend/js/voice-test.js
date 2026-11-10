(() => {
  const $=s=>document.querySelector(s),phrase=$('#preview-phrase').textContent;
  const player=new window.PixelPetAudioPlayer({onState(state,metadata){
    $('#test-state').textContent=state;
    $('#test-status').textContent=state==='GENERATING_AUDIO'?'正在生成在线自然语音…':state==='PLAYING_AUDIO'?'正在播放真实 WAV。':state==='IDLE'?'播放已结束，可以继续对比。':state==='STOPPING_AUDIO'?'正在停止…':'语音生成或播放失败。';
    if(metadata.provider){$('#test-provider').textContent=metadata.provider+(metadata.fallback&&metadata.fallback!=='none'&&metadata.fallback!=='false'?'（发生降级）':'');$('#test-voice').textContent=metadata.voice||'—';$('#test-ms').textContent=(metadata.synthesis_ms??'—')+' ms';$('#test-params').textContent=`语速 ${metadata.rate_percent??'—'}% · 音高 ${metadata.pitch_hz??'—'} Hz · 音量 ${metadata.volume_percent??'—'}%`;$('#test-format').textContent=`${metadata.codec||'WAV'} · ${metadata.sample_rate||'—'} Hz · ${metadata.channels||'—'} 声道`;}
  }});
  const controls=()=>({provider:'edge',rate:Number($('#test-rate').value),volume:Number($('#test-volume').value),pitch_hz:Number($('#test-pitch').value),allow_fallback:false});
  const signed=n=>(n>=0?'+':'')+n;
  function labels(){$('#test-rate-value').textContent=signed(Math.round((controls().rate-1)*100))+'%';$('#test-volume-value').textContent=Math.round(controls().volume*100)+'%';$('#test-pitch-value').textContent=signed(controls().pitch_hz)+' Hz';}
  async function preview(voice){player.stop();const value=controls();$('#test-provider').textContent='edge（请求中）';$('#test-voice').textContent=voice+'（待响应确认）';$('#test-ms').textContent='—';$('#test-format').textContent='等待 WAV 响应';$('#test-params').textContent=`语速 ${signed(Math.round((value.rate-1)*100))}% · 音高 ${signed(value.pitch_hz)} Hz · 音量 ${signed(Math.round((value.volume-1)*100))}%`;try{await player.speak(phrase,{...value,voice});}catch(error){$('#test-status').textContent=error.message;}}
  for(const input of $('#test-controls').querySelectorAll('input'))input.oninput=labels;
  $('#test-stop').onclick=()=>player.stop();$('#test-reset').onclick=()=>{player.stop();$('#test-rate').value=1;$('#test-volume').value=1;$('#test-pitch').value=0;labels();};
  window.voiceTest={player,preview,controls,phrase};
  async function load(){
    const response=await fetch('/api/audio/voices?provider=edge');if(!response.ok)throw new Error('无法读取自然声音列表。');const voices=await response.json();
    for(const voice of voices){const card=document.createElement('article');card.className='voice-card';const title=document.createElement('h2');title.textContent=voice.label||voice.name;const name=document.createElement('code');name.textContent=voice.name;const button=document.createElement('button');button.type='button';button.dataset.voice=voice.name;button.disabled=voice.available===false;button.textContent=button.disabled?'暂不可用':'▷ 试听这句';button.onclick=()=>preview(voice.name);const info=document.createElement('p');info.textContent=voice.available===false?(voice.reason||'当前 Edge 声音目录暂不提供此声音。'):'Edge 在线自然语音 · 原速播放';card.append(title,name,info,button);$('#voice-cards').append(card);}
  }
  load().catch(error=>{$('#test-status').textContent=error.message;});
  window.addEventListener('pagehide',()=>player.stop());
})();
