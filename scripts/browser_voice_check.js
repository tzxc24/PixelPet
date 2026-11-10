/* Run with playwright-cli run-code --filename scripts/browser_voice_check.js.
   Decodes real provider WAVs; does not claim physical speaker audibility. */
async page => {
  const checks=[],errors=[],requests=[],networkRetries=[];
  const check=(passed,label)=>checks.push({label,passed:!!passed});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(request.url().includes('/api/audio/synthesize'))requests.push(request.postDataJSON());});
  await page.addInitScript(()=>{const Original=window.Audio;window.Audio=class extends Original{constructor(...args){super(...args);window.__voiceAudio=this;window.__voiceEnded=false;window.__playedTime=0;this.addEventListener('timeupdate',()=>window.__playedTime=Math.max(window.__playedTime,this.currentTime));this.addEventListener('ended',()=>{window.__voiceEnded=true;window.__playedTime=Math.max(window.__playedTime,this.currentTime);});}};});
  const fresh=route=>route.continue();await page.route('**/static/**',fresh);
  await page.goto('http://127.0.0.1:8765/');
  await page.waitForFunction(()=>window.pixelPetRuntime&&window.pixelPetSettings?.tts_provider);
  const original=await page.evaluate(()=>fetch('/api/pet/settings').then(r=>r.json()));
  try{
    await page.locator('#settings-toggle').click();
    await page.locator('#settings-form [name="name"]').fill('未保存的名字');
    await page.locator('#voice-defaults').click();
    await page.waitForFunction(()=>document.querySelector('#settings-status').textContent.includes('自动保存'));
    check(await page.locator('#settings-form [name="name"]').inputValue()==='未保存的名字','speech autosave preserves unrelated unsaved controls');
    const settings=await page.evaluate(()=>fetch('/api/pet/settings').then(r=>r.json()));
    check(settings.tts_provider==='edge'&&settings.voice==='zh-CN-XiaoyiNeural'&&settings.rate===1&&settings.volume===1&&settings.pitch_hz===0,'voice defaults persist naturally');
    check(settings.name===original.name,'speech autosave excludes unrelated controls');
    const fail=async route=>{await new Promise(resolve=>setTimeout(resolve,300));await route.fulfill({status:503,json:{detail:{message:'测试：自然语音暂不可用'}}});};
    await page.route('**/api/audio/synthesize',fail);await page.locator('#voice-preview').click();
    await page.waitForFunction(()=>window.pixelPetRuntime.audioState==='GENERATING_AUDIO');
    check(await page.locator('#state-code').textContent()==='THINKING','audio generation shows thinking before actual playback');
    await page.waitForFunction(()=>window.pixelPetRuntime.audioState==='AUDIO_ERROR');
    check((await page.locator('#voice-status').textContent()).includes('暂不可用'),'synthesis failure is visible and does not pretend playback');
    check(await page.locator('#state-code').textContent()==='IDLE','synthesis failure restores idle pet without playback');
    await page.unroute('**/api/audio/synthesize',fail);
    async function realPlayback(selector,testPage=false){
      for(let attempt=0;attempt<2;attempt++){
        await page.locator(selector).click();
        await page.waitForFunction(isTest=>['PLAYING_AUDIO','AUDIO_ERROR'].includes(isTest?window.voiceTest.player.state:window.pixelPetRuntime.audioState),testPage,{timeout:45000});
        const state=await page.evaluate(isTest=>isTest?window.voiceTest.player.state:window.pixelPetRuntime.audioState,testPage);
        if(state==='PLAYING_AUDIO')return;
        const message=await page.locator(testPage?'#test-status':'#voice-status').textContent();
        networkRetries.push({selector,attempt:attempt+1,message});
        if(attempt===1)throw new Error('Real provider synthesis failed after one retry: '+message);
      }
    }
    await realPlayback('#voice-preview');
    check(await page.evaluate(()=>window.__voiceAudio.playbackRate===1&&window.__voiceAudio.preservesPitch),'WAV plays at original rate and preserves pitch');
    check(await page.locator('#state-code').textContent()==='SPEAKING','pet speaks only when WAV is playing');
    await page.evaluate(()=>window.__previousVoiceAudio=window.__voiceAudio);await page.locator('#voice-preview').click();
    check(await page.evaluate(()=>window.__previousVoiceAudio.paused),'repeated preview stops previous WAV immediately');
    await page.locator('#voice-cancel').click();
    check(await page.evaluate(()=>window.pixelPetRuntime.audioState==='IDLE'&&!window.pixelPetRuntime.speaking),'cancel releases playing state');
    check(requests.at(-1).allow_fallback===false&&requests.at(-1).text==='你好呀，我是小星！今天也很开心见到你，嘿嘿，要不要陪我聊聊天？','preview uses fixed phrase and no fallback');
    await page.locator('#voice-preview').click();await page.locator('#voice-cancel').click();await page.waitForTimeout(700);
    check(await page.evaluate(()=>window.pixelPetRuntime.audioState==='IDLE'),'cancel during synthesis cannot restart stale playback');
    check(await page.locator('#state-code').textContent()==='IDLE','cancel generating restores idle pet');
    await page.evaluate(()=>{navigator.mediaDevices.getUserMedia=()=>Promise.reject(new DOMException('test denial','NotAllowedError'));});
    await page.locator('#voice-start').click();await page.waitForFunction(()=>document.querySelector('#voice-status').textContent.includes('被拒绝'));
    check(await page.locator('#voice-start').isEnabled(),'microphone denial recovers recording controls');
    await page.evaluate(()=>{window.__released=false;navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>{window.__grant=()=>resolve({getTracks:()=>[{stop:()=>{window.__released=true;}}]});});});
    await page.locator('#voice-start').click();await page.locator('#voice-cancel').click();await page.evaluate(()=>window.__grant());
    await page.waitForFunction(()=>window.__released);
    check(await page.evaluate(()=>!window.pixelPetRuntime.isCapturing()),'late microphone grant releases after cancellation');
    await page.goto('http://127.0.0.1:8765/voice-test');
    await page.waitForFunction(()=>document.querySelectorAll('#voice-cards button').length===4);
    check(await page.locator('[data-voice="zh-CN-XiaomengNeural"]').isDisabled(),'unavailable Xiaomeng remains disabled');
    const real=[];
    for(const voice of ['zh-CN-XiaoyiNeural','zh-CN-XiaoxiaoNeural','zh-CN-YunxiNeural']){
      await realPlayback(`[data-voice="${voice}"]`,true);
      check(await page.locator('#test-provider').textContent()==='edge',`${voice} actually plays Edge`);
      check(await page.locator('#test-voice').textContent()===voice,`${voice} actual response voice`);
      real.push(await page.evaluate(()=>({...window.voiceTest.player.metadata})));
      await page.waitForFunction(()=>window.voiceTest.player.state==='IDLE',null,{timeout:30000});
      check(await page.evaluate(()=>window.__voiceEnded&&window.__playedTime>0),'real WAV decoded and advanced');
    }
    await page.setViewportSize({width:390,height:844});
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'voice comparison mobile has no overflow');
    await page.screenshot({path:'D:/PixelPet/output/playwright/voice-test-mobile.png',fullPage:true});
    await page.setViewportSize({width:1280,height:1100});await page.screenshot({path:'D:/PixelPet/output/playwright/voice-test-desktop.png',fullPage:true});
    check(errors.length===0,'no browser runtime errors');
    return {checks,failures:checks.filter(c=>!c.passed),errors,real,networkRetries,physical_speaker_audibility_verified:false};
  }catch(error){check(false,'full acceptance completed');return {checks,failures:checks.filter(c=>!c.passed),errors,networkRetries,fatal_error:error.message,physical_speaker_audibility_verified:false};}
  finally{await page.unroute('**/static/**',fresh);await page.evaluate(settings=>fetch('/api/pet/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)}),original);}
}
