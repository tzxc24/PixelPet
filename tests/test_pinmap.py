import copy,json,subprocess,sys
from pathlib import Path
import pytest
from scripts.generate_pinmap import validate,render
ROOT=Path(__file__).resolve().parents[1]

def source(): return json.loads((ROOT/'hardware/pinmap.json').read_text(encoding='utf-8'))

def test_frozen_map_header_matches_source():
    data=source();validate(data)
    assert render(data)==(ROOT/'firmware/main/board/pixelpet_pin_config.h').read_text(encoding='utf-8')
    assert data['pins']['mic_bclk']==4
    assert data['pins']['motor']==21
    assert data['pins']['display_bl']==-1
    assert data['reserved']['display_bl']==10
    assert data['pins']['display_font_cs']==-1
    assert not data['hardware_enabled']

@pytest.mark.parametrize('pin',[0,3,19,20,26,27,34,35,36,37,45,46,39,43,48,10,11,12,1,2,22,49])
def test_protected_pins_rejected(pin):
    data=source();data['pins']['motor']=pin
    with pytest.raises(ValueError):validate(data)

def test_duplicate_pin_rejected():
    data=source();data['pins']['motor']=data['pins']['touch']
    with pytest.raises(ValueError):validate(data)

@pytest.mark.parametrize('signal',['display_bl','display_font_cs'])
def test_unverified_signal_cannot_be_enabled(signal):
    data=source();data['pins'][signal]=38
    with pytest.raises(ValueError):validate(data)

def test_activation_requires_reviewed_electrical_conditions():
    data=source();data['hardware_enabled']=True
    with pytest.raises(ValueError):validate(data)

def test_generator_check_command():
    result=subprocess.run([sys.executable,str(ROOT/'scripts/generate_pinmap.py'),'--check'],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
