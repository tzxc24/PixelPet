"""Validate the single software pin source and generate the central C header."""
import argparse
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'hardware/pinmap.json'
HEADER=ROOT/'firmware/main/board/pixelpet_pin_config.h'
EXPECTED={'mic_bclk','mic_ws','mic_din','speaker_bclk','speaker_ws','speaker_dout','display_sck','display_mosi','display_rst','display_dc','display_cs','touch','motor','display_bl','display_font_cs'}
PROTECTED={0,3,19,20,*range(22,38),*range(39,49)}

def validate(data):
    pins=data['pins']
    if set(pins)!=EXPECTED:raise ValueError('missing or unknown signal')
    if pins['display_bl']!=-1 or pins['display_font_cs']!=-1:raise ValueError('HW_PENDING: BL and CS-F must remain disabled')
    used=[p for p in pins.values() if p!=-1]
    reserved=set(data['reserved'].values())
    if any(type(p) is not int or p<0 or p>48 or p in PROTECTED or p in reserved for p in used):raise ValueError('protected/reserved/invalid GPIO')
    if len(used)!=len(set(used)):raise ValueError('duplicate GPIO')
    if data['hardware_enabled'] and not all(data.get(k) for k in ('electrical_reviewed','display_csf_isolated_verified','motor_supply_and_threshold_verified')):
        raise ValueError('HW_PENDING: hardware activation requires explicit electrical review')
    return data

def render(data):
    validate(data)
    lines=['#pragma once','// GENERATED from hardware/pinmap.json by scripts/generate_pinmap.py; do not edit.','// SOFTWARE_PINMAP_FROZEN / PHYSICAL_PINOUT_UNVERIFIED', '#define PIXELPET_HARDWARE_ENABLED '+str(int(data['hardware_enabled']))]
    for name,pin in data['pins'].items(): lines.append('#define PIXELPET_PIN_'+name.upper()+' '+str(pin))
    lines.append('#define PIXELPET_RESERVED_BL_GPIO '+str(data['reserved']['display_bl']))
    for group in ('display','audio','touch'):
        for key,value in data[group].items():
            lines.append('#define PIXELPET_'+group.upper()+'_'+key.upper()+' '+str(int(value) if isinstance(value,bool) else value))
    return '\n'.join(lines)+'\n'

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    generated=render(json.loads(SOURCE.read_text(encoding='utf-8-sig')))
    if args.check:
        if not HEADER.exists() or HEADER.read_text(encoding='utf-8')!=generated:raise SystemExit('Generated pin header differs; run scripts/generate_pinmap.py')
        print('PASS: pin guards and JSON/header consistency')
    else:
        HEADER.parent.mkdir(parents=True,exist_ok=True);HEADER.write_text(generated,encoding='utf-8');print(HEADER)
if __name__=='__main__':main()
