  // ---------- letadla (ADS-B z adsb.lol přes api/flights, v úrovni mraků a nad nimi) ----------
  // Kategorie modelu: jet (úzkotrupé dopravní), jetL (širokotrupé), jetS (regionální a business tryskáče), turbo (turbovrtulová), light (malá
  // vrtulová), heli (vrtulník), heliR (vrtulník záchranné služby). Typ letadla (ICAO kód z ADS-B) určuje model a název v kartě.
  const AC_TABLE = {
    jetL: 'A332:Airbus A330-200,A333:Airbus A330-300,A338:Airbus A330-800,A339:Airbus A330-900,A342:Airbus A340-200,A343:Airbus A340-300,A346:Airbus A340-600,A359:Airbus A350-900,A35K:Airbus A350-1000,A388:Airbus A380,B744:Boeing 747-400,B748:Boeing 747-8,B762:Boeing 767-200,B763:Boeing 767-300,B764:Boeing 767-400,B772:Boeing 777-200,B77L:Boeing 777F,B77W:Boeing 777-300ER,B788:Boeing 787-8,B789:Boeing 787-9,B78X:Boeing 787-10,A124:Antonov An-124,A225:Antonov An-225,IL96:Iljušin Il-96,MD11:McDonnell Douglas MD-11,A306:Airbus A300-600,A310:Airbus A310',
    jet: 'A318:Airbus A318,A319:Airbus A319,A320:Airbus A320,A321:Airbus A321,A19N:Airbus A319neo,A20N:Airbus A320neo,A21N:Airbus A321neo,BCS1:Airbus A220-100,BCS3:Airbus A220-300,B731:Boeing 737-100,B733:Boeing 737-300,B734:Boeing 737-400,B735:Boeing 737-500,B736:Boeing 737-600,B737:Boeing 737-700,B738:Boeing 737-800,B739:Boeing 737-900,B37M:Boeing 737 MAX 7,B38M:Boeing 737 MAX 8,B39M:Boeing 737 MAX 9,B752:Boeing 757-200,B753:Boeing 757-300,E190:Embraer 190,E195:Embraer 195,E290:Embraer E190-E2,E295:Embraer E195-E2,MD82:McDonnell Douglas MD-82,MD83:McDonnell Douglas MD-83,MD88:McDonnell Douglas MD-88,B712:Boeing 717,T154:Tupolev Tu-154,RJ85:Avro RJ85,F100:Fokker 100,SU95:Suchoj Superjet 100',
    jetS: 'E170:Embraer 170,E75L:Embraer 175,E75S:Embraer 175,E135:Embraer 135,E145:Embraer 145,CRJ2:Bombardier CRJ-200,CRJ7:Bombardier CRJ-700,CRJ9:Bombardier CRJ-900,CRJX:Bombardier CRJ-1000,E50P:Embraer Phenom 100,E55P:Embraer Phenom 300,C25A:Cessna CitationJet,C25B:Cessna CJ3,C25C:Cessna CJ4,C510:Cessna Citation Mustang,C525:Cessna CitationJet,C550:Cessna Citation II,C56X:Cessna Citation Excel,C680:Cessna Citation Sovereign,C700:Cessna Citation Longitude,C750:Cessna Citation X,CL30:Bombardier Challenger 300,CL35:Bombardier Challenger 350,CL60:Bombardier Challenger 600,GLEX:Bombardier Global Express,GL5T:Bombardier Global 5000,GL7T:Bombardier Global 7500,GLF4:Gulfstream IV,GLF5:Gulfstream V,GLF6:Gulfstream G650,LJ35:Learjet 35,LJ45:Learjet 45,LJ60:Learjet 60,FA50:Dassault Falcon 50,FA7X:Dassault Falcon 7X,FA8X:Dassault Falcon 8X,F2TH:Dassault Falcon 2000,F900:Dassault Falcon 900,H25B:Hawker 800,PC24:Pilatus PC-24,SF50:Cirrus Vision Jet,L39:Aero L-39 Albatros,L159:Aero L-159 ALCA,JAS39:Saab Gripen,GRIF:Saab Gripen',
    turbo: 'AT43:ATR 42-300,AT45:ATR 42-500,AT72:ATR 72,AT76:ATR 72-600,DH8A:Dash 8-100,DH8B:Dash 8-200,DH8C:Dash 8-300,DH8D:Dash 8 Q400,SF34:Saab 340,SB20:Saab 2000,JS31:Jetstream 31,JS41:Jetstream 41,B190:Beechcraft 1900,PC12:Pilatus PC-12,TBM7:TBM 700,TBM8:TBM 850,TBM9:TBM 900,C208:Cessna Caravan,BE20:King Air 200,BE9L:King Air 90,BE30:King Air 300,B350:King Air 350,AN26:Antonov An-26,AN24:Antonov An-24,AN28:Antonov An-28,C130:Lockheed C-130 Hercules,C295:Airbus C295,C27J:Alenia C-27J,DHC6:Twin Otter,D328:Dornier 328,E120:Embraer Brasilia,SW4:Fairchild Metroliner,P180:Piaggio Avanti,PAY2:Piper Cheyenne,AC90:Aero Commander 690,L410:Let L-410 Turbolet,Z37T:Zlín Z-37T Čmelák,AN2:Antonov An-2',
    heli: 'EC35:Airbus H135,H135:Airbus H135,EC45:Airbus H145,H145:Airbus H145,EC30:Airbus EC130,H130:Airbus H130,AS50:Airbus H125,H125:Airbus H125,AS55:Airbus AS355,AS65:Airbus AS365 Dauphin,EC20:Eurocopter EC120,EC55:Airbus H155,H160:Airbus H160,B06:Bell 206,B06T:Bell 206,B407:Bell 407,B412:Bell 412,B429:Bell 429,B505:Bell 505,R22:Robinson R22,R44:Robinson R44,R66:Robinson R66,MI8:Mil Mi-8,MI17:Mil Mi-17,MI2:Mil Mi-2,MI24:Mil Mi-24,KA32:Kamov Ka-32,UH60:Sikorsky Black Hawk,S76:Sikorsky S-76,S92:Sikorsky S-92,A109:Leonardo AW109,A139:Leonardo AW139,A119:Leonardo AW119,EN28:Enstrom 280,EN48:Enstrom 480,H269:Schweizer 269,H500:MD 500,MD52:MD 520N,B47G:Bell 47,SCHZ:Schweizer 300',
  };
  const AC_INFO = new Map();
  for (const [cat, list] of Object.entries(AC_TABLE)) for (const it of list.split(',')) { const i = it.indexOf(':'); AC_INFO.set(it.slice(0, i), [cat, it.slice(i + 1)]); }
  const AC_LIGHT = 'C150:Cessna 150,C152:Cessna 152,C172:Cessna 172,C182:Cessna 182,C206:Cessna 206,T206:Cessna T206,C210:Cessna 210,C177:Cessna 177,C162:Cessna 162,PA28:Piper PA-28,P28A:Piper Cherokee,P28R:Piper Arrow,PA18:Piper Super Cub,PA24:Piper Comanche,PA32:Piper Cherokee Six,PA34:Piper Seneca,PA44:Piper Seminole,SR20:Cirrus SR20,SR22:Cirrus SR22,DA20:Diamond DA20,DA40:Diamond DA40,DA42:Diamond DA42,DA62:Diamond DA62,BR23:BRM Bristell,TL20:TL-3000 Sirius,Z42:Zlín Z-42,Z43:Zlín Z-43,Z142:Zlín Z-142,Z242:Zlín Z-242,Z143:Zlín Z-143,AAT3:AAT-3,SIRA:Sirius,TBM:TBM,AT3:Aero AT-3,EV97:Evektor Sportstar,EVSS:Evektor Sportstar,JK05:Jabiru,AC11:Aero Commander,M20P:Mooney M20,BE33:Beechcraft Bonanza,BE35:Beechcraft Bonanza,BE36:Beechcraft Bonanza,BE55:Beechcraft Baron,BE58:Beechcraft Baron,GLID:Kluzák,ULAC:Ultralight,GYRO:Autogyro'.split(',');
  for (const it of AC_LIGHT) { const i = it.indexOf(':'); AC_INFO.set(it.slice(0, i), ['light', it.slice(i + 1)]); }
  // úplný seznam typů z ICAO Doc 8643 (87-letadla-typy.js, nástroj nastroje/letadla_typy.py): doplní jen kódy, které výše vybrané modely neznají
  for (const [cat, list] of Object.entries(AC_ICAO)) for (const it of list.split(',')) { const i = it.indexOf(':'), kod = it.slice(0, i); if (!AC_INFO.has(kod)) AC_INFO.set(kod, [cat, it.slice(i + 1)]); }
  // t = ICAO typ, c = kategorie ADS-B (A1 lehké … A5 těžké, A7 vrtulník, B1 kluzák…), alt v m, speed v m/s
  function acClass(t, c, alt, speed) {
    const i = AC_INFO.get(t);
    if (i) return { cat: i[0], name: i[1] };
    const cat = c === 'A7' ? 'heli' : c === 'A5' ? 'jetL' : c === 'A6' ? 'jetS' : c === 'A1' || c === 'B1' || c === 'B4' || c === 'B6' ? 'light' : c === 'A2' || c === 'A3' || c === 'A4' ? 'jet' : (alt < 3000 && speed < 110 ? 'light' : 'jet');
    return { cat, name: '' };
  }
  const isJet = (c) => c === 'jet' || c === 'jetL' || c === 'jetS';
  const isHeli = (c) => c === 'heli' || c === 'heliR';
  const lowFlyer = (p) => p.cat === 'light' || isHeli(p.cat) || (p.cat === 'turbo' && p.alt < 3500);
  const planesOn = () => !!$('l-planes') && $('l-planes').checked;
  const showPlane = (p) => planesOn() || p.lzs;
  // vrtulník záchranné služby (mesto.json "letadla_lzs": {nazev, registrace [], hex [], volaci (regulární výraz), typy []}): na mapě výrazně i při vypnutých letadlech
  const LZS = {{LETADLA_LZS}};
  const lzsRe = LZS && LZS.volaci ? new RegExp(LZS.volaci, 'i') : null;
  const isLzs = (a) => !!LZS && ((LZS.registrace || []).includes((a.reg || '').toUpperCase()) || (LZS.hex || []).includes((a.id || '').toLowerCase())
    || (lzsRe !== null && lzsRe.test(a.callsign || '') && (!(LZS.typy || []).length || (LZS.typy || []).includes(a.model))));
  const compass = (d) => ['S', 'SV', 'V', 'JV', 'J', 'JZ', 'Z', 'SZ'][Math.round(((d % 360) + 360) % 360 / 45) % 8];
  const lzsToast = (txt, id) => { const el = $('toast'); el.textContent = txt; el.dataset.lzs = id == null ? '' : String(id); el.style.cursor = id == null ? '' : 'pointer'; el.hidden = false; clearTimeout(lzsToast.t); lzsToast.t = setTimeout(() => { el.hidden = true; el.dataset.lzs = ''; el.style.cursor = ''; }, 9000); };
  $('toast').addEventListener('click', () => {            // klik na oznámení o vrtulníku LZS: pohled se vycentruje na vrtulník a otevře se jeho karta
    const el = $('toast'), p = el.dataset.lzs ? PLANES.list.get(el.dataset.lzs) : null; if (!p || !el.textContent.startsWith('🚁')) return;
    const [pix, piy] = toImg(p.x, p.y, gz(p.x, p.y) + planeVisualH(p));
    viewer.viewport.panTo(new OpenSeadragon.Point(pix / W, piy / W));
    planeCard(p); el.hidden = true; el.dataset.lzs = '';
  });
  if ({{LETADLA}} && $('l-planes-row')) {
    $('l-planes-row').hidden = false;
    try { $('l-planes').checked = localStorage.getItem('izo-letadla') === '1'; } catch {}
    $('l-planes').addEventListener('change', () => { try { localStorage.setItem('izo-letadla', $('l-planes').checked ? '1' : '0'); } catch {} PLANES.lastFetch = -1e9; });
  }
  const PLANESPR = new Map(), PLANESH = new Map();
  function planeSprite(cat, k) {
    const key = `${cat}|${k}`;
    if (PLANESPR.has(key)) return PLANESPR.get(key);
    const a = k / NDIR * Math.PI * 2, fx_ = Math.cos(a), fy_ = Math.sin(a), sxv = -fy_, syv = fx_;
    const SC = cat === 'jetL' ? 1.32 : cat === 'jetS' ? 0.7 : cat === 'turbo' ? 1.45 : 1;
    const O = toImg(0, 0, 0), R = (s, t, h) => { const p = toImg(fx_ * s * SC + sxv * t * SC, fy_ * s * SC + syv * t * SC, h * SC); return [p[0] - O[0], p[1] - O[1]]; };
    const vis = (nx, ny) => nx + ny < 0;
    const sun = (nx, ny, nz) => nx * SUNV[0] + ny * SUNV[1] + nz * SUNV[2];
    const faces = [];
    const Q = (pts, rgb, normal) => {
      const d = normal ? sun(normal[0], normal[1], normal[2]) : 0;
      faces.push({ pts: pts.map((p) => R(p[0], p[1], p[2])), col: lit(rgb, d), depth: pts.reduce((acc, p) => acc + (fx_ * p[0] + sxv * p[1]) + (fy_ * p[0] + syv * p[1]) - p[2] * 1.5, 0) / pts.length });
    };

    if (isJet(cat)) {
      const WH = [246, 248, 252], BELLY = [208, 214, 224], WING = [224, 228, 234], FIN = [26, 78, 146], GL = [40, 52, 70], ENG = [170, 175, 184];
      const l = 14, w = 13, r = 1.25, h0 = 0;
      const ring = (s, scale = 1, zOff = 0) => [
        [s, 0, h0 + zOff + r * scale * 1.1],
        [s, -r * scale * 0.9, h0 + zOff + r * scale * 0.5],
        [s, -r * scale * 0.9, h0 + zOff - r * scale * 0.5],
        [s, 0, h0 + zOff - r * scale * 0.9],
        [s, r * scale * 0.9, h0 + zOff - r * scale * 0.5],
        [s, r * scale * 0.9, h0 + zOff + r * scale * 0.5],
      ];
      const sections = [
        [l, 0.05, 0], [l - 2, 0.55, 0.05], [l - 4.5, 0.9, 0], [7, 1, 0],
        [-6, 1, 0], [-10, 0.85, 0.15], [-14, 0.15, 0.35]
      ];
      const rings = sections.map(([s, sc, zOff]) => ring(s, sc, zOff));
      for (let i = 0; i < rings.length - 1; i++) {
        const A = rings[i], B = rings[i + 1];
        for (let j = 0; j < 6; j++) {
          const j2 = (j + 1) % 6;
          const p1 = A[j], p2 = A[j2], p3 = B[j2], p4 = B[j];
          const mx = (p1[1] + p2[1]) / 2, mz = (p1[2] + p2[2]) / 2;
          const isBottom = j === 2 || j === 3;
          const isCockpit = i === 1 && (j === 0 || j === 1 || j === 5);
          const col = isCockpit ? GL : isBottom ? BELLY : WH;
          const normLocal = [i === 0 ? 0.6 : i === rings.length - 2 ? -0.4 : 0, mx < 0 ? -0.8 : mx > 0 ? 0.8 : 0, mz < h0 ? -0.7 : 0.7];
          const nx = fx_ * normLocal[0] + sxv * normLocal[1], ny = fy_ * normLocal[0] + syv * normLocal[1];
          if (vis(nx, ny) || normLocal[2] > 0.4) Q([p1, p2, p3, p4], col, [nx, ny, normLocal[2]]);
        }
      }
      const wRootF = 2.5, wRootB = -3.2, wTipF = -4.5, wTipB = -6.2;
      for (const side of [-1, 1]) {
        const rw = side * 1.1, tw = side * w;
        const W1 = [wRootF, rw, 0], W2 = [wTipF, tw, 0.25], W3 = [wTipB, tw, 0.25], W4 = [wRootB, rw, 0];
        Q([W1, W2, W3, W4], WING, [0, 0, 1]);
        Q([W4, W3, W2, W1], BELLY, [0, 0, -1]);
        Q([W2, [wTipF + 0.3, tw + side * 0.1, 1.2], [wTipB, tw + side * 0.1, 1.2], W3], FIN, [0, side * 0.8, 0.6]);
      }
      for (const side of [-1, 1]) {
        const ew = side * 4.6, ez = -0.9, elen = 3.2, er = 0.75;
        const M1 = [1.2, ew - er, ez - er], M2 = [1.2, ew + er, ez - er], M3 = [1.2, ew + er, ez + er], M4 = [1.2, ew - er, ez + er];
        const B1 = [1.2 - elen, ew - er, ez - er], B2 = [1.2 - elen, ew + er, ez - er], B3 = [1.2 - elen, ew + er, ez + er], B4 = [1.2 - elen, ew - er, ez + er];
        Q([M1, M2, M3, M4], GL, [fx_, fy_, 0]);
        Q([M2, B2, B3, M3], WH, [sxv * side, syv * side, 0]);
        Q([M4, B4, B1, M1], WH, [-sxv * side, -syv * side, 0]);
        Q([M3, B3, B4, M4], WH, [0, 0, 1]);
        Q([M1, B1, B2, M2], ENG, [0, 0, -1]);
      }
      const finF = -9.2, finB = -13.5, finTop = 4.8;
      Q([[finF, -0.12, 0.8], [finB + 1.2, -0.08, finTop], [finB, -0.08, finTop], [finB, -0.12, 0.6]], FIN, [-sxv, -syv, 0.2]);
      Q([[finB, 0.12, 0.6], [finB, 0.08, finTop], [finB + 1.2, 0.08, finTop], [finF, 0.12, 0.8]], FIN, [sxv, syv, 0.2]);
      for (const side of [-1, 1]) {
        const hw = side * 4.8, hRootF = -10.5, hRootB = -13.2, hTipF = -12.4, hTipB = -13.8;
        Q([[hRootF, side * 0.4, 0.7], [hTipF, hw, 0.8], [hTipB, hw, 0.8], [hRootB, side * 0.4, 0.7]], WING, [0, 0, 1]);
        Q([[hRootB, side * 0.4, 0.7], [hTipB, hw, 0.8], [hTipF, hw, 0.8], [hRootF, side * 0.4, 0.7]], BELLY, [0, 0, -1]);
      }
    } else if (isHeli(cat)) {
      const rescue = cat === 'heliR';
      const BODY = rescue ? [226, 46, 40] : [236, 238, 244], ROOF = rescue ? [248, 248, 250] : [38, 76, 130], GLS = [34, 50, 74], DK = [58, 62, 70];
      const w = 0.95;
      Q([[3.2, 0, 0.7], [2.2, -w * 0.85, 1.55], [2.2, w * 0.85, 1.55]], GLS, [fx_ * 0.8, fy_ * 0.8, 0.5]);
      Q([[2.2, -w * 0.85, 1.55], [2.2, w * 0.85, 1.55], [-1.4, w * 0.8, 2.0], [-1.4, -w * 0.8, 2.0]], ROOF, [0, 0, 1]);
      Q([[3.2, 0, 0.7], [2.2, w * 0.85, 1.55], [-1.4, w * 0.8, 2.0], [-1.9, w * 0.4, 0.8], [1.4, w * 0.9, 0.3]], BODY, [sxv, syv, 0.1]);
      Q([[3.2, 0, 0.7], [1.4, -w * 0.9, 0.3], [-1.9, -w * 0.4, 0.8], [-1.4, -w * 0.8, 2.0], [2.2, -w * 0.85, 1.55]], BODY, [-sxv, -syv, 0.1]);
      Q([[3.2, 0, 0.7], [1.4, w * 0.9, 0.3], [-1.9, w * 0.4, 0.8], [-1.9, -w * 0.4, 0.8], [1.4, -w * 0.9, 0.3]], DK, [0, 0, -1]);
      Q([[-1.6, -0.24, 1.55], [-1.6, 0.24, 1.55], [-6.2, 0.12, 1.6], [-6.2, -0.12, 1.6]], BODY, [0, 0, 1]);
      Q([[-1.6, 0.24, 1.55], [-1.6, 0.24, 1.0], [-6.2, 0.12, 1.25], [-6.2, 0.12, 1.6]], BODY, [sxv, syv, 0]);
      Q([[-1.6, -0.24, 1.0], [-1.6, -0.24, 1.55], [-6.2, -0.12, 1.6], [-6.2, -0.12, 1.25]], BODY, [-sxv, -syv, 0]);
      Q([[-5.0, -0.07, 1.4], [-5.9, -0.07, 3.1], [-6.5, -0.07, 3.1], [-6.3, -0.07, 1.3]], rescue ? BODY : ROOF, [-sxv, -syv, 0.2]);
      Q([[-6.3, 0.07, 1.3], [-6.5, 0.07, 3.1], [-5.9, 0.07, 3.1], [-5.0, 0.07, 1.4]], rescue ? BODY : ROOF, [sxv, syv, 0.2]);
      Q([[-5.4, -1.1, 1.45], [-5.4, 1.1, 1.45], [-6.2, 1.1, 1.45], [-6.2, -1.1, 1.45]], ROOF, [0, 0, 1]);
      for (const side of [-1, 1]) {
        Q([[2.5, side * 0.92, -0.15], [-1.9, side * 0.92, -0.15], [-1.9, side * 0.92, -0.04], [2.5, side * 0.92, -0.04]], DK, [0, 0, 1]);
        Q([[1.0, side * 0.7, 0.4], [1.0, side * 0.92, -0.1], [0.7, side * 0.92, -0.1], [0.7, side * 0.7, 0.4]], DK, [sxv * side, syv * side, 0]);
        Q([[-1.0, side * 0.7, 0.4], [-1.0, side * 0.92, -0.1], [-1.3, side * 0.92, -0.1], [-1.3, side * 0.7, 0.4]], DK, [sxv * side, syv * side, 0]);
      }
    } else {
      const turbo = cat === 'turbo';
      const WH = [250, 250, 252], RED = turbo ? [34, 82, 150] : [224, 44, 34], GL = [42, 54, 72];
      const l = 4.4, w = 5.6, r = 0.72;
      const P1 = [l, 0, 0], P2 = [l - 1.2, -r, -r * 0.6], P3 = [l - 1.2, r, -r * 0.6], P4 = [l - 1.2, r, r * 0.8], P5 = [l - 1.2, -r, r * 0.8];
      const T2 = [-l, -r * 0.3, 0.2], T3 = [-l, r * 0.3, 0.2], T4 = [-l, r * 0.3, 0.6], T5 = [-l, -r * 0.3, 0.6];
      Q([P1, P3, P4], RED, [fx_, fy_, 0.5]);
      Q([P1, P5, P2], RED, [fx_, fy_, -0.5]);
      Q([[l - 1.2, -r * 0.9, r * 0.8], [l - 1.2, r * 0.9, r * 0.8], [0.6, r * 0.85, 1.05], [0.6, -r * 0.85, 1.05]], GL, [fx_ * 0.7, fy_ * 0.7, 0.7]);
      Q([P3, T3, T4, P4], WH, [sxv, syv, 0]);
      Q([P5, T5, T2, P2], WH, [-sxv, -syv, 0]);
      Q([P2, T2, T3, P3], RED, [0, 0, -1]);
      const wF = 0.8, wB = -0.6;
      for (const side of [-1, 1]) {
        const sw = side * w;
        Q([[wF, 0, 1.05], [wF, sw, 1.08], [wB, sw, 1.08], [wB, 0, 1.05]], WH, [0, 0, 1]);
        Q([[wB, 0, 1.05], [wB, sw, 1.08], [wF, sw, 1.08], [wF, 0, 1.05]], RED, [0, 0, -1]);
        Q([[wF, sw, 1.08], [wF, sw - side * 0.8, 1.08], [wB, sw - side * 0.8, 1.08], [wB, sw, 1.08]], RED, [0, 0, 1]);
      }
      if (turbo) for (const side of [-1, 1]) {            // motorové gondoly turbovrtulových
        Q([[1.8, side * 2.3 - 0.45, 1.15], [1.8, side * 2.3 + 0.45, 1.15], [-1.4, side * 2.3 + 0.45, 1.15], [-1.4, side * 2.3 - 0.45, 1.15]], [60, 64, 72], [0, 0, 1]);
        Q([[1.8, side * 2.3 + 0.45, 1.15], [1.8, side * 2.3 + 0.45, 0.6], [-1.4, side * 2.3 + 0.45, 0.6], [-1.4, side * 2.3 + 0.45, 1.15]], [190, 194, 202], [sxv, syv, 0]);
        Q([[1.8, side * 2.3 - 0.45, 1.15], [1.8, side * 2.3 - 0.45, 0.6], [-1.4, side * 2.3 - 0.45, 0.6], [-1.4, side * 2.3 - 0.45, 1.15]], [190, 194, 202], [-sxv, -syv, 0]);
      }
      Q([[-l + 1.2, -0.05, 0.5], [-l, -0.05, 2.1], [-l - 0.4, -0.05, 2.1], [-l - 0.3, -0.05, 0.4]], RED, [-sxv, -syv, 0.2]);
      Q([[-l - 0.3, 0.05, 0.4], [-l - 0.4, 0.05, 2.1], [-l, 0.05, 2.1], [-l + 1.2, 0.05, 0.5]], RED, [sxv, syv, 0.2]);
      for (const side of [-1, 1]) {
        const hw = side * 1.8;
        Q([[-l + 0.3, 0, 0.45], [-l, hw, 0.45], [-l - 0.4, hw, 0.45], [-l - 0.2, 0, 0.45]], WH, [0, 0, 1]);
      }
    }

    faces.sort((a, b) => b.depth - a.depth);
    let minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
    for (const f of faces) {
      for (const [px, py] of f.pts) {
        if (px < minX) minX = px; if (px > maxX) maxX = px;
        if (py < minY) minY = py; if (py > maxY) maxY = py;
      }
    }
    const pad = 4;
    const wPx = Math.ceil(maxX - minX + pad * 2), hPx = Math.ceil(maxY - minY + pad * 2);
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, wPx); canvas.height = Math.max(1, hPx);
    const g = canvas.getContext('2d');
    g.imageSmoothingEnabled = false;
    const offX = -minX + pad, offY = -minY + pad;
    for (const f of faces) {
      g.beginPath();
      f.pts.forEach(([px, py], idx) => { const x = px + offX, y = py + offY; idx === 0 ? g.moveTo(x, y) : g.lineTo(x, y); });
      g.closePath();
      g.fillStyle = f.col;
      g.fill();
    }
    const shCanvas = document.createElement('canvas');
    shCanvas.width = canvas.width; shCanvas.height = canvas.height;
    const sg = shCanvas.getContext('2d');
    sg.imageSmoothingEnabled = false;
    for (const f of faces) {
      sg.beginPath();
      f.pts.forEach(([px, py], idx) => { const x = px + offX, y = py + offY; idx === 0 ? sg.moveTo(x, y) : sg.lineTo(x, y); });
      sg.closePath();
      sg.fillStyle = 'rgba(15, 22, 35, 0.22)';
      sg.fill();
    }
    const res = { c: canvas, x0: minX - pad, y0: minY - pad };
    PLANESH.set(key, { c: shCanvas, x0: minX - pad, y0: minY - pad });
    PLANESPR.set(key, res);
    return res;
  }

  const PLANES = {
    list: new Map(),
    drawn: [],
    hover: null,
    follow: null,
    cardId: null, cardT: 0, lzsSeen: new Set(),
    lastFetch: 0,
    off: false
  };

  function planeVisualH(p) {
    // V úrovni mraků (~150-220 m) nebo nad nimi (~340-480 m)
    return lowFlyer(p) ? 160 + (Math.min(p.alt, 2500) / 2500) * 60 : 340 + (p.alt / 12000) * 140;
  }

  function planeFollow(p) {
    PLANES.follow = (PLANES.follow === p.id ? null : p.id);
    if (PLANES.follow) {
      if (MHD.follow !== null) MHD.follow = null;
      $('follow').hidden = false;
      const b = document.createElement('b'); b.textContent = `${isHeli(p.cat) ? '🚁' : '✈️'} ${p.lzs ? (LZS.nazev || 'LZS') : p.callsign}`;
      $('followTxt').replaceChildren(b, ` · ${planeName(p)} · Výška: ${Math.round(p.alt)} m (${Math.round(p.alt * 3.2808)} ft) · Rychlost: ${Math.round(p.speed * 3.6)} km/h`);
    } else {
      $('follow').hidden = true;
    }
  }
  const planeName = (p) => p.name || p.model || (isHeli(p.cat) ? 'Vrtulník' : isJet(p.cat) ? 'Dopravní letadlo' : 'Sportovní letadlo');
  // karta letadla (klik): typ, registrace, výška, rychlost, směr, stoupání, ujetá dráha od načtení stránky; dráha se kreslí do mapy
  function planeCard(p, refresh) {
    const hist = p.hist || [], km = hist.reduce((s_, h, i) => s_ + (i ? Math.hypot(h[0] - hist[i - 1][0], h[1] - hist[i - 1][1]) : 0), 0) / 1000;
    const vr = p.vr || 0, min = hist.length ? Math.round((performance.now() - hist[0][3]) / 60000) : 0;
    const rows = [
      ['Typ', planeName(p) + (p.model && p.name ? ` (${p.model})` : '')], ['Registrace', p.reg], ['Volací znak', p.callsign],
      ['Výška', `${Math.round(p.alt)} m (${Math.round(p.alt * 3.2808)} ft)`], ['Rychlost', `${Math.round(p.speed * 3.6)} km/h (${Math.round(p.speed * 1.9438)} kt)`],
      ['Směr letu', `${Math.round(p.track)}° (${compass(p.track)})`],
      ['Stoupání', Math.abs(vr) < 0.5 ? 'vodorovný let' : `${vr > 0 ? '↑ stoupá' : '↓ klesá'} ${Math.abs(vr).toFixed(1)} m/s`],
      ['Squawk', p.squawk], ['Dráha letu', hist.length > 1 ? `${km.toFixed(1)} km za ${Math.max(1, min)} min (od otevření mapy)` : 'zatím krátce sledováno'],
    ];
    const old = PLANES.cardId === p.id && refresh && $('cardExtra').firstChild ? $('cardExtra').scrollTop : null;
    showCard({ title: `${isHeli(p.cat) ? '🚁' : '✈️'} ${p.lzs ? (LZS.nazev || 'LZS') : p.callsign || planeName(p)}`, text: p.lzs ? 'Vrtulník letecké záchranné služby. Poloha z ADS-B, bez záruky úplnosti.' : '',
      rows, lon: p.lon, lat: p.lat });
    $('card').dataset.plane = p.id; PLANES.cardId = p.id; PLANES.cardT = performance.now();
    const b = document.createElement('button'); b.type = 'button'; b.className = 'px-btn'; b.textContent = PLANES.follow === p.id ? 'Přestat sledovat' : 'Sledovat kamerou';
    b.addEventListener('click', () => { planeFollow(p); planeCard(p, true); });
    $('cardExtra').append(b);
  }
  function planeCardClose() { PLANES.cardId = null; }

  function parseFlightData(d) {
    if (d && Array.isArray(d.states)) {
      return d.states.filter((r) => !r[8] && r[5] != null && r[6] != null).map((r) => {
        const alt = r[7] ?? r[13] ?? 8000, speed = r[9] || 200, k = acClass('', '', alt, speed);
        return { id: r[0], callsign: (r[1] || '').trim() || r[0].toUpperCase(), reg: '', country: r[2] || '', lon: r[5], lat: r[6], alt, speed, track: r[10] || 0, vr: r[11] || 0, squawk: r[14] || '', cat: k.cat, model: '', name: '' };
      });
    }
    const ac = d?.ac || d?.aircraft;
    if (Array.isArray(ac)) {
      return ac.filter((a) => a.lat != null && a.lon != null && a.alt_baro !== 'ground').map((a) => {
        const alt = (a.alt_geom ?? a.alt_baro ?? 25000) * 0.3048, speed = (a.gs ?? 400) * 0.5144, k = acClass(a.t || '', a.category || '', alt, speed);
        const f = { id: a.hex || a.flight, callsign: (a.flight || '').trim() || (a.r || a.hex || '').trim(), reg: (a.r || '').trim(), country: '', lon: a.lon, lat: a.lat, alt, speed,
          track: a.track || a.mag_heading || 0, vr: (a.baro_rate || 0) * 0.00508, squawk: a.squawk || '', cat: k.cat, model: a.t || '', name: k.name || (a.desc || '') };
        f.lzs = isLzs(f);
        if (f.lzs) f.cat = 'heliR';
        return f;
      });
    }
    return null;
  }

  function applyIncomingFlights(incoming) {
    const seen = new Set();
    const now = performance.now();
    for (const f of incoming) {
      seen.add(f.id);
      const tx = (f.lon - cam.lon0) * cam.kx, ty = (f.lat - cam.lat0) * cam.ky;
      let existing = PLANES.list.get(f.id);
      if (existing) {
        existing.x += (tx - existing.x) * 0.35;
        existing.y += (ty - existing.y) * 0.35;
        existing.speed = f.speed;
        existing.track = f.track;
        existing.alt = f.alt;
        existing.vr = f.vr; existing.squawk = f.squawk; existing.reg = f.reg || existing.reg; existing.callsign = f.callsign || existing.callsign;
        existing.cat = f.cat; existing.lzs = f.lzs; existing.name = f.name || existing.name;
        existing.lastSeen = now;
        (existing.hist || (existing.hist = [])).push([existing.x, existing.y, f.alt, now]); if (existing.hist.length > 400) existing.hist.shift();
      } else {
        PLANES.list.set(f.id, {
          id: f.id, callsign: f.callsign, country: f.country,
          cat: f.cat, model: f.model, name: f.name, reg: f.reg, vr: f.vr, squawk: f.squawk, lzs: f.lzs,
          lon: f.lon, lat: f.lat, alt: f.alt, speed: f.speed, track: f.track,
          x: tx, y: ty, trail: [], hist: [[tx, ty, f.alt, now]], lastSeen: now
        });
        if (f.lzs && !PLANES.lzsSeen.has(f.id)) { PLANES.lzsSeen.add(f.id); lzsToast(`🚁 ${LZS.nazev || 'Vrtulník LZS'} je ve vzduchu. Klikněte pro zobrazení na mapě.`, f.id); }
      }
    }
    for (const [id, p] of PLANES.list) {
      if (!seen.has(id) && (now - p.lastSeen > 45000)) {
        if (PLANES.follow === id) { PLANES.follow = null; $('follow').hidden = true; }
        if (p.lzs) PLANES.lzsSeen.delete(id);
        PLANES.list.delete(id);
      }
    }
  }

  async function fetchFlights() {
    const pad = 0.35;
    const lamin = (cam.lat0 - pad).toFixed(4), lamax = (cam.lat0 + pad).toFixed(4);
    const lomin = (cam.lon0 - pad * 1.5).toFixed(4), lomax = (cam.lon0 + pad * 1.5).toFixed(4);
    try {
      const r = await fetch(`api/flights?lamin=${lamin}&lamax=${lamax}&lomin=${lomin}&lomax=${lomax}`, { signal: AbortSignal.timeout(4500) });
      if (r.status === 404) { PLANES.off = true; return; }
      if (!r.ok) return;
      const incoming = parseFlightData(await r.json());
      if (incoming && incoming.length) applyIncomingFlights(incoming);
    } catch {}
  }

  function stepPlanes(dt, now) {
    if (!PLANES.off && now - PLANES.lastFetch > (planesOn() ? 20000 : 45000)) {
      PLANES.lastFetch = now;
      fetchFlights();
    }
    if (PLANES.cardId && now - PLANES.cardT > 1500) {
      const pc = PLANES.list.get(PLANES.cardId);
      if (!$('card').hidden && $('card').dataset.plane === String(PLANES.cardId) && pc) planeCard(pc, true); else PLANES.cardId = null;
    }
    for (const [id, p] of PLANES.list) {
      const rad = p.track * Math.PI / 180;
      p.x += Math.sin(rad) * p.speed * dt;
      p.y += Math.cos(rad) * p.speed * dt;
      p.lon = cam.lon0 + p.x / cam.kx;
      p.lat = cam.lat0 + p.y / cam.ky;

      if (isJet(p.cat) && p.alt > 6500 && showPlane(p)) {
        if (!p.trailT || now - p.trailT > 220) {
          p.trailT = now;
          const k = ((Math.round(Math.atan2(Math.cos(rad), Math.sin(rad)) / (Math.PI * 2) * NDIR) % NDIR) + NDIR) % NDIR;
          const a = k / NDIR * Math.PI * 2, fx_ = Math.cos(a), fy_ = Math.sin(a), sxv = -fy_, syv = fx_;
          const vH = planeVisualH(p);
          const gz0 = gz(p.x, p.y);
          const eL = toImg(p.x + fx_ * 0.5 + sxv * (-4.6), p.y + fy_ * 0.5 + syv * (-4.6), gz0 + vH - 1.0);
          const eR = toImg(p.x + fx_ * 0.5 + sxv * (4.6), p.y + fy_ * 0.5 + syv * (4.6), gz0 + vH - 1.0);
          if (!p.trail) p.trail = [];
          p.trail.push({ l: eL, r: eR, t: now });
        }
      }
      if (p.trail && p.trail.length) {
        const driftX = realWind ? realWind.dx * 6 * dt : 0;
        const driftY = realWind ? realWind.dy * 6 * dt : 0;
        for (const pt of p.trail) {
          pt.l[0] += driftX; pt.l[1] += driftY;
          pt.r[0] += driftX; pt.r[1] += driftY;
        }
        while (p.trail.length && now - p.trail[0].t > 15000) p.trail.shift();
      }

      if (Math.hypot(p.x, p.y) > 55000) {
        if (PLANES.follow === id) { PLANES.follow = null; $('follow').hidden = true; }
        PLANES.list.delete(id);
      }
    }
  }

  function drawPlanes(sx, ox, oy, night, now, cw, ch) {
    PLANES.drawn = [];
    const NL_planes = [];
    const visScreen = (x, y, m = 140) => x > -m && y > -m && x < cw + m && y < ch + m;

    // 1. Kondenzační čáry (contrails)
    for (const [, p] of PLANES.list) {
      if (!showPlane(p) || !p.trail || !p.trail.length) continue;
      for (const side of ['l', 'r']) {
        ctx.beginPath();
        let started = false;
        for (let i = 0; i < p.trail.length; i++) {
          const pt = p.trail[i];
          const age = (now - pt.t) / 1000;
          if (age > 15) continue;
          const X = Math.round(ox + pt[side][0] * sx), Y = Math.round(oy + pt[side][1] * sx);
          if (!started) { ctx.moveTo(X, Y); started = true; } else { ctx.lineTo(X, Y); }
        }
        if (started) {
          ctx.strokeStyle = night > 0.5 ? 'rgba(180, 195, 220, 0.35)' : 'rgba(245, 248, 255, 0.45)';
          ctx.lineWidth = Math.max(1, Math.round(2.5 * sx));
          ctx.stroke();
        }
      }
    }

    // 2. Stíny na terénu
    for (const [, p] of PLANES.list) {
      if (!showPlane(p)) continue;
      const vH = planeVisualH(p);
      const shX = p.x - 0.45 * vH, shY = p.y + 0.35 * vH;
      const [six, siy] = toImg(shX, shY, gz(shX, shY));
      const X_sh = Math.round(ox + six * sx), Y_sh = Math.round(oy + siy * sx);
      if (!visScreen(X_sh, Y_sh, 200)) continue;
      const rad = p.track * Math.PI / 180;
      const k = ((Math.round(Math.atan2(Math.cos(rad), Math.sin(rad)) / (Math.PI * 2) * NDIR) % NDIR) + NDIR) % NDIR;
      planeSprite(p.cat, k);
      const shSpr = PLANESH.get(`${p.cat}|${k}`);
      if (shSpr) {
        ctx.globalAlpha = lowFlyer(p) ? 0.16 : 0.08;
        const mzs = p.lzs ? 1.9 : 1.5;
        const sW = Math.max(12 * mzs, Math.round(shSpr.c.width * sx * mzs)), sH = Math.max(12 * mzs, Math.round(shSpr.c.height * sx * mzs));
        const scR = sW / shSpr.c.width;
        ctx.drawImage(shSpr.c, Math.round(X_sh + shSpr.x0 * scR), Math.round(Y_sh + shSpr.y0 * scR), sW, sH);
        ctx.globalAlpha = 1.0;
      }
    }

    // 2b. Dráha letu vybraného letadla (z karty)
    {
      const sp = PLANES.cardId && PLANES.list.get(PLANES.cardId);
      if (sp && showPlane(sp) && sp.hist && sp.hist.length > 1) {
        ctx.save(); ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.setLineDash([6, 4]); ctx.strokeStyle = 'rgba(242,198,109,.9)'; ctx.beginPath();
        sp.hist.forEach(([hx, hy, ha], i) => { const q = toImg(hx, hy, gz(hx, hy) + planeVisualH({ ...sp, alt: ha })); const X_ = ox + q[0] * sx, Y_ = oy + q[1] * sx; if (i) ctx.lineTo(X_, Y_); else ctx.moveTo(X_, Y_); });
        ctx.stroke(); ctx.restore();
      }
    }

    // 2c. Svislá tenká linka od letadla k zemi, na zemi průhledný šedý kruh (nad jakým místem a jak vysoko letadlo je)
    for (const [, p] of PLANES.list) {
      if (!showPlane(p)) continue;
      const g0 = gz(p.x, p.y), vH = planeVisualH(p);
      const top = toImg(p.x, p.y, g0 + vH), bot = toImg(p.x, p.y, g0);
      const Xt = ox + top[0] * sx, Yt = oy + top[1] * sx, Xb = ox + bot[0] * sx, Yb = oy + bot[1] * sx;
      if (!visScreen(Xb, Yb, 200) && !visScreen(Xt, Yt, 200)) continue;
      const R_ = 14, ux = toImg(p.x + R_, p.y, g0), uy = toImg(p.x, p.y + R_, g0);
      ctx.save();
      ctx.translate(Xb, Yb);
      ctx.transform((ux[0] - bot[0]) * sx, (ux[1] - bot[1]) * sx, (uy[0] - bot[0]) * sx, (uy[1] - bot[1]) * sx, 0, 0);
      ctx.fillStyle = 'rgba(128,132,140,0.28)'; ctx.strokeStyle = 'rgba(110,114,122,0.55)'; ctx.lineWidth = 1 / Math.max(1, R_ * sx * 0.6);
      ctx.beginPath(); ctx.arc(0, 0, 1, 0, 6.2832); ctx.fill(); ctx.stroke();
      ctx.restore();
      ctx.save();
      ctx.strokeStyle = 'rgba(120,124,132,0.6)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(Math.round(Xt) + 0.5, Yt); ctx.lineTo(Math.round(Xb) + 0.5, Yb); ctx.stroke();
      ctx.restore();
    }

    // 3. Těla letadel
    for (const [id, p] of PLANES.list) {
      if (!showPlane(p)) continue;
      const vH = planeVisualH(p);
      const gz0 = gz(p.x, p.y);
      const [pix, piy] = toImg(p.x, p.y, gz0 + vH);
      const X_pl = Math.round(ox + pix * sx), Y_pl = Math.round(oy + piy * sx);
      if (!visScreen(X_pl, Y_pl, 220)) continue;

      const rad = p.track * Math.PI / 180;
      const k = ((Math.round(Math.atan2(Math.cos(rad), Math.sin(rad)) / (Math.PI * 2) * NDIR) % NDIR) + NDIR) % NDIR;
      const spr = planeSprite(p.cat, k);

      const mz = p.lzs ? 1.9 : 1.5;                           // vrtulník LZS je větší, aby byl vidět i z dálky
      const sW = Math.max(16 * mz, Math.round(spr.c.width * sx * mz)), sH = Math.max(16 * mz, Math.round(spr.c.height * sx * mz));
      const scR = sW / spr.c.width;
      const imgX = Math.round(X_pl + spr.x0 * scR), imgY = Math.round(Y_pl + spr.y0 * scR);
      ctx.drawImage(spr.c, imgX, imgY, sW, sH);

      PLANES.drawn.push([X_pl, Y_pl, p]);
      if (isHeli(p.cat)) {                                  // rotory: nosný (rozmazaný disk s lopatkami) a vyrovnávací
        const R_ = 5.2 * mz, u0 = toImg(p.x, p.y, gz0 + vH + 2.4 * mz), ux = toImg(p.x + R_, p.y, gz0 + vH + 2.4 * mz), uy = toImg(p.x, p.y + R_, gz0 + vH + 2.4 * mz);
        const cX = ox + u0[0] * sx, cY = oy + u0[1] * sx;
        ctx.save(); ctx.translate(cX, cY); ctx.transform((ux[0] - u0[0]) * sx / 1, (ux[1] - u0[1]) * sx / 1, (uy[0] - u0[0]) * sx / 1, (uy[1] - u0[1]) * sx / 1, 0, 0);
        ctx.fillStyle = 'rgba(30,36,48,0.16)'; ctx.beginPath(); ctx.arc(0, 0, 1, 0, 6.2832); ctx.fill();
        ctx.strokeStyle = 'rgba(20,24,32,0.75)'; ctx.lineWidth = Math.max(0.05, 1.6 / Math.max(6, R_ * sx * 2.4)); ctx.lineCap = 'round';
        const ang = now / 55;
        for (let b_ = 0; b_ < 4; b_++) { const a_ = ang + b_ * Math.PI / 2; ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(Math.cos(a_), Math.sin(a_)); ctx.stroke(); }
        ctx.restore();
      }
      if (p.lzs) {                                          // LZS: pulzující kruh, modrý majáček a štítek vždy
        const pulse = (now % 1400) / 1400, rr = Math.max(18, 30 * sx) + pulse * 26;
        ctx.save(); ctx.strokeStyle = `rgba(255,70,60,${(1 - pulse) * 0.9})`; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(X_pl, Y_pl, rr, 0, 6.2832); ctx.stroke();
        ctx.fillStyle = Math.floor(now / 160) % 2 ? '#3da5ff' : '#e8f4ff'; ctx.fillRect(X_pl - 2, Y_pl - Math.max(10, 16 * sx) - 2, 5, 5);
        ctx.restore();
      }

      // Poziční a výstražná světla (ve dne i v noci): červené vlevo, zelené vpravo, bílé vzadu; viditelnost podle směru pohledu kamery
      {
        const a = k / NDIR * Math.PI * 2, fx_ = Math.cos(a), fy_ = Math.sin(a), sxv = -fy_, syv = fx_;
        const SCn = (p.cat === 'jetL' ? 1.32 : p.cat === 'jetS' ? 0.7 : p.cat === 'turbo' ? 1.45 : 1) * mz, jt = isJet(p.cat), hl = isHeli(p.cat);
        const tipW = (jt ? 13.0 : hl ? 1.0 : 5.6) * SCn, tipS = (jt ? -4.5 : hl ? -0.4 : 0.2) * SCn, tipZ = (jt ? 0.2 : hl ? 1.5 : 1.08) * SCn;
        const P_light = (s_, t_, h_) => {
          const pt = toImg(p.x + fx_ * s_ + sxv * t_, p.y + fy_ * s_ + syv * t_, gz0 + vH + h_);
          return [Math.round(ox + pt[0] * sx), Math.round(oy + pt[1] * sx)];
        };
        // úhel kamery vůči nosu letadla (φ > 0 = kamera vlevo od směru letu); kamera je na jihozápadě, tj. pohled míří na severovýchod
        const hx = Math.sin(rad), hy = Math.cos(rad), vx = -Math.SQRT1_2, vy = -Math.SQRT1_2;
        const phi = Math.atan2(hx * vy - hy * vx, hx * vx + hy * vy) * 180 / Math.PI;
        const redOn = phi > -12 && phi < 110, greenOn = phi < 12 && phi > -110, tailOn = Math.abs(phi) > 110;
        const dayK = 0.6 + 0.4 * Math.min(1, night * 1.5);
        const sz = Math.max(3, Math.round(4 * sx * mz));
        if (redOn) NL_planes.push({ p: P_light(tipS, tipW, tipZ), col: '#ff2a2a', glowC: '255,40,40', size: sz, a: dayK, glow: true });
        if (greenOn) NL_planes.push({ p: P_light(tipS, -tipW, tipZ), col: '#22ff55', glowC: '40,255,90', size: sz, a: dayK, glow: true });
        if (tailOn) NL_planes.push({ p: P_light((jt ? -14 : hl ? -6.2 : -4.4) * SCn, 0, jt ? 0.5 * SCn : tipZ * 0.9), col: '#fffbe8', glowC: '255,250,220', size: sz, a: dayK, glow: true });
        let hs = 0; for (let i_ = 0; i_ < String(id).length; i_++) hs = (hs * 31 + String(id).charCodeAt(i_)) | 0;
        const ph = (now + Math.abs(hs) % 1200) % 1200;            // bílý strobo: dvojitý záblesk co 1,2 s
        if (ph < 90 || (ph > 190 && ph < 280)) {
          const finS = (jt ? -13.8 : hl ? -6.4 : -4.2) * SCn, finZ = (jt ? 4.8 : hl ? 3.1 : 2.1) * SCn;
          NL_planes.push({ p: P_light(finS, 0, finZ), col: '#ffffff', glowC: '255,255,255', size: Math.round(sz * 1.6), a: 1, glow: true, big: true });
          NL_planes.push({ p: P_light(tipS, -tipW, tipZ), col: '#ffffff', glowC: '255,255,255', size: sz, a: 1, glow: true, big: true });
          NL_planes.push({ p: P_light(tipS, tipW, tipZ), col: '#ffffff', glowC: '255,255,255', size: sz, a: 1, glow: true, big: true });
        }
        if ((now + Math.abs(hs) % 1000) % 1000 < 450) {          // červený maják (beacon) na trupu
          NL_planes.push({ p: P_light(0, 0, (hl ? 2.6 * mz : 0.7 * SCn)), col: '#ff2222', glowC: '255,40,40', size: Math.round(sz * 1.3), a: 1, glow: true, big: true });
        }
      }

      // 4. Štítek letu na hover / follow
      const isHovered = PLANES.hover && PLANES.hover.id === id;
      const isFollowed = PLANES.follow === id;
      if (isHovered || isFollowed || sx > 0.42 || p.lzs) {
        ctx.font = '700 12px "Atkinson Hyperlegible", system-ui, sans-serif';
        const txt = p.lzs ? `🚁 ${LZS.nazev || 'LZS'} · ${Math.round(p.alt)} m · ${Math.round(p.speed * 3.6)} km/h` : `${isHeli(p.cat) ? '🚁' : '✈️'} ${p.callsign}${p.model ? ' · ' + p.model : ''} · ${Math.round(p.alt)} m`;
        const tw = Math.ceil(ctx.measureText(txt).width) + 12;
        const tagX = X_pl, tagY = Y_pl - Math.round(sH / 2) - 14;
        ctx.fillStyle = p.lzs ? 'rgba(176, 28, 24, 0.94)' : 'rgba(22, 25, 31, 0.88)';
        ctx.fillRect(tagX - tw / 2, tagY - 9, tw, 20);
        if (isFollowed) {
          ctx.strokeStyle = '#f2c66d'; ctx.lineWidth = 1.5;
          ctx.strokeRect(tagX - tw / 2, tagY - 9, tw, 20);
        }
        ctx.fillStyle = p.lzs ? '#fff' : isFollowed ? '#f2c66d' : '#f3efe2';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(txt, tagX, tagY + 1);
        ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';
      }

      if (isFollowed) {
        viewer.viewport.panTo(new OpenSeadragon.Point(pix / W, piy / W), true);
      }
    }

    if (NL_planes.length) {
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      const ga = 0.35 + 0.65 * Math.min(1, night * 2);                  // ve dne slabší aureola, aby se na světlém pozadí nepřepálila
      for (const l of NL_planes) {
        const [lx, ly] = l.p, R = l.size * (l.big ? 4.5 : 3);
        const gr = ctx.createRadialGradient(lx, ly, 0, lx, ly, R);
        gr.addColorStop(0, `rgba(${l.glowC},${0.85 * l.a * ga})`); gr.addColorStop(0.35, `rgba(${l.glowC},${0.35 * l.a * ga})`); gr.addColorStop(1, `rgba(${l.glowC},0)`);
        ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(lx, ly, R, 0, 6.2832); ctx.fill();
      }
      ctx.restore();
      for (const l of NL_planes) {
        const [lx, ly] = l.p;
        ctx.fillStyle = l.col;
        ctx.fillRect(lx - l.size / 2, ly - l.size / 2, l.size, l.size);
      }
    }
  }

