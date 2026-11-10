"""Screen and interface contracts for the existing 240x240 simulator."""
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.core.config import Settings


def test_actual_screen_resolution_and_extra_states(tmp_path):
    with TestClient(create_app(database_path=tmp_path/'screen.db',settings=Settings(llm_mode='mock'))) as client:
        page=client.get('/').text
        assert 'width="240" height="240"' in page
        for state in ['ANNOYED','ERROR']:
            assert client.post('/api/simulator/preview',json={'state':state}).status_code==200


def test_rgb565_export(tmp_path):
    with TestClient(create_app(database_path=tmp_path/'sprite.db',settings=Settings(llm_mode='mock'))) as client:
        response=client.post('/api/assets/rgb565',json={'width':2,'height':1,'rgba':[255,0,0,255,0,255,0,255]})
        assert response.status_code==200
        assert response.content==bytes([0x00,0xf8,0xe0,0x07])
        assert response.headers['x-pixel-format']=='RGB565_LE_RGB'
        assert client.post('/api/assets/rgb565',json={'width':2,'height':1,'rgba':[1]}).status_code==422
