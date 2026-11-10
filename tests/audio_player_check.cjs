const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const events=[];let request,delayed=false,deliver,created=0,playing=false,mode="normal",resolvePlay;
class FakeAudio{constructor(src){created++;this.src=src;this.currentTime=0;this.duration=1;}pause(){playing=false;} async play(){if(mode==='failure'){this.onerror?.();throw new Error('play rejected');}playing=true;this.onplaying?.();if(mode==='deferred')return new Promise(resolve=>{resolvePlay=resolve;});this.currentTime=1;queueMicrotask(()=>this.onended?.());}}
const response=()=>({ok:true,headers:new Headers({'X-Audio-Provider':'sapi','X-Audio-Voice':'legacy','X-Audio-Fallback':'sapi','X-Audio-Requested-Provider':'edge'}),blob:async()=>new Blob(['wav'])});
const context={window:{},Audio:FakeAudio,AbortController,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},requestAnimationFrame:()=>1,cancelAnimationFrame(){},performance,fetch:async(url,options)=>{request=JSON.parse(options.body);if(delayed)return new Promise(resolve=>{deliver=()=>resolve(response());});return response();},Headers,Blob};
vm.runInNewContext(fs.readFileSync('frontend/js/audio-player.js','utf8'),context);
(async()=>{
 const player=new context.window.PixelPetAudioPlayer({onState:s=>events.push(s)});
 await player.speak('你好',{provider:'edge',voice:'zh-CN-XiaoyiNeural',rate:1.1,volume:1,pitch_hz:0,allow_fallback:false});
 assert.equal(request.rate_percent,10);assert.equal(request.volume_percent,0);assert.equal(request.output_format,'pc');assert.equal(request.allow_fallback,false);assert.equal(player.metadata.provider,'sapi');assert.equal(player.metadata.fallback,'sapi');assert.equal(player.metadata.requested_provider,'edge');assert.deepEqual(events,['GENERATING_AUDIO','PLAYING_AUDIO','IDLE']);assert.equal(player.state,'IDLE');
 delayed=true;const count=created;const old=player.speak('stale');assert.equal(player.state,'GENERATING_AUDIO');player.stop();assert.equal(player.state,'IDLE');deliver();await old;assert.equal(created,count,'late synthesis may not create player');assert.equal(playing,false);assert.deepEqual(events.slice(-3),['GENERATING_AUDIO','STOPPING_AUDIO','IDLE']);
 const pending=player.speak('old');const oldDeliver=deliver;delayed=false;await player.speak('new');oldDeliver();await pending;assert.equal(created,count+1,'only newest request creates audio');assert.equal(player.state,'IDLE');
 mode='failure';const unhandled=[];const handler=error=>unhandled.push(error);process.on('unhandledRejection',handler);await assert.rejects(player.speak('fails'));await new Promise(resolve=>setImmediate(resolve));assert.equal(player.state,'AUDIO_ERROR');assert.equal(unhandled.length,0,'audio error plus play rejection must be handled');process.off('unhandledRejection',handler);mode='normal';await player.speak('retry');assert.equal(player.state,'IDLE');
 mode='deferred';const late=player.speak('late play');await new Promise(resolve=>setImmediate(resolve));player.stop();resolvePlay();await late;assert.equal(player.state,'IDLE');assert.equal(playing,false);
 console.log('audio-player contract, real-provider metadata, lifecycle and stale cancellation passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
