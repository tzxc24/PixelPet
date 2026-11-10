async page => {
 const fresh=route=>route.continue();await page.route('**/static/**',fresh);
 await page.goto('http://127.0.0.1:8765/');await page.waitForFunction(()=>window.pixelPetRuntime&&window.pixelPetSettings?.tts_provider);
 const requests=[];const intercept=async route=>{requests.push(route.request().postDataJSON());await route.fulfill({status:503,json:{detail:{message:'contract probe'}}});};
 await page.route('**/api/audio/synthesize',intercept);
 try{for(const provider of ['sapi','mock','edge'])await page.evaluate(provider=>window.pixelPetRuntime.speak('默认声音回归测试',true,{tts_provider:provider,voice:'',rate:1,volume:1,pitch_hz:0}),provider);}
 finally{await page.unroute('**/api/audio/synthesize',intercept);await page.unroute('**/static/**',fresh);}
 const checks=requests.map(request=>({provider:request.provider,voice:request.voice,passed:request.voice===(request.provider==='edge'?'zh-CN-XiaoyiNeural':null)}));
 if(checks.length!==3||checks.some(check=>!check.passed))throw new Error('Provider default voice regression: '+JSON.stringify(checks));
 return {passed:checks.length,checks};
}
