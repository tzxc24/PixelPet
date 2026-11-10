const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

let timeout;
let nextTimer = 0;
let mode = 'noStart';
let audio;
let fetchMode = 'normal';
let synthSignal;
class FakeAudio {
  constructor() {
    this.duration = 1;
    this.currentTime = 0;
    audio = this;
  }
  play() {
    if (mode === 'noStart') return new Promise(() => {});
    this.onplaying();
    if (mode === 'normal') queueMicrotask(() => this.onended?.());
    return Promise.resolve();
  }
  pause() { this.paused = true; }
}
const context = {
  window: {
    setTimeout(callback, ms) {
      timeout = {id: ++nextTimer, callback, ms};
      return timeout.id;
    },
    clearTimeout(id) {
      if (timeout?.id === id) timeout = null;
    }
  },
  Audio: FakeAudio,
  AbortController,
  URL: {createObjectURL: () => 'blob:test', revokeObjectURL() {}},
  requestAnimationFrame: () => 1,
  cancelAnimationFrame() {},
  fetch: async (_, {signal}) => {
    synthSignal=signal;
    if (fetchMode === 'headers') return new Promise(() => {});
    const blob=fetchMode==='body'?()=>new Promise(()=>{}):async()=>new Blob(['wav']);
    return {ok:true,headers:new Headers(),blob};
  }
};
vm.runInNewContext(fs.readFileSync('frontend/js/audio-player.js', 'utf8'), context);

async function main() {
  const player = new context.window.PixelPetAudioPlayer();
  for (const phase of ['headers','body']) {
    fetchMode=phase;
    const pending=player.enqueue(phase);
    const failure=assert.rejects(pending,/语音合成请求超时/);
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(timeout?.ms,65000);
    timeout.callback();
    await failure;
    assert.equal(synthSignal.aborted,true);
    assert.equal(player.state,'AUDIO_ERROR');
    assert.equal(timeout,null);
  }
  fetchMode='normal';
  for (const [phase, limit] of [['noStart',15000],['noEnd',11000]]) {
    mode = phase;
    const pending = player.enqueue(phase);
    const failure = assert.rejects(pending, /语音播放超时/);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(timeout?.ms, limit);
    timeout.callback();
    await failure;
    assert.equal(player.state,'AUDIO_ERROR');
    assert.equal(audio.paused,true);
    assert.equal(timeout,null);
  }
  mode = 'normal';
  assert.equal(await player.speak('retry'),true);
  assert.equal(player.state,'IDLE');
  assert.equal(timeout,null);
  mode = 'noEnd';
  const pending = player.enqueue('cancel');
  await new Promise(resolve => setImmediate(resolve));
  player.stop();
  assert.equal(await pending,false);
  assert.equal(timeout,null);
  assert.equal(player.state,'IDLE');
  context.window.speechSynthesis={getVoices:()=>[{name:'replacement',lang:'zh-CN'}]};
  await assert.rejects(player.speak('voice',{provider:'browser',voice:'missing'}),/所选浏览器声音已不可用/);
  console.log('Audio watchdog detects stalled headers, body, media start and media end, then permits retry');
}
main().catch(error => {console.error(error);process.exitCode=1;});
