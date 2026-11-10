async page => {
  const requests = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/audio/transcribe', route => {
    requests.push('asr');
    return route.fulfill({json: {text: ['提到了小星', '小星', '你叫什么名字'][requests.filter(x => x === 'asr').length - 1] || ''}});
  });
  page.on('request', request => {
    if (request.url().endsWith('/api/chat/stream')) requests.push(request.postDataJSON().message);
  });
  await page.addInitScript(() => {
    window.testMicTracks = [];
    navigator.mediaDevices.getUserMedia = async () => {
      const context = new AudioContext();
      await context.resume();
      const destination = context.createMediaStreamDestination();
      const source = context.createOscillator();
      const gain = context.createGain();
      gain.gain.value = .2;
      source.connect(gain).connect(destination);
      source.start(context.currentTime + .15);
      source.stop(context.currentTime + .9);
      const track = destination.stream.getAudioTracks()[0];
      window.testMicTracks.push(track);
      const stop = track.stop.bind(track);
      track.stop = () => { stop(); context.close().catch(() => {}); };
      return destination.stream;
    };
  });
  await page.goto('http://127.0.0.1:8766/');
  await page.waitForFunction(() => window.pixelPetSettings && !window.pixelPetChat.isBusy());
  await page.locator('#auto-speak').uncheck();
  await page.locator('#wake-toggle').click();
  await page.waitForFunction(() => document.querySelector('#state-code').textContent === 'LISTENING');
  await page.waitForResponse('**/api/chat/stream');
  await page.locator('#wake-toggle').click();
  await page.waitForFunction(() => window.testMicTracks.every(track => track.readyState === 'ended'));
  if (JSON.stringify(requests) !== JSON.stringify(['asr', 'asr', 'asr', '你叫什么名字']) || errors.length)
    throw new Error(JSON.stringify({requests, errors}));
  return {requests, errors, tracksReleased: true};
}
