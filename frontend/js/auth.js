/* Optional LAN access token, never the model API key. Local mode needs no token. */
(() => {
  const storage='pixelpet-access-token';let token='';
  try{token=sessionStorage.getItem(storage)||'';}catch{}
  function headers(extra={}){const result=new Headers(extra);if(token)result.set('Authorization','Bearer '+token);return result;}
  window.pixelPetAuth={headers};
  const original=window.fetch.bind(window);
  let panel=null;
  function show(){
    if(panel)return;
    panel=document.createElement('form');panel.className='error';panel.style.flexWrap='wrap';
    const label=document.createElement('label');label.textContent='本地服务启用了访问保护。请输入访问令牌（不是 DeepSeek 密钥）：';
    const input=document.createElement('input');input.type='password';input.autocomplete='off';input.setAttribute('aria-label','局域网访问令牌');
    const button=document.createElement('button');button.textContent='连接';button.type='submit';
    panel.append(label,input,button);document.querySelector('main').prepend(panel);
    panel.onsubmit=event=>{event.preventDefault();token=input.value.trim();try{sessionStorage.setItem(storage,token);}catch{}location.reload();};
  }
  window.fetch=async(input,options={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return original(input,options);
    const response=await original(input,{...options,headers:headers(options.headers|| (input instanceof Request?input.headers:{}))});
    if(response.status===401)show();return response;
  };
  document.addEventListener('click',async event=>{
    const anchor=event.target.closest('a[href="/api/memories/export"]');if(!anchor)return;
    event.preventDefault();
    const response=await fetch(anchor.href);if(!response.ok)return;
    const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download='pixelpet-memories.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
})();
