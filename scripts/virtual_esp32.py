"""Virtual ESP32-S3 control client for the PixelPet business WebSocket."""
import argparse
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
import sys
from time import monotonic, sleep

from websockets.exceptions import ConnectionClosed, InvalidHandshake
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.mock_device import connection_options


class DeviceEvent(str, Enum):
    TOUCH_START = 'TOUCH_START'
    TOUCH_END = 'TOUCH_END'
    TOUCH_SHORT = 'TOUCH_SHORT'
    TOUCH_DOUBLE = 'TOUCH_DOUBLE'
    TOUCH_LONG = 'TOUCH_LONG'
    RECORD_START = 'RECORD_START'
    RECORD_STOP = 'RECORD_STOP'
    AUDIO_PLAY_START = 'AUDIO_PLAY_START'
    AUDIO_PLAY_END = 'AUDIO_PLAY_END'
    HAPTIC_SHORT = 'HAPTIC_SHORT'
    HAPTIC_DOUBLE = 'HAPTIC_DOUBLE'
    DISPLAY_EMOTION = 'DISPLAY_EMOTION'


class DeviceRejected(RuntimeError):
    """The peer responded, but rejected the operation."""


@dataclass
class VirtualState:
    wifi: str = 'DISCONNECTED'
    display: str = 'IDLE'
    emotion: str = 'normal'
    recording: bool = False
    playing: bool = False
    reconnects: int = 0
    last_rtt_ms: float | None = None
    motor_pulses: list[int] = field(default_factory=list)


class VirtualESP32:
    """Serial request/ACK transport, with bounded reconnection and no event replay."""

    def __init__(self, url, *, timeout=3.0, reconnect_attempts=3):
        if timeout <= 0 or reconnect_attempts < 1:
            raise ValueError('timeout and reconnect attempts must be positive')
        self.url = url
        self.options = connection_options(url)
        self.timeout = timeout
        self.reconnect_attempts = reconnect_attempts
        self.state = VirtualState()
        self.heartbeat_interval = 5.0
        self._socket = None
        self._successful_connections = 0
        self._seq = 0

    def _receive(self):
        frame = self._socket.recv(timeout=self.timeout)
        try:
            data = json.loads(frame)
        except (ValueError, TypeError) as exc:
            raise ConnectionError('Malformed server response') from exc
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ConnectionError('Unsupported server response')
        return data

    def connect(self):
        if self._socket is not None:
            return
        self.state.wifi = 'CONNECTING'
        try:
            self._socket = connect(
                self.url, open_timeout=self.timeout, close_timeout=self.timeout,
                max_size=16384, **self.options,
            )
            greeting = self._receive()
            if greeting.get('type') != 'device.connected' or greeting.get('protocol') != 'pixelpet-business-v1':
                raise ConnectionError('Expected PixelPet device greeting')
            self._seq = 0
            self._exchange('hello', {'client': 'virtual'})
            self.state.wifi = 'CONNECTED'
            self.state.reconnects = self._successful_connections
            self._successful_connections += 1
            deadline = greeting.get('heartbeat_timeout', 30)
            if isinstance(deadline, (float, int)) and deadline > 0:
                self.heartbeat_interval = min(5.0, deadline / 3)
        except BaseException:
            self.disconnect()
            raise

    def disconnect(self):
        socket, self._socket = self._socket, None
        self.state.wifi = 'DISCONNECTED'
        self.state.display = 'IDLE'
        self.state.emotion = 'normal'
        self.state.recording = self.state.playing = False
        self.state.motor_pulses.clear()
        if socket is not None:
            socket.close()

    def reconnect(self):
        self.disconnect()
        for attempt in range(self.reconnect_attempts):
            try:
                self.connect()
                return
            except (ConnectionClosed, InvalidHandshake, OSError):
                if attempt + 1 == self.reconnect_attempts:
                    raise
                sleep(min(.25 * 2 ** attempt, 2))

    def _exchange(self, kind, payload):
        if self._socket is None:
            raise ConnectionError('Virtual device is offline')
        self._seq += 1
        started = monotonic()
        try:
            self._socket.send(json.dumps({
                'version': 1, 'seq': self._seq, 'type': kind, 'payload': payload,
            }, allow_nan=False))
            response = self._receive()
            if response.get('seq') != self._seq:
                raise ConnectionError('Server ACK sequence mismatch')
            if response.get('type') == 'error':
                if response.get('payload', {}).get('code') == 'invalid_sequence':
                    raise ConnectionError('Server requires sequence resynchronization')
                raise DeviceRejected('Server rejected the device event')
            if response.get('type') != 'ack' or response.get('payload', {}).get('received') != kind:
                raise ConnectionError('Unexpected server ACK')
        except (ConnectionClosed, OSError):
            self.disconnect()
            raise

        self.state.last_rtt_ms = round((monotonic() - started) * 1000, 2)
        snapshot = response['pet']
        self.state.display = snapshot['state']
        self.state.emotion = snapshot.get('emotion', 'normal')
        self.state.recording = snapshot['recording']
        self.state.playing = snapshot['speaking']
        for effect in response['effects']:
            if effect['type'] == 'haptic.pattern':
                self.state.motor_pulses.extend(effect['payload']['durations_ms'])
                del self.state.motor_pulses[:-24]
        return response

    def heartbeat(self):
        try:
            return self._exchange('heartbeat', {})
        except (ConnectionClosed, OSError):
            self.reconnect()
            return self._exchange('heartbeat', {})

    def send(self, event: DeviceEvent, **payload):
        return self._exchange(DeviceEvent(event).value, payload)

    def watch(self, seconds):
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            self.heartbeat()
            sleep(max(0, min(self.heartbeat_interval, deadline - monotonic())))

    def demo(self):
        events = [
            DeviceEvent.TOUCH_START, DeviceEvent.TOUCH_END, DeviceEvent.TOUCH_SHORT,
            DeviceEvent.TOUCH_LONG, DeviceEvent.RECORD_STOP,
            DeviceEvent.RECORD_START, DeviceEvent.RECORD_STOP,
            DeviceEvent.AUDIO_PLAY_START, DeviceEvent.AUDIO_PLAY_END,
            DeviceEvent.HAPTIC_SHORT, DeviceEvent.HAPTIC_DOUBLE,
        ]
        trace = {}
        for event in events:
            self.send(event)
            trace[event.value] = self.state.display
        self.send(DeviceEvent.DISPLAY_EMOTION, emotion='shy')
        trace[DeviceEvent.DISPLAY_EMOTION.value] = self.state.display
        return trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='ws://127.0.0.1:8765/api/devices/ws?device_id=virtual-001')
    parser.add_argument('--watch', type=float, default=5, metavar='SECONDS')
    parser.add_argument('--reconnect-demo', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.watch <= 3600:
        parser.error('--watch must be between 0 and 3600 seconds')
    try:
        device = VirtualESP32(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        device.reconnect()
        trace = device.demo()
        if args.reconnect_demo:
            device.reconnect()
        device.watch(args.watch)
        print(json.dumps({'states': trace, 'device': asdict(device.state)}, ensure_ascii=False))
    except KeyboardInterrupt:
        print('Virtual ESP32 stopped.')
    except (DeviceRejected, ConnectionClosed, InvalidHandshake, OSError) as exc:
        print(f'Virtual ESP32 failed: {type(exc).__name__}', file=sys.stderr)
        return 1
    finally:
        device.disconnect()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
