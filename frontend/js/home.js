(() => {
  const $ = id => document.getElementById(id);
  async function api(path, body, method) {
    const response = await fetch(path, {
      method: method || (body ? 'POST' : 'GET'),
      headers: window.pixelPetAuth.headers({'Content-Type':'application/json'}),
      ...(body ? {body:JSON.stringify(body)} : {})
    });
    if (!response.ok) throw new Error('操作失败，请检查登录和设备状态。');
    return response.json();
  }
  async function run(action) {
    try { await action(); } catch (error) { $('home-status').textContent = error.message; }
  }
  function device() {
    if (!$('home-device').value) throw new Error('请连接已升级的桌宠，再刷新设备。');
    return {device_id:$('home-device').value};
  }
  async function refresh() {
    const [data, live] = await Promise.all([api('/api/home'),api('/api/devices/voice/status')]);
    const selected = $('home-device').value;
    $('home-device').replaceChildren(...live.devices.filter(d => d.home_control).map(d => new Option(d.id,d.id)));
    if ([...$('home-device').options].some(o => o.value === selected)) $('home-device').value = selected;
    $('home-track').replaceChildren(...data.tracks.map(t => new Option(t.name,t.id)));
    $('home-status').textContent = $('home-device').value ? '设备已连接。灯光指令在设备下次轮询时执行。' : '等待升级后的桌宠连接。';
    $('home-alarms').replaceChildren();
    for (const item of data.alarms) {
      const row = document.createElement('p');
      row.textContent = new Date(item.due_at).toLocaleString()+' · '+item.device_id+' · '+(data.tracks.find(t => t.id===item.track)?.name||item.track)+' · '+({pending:'等待',playing:'已派发',delivered:'已播放',expired:'已过期',cancelled:'已取消',interrupted:'播放中断'}[item.status]||item.status)+' ';
      const remove = document.createElement('button');
      remove.textContent = '删除';
      remove.onclick = () => run(async () => {await api('/api/home/alarms/'+item.id,null,'DELETE');await refresh();});
      row.append(remove); $('home-alarms').append(row);
    }
  }
  document.querySelectorAll('[data-lamp]').forEach(button => button.onclick = () => run(async () => {
    const kind = button.dataset.lamp;
    await api('/api/home/lamp', {...device(),mode:kind==='breath'?'breath':['fade','dim'].includes(kind)?'fade':'steady',level:['off','dim'].includes(kind)?0:Number($('home-level').value),seconds:Number($('home-seconds').value)});
    $('home-status').textContent = '灯光指令已保存，等待设备接收。';
  }));
  $('home-level').oninput = () => {$('home-level-value').value=$('home-level').value+'%';};
  $('home-level').onchange = () => run(async () => {await api('/api/home/lamp',{...device(),level:Number($('home-level').value)});$('home-status').textContent='亮度指令已保存。';});
  $('home-play').onclick = () => run(async () => {await api('/api/home/play',{...device(),track:$('home-track').value});$('home-status').textContent='音乐已排队，设备空闲时播放。';});
  $('home-stop').onclick = () => run(async () => {await api('/api/home/stop',device());$('home-status').textContent='停止指令已发送。';});
  $('home-create').onclick = () => run(async () => {
    const time=new Date($('home-time').value);
    if (!Number.isFinite(time.getTime()) || time <= new Date()) throw new Error('请选择将来的播放时间。');
    await api('/api/home/alarms',{...device(),due_at:time.toISOString(),track:$('home-track').value,wake_light:$('home-wake').checked});
    await refresh();
  });
  $('home-refresh').onclick = () => run(refresh);
  run(refresh);
})();
