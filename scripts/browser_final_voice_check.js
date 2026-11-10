/* Run against an isolated server on port 8766. The mic source is software audio. */
async page => {
  const origin = 'http://127.0.0.1:8766';
  const errors = [];
  const checks = [];
  const check = (passed, label, detail) => {
    checks.push({label, passed: Boolean(passed)});
    if (!passed) throw new Error(detail ? `${label}: ${JSON.stringify(detail)}` : label);
  };
  page.on('pageerror', error => errors.push(error.message));
  const status = await (await page.request.get(origin + '/api/status')).json();
  check(status.mode === 'mock' || status.mode === 'deepseek', 'isolated server mode');
  const provider = status.mode === 'mock' ? 'mock' : 'edge';
  const patch = await page.request.patch(origin + '/api/pet/settings', {
    data: {tts_provider: provider, voice: provider === 'mock' ? 'mock-tone' : 'zh-CN-XiaoyiNeural',
      volume: 1, quiet_start: '00:00', quiet_end: '00:00'}
  });
  check(patch.ok(), 'isolated audio settings');
  const memory = await page.request.post(origin + '/api/memories', {
    data: {content: '我喜欢喝柚子茶', category: 'preference', importance: .95}
  });
  check(memory.ok(), 'store recall fixture');
  const sample = await page.request.post(origin + '/api/audio/synthesize', {
    data: {text: '你还记得我喜欢什么吗？', provider: 'sapi', allow_fallback: false}
  });
  check(sample.ok() && (await sample.body()).length > 4096, 'prepare actual Chinese waveform');
  const waveBytes = Array.from(await sample.body());
  await page.addInitScript(bytes => {
    navigator.mediaDevices.getUserMedia = async () => {
      const context = new AudioContext();
      await context.resume();
      const buffer = await context.decodeAudioData(Uint8Array.from(bytes).buffer);
      const destination = context.createMediaStreamDestination();
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(destination);
      window.testMic = {context, source, duration: buffer.duration, stream: destination.stream};
      source.start(context.currentTime + .15);
      return destination.stream;
    };
    window.testPlayback = {poses: new Set(), states: new Set()};
    const monitor = () => {
      if (window.pixelPetRuntime) {
        window.testPlayback.states.add(document.querySelector('#state-code').textContent);
        if (window.pixelPetRuntime.audioState === 'PLAYING_AUDIO') window.testPlayback.poses.add(window.pixelPet.mouth);
      }
      requestAnimationFrame(monitor);
    };
    requestAnimationFrame(monitor);
  }, waveBytes);
  await page.goto(origin + '/');
  await page.waitForFunction(() => window.pixelPetSettings?.tts_provider && !window.pixelPetChat.isBusy());
  await page.locator('#new-chat').click();
  await page.waitForFunction(() => !window.pixelPetChat.isBusy());
  await page.locator('#touch-record').click();
  await page.waitForFunction(() => document.querySelector('#state-code').textContent === 'LISTENING');
  await page.waitForTimeout(1000 * ((await page.evaluate(() => window.testMic.duration)) + .45));
  const recognized = page.waitForResponse('**/api/audio/transcribe', {timeout: 125000});
  const chatted = page.waitForResponse('**/api/chat/stream', {timeout: 125000});
  const synthesized = page.waitForResponse('**/api/audio/synthesize', {timeout: 125000});
  await page.locator('#touch-record').click();
  const asrResponse = await recognized;
  const asr = await asrResponse.json();
  check(asrResponse.ok() && /喜欢|喜歡/.test(asr.text), 'MediaRecorder → real CPU Whisper', asr);
  const chatResponse = await chatted;
  const transcript = await chatResponse.text();
  check(chatResponse.ok() && transcript.includes('柚子茶'), 'speech → fresh conversation → relevant memory', {asr:asr.text});
  const speechResponse = await synthesized;
  check(speechResponse.ok() && speechResponse.headers()['x-audio-provider'] === provider, 'reply → selected WAV provider');
  await page.waitForFunction(() => window.testPlayback.states.has('SPEAKING') &&
    window.pixelPetRuntime.audioState === 'IDLE' && !window.pixelPetChat.isBusy(), null, {timeout: 20000});
  const motion = await page.evaluate(() => ({states: Array.from(window.testPlayback.states), poses: Array.from(window.testPlayback.poses), mouth: window.pixelPet.mouth}));
  check(motion.states.includes('THINKING') && motion.states.includes('LISTENING'), 'listening, thinking and speaking transitions');
  check(motion.poses.some(pose => pose === 'small' || pose === 'large') && motion.mouth === 'closed', 'decoded PCM drives mouth and resets after playback');
  check(await page.evaluate(() => window.testMic.stream.getTracks().every(track => track.readyState === 'ended')), 'capture tracks close before playback');
  await page.evaluate(() => window.testMic.context.close());
  await page.locator('#diagnostics-toggle').click();
  await page.waitForFunction(() => document.querySelector('#diagnostics-output').textContent.includes('voice_to_playing_ms'));
  const browser = JSON.parse(await page.locator('#diagnostics-output').textContent()).browser;
  check(browser.asr_ms >= 0 && browser.voice_to_playing_ms >= browser.voice_to_first_text_ms &&
    browser.voice_to_first_text_ms > 0, 'diagnostics timing links microphone release to text and playback');

  const fail = route => route.abort('internetdisconnected');
  await page.route('**/api/audio/synthesize', fail);
  await page.locator('#voice-play').click();
  await page.waitForFunction(() => window.pixelPetRuntime.audioState === 'AUDIO_ERROR');
  check(await page.locator('#state-code').textContent() === 'IDLE', 'network failure resets avatar');
  await page.unroute('**/api/audio/synthesize', fail);
  const recovered = page.waitForResponse('**/api/audio/synthesize');
  await page.locator('#voice-play').click();
  check((await recovered).ok(), 'playback retry after restored connection');
  await page.waitForFunction(() => window.pixelPetRuntime.audioState === 'IDLE');
  const queue = await page.evaluate(async () => {
    const player = new window.PixelPetAudioPlayer();
    const text = '队列取消测试';
    const active = player.enqueue(text,{provider:'mock'});
    const duplicate = await player.enqueue(text,{provider:'mock'});
    const queued = Array.from({length:5},(_,i) => player.enqueue('排队'+i,{provider:'mock'}));
    const pending = player.queueLength;
    player.stop();
    return {pending, duplicate, results: await Promise.all([active,...queued]), state: player.state};
  });
  check(queue.pending === 4 && queue.duplicate === false && queue.results.every(value => value === false) && queue.state === 'IDLE',
    'bounded queue, duplicate suppression and cancellation');
  const fifo = await page.evaluate(async () => {
    const started = [];
    const player = new window.PixelPetAudioPlayer({onPlaying: (_, options) => started.push(options.emotion)});
    const first = player.enqueue('第一句',{provider:'mock',emotion:'happy'});
    const second = player.enqueue('第二句',{provider:'mock',emotion:'shy'});
    const results = await Promise.all([first,second]);
    return {started, results};
  });
  check(fifo.started.join(',') === 'happy,shy' && fifo.results.every(Boolean), 'queued audio completes in order');
  await page.locator('#touch-record').click();
  await page.waitForFunction(() => document.querySelector('#state-code').textContent === 'LISTENING');
  await page.locator('#voice-cancel').click();
  check(await page.evaluate(() => !window.pixelPetRuntime.isCapturing() &&
    window.testMic.stream.getTracks().every(track => track.readyState === 'ended')), 'cancel current voice dialogue and release microphone');
  await page.evaluate(() => window.testMic.context.close());
  await page.evaluate(() => {
    const originalTimeout = window.setTimeout;
    const originalCapture = navigator.mediaDevices.getUserMedia;
    window.setTimeout = (callback, delay, ...args) => originalTimeout(callback,delay===20000?80:delay,...args);
    navigator.mediaDevices.getUserMedia = () => new Promise(resolve => {
      window.releaseLateGrant = () => resolve({getTracks:() => [{stop(){window.lateGrantStopped=true;}}]});
    });
    window.restorePermissionTest = () => {
      window.setTimeout = originalTimeout;
      navigator.mediaDevices.getUserMedia = originalCapture;
    };
  });
  await page.locator('#touch-record').click();
  await page.waitForFunction(() => document.querySelector('#voice-status').textContent.includes('授权超时'));
  await page.evaluate(() => window.releaseLateGrant());
  await page.waitForFunction(() => window.lateGrantStopped);
  check(await page.evaluate(() => !window.pixelPetRuntime.isCapturing() &&
    document.querySelector('#touch-record').getAttribute('aria-pressed') === 'false'), 'ignored permission request recovers and late mic stream stops');
  await page.evaluate(() => window.restorePermissionTest());
  const previews = await page.locator('[data-state]').evaluateAll(nodes => nodes.map(node => node.dataset.state));
  for (const state of previews) {
    await page.locator(`[data-state="${state}"]`).click();
    await page.waitForFunction(expected => document.querySelector('#pet').dataset.petState === expected, state);
  }
  check(previews.length === 10, 'all ten animation states render on canvas');
  const frame = await page.evaluate(async () => {
    const canvas = document.querySelector('#pet');
    const rgba = Array.from(canvas.getContext('2d').getImageData(0,0,240,240).data);
    const response = await fetch('/api/assets/rgb565', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({width:240,height:240,rgba})});
    return {ok:response.ok, bytes:(await response.arrayBuffer()).byteLength};
  });
  check(frame.ok && frame.bytes === 115200, '240 × 240 RGB565 export');
  check(errors.length === 0, 'no JavaScript runtime errors');
  return {mode:status.mode, provider, checks, motion, browser, asr, physicalMicrophone:false, physicalSpeaker:false};
}
