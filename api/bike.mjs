// Kereta Den: one of the 7 asks for a small change to the shared cartoon bike, in plain words.
// Claude picks at most a few changes from a fixed menu (colours, exhaust, headlight, stance,
// extras, plate); this function checks them, applies them and returns the new design.
// The app saves it to the shared items table, so everyone sees the same bike.
//
// POST { prompt, bike } with the person's Supabase session as Bearer token → { bike, caption }
// Needs ANTHROPIC_API_KEY (Vercel → Settings → Environment Variables). Optional: BIKE_MODEL.

export const config = { maxDuration: 30 };

const SB = 'https://meagwjmfqhdcigqodaas.supabase.co';
const ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lYWd3am1mcWhkY2lncW9kYWFzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTUwMDE0NTcsImV4cCI6MjExMDU3NzQ1N30.7qDTO-8BEU7OELTMv0C0exlRrTlDXhATcouAOPD55xk';
const DAILY = 15;

export const DEFAULT_BIKE = {
  body: '#161618', shield: '#f6f6f3', seat: '#1f1f22', stripe1: '#20a35c', stripe2: '#d42a2a', rims: '#dfe2e5',
  exhaust: 'standar', headlight: 'standar', stance: 'standar', extras: [], plate: 'BM 2004 DHC',
};
const COLORS = ['body', 'shield', 'seat', 'stripe1', 'stripe2', 'rims'];
const ENUMS = { exhaust: ['standar', 'racing', 'racing_api'], headlight: ['standar', 'bulat', 'sangar'], stance: ['standar', 'ceper', 'trail'] };
const EXTRAS = ['spion_bulat', 'box_belakang', 'bendera', 'stiker_dhc', 'lampu_disko', 'bulu_jok', 'tas_gitar', 'keranjang'];
const MAX_CHANGES = 3, MAX_EXTRAS = 5;

/** Any stored design, cleaned to known fields and safe values. */
export function cleanBike(b) {
  const o = { ...DEFAULT_BIKE };
  if (!b || typeof b !== 'object') return o;
  for (const k of COLORS) if (/^#[0-9a-f]{6}$/i.test(b[k] || '')) o[k] = b[k].toLowerCase();
  for (const [k, list] of Object.entries(ENUMS)) if (list.includes(b[k])) o[k] = b[k];
  if (Array.isArray(b.extras)) o.extras = [...new Set(b.extras.filter((e) => EXTRAS.includes(e)))].slice(0, MAX_EXTRAS);
  if (typeof b.plate === 'string') o.plate = b.plate.toUpperCase().replace(/[^A-Z0-9 ]/g, '').trim().slice(0, 12) || DEFAULT_BIKE.plate;
  return o;
}

/** Applies Claude's proposed changes, at most MAX_CHANGES of them. */
export function applyChanges(bike, ch) {
  const out = { ...bike, extras: [...bike.extras] };
  let n = 0;
  const take = () => n++ < MAX_CHANGES;
  if (!ch || typeof ch !== 'object') return out;
  for (const k of COLORS) if (/^#[0-9a-f]{6}$/i.test(ch[k] || '') && ch[k].toLowerCase() !== out[k] && take()) out[k] = ch[k].toLowerCase();
  for (const [k, list] of Object.entries(ENUMS)) if (list.includes(ch[k]) && ch[k] !== out[k] && take()) out[k] = ch[k];
  for (const e of Array.isArray(ch.remove_extras) ? ch.remove_extras : []) if (out.extras.includes(e) && take()) out.extras = out.extras.filter((x) => x !== e);
  for (const e of Array.isArray(ch.add_extras) ? ch.add_extras : []) if (EXTRAS.includes(e) && !out.extras.includes(e) && out.extras.length < MAX_EXTRAS && take()) out.extras.push(e);
  if (typeof ch.plate === 'string') { const p = cleanBike({ plate: ch.plate }).plate; if (p !== out.plate && take()) out.plate = p; }
  return out;
}

const TOOL = {
  name: 'modify_bike',
  description: 'Apply a small change to the cartoon bike and say what you did.',
  input_schema: {
    type: 'object',
    properties: {
      changes: {
        type: 'object',
        description: `Only the fields you change. At most ${MAX_CHANGES} changes in total.`,
        properties: {
          ...Object.fromEntries(COLORS.map((k) => [k, { type: 'string', description: 'Hex colour like #1a2b3c' }])),
          exhaust: { type: 'string', enum: ENUMS.exhaust }, headlight: { type: 'string', enum: ENUMS.headlight }, stance: { type: 'string', enum: ENUMS.stance },
          add_extras: { type: 'array', items: { type: 'string', enum: EXTRAS } },
          remove_extras: { type: 'array', items: { type: 'string', enum: EXTRAS } },
          plate: { type: 'string', description: 'Number plate text, max 12 characters, only if asked' },
        },
        additionalProperties: false,
      },
      caption: { type: 'string', description: 'One short playful sentence in Indonesian (Pekanbaru slang welcome), max 90 characters, saying what changed.' },
    },
    required: ['changes', 'caption'],
  },
};

const SYSTEM = [
  'You customise "Kereta Den", a cartoon of a 2000s Indonesian underbone motorbike (bebek) shared by 7 old bandmates from Rumbai, Pekanbaru (band: Bandiecoot, motto "Destruction Hip Core").',
  'Parts you can change: colours of body, shield (the white leg-shield), seat, stripe1 (upper stripe), stripe2 (lower stripe), rims;',
  'exhaust: standar | racing | racing_api (racing with flames); headlight: standar | bulat (round) | sangar (angry);',
  'stance: standar | ceper (lowered) | trail (raised, knobby tyres);',
  'extras: spion_bulat (round mirrors), box_belakang (top box), bendera (flag on a pole), stiker_dhc (band sticker), lampu_disko (under-glow lights), bulu_jok (furry seat cover), tas_gitar (guitar bag strapped on), keranjang (front basket);',
  'plate: the number-plate text.',
  `Make a SMALL change that matches the request: at most ${MAX_CHANGES} changes. If the request can't be done with these parts, pick the closest and say so with humour.`,
  'Keep the plate unless they ask to change it. Never put rude or hateful words on the plate or caption.',
  'Always answer by calling modify_bike.',
].join('\n');

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });
  const auth = req.headers.authorization || '';
  if (!auth.startsWith('Bearer ')) return res.status(401).json({ error: 'Masuk dulu.' });
  const H = { apikey: ANON, Authorization: auth, 'Content-Type': 'application/json' };

  const who = await fetch(`${SB}/rest/v1/rpc/whoami`, { method: 'POST', headers: H, body: '{}' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (!who?.member) return res.status(403).json({ error: 'Cuma buat 7 orang Bandiecoot.' });

  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body || {};
  const prompt = String(body.prompt || '').trim().slice(0, 200);
  if (!prompt) return res.status(400).json({ error: 'Mau modif apa?' });
  if (!process.env.ANTHROPIC_API_KEY) return res.status(503).json({ error: 'Bengkel belum buka: ANTHROPIC_API_KEY belum diisi di Vercel.' });

  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const cr = await fetch(`${SB}/rest/v1/bike_log?select=id&created_at=gte.${encodeURIComponent(since)}`, { headers: { ...H, Prefer: 'count=exact', Range: '0-0' } }).catch(() => null);
  const used = Number(/\/(\d+)$/.exec(cr?.headers.get('content-range') || '')?.[1] ?? 0);
  if (used >= DAILY) return res.status(429).json({ error: `Jatah modif hari ini habis (${DAILY}x). Besok lagi ya.` });

  const bike = cleanBike(body.bike);
  try {
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
      body: JSON.stringify({
        model: process.env.BIKE_MODEL || 'claude-haiku-5-5',
        max_tokens: 600,
        system: SYSTEM,
        tools: [TOOL],
        tool_choice: { type: 'auto' },
        messages: [{ role: 'user', content: `Current bike: ${JSON.stringify(bike)}\nRequest from ${who.name || 'a bandmate'}: ${prompt}` }],
      }),
    });
    if (!r.ok) throw new Error(`claude ${r.status}: ${(await r.text()).slice(0, 200)}`);
    const j = await r.json();
    const call = (j.content || []).find((c) => c.type === 'tool_use' && c.name === TOOL.name);
    if (!call) return res.status(502).json({ error: 'Montirnya bingung. Coba kata lain.' });
    const next = applyChanges(bike, call.input.changes);
    const caption = String(call.input.caption || 'Udah dimodif.').slice(0, 120);
    await fetch(`${SB}/rest/v1/bike_log`, { method: 'POST', headers: { ...H, Prefer: 'return=minimal' }, body: JSON.stringify({ prompt }) }).catch(() => {});
    return res.status(200).json({ bike: next, caption });
  } catch (e) {
    console.error('bike', e);
    return res.status(502).json({ error: 'Bengkel lagi error. Coba lagi sebentar.' });
  }
}
