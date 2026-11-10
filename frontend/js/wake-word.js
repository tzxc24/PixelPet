/* Opt-in browser microphone loop. Standby clips go only to local Whisper. */
function isWakeWord(text) {
  const phrase = String(text).normalize('NFKC').replace(/[\p{P}\p{Z}\s]/gu, '');
  return /^(?:你好|嘿|喂)?(?:小星|小星小星)$/.test(phrase);
}

function shouldFinish(elapsed, lastSpeech) {
  if (elapsed >= 15000) return true;
  return lastSpeech === null ? elapsed >= 6000 : elapsed - lastSpeech >= 1200;
}

if (typeof module !== 'undefined') module.exports = {isWakeWord, shouldFinish};

if (typeof window !== 'undefined') {
  window.pixelPetWake = {shouldFinish, suspend: () => {}};
  window.addEventListener('DOMContentLoaded', () => {
    const button = document.querySelector('#wake-toggle');
    const status = document.querySelector('#wake-status');
    let enabled = false;
    let generation = 0;
    let active = null;
    let abort = null;
    let timer = null;
    let context = null;
    const release = () => {
      clearTimeout(timer);
      timer = null;
      abort?.abort();
      abort = null;
      active?.getTracks().forEach(track => track.stop());
      active = null;
      context?.close().catch(() => {});
      context = null;
    };
    function available() {
      const runtime = window.pixelPetRuntime;
      return runtime && window.pixelPetSettings && !runtime.isCapturing() && !runtime.speaking &&
        !window.pixelPetChat?.isBusy() && window.pixelPetSettings?.asr_provider !== 'disabled';
    }
    function schedule() {
      if (enabled) timer = setTimeout(poll, 400);
    }
    window.pixelPetWake.suspend = () => {
      generation++;
      release();
      schedule();
    };
    function disable(message) {
      enabled = false;
      generation++;
      release();
      button.setAttribute('aria-pressed', 'false');
      button.textContent = '开启「小星」唤醒';
      status.textContent = message;
    }
    async function poll() {
      if (!enabled) return;
      if (!available()) { schedule(); return; }
      const current = ++generation;
      try {
        const audio = {echoCancellation: true, noiseSuppression: true, channelCount: 1};
        const device = window.pixelPetSettings?.microphone_id;
        if (device) audio.deviceId = {exact: device};
        timer = setTimeout(() => {
          if (current === generation) disable("麦克风授权超时，请重新开启唤醒。");
        }, 20000);
        const stream = await navigator.mediaDevices.getUserMedia({audio});
        if (current !== generation || !available()) {
          stream.getTracks().forEach(track => track.stop());
          return;
        }
        clearTimeout(timer);
        timer = null;
        active = stream;
        const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4']
          .find(type => MediaRecorder.isTypeSupported(type));
        const recorder = new MediaRecorder(stream, mime ? {mimeType: mime} : {});
        context = new AudioContext();
        context.resume().catch(() => {});
        const analyser = context.createAnalyser();
        analyser.fftSize = 256;
        context.createMediaStreamSource(stream).connect(analyser);
        const samples = new Float32Array(analyser.fftSize);
        const chunks = [];
        let heard = false;
        const clip = await new Promise((resolve, reject) => {
          const meter = setInterval(() => {
            if (current !== generation || !available()) {
              if (recorder.state !== 'inactive') recorder.stop();
              return;
            }
            analyser.getFloatTimeDomainData(samples);
            const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
            heard ||= rms >= .012;
          }, 50);
          const end = setTimeout(() => { if (recorder.state !== 'inactive') recorder.stop(); }, 2300);
          const cleanup = () => { clearInterval(meter); clearTimeout(end); };
          recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
          recorder.onstop = () => { cleanup(); resolve(new Blob(chunks, {type: recorder.mimeType})); };
          recorder.onerror = () => { cleanup(); reject(new Error('唤醒录音失败')); };
          try { recorder.start(); } catch (error) { cleanup(); reject(error); }
        });
        if (current !== generation || !available() || !heard || !clip.size) return;
        release();
        const body = new FormData();
        body.append('audio', clip, 'wake-clip');
        body.append('purpose', 'wake');
        abort = new AbortController();
        const response = await fetch('/api/audio/transcribe', {
          method: 'POST', body, signal: AbortSignal.any([abort.signal, AbortSignal.timeout(12000)])
        });
        if (!response.ok) throw new Error('本地唤醒识别失败');
        const {text} = await response.json();
        if (current === generation && available() && isWakeWord(text)) {
          status.textContent = '听到了。等小星进入聆听状态后再说，停顿后自动发送。';
          await window.pixelPetRuntime.startRecording({handsFree: true});
        }
      } catch (error) {
        if (current === generation && error.name === 'NotAllowedError') disable('麦克风权限被拒绝。');
        else if (current === generation && error.name !== 'AbortError') status.textContent = '唤醒检测暂不可用，正在重试。';
      } finally {
        if (current === generation) { release(); schedule(); }
      }
    }
    button.onclick = () => {
      if (enabled) { disable('语音唤醒已关闭。'); return; }
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder || !window.AudioContext) {
        disable('当前浏览器不支持唤醒录音。');
        return;
      }
      enabled = true;
      button.setAttribute('aria-pressed', 'true');
      button.textContent = '关闭语音唤醒';
      status.textContent = '唤醒已开启。先单独说「小星」，等进入聆听后再说。';
      poll();
    };
    window.addEventListener('pagehide', () => disable('语音唤醒已关闭。'));
  });
}
