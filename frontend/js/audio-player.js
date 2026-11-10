/* Shared speech lifecycle with a bounded queue and PCM-based mouth movement. */
(() => {
  const clip=(value,min,max)=>Math.min(max,Math.max(min,Number(value)));
  class PixelPetAudioPlayer {
    constructor({onState=()=>{},onPlaying=()=>{},onProgress=()=>{}}={}){
      this.state='IDLE';
      this.metadata={};
      this.generation=0;
      this.pending=[];
      this.job=null;
      this.onState=onState;
      this.onPlaying=onPlaying;
      this.onProgress=onProgress;
    }
    get queueLength(){return this.pending.length;}
    setState(state){this.state=state;this.onState(state,this.metadata);}
    release(){
      cancelAnimationFrame(this.frame);
      this.frame=null;
      this.clearDeadline();
      if(this.audio){
        this.audio.onended=this.audio.onerror=this.audio.onplaying=null;
        this.audio.pause();
        this.audio.removeAttribute?.('src');
        this.audio=null;
      }
      if(this.url){
        URL.revokeObjectURL(this.url);
        this.url=null;
      }
      this.onProgress(0,false);
    }
    clearDeadline(){
      window.clearTimeout?.(this.playbackTimer);
      this.playbackTimer=null;
    }
    setDeadline(milliseconds,onTimeout){
      this.clearDeadline();
      this.playbackTimer=window.setTimeout?.(onTimeout,milliseconds);
    }
    async synthesize(text,provider,options,signal){
      const parameters={
        text:text.slice(0,2000),provider,voice:options.voice||null,
        rate_percent:Math.round((clip(options.rate??1,.8,1.2)-1)*100),
        pitch_hz:clip(options.pitch_hz??0,-12,12),
        volume_percent:Math.round((clip(options.volume??1,0,1)-1)*100),
        emotion:options.emotion||'normal',output_format:'pc',allow_fallback:options.allow_fallback??false
      };
      const headers={'Content-Type':'application/json'};
      const response=await fetch('/api/audio/synthesize',{
        method:'POST',headers:window.pixelPetAuth?.headers(headers)||headers,signal,body:JSON.stringify(parameters)
      });
      if(!response.ok){
        let body={};
        try{body=await response.json();}catch{}
        throw new Error(body.detail?.message||(typeof body.detail==='string'?body.detail:'语音合成失败，请检查网络或声音设置。'));
      }
      return {response,blob:await response.blob()};
    }
    stop(){
      const active=this.state==='GENERATING_AUDIO'||this.state==='PLAYING_AUDIO';
      this.job?.resolve(false);
      this.job=null;
      for(const queued of this.pending.splice(0))queued.resolve(false);
      ++this.generation;
      if(active)this.setState('STOPPING_AUDIO');
      this.abort?.abort();
      this.abort=null;
      if(this.browserSpeaking)window.speechSynthesis?.cancel();
      this.browserSpeaking=false;
      this.resolveEnd?.();
      this.resolveEnd=null;
      this.release();
      if(this.state!=='IDLE')this.setState('IDLE');
    }
    speak(text,options={}){
      this.stop();
      return this.enqueue(text,options);
    }
    enqueue(text,options={}){
      const key=JSON.stringify([text,options.provider,options.voice,options.rate,options.volume,options.pitch_hz,options.emotion]);
      if(this.job?.key===key||this.pending.some(job=>job.key===key)||this.pending.length>=4)return Promise.resolve(false);
      return new Promise((resolve,reject)=>{
        this.pending.push({key,text,options,resolve,reject});
        this.drain();
      });
    }
    async drain(){
      if(this.job||!this.pending.length)return;
      const job=this.job=this.pending.shift();
      try{await this.play(job.text,job.options);job.resolve(true);}
      catch(error){job.reject(error);}
      finally{
        if(this.job===job){
          this.job=null;
          this.drain();
        }
      }
    }
    async play(text,options){
      const generation=++this.generation;this.metadata={};this.setState('GENERATING_AUDIO');const controller=new AbortController();this.abort=controller;
      const current=()=>generation===this.generation;
      const started=()=>{if(!current())return;this.setState('PLAYING_AUDIO');this.onPlaying(this.metadata,options);};
      try{
        const provider=options.provider||'edge';
        if(provider==='browser'){
          if(!window.speechSynthesis)throw new Error('浏览器语音合成不可用。');
          const voices=window.speechSynthesis.getVoices();
          const voice=options.voice?voices.find(v=>v.name===options.voice):voices.find(v=>v.lang.startsWith('zh'));
          if(!voice)throw new Error(options.voice?'所选浏览器声音已不可用，请重新选择。':'没有可用的浏览器中文声音。');
          this.metadata={provider:'browser',voice:voice.name,fallback:'false'};
          const utterance=new SpeechSynthesisUtterance(text);utterance.voice=voice;utterance.lang='zh-CN';utterance.rate=clip(options.rate??1,.8,1.2);utterance.volume=clip(options.volume??1,0,1);utterance.pitch=1;
          this.browserSpeaking=true;
          await new Promise((resolve,reject)=>{
            this.resolveEnd=resolve;
            utterance.onstart=started;
            utterance.onend=resolve;
            utterance.onerror=()=>reject(new Error('浏览器语音播放失败。'));
            this.setDeadline(120000,()=>reject(new Error('语音播放超时，请重试。')));
            window.speechSynthesis.speak(utterance);
          });
        }else{
          const deadline=new Promise((_,reject)=>{
            this.setDeadline(65000,()=>{
              reject(new Error('语音合成请求超时，请重试。'));
              controller.abort();
            });
          });
          const {response,blob}=await Promise.race([this.synthesize(text,provider,options,controller.signal),deadline]);
          if(!current())return;
          this.clearDeadline();
          for(const [key,header] of Object.entries({provider:'Provider',voice:'Voice',rate_percent:'Rate-Percent',pitch_hz:'Pitch-Hz',volume_percent:'Volume-Percent',synthesis_ms:'Synthesis-Ms',fallback:'Fallback',requested_provider:'Requested-Provider',fallback_reason:'Fallback-Reason',codec:'Codec',sample_rate:'Sample-Rate',channels:'Channels',cache:'Cache'}))this.metadata[key]=response.headers.get('X-Audio-'+header);
          const lipSync=window.PixelPetLipSync?window.PixelPetLipSync.fromWav(await blob.arrayBuffer()):null;
          if(!current())return;
          this.url=URL.createObjectURL(blob);const audio=this.audio=new Audio(this.url);audio.volume=1;audio.playbackRate=1;audio.preservesPitch=true;
          const progress=()=>{
            if(!current()||this.state!=='PLAYING_AUDIO')return;
            const pose=audio.paused||!lipSync?{mouth:'closed',rms:0}:lipSync.sample(audio.currentTime);
            this.onProgress(audio.currentTime,true,pose);
            this.frame=requestAnimationFrame(progress);
          };
          const ended=new Promise((resolve,reject)=>{
            this.resolveEnd=resolve;
            const timedOut=()=>reject(new Error('语音播放超时，请重试。'));
            this.setDeadline(15000,timedOut);
            audio.onended=resolve;
            audio.onerror=()=>reject(new Error('WAV 播放失败，请检查系统声音设备。'));
            audio.onplaying=()=>{
              if(!current())return;
              if(this.state!=='PLAYING_AUDIO'){
                const limit=Number.isFinite(audio.duration)?Math.min(audio.duration,300)*1000+10000:120000;
                this.setDeadline(limit,timedOut);
                started();
              }
              cancelAnimationFrame(this.frame);
              progress();
            };
          });
          await Promise.all([Promise.resolve().then(()=>audio.play()),ended]);
        }
        if(current()){this.release();this.setState('IDLE');}
      }catch(error){
        if(current()){
          if(this.browserSpeaking)window.speechSynthesis?.cancel();
          this.release();
          this.setState('AUDIO_ERROR');
          if(error instanceof TypeError)throw new Error('语音连接或音频读取失败，请检查连接后重试。',{cause:error});
          throw error;
        }
      }
      finally{if(current()){this.resolveEnd=null;this.abort=null;this.browserSpeaking=false;}}
    }
  }
  window.PixelPetAudioPlayer=PixelPetAudioPlayer;
})();
