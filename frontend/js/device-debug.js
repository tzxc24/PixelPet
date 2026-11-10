(() => {
  const status = document.querySelector('#status');
  const output = document.querySelector('#devices');
  const payloads = {
    'haptic.pattern': {name: 'short'},
    'pet.emotion': {state: 'HAPPY', emotion: 'happy'}
  };
  async function refresh() {
    const response = await fetch('/api/diagnostics', {signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('诊断请求失败');
    const data = await response.json();
    output.textContent = JSON.stringify({
      控制连接: data.devices, 语音连接: data.voice_devices, 桌宠状态: data.pet
    }, null, 2);
  }
  for (const button of document.querySelectorAll('[data-event]')) {
    button.onclick = async () => {
      button.disabled = true;
      try {
        const type = button.dataset.event;
        const response = await fetch('/api/events', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({type, device_id: 'pixelpet-sim-debug', payload: payloads[type] || {}}),
          signal: AbortSignal.timeout(5000)
        });
        if (!response.ok) throw new Error('模拟事件发送失败');
        await refresh();
        status.textContent = '模拟事件已发送';
      } catch (error) {
        status.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    };
  }
  async function poll() {
    try { await refresh(); }
    catch (error) { status.textContent = error.message; }
    setTimeout(poll, 2000);
  }
  poll();
})();
