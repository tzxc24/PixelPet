async page => {
 const fresh=route=>route.continue();await page.route('**/static/**',fresh);await page.goto('http://127.0.0.1:8765/');await page.waitForFunction(()=>window.pixelPetRuntime&&window.pixelPetSettings?.tts_provider);
 let release;const deferred=async route=>{await new Promise(resolve=>release=resolve);try{await route.fulfill({status:503,json:{detail:{message:'state lifecycle probe'}}});}catch{}};
 await page.route('**/api/audio/synthesize',deferred);const checks=[];
 try{
  await page.evaluate(()=>{window.petUI.renderAnimation('HAPPY');window.__statePending=window.pixelPetRuntime.speak('测试',true,{tts_provider:'edge',voice:'',rate:1,volume:1,pitch_hz:0});});
  await page.waitForFunction(()=>window.pixelPetRuntime.audioState==='GENERATING_AUDIO');
  checks.push({label:'generating audio shows thinking',passed:await page.locator('#state-code').textContent()==='THINKING'});
  while(!release)await page.waitForTimeout(10);release();await page.evaluate(()=>window.__statePending);
  checks.push({label:'audio error restores idle pet before any playback',passed:await page.locator('#state-code').textContent()==='IDLE'&&await page.evaluate(()=>window.pixelPetRuntime.audioState==='AUDIO_ERROR')});
  release=null;await page.evaluate(()=>{window.petUI.renderAnimation('THINKING');window.__statePending=window.pixelPetRuntime.speak('取消测试',true,{tts_provider:'edge',voice:'',rate:1,volume:1,pitch_hz:0});});
  await page.waitForFunction(()=>window.pixelPetRuntime.audioState==='GENERATING_AUDIO');while(!release)await page.waitForTimeout(10);await page.evaluate(()=>window.pixelPetRuntime.stopSpeech());release();await page.evaluate(()=>window.__statePending);
  checks.push({label:'cancel generating audio restores idle pet',passed:await page.locator('#state-code').textContent()==='IDLE'&&await page.evaluate(()=>window.pixelPetRuntime.audioState==='IDLE')});
 }finally{await page.unroute('**/api/audio/synthesize',deferred);await page.unroute('**/static/**',fresh);}
 const failures=checks.filter(check=>!check.passed);return {checks,failures};
}
