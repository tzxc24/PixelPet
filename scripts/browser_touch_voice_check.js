async page => {
  const audio = [];
  const messages = [];
  await page.route('**/static/**', route => route.continue());
  await page.route('**/api/pet/settings', async route => {
    const response = await route.fetch();
    const settings = await response.json();
    await route.fulfill({response, json: {...settings, quiet_start: '', quiet_end: '', tts_provider: 'edge', voice: 'zh-CN-XiaoxiaoNeural', volume: 1, rate: 1}});
  });
  await page.route('**/api/chat/stream', async route => {
    messages.push(route.request().postDataJSON().message);
    const reply = {reply: '嘿嘿，被你发现啦！', emotion: 'shy', state: 'SHY'};
    await route.fulfill({contentType: 'text/event-stream', body: `event: done\ndata: ${JSON.stringify(reply)}\n\n`});
  });
  await page.route('**/api/audio/synthesize', async route => {
    audio.push(route.request().postDataJSON());
    await route.fulfill({status: 503, json: {detail: {message: 'Edge 测试故障'}}});
  });
  await page.goto('http://127.0.0.1:8765/');
  await page.waitForFunction(() => window.pixelPetSettings?.voice === 'zh-CN-XiaoxiaoNeural' && !window.pixelPetChat.isBusy());
  for (const selector of ['[data-touch="tap"]', '[data-touch="double_tap"]', '#touch-pad', '#voice-play']) {
    const next = page.waitForResponse('**/api/audio/synthesize', {timeout: 5000});
    await page.locator(selector).click();
    await next;
    await page.waitForFunction(() => !window.pixelPetChat.isBusy() && window.pixelPetRuntime.audioState === 'AUDIO_ERROR');
    const request = audio.at(-1);
    if (request.voice !== 'zh-CN-XiaoxiaoNeural' || request.emotion !== 'shy' || request.allow_fallback !== false) {
      throw new Error(`Incorrect touch voice request for ${selector}: ${JSON.stringify(request)}`);
    }
  }
  if (messages.length !== 3 || !messages[1].includes('两下')) throw new Error('Touch gesture routing failed');
  return {passed: 4, audio, messages};
}
