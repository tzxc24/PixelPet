"""Device presence and guarded provisional pin mappings."""
from time import monotonic
from threading import RLock
from backend.events import Event

class PinConfig:
    def __init__(self,pins=None,hardware_approved=False):
        self.pins=pins or {}
        mapped=[p for p in self.pins.values() if p!=-1]
        # Conservative S3 N16R8 guard: strapping, USB, flash/PSRAM, unavailable pins.
        prohibited={0,3,19,20,*range(22,38),45,46}
        if mapped and not hardware_approved: raise ValueError('HW_PENDING: explicit verified board approval required')
        if len(mapped)!=len(set(mapped)): raise ValueError('duplicate GPIO')
        if any(type(p) is not int or p<0 or p>48 or p in prohibited for p in mapped): raise ValueError('reserved or invalid GPIO')
        self.status='CONFIGURED_UNTESTED' if mapped else 'HW_PENDING'

class DeviceService:
    def __init__(self,bus,engine,heartbeat_timeout=30):
        self.bus,self.engine=bus,engine
        self.heartbeat_timeout=heartbeat_timeout
        self._devices={}
        self._lock=RLock()

    def connect(self,device_id,now=None):
        with self._lock:
            previous = self._devices.get(device_id)
            if previous and previous['connected']:
                return None
            reconnect_count = previous['reconnect_count'] + 1 if previous else 0
            self._devices[device_id] = {
                'device_id': device_id, 'kind': 'mock', 'connected': True,
                'last_heartbeat': monotonic() if now is None else now,
                'protocol': 'pixelpet-business-v1', 'hardware_status': 'HW_PENDING',
                'reconnect_count': reconnect_count,
            }
            self.engine.handle_event(Event(type='device.connected',device_id=device_id))
            return reconnect_count + 1

    def heartbeat(self,device_id,now=None,*,generation=None,kind=None):
        with self._lock:
            item = self._devices.get(device_id)
            if not item or not item['connected'] or generation not in (None, item['reconnect_count'] + 1):
                raise ValueError('device not connected')
            item['last_heartbeat'] = monotonic() if now is None else now
            if kind in ('virtual', 'esp32'):
                item['kind'] = kind

    def disconnect(self,device_id,*,generation=None):
        with self._lock:
            item = self._devices.get(device_id)
            if item and item['connected'] and generation in (None, item['reconnect_count'] + 1):
                item['connected'] = False
                self.engine.handle_event(Event(type='device.disconnected',device_id=device_id))

    def expire(self,now=None):
        now=monotonic() if now is None else now
        with self._lock:
            expired=[key for key,item in self._devices.items() if item['connected'] and now-item['last_heartbeat']>self.heartbeat_timeout]
            for key in expired: self.disconnect(key)
            return expired

    def status(self):
        with self._lock:
            return [dict(item) for item in self._devices.values()]

class XiaozhiAdapter:
    status='BLOCKED_PROTOCOL_INTEGRATION'
    protocol='xiaozhi-websocket-external-gateway'
    def send(self,event):
        raise RuntimeError('Native xiaozhi audio gateway not installed; PixelPet JSON is not native protocol')
