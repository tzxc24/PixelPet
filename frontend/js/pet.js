/* Original procedural pixel character. Rendering stays independent of API availability. */
(() => {
  const canvas = document.querySelector('#pet');
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled=false;
  ctx.scale(3,3); // Logical pixels rendered onto an actual 240x240 panel.
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let baseState='IDLE',lastFrame=-Infinity,mouthPose='closed',sleepScheduled=false;
  let currentBehavior={kind:'none',lowActivity:false};
  const behavior=new window.PixelPetBehavior();
  const ink = '#805b2f', gold = '#f4cc69', light = '#ffe8a0';
  // Stair-step outline on an 80 x 80 logical screen, enlarged with nearest-neighbour scaling.
  const outline = [[38,19],[42,19],[42,23],[44,23],[44,27],[46,27],[46,31],[50,31],[50,33],[60,33],[60,37],[58,37],[58,39],[56,39],[56,41],[54,41],[54,43],[52,43],[52,49],[54,49],[54,57],[50,57],[50,55],[46,55],[46,53],[42,53],[42,51],[38,51],[38,53],[34,53],[34,55],[30,55],[30,57],[26,57],[26,49],[28,49],[28,43],[26,43],[26,41],[24,41],[24,39],[22,39],[22,37],[20,37],[20,33],[30,33],[30,31],[34,31],[34,27],[36,27],[36,23],[38,23]];
  function rect(x,y,w,h,color) { ctx.fillStyle=color;ctx.fillRect(Math.round(x),Math.round(y),w,h); }
  function cross(x,y,color) {rect(x,y,1,5,color);rect(x-2,y+2,5,1,color);}
  function draw(timestamp) {
    const fps=Math.max(1,Math.min(currentBehavior.lowActivity&&baseState==='IDLE'?5:30,window.pixelPetSettings?.animation_fps||12));
    if(timestamp-lastFrame<1000/fps){window.requestAnimationFrame(draw);return;}
    lastFrame=timestamp;
    currentBehavior=behavior.update(timestamp,{idle:baseState==='IDLE',sleep:sleepScheduled,reduced:reduced.matches});
    const {kind,lowActivity}=currentBehavior;
    const state=kind==='sleep'?'SLEEP':baseState;
    if(canvas.dataset.behavior!==kind)canvas.dataset.behavior=kind;
    if(canvas.dataset.petState!==state)canvas.dataset.petState=state;
    const t = reduced.matches ? 0 : timestamp / 1000;
    ctx.clearRect(0,0,80,80);
    // Ground shadow remains separate from the bouncing character.
    rect(28,65,24,2,'#dde0c9');rect(32,64,16,4,'#dde0c9');
    let dy = Math.sin(t*2)*(lowActivity?.25:.7), dx = 0;
    if(kind==='sway')dx=Math.sin(t*5)*1.2;
    if(state==='HAPPY') dy=-Math.abs(Math.sin(t*5))*6;
    if(state==='SHY') dx=Math.sin(t*3)*1;
    if(state==='SURPRISED') dy=-Math.abs(Math.sin(t*7))*2;
    if(state==='ANNOYED') dx=Math.sin(t*12)*1.5;
    if(state==='SLEEP') dy=Math.sin(t*1.4)*1.2+3;
    ctx.save();ctx.translate(Math.round(dx),Math.round(dy));
    ctx.beginPath();outline.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fillStyle=gold;ctx.fill();ctx.strokeStyle=ink;ctx.lineWidth=1.5;ctx.lineJoin='miter';ctx.stroke();
    rect(39,23,2,8,light);rect(36,31,2,3,light);rect(25,35,8,2,light);
    rect(30,49,3,4,'#eab553');rect(49,49,2,4,'#eab553');
    // Little feet and animated arms.
    rect(32,58,4,3,ink);rect(44,58,4,3,ink);
    const wave=state==='HAPPY'||state==='SPEAKING';
    rect(23,44+(wave?Math.round(Math.sin(t*8)*2):0),3,2,ink);
    rect(54,44-(wave?Math.round(Math.sin(t*8)*2):0),3,2,ink);
    const blink = state==='SLEEP'||kind==='blink';
    if(state==='ERROR') {
      for(const x of [31,44]){rect(x,38,1,1,ink);rect(x+1,39,1,1,ink);rect(x+2,40,1,1,ink);rect(x+3,41,1,1,ink);rect(x+3,38,1,1,ink);rect(x+2,39,1,1,ink);rect(x+1,40,1,1,ink);rect(x,41,1,1,ink);}
    } else if(state==='ANNOYED') {
      rect(31,38,2,1,ink);rect(33,39,2,1,ink);rect(45,39,2,1,ink);rect(47,38,2,1,ink);rect(32,41,3,1,ink);rect(45,41,3,1,ink);
    } else if(state==='HAPPY') {
      rect(32,38,2,1,ink);rect(31,39,1,2,ink);rect(34,39,1,2,ink);
      rect(45,38,2,1,ink);rect(44,39,1,2,ink);rect(47,39,1,2,ink);
    } else if(blink||state==='SHY') {
      rect(31,40,5,1,ink);rect(44,40,5,1,ink);
    } else if(state==='SURPRISED') {
      rect(31,36,5,7,ink);rect(44,36,5,7,ink);rect(32,37,2,2,'#fff8db');rect(45,37,2,2,'#fff8db');
    } else {
      const look=state==='THINKING'?Math.round(Math.sin(t*2)):kind==='lookLeft'?-2:kind==='lookRight'?2:0;
      rect(32+look,38,3,5,ink);rect(45+look,38,3,5,ink);
      rect(32+look,38,1,1,'#fff8db');rect(45+look,38,1,1,'#fff8db');
    }
    rect(29,44,state==='SHY'?7:4,2,state==='SHY'?'#e98e7b':'#eeb08a');rect(46,44,state==='SHY'?7:4,2,state==='SHY'?'#e98e7b':'#eeb08a');
    if(state==='SPEAKING'||kind==='yawn') {
      const mouth=kind==='yawn'||mouthPose==='large'?5:mouthPose==='small'?3:1;
      rect(38,44,5,mouth,ink);
      if(mouth>1)rect(39,45,3,mouth-2,'#e9a17c');
    } else if(state==='SURPRISED') {rect(38,44,4,5,ink);rect(39,45,2,3,'#ffedb0');}
    else if(state==='SLEEP') {rect(39,44,3,1,ink);}
    else {rect(37,44,1,2,ink);rect(42,44,1,2,ink);rect(38,46,4,1,ink);}
    ctx.restore();
    if(state==='HAPPY') {cross(19,25+Math.round(Math.sin(t*4)*2),'#c5aa56');cross(60,22-Math.round(Math.sin(t*4)*2),'#c5aa56');}
    if(state==='LISTENING') {const pulse=Math.floor(t*3)%3;ctx.strokeStyle='#8a9b72';ctx.lineWidth=1;ctx.strokeRect(59+pulse,38-pulse,2+pulse,7+pulse*2);rect(20-pulse,38,1,5,'#8a9b72');}
    if(state==='THINKING') {for(let i=0;i<3;i++)rect(51+i*5,20-(Math.floor(t*3)%3===i?2:0),2,2,'#9da882');}
    if(state==='SHY') {cross(19,39+Math.round(Math.sin(t*2)*2),'#d3a2a0');}
    if(state==='SLEEP') {ctx.font='5px monospace';ctx.fillStyle='#8a9b72';ctx.fillText('z',54,30-Math.floor(t%2));ctx.font='7px monospace';ctx.fillText('Z',59,24-Math.floor(t%3));}
    if(state==='SURPRISED') {rect(61,27,2,6,'#b7873e');rect(61,35,2,2,'#b7873e');}
    window.requestAnimationFrame(draw);
  }
  window.pixelPet={
    setState(value){
      if(baseState!==value)behavior.activity(performance.now());
      baseState=value;
      if(value!=='SPEAKING')mouthPose='closed';
    },
    setMouth(value){mouthPose=value;},
    touch(double){return behavior.touch(performance.now(),double);},
    setSleepSchedule(value){sleepScheduled=value;},
    get state(){return canvas.dataset.petState||baseState;},
    get behavior(){return currentBehavior;},
    get mouth(){return mouthPose;}
  };
  window.requestAnimationFrame(draw);
})();
