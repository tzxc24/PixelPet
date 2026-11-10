"""Pure effect decisions; no GPIO, playback or recording side effects."""
from collections import deque
from time import monotonic
from threading import RLock
from typing import get_args
from backend.ai.schemas import Emotion
from backend.events import Event

STATES = {'IDLE','LISTENING','THINKING','SPEAKING','SLEEP','HAPPY','SHY','SURPRISED','ANNOYED','ERROR'}
EMOTIONS = get_args(Emotion)
STATE_EMOTIONS = {
    'THINKING': 'thinking', 'SLEEP': 'sleepy', 'HAPPY': 'happy',
    'SHY': 'shy', 'SURPRISED': 'surprised', 'ANNOYED': 'angry',
}

class PetEngine:
    def __init__(self,bus):
        self._lock=RLock()
        self.bus=bus
        self.state='IDLE'
        self.emotion='normal'
        self.recording=False
        self.speaking=False
        self._audio_owner=None
        self._state_owner=None
        self._seen=deque(maxlen=1024)
        self._down=None
        self._connected=set()
        self._last_touch=-float('inf')
        self._last_gesture=-float('inf')
        self.configure({})

    def configure(self,settings):
        with self._lock:
            return self._configure(settings)

    def _configure(self,settings):
        settings=dict(settings)
        if 'haptics' in settings: settings['haptic_enabled']=settings['haptics']
        self.settings=getattr(self,'settings',{'haptic_enabled':True,'haptic_strength':.5,'quiet_mode':False,'long_press_ms':650,'touch_debounce_ms':40}) | settings
        self.settings['haptic_strength']=max(0,min(1,float(self.settings['haptic_strength'])))
        self.settings['long_press_ms']=max(200,min(3000,int(self.settings['long_press_ms'])))
        self.settings['touch_debounce_ms']=max(10,min(200,int(self.settings['touch_debounce_ms'])))

    def snapshot(self):
        with self._lock:
            return {'state':self.state,'emotion':self.emotion,'recording':self.recording,'speaking':self.speaking,'hardware_status':'HW_PENDING'}

    def handle_event(self,event,now=None):
        with self._lock:
            return self._handle_event(event,now)

    def _handle_event(self,event,now=None):
        event=Event.model_validate(event) if isinstance(event,dict) else event
        if event.event_id in self._seen: return []
        self._seen.append(event.event_id)
        self.bus.publish(event)
        now=monotonic() if now is None else now
        kind=event.type
        preferences=getattr(self,'preferences',None)
        quiet=preferences.is_quiet() if preferences is not None else self.settings['quiet_mode']
        effects=[]
        def state(value,owner=event.device_id,emotion=None):
            self.state=value
            self._state_owner=owner
            if value!='SPEAKING' or emotion is not None:
                self.emotion=emotion or STATE_EMOTIONS.get(value,'normal')
            effects.append({'type':'pet.state','payload':{'state':value}})
        def record(owner=event.device_id):
            if self.speaking or self.recording: return
            self.recording=True
            self._audio_owner=owner
            state('LISTENING',owner)
            effects.append({'type':'audio.record_start','payload':{}})
        def stop_recording():
            if not self.recording or self._audio_owner!=event.device_id: return False
            self.recording=False
            self._audio_owner=None
            state('THINKING')
            return True
        def haptic(name):
            if self.recording or not self.settings['haptic_enabled'] or quiet: return
            effects.append({'type':'haptic.pattern','payload':{'name':name,'strength':self.settings['haptic_strength'],'durations_ms':{'short':[70],'double':[60,60,60],'long':[220]}[name],'simulated':True}})
        if kind=='touch.touch_down':
            if self._down is not None or now-self._last_touch < self.settings['touch_debounce_ms']/1000: return []
            self._down=(event.device_id,now)
            self._last_touch=now
        elif kind=='clock.tick':
            if self._down is not None and now-self._down[1]>=self.settings['long_press_ms']/1000:
                record(self._down[0])
        elif kind=='touch.touch_up':
            if self._down is not None and self._down[0]==event.device_id:
                elapsed=now-self._down[1]
                self._down=None
                if not self.recording and elapsed<self.settings['touch_debounce_ms']/1000:
                    return []
                if elapsed>=self.settings['long_press_ms']/1000:
                    record()
            self._last_touch=now
            if stop_recording():
                effects.append({'type':'audio.record_stop','payload':{}})
        elif kind in ('touch.long_press','audio.record_start'): record()
        elif kind=='audio.record_stop':
            stop_recording()
        elif kind=='audio.speak_start':
            if not event.device_id.startswith(('pixelpet-sim','browser','pc-')) and event.device_id not in self._connected: return []
            if not self.recording and not self.speaking:
                self.speaking=True
                self._audio_owner=event.device_id
                state('SPEAKING')
        elif kind=='audio.speak_end':
            if self.speaking and self._audio_owner==event.device_id:
                self.speaking=False
                self._audio_owner=None
                state('IDLE')
        elif kind in ('touch.tap','touch.double_tap'):
            if self.recording or self.speaking: return []
            if now-self._last_gesture<self.settings['touch_debounce_ms']/1000: return []
            self._last_gesture=now
            state('SHY' if kind=='touch.double_tap' else 'HAPPY')
            haptic('double' if kind=='touch.double_tap' else 'short')
        elif kind=='haptic.pattern':
            name=event.payload.get('name','short')
            if name not in ('short','double','long'): return []
            haptic(name)
        elif kind=='haptic.pulse':
            if not self.recording and self.settings['haptic_enabled'] and not quiet:
                effects.append({'type':kind,'payload':{'duration_ms':max(1,min(500,int(float(event.payload.get('duration_ms',70))))),'strength':max(0,min(self.settings['haptic_strength'],float(event.payload.get('strength',.5)))),'simulated':True}})
        elif kind=='device.connected':
            self._connected.add(event.device_id)
        elif kind in ('device.disconnected','device.error'):
            self._connected.discard(event.device_id)
            if self._down is not None and self._down[0]==event.device_id:
                self._down=None
            if self._audio_owner==event.device_id:
                self.recording=self.speaking=False
                self._audio_owner=None
            if self._state_owner==event.device_id or (kind=='device.error' and self._state_owner is None):
                state('ERROR' if kind=='device.error' else 'IDLE')
        elif kind in ('pet.state','pet.emotion'):
            value=str(event.payload.get('state',event.payload.get('emotion','IDLE'))).upper()
            if value=='SLEEPY': value='SLEEP'
            emotion=event.payload.get('emotion')
            if value in STATES and not self.recording and not self.speaking:
                if value not in ('LISTENING','SPEAKING'):
                    state(value,emotion=emotion if emotion in EMOTIONS else None)
                elif kind=='pet.emotion' and emotion in EMOTIONS:
                    self.emotion=emotion
        return effects
