/* Explicit acceptance: synthetic browser audio is not a physical microphone test. */
async page => {
  const checks=[],errors=[];let chatRequests=0;
  const check=(passed,label)=>checks.push({label,passed:!!passed});
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',request=>{if(request.url().endsWith('/api/chat/stream'))chatRequests++;});
  await page.addInitScript(()=>{const Original=window.Audio;window.Audio=class extends Original{constructor(...args){super(...args);window.__lastAudio=this;}};});
  await page.setViewportSize({width:1280,height:1100});await page.reload();
  await page.waitForFunction(()=>document.querySelector('#asr-ready').textContent.includes('Ready')&&!document.querySelector('#chat-form button').disabled,null,{timeout:20000});
  check(await page.locator('#pet').getAttribute('width')==='240','actual screen width 240');
  check((await page.locator('#tts-ready').textContent()).includes('TTS Ready'),'backend TTS ready');
  check((await page.locator('#asr-ready').textContent()).includes('ASR Ready'),'local CPU ASR ready');
  const original=await page.evaluate(()=>fetch('/api/pet/settings').then(r=>r.json()));
  try{
    await page.locator('#auto-speak').uncheck();
    await page.locator('#voice-play').click();
    await page.waitForFunction(()=>document.querySelector('#voice-status').textContent.includes('语音播放完成'),null,{timeout:25000});
    check(await page.evaluate(()=>!!window.__lastAudio&&window.__lastAudio.ended&&window.__lastAudio.currentTime>0),'real SAPI WAV decoded and playback completed');
    await page.locator('#voice-play').click();await page.waitForTimeout(300);await page.locator('#voice-cancel').click();
    check(!await page.evaluate(()=>window.pixelPetRuntime.speaking),'cancel stops speech preparation/playback');
    await page.evaluate(()=>{navigator.mediaDevices.getUserMedia=()=>Promise.reject(new DOMException('test denial','NotAllowedError'));});
    await page.locator('#voice-start').click();await page.waitForFunction(()=>document.querySelector('#voice-status').textContent.includes('被拒绝'));
    check(await page.locator('#voice-start').isEnabled(),'permission denial restores recording button');
    await page.evaluate(()=>{window.__released=false;navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>{window.__grant=()=>resolve({getTracks:()=>[{stop:()=>{window.__released=true;}}]});});});
    await page.locator('#voice-start').click();await page.locator('#voice-cancel').click();await page.evaluate(()=>window.__grant());await page.waitForTimeout(100);
    check(await page.evaluate(()=>window.__released&&!window.pixelPetRuntime.isCapturing()),'late permission result stopped after cancellation');
    // Real MediaRecorder captures a generated oscillator stream; ASR is delayed to test abort.
    await page.evaluate(()=>{navigator.mediaDevices.getUserMedia=async()=>{const ctx=new AudioContext();await ctx.resume();const dest=ctx.createMediaStreamDestination(),osc=ctx.createOscillator();osc.connect(dest);osc.start();window.__oscContext=ctx;return dest.stream;};});
    const waitASR=async route=>{await new Promise(resolve=>setTimeout(resolve,900));try{await route.fulfill({json:{text:'不得发送的取消识别文本',elapsed_ms:1}});}catch{}};
    await page.route('**/api/audio/transcribe',waitASR);
    const before=chatRequests;
    await page.locator('#voice-start').click();await page.waitForFunction(()=>document.querySelector('#voice-stop').disabled===false);await page.waitForTimeout(500);
    await page.locator('#voice-stop').click();await page.waitForFunction(()=>document.querySelector('#voice-status').textContent.includes('正在本机识别'));
    await page.locator('#voice-cancel').click();await page.waitForTimeout(1100);
    check(chatRequests===before,'canceled ASR never auto-sends transcript');
    check(!await page.evaluate(()=>window.pixelPetRuntime.isCapturing()),'canceled ASR releases capture state');
    await page.unroute('**/api/audio/transcribe',waitASR);await page.evaluate(()=>window.__oscContext.close());
    // True PC software loop: SAPI Chinese WAV -> browser WebM recorder -> local Whisper -> live model -> WAV.
    await page.evaluate(()=>{navigator.mediaDevices.getUserMedia=async()=>{const ctx=new AudioContext();await ctx.resume();const response=await fetch('/api/audio/synthesize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'你好小星，你叫什么名字？'})});const buffer=await ctx.decodeAudioData(await response.arrayBuffer());const destination=ctx.createMediaStreamDestination(),source=ctx.createBufferSource();source.buffer=buffer;source.connect(destination);window.__synthetic={ctx,source,duration:buffer.duration};setTimeout(()=>source.start(),150);return destination.stream;};});
    await page.locator('#new-chat').click();await page.waitForFunction(()=>!document.querySelector('#chat-form button').disabled);
    await page.locator('#auto-speak').check();
    await page.locator('#voice-start').click();await page.waitForFunction(()=>!document.querySelector('#voice-stop').disabled,null,{timeout:20000});
    const duration=await page.evaluate(()=>window.__synthetic.duration);await page.waitForTimeout((duration+.5)*1000);
    const transcribed=page.waitForResponse(response=>response.url().endsWith('/api/audio/transcribe'));
    await page.locator('#voice-stop').click();const asrResponse=await transcribed;const asr=await asrResponse.json();
    check(asrResponse.status()===200&&asr.text.length>0,'real WebM upload recognized by CPU Whisper');
    await page.waitForFunction(()=>!document.querySelector('#chat-form button').disabled&&document.querySelector('#chat-log').textContent.includes('DeepSeek'),null,{timeout:70000});
    await page.waitForFunction(()=>document.querySelector('#voice-status').textContent.includes('语音播放完成'),null,{timeout:30000});
    check((await page.locator('#chat-log').textContent()).includes('小星'),'recognized text receives real character reply');
    check(await page.evaluate(()=>window.__lastAudio.ended&&window.__lastAudio.currentTime>0),'AI reply synthesized and browser playback ended');
    await page.evaluate(()=>window.__synthetic.ctx.close());
    await page.locator('#settings-toggle').click();
    await page.locator('#settings-form [name="volume"]').evaluate(input=>{input.value='0.65';input.dispatchEvent(new Event('input'));});
    await page.locator('#settings-form button[type="submit"]').click();
    await page.waitForFunction(()=>document.querySelector('#settings-status').textContent.includes('已保存'));
    const stored=await page.evaluate(()=>fetch('/api/pet/settings').then(r=>r.json()));check(stored.volume===.65,'settings persisted through API');
    await page.locator('#close-settings').click();await page.locator('#diagnostics-toggle').click();
    await page.waitForFunction(()=>document.querySelector('#diagnostics-output').textContent.includes('HW_PENDING'));
    check((await page.locator('#diagnostics-output').textContent()).includes('pcm_s16le'),'diagnostics reports actual audio codec');
    await page.locator('#diagnostics-toggle').click();
    await page.locator('#auto-speak').uncheck();
    for(const state of ['ANNOYED','ERROR']){await page.locator(`[data-state="${state}"]`).click();check(await page.locator('#state-code').textContent()===state,`${state} preview`);}
    const result=await page.evaluate(async()=>{const c=document.querySelector('#pet');const r=await fetch('/api/assets/rgb565',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({width:240,height:240,rgba:Array.from(c.getContext('2d').getImageData(0,0,240,240).data)})});return {status:r.status,length:(await r.arrayBuffer()).byteLength};});
    check(result.status===200&&result.length===115200,'240x240 RGB565 frame exports 115200 bytes');
    await page.locator('[data-state="HAPPY"]').click();
    await page.screenshot({path:'D:/PixelPet/output/playwright/v1-desktop.png',fullPage:true});await page.setViewportSize({width:390,height:844});
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile V1 has no horizontal overflow');
    await page.screenshot({path:'D:/PixelPet/output/playwright/v1-mobile.png',fullPage:true});
    check(errors.length===0,'no browser runtime errors');
    return {total:checks.length,checks,failures:checks.filter(item=>!item.passed),errors,synthetic_audio:true,physical_microphone_tested:false,speaker_audibility_verified:false};
  }finally{
    await page.evaluate(settings=>fetch('/api/pet/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)}),original);
    await page.setViewportSize({width:1280,height:1100});
  }
}
