"""Databáze typů letadel pro prohlížeč: z úředního seznamu ICAO Doc 8643 (kód typu z ADS-B -> kategorie modelu + název)
vyrobí web/js/87-letadla-typy.js (AC_ICAO). Kategorie: jet, jetL, jetS, turbo, light, heli. Ručně vybrané modely z AC_TABLE
ve web/js/87-letadla.js mají přednost. Spuštění: PYTHONUTF8=1 .venv/Scripts/python nastroje/letadla_typy.py"""
import json, os, urllib.request

URL = 'https://doc8643.icao.int/external/aircrafttypes'
OUT = os.path.join(os.path.dirname(__file__), '..', 'web', 'js', '87-letadla-typy.js')


def kategorie(x):
    cls, eng, wtc = x['AircraftDescription'], x['EngineType'], x['WTC']
    if cls == 'Helicopter': return 'heli'
    if cls == 'Gyrocopter': return 'light'
    if cls == 'Tiltrotor': return 'turbo'
    if eng == 'Jet': return 'jetL' if wtc in ('H', 'J') else 'jetS' if wtc == 'L' else 'jet'
    if eng == 'Turboprop/Turboshaft': return 'turbo'
    return 'light'


def main():
    req = urllib.request.Request(URL, method='POST', data=b'', headers={'User-Agent': 'izomapa-letadla-typy'})
    data = json.load(urllib.request.urlopen(req, timeout=90))
    typy = {}
    for x in data:
        kod = x['Designator']
        if not kod or kod in typy: continue
        nm = f"{x['ManufacturerCode'].title()} {x['ModelFullName']}" if x['ModelFullName'].split(' ')[0].lower() not in x['ManufacturerCode'].lower() else x['ModelFullName']
        typy[kod] = (kategorie(x), nm.replace(',', ' ').replace(':', ' ').replace('|', ' ').strip()[:40])
    por = {}
    for kod, (k, nm) in sorted(typy.items()): por.setdefault(k, []).append(f'{kod}:{nm}')
    radky = ["  // Generováno nastroje/letadla_typy.py z ICAO Doc 8643 (kód typu -> kategorie modelu a název); neupravovat ručně.", "  const AC_ICAO = {"]
    for k, v in por.items(): radky.append(f"    {k}: {json.dumps(','.join(v), ensure_ascii=False)},")
    radky.append("  };")
    open(OUT, 'w', encoding='utf-8', newline='\n').write('\n'.join(radky) + '\n')
    print(len(typy), 'typů,', {k: len(v) for k, v in por.items()}, os.path.getsize(OUT) // 1024, 'kB')


main()
