// Kuis Mingguan: one 10-question quiz per week on a random SMA subject, the same for all 7.
// The first person to open the week's quiz makes Claude write it; it is stored in items
// (coll 'quiz', id = week key like 2026-W47) and everyone after that gets the stored copy.
//
// POST { week } with the person's Supabase session as Bearer token → { quiz }
// Needs ANTHROPIC_API_KEY. Optional: QUIZ_MODEL.

export const config = { maxDuration: 60 };

const SB = 'https://meagwjmfqhdcigqodaas.supabase.co';
const ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lYWd3am1mcWhkY2lncW9kYWFzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTUwMDE0NTcsImV4cCI6MjExMDU3NzQ1N30.7qDTO-8BEU7OELTMv0C0exlRrTlDXhATcouAOPD55xk';

export const SUBJECTS = ['Matematika', 'Fisika', 'Kimia', 'Biologi', 'Sejarah', 'Geografi', 'Ekonomi', 'Sosiologi', 'Bahasa Indonesia', 'Bahasa Inggris', 'PPKn'];

/** The current week in Jakarta time, as 2026-W47. */
export function weekKey(d = new Date()) {
  const t = new Date(d.getTime() + 7 * 3600 * 1000);
  const day = (t.getUTCDay() + 6) % 7;
  t.setUTCDate(t.getUTCDate() - day + 3);
  const y = t.getUTCFullYear(), jan4 = new Date(Date.UTC(y, 0, 4));
  const w = 1 + Math.round(((t - jan4) / 864e5 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
  return `${y}-W${String(w).padStart(2, '0')}`;
}

/** Looks random, same for everyone that week, and goes through every subject before any repeats. */
// Arab Melayu (Jawi, muatan lokal Riau) joins the mix: first in week 49 of 2026, then in the rotation.
// Weeks before that keep the original 11-subject cycle, so past quizzes keep their subjects.
export const SUBJECTS_2 = [...SUBJECTS, 'Arab Melayu'];
const FIXED = { '2026-W49': 'Arab Melayu' };
export function subjectFor(week) {
  if (FIXED[week]) return FIXED[week];
  const [y, w] = week.split('-W').map(Number);
  const list = week < '2026-W49' ? SUBJECTS : SUBJECTS_2;
  const order = shuffle([...list], 2004);
  return order[(y * 53 + w) % order.length];
}

function shuffle(a, seed) {
  let s = seed || 1;
  const r = () => ((s = Math.imul(s ^ (s >>> 15), 2246822507) + 0x9e3779b9 >>> 0) / 4294967296);
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}

/** Checks Claude's questions and shuffles the choices so the answer isn't always in one spot. */
export function cleanQuiz(raw, week, subject) {
  const qs = Array.isArray(raw?.questions) ? raw.questions : [];
  const out = [];
  qs.forEach((q, i) => {
    const choices = Array.isArray(q?.choices) ? q.choices.map((c) => String(c || '').trim().slice(0, 120)) : [];
    const a = Number(q?.answer);
    if (choices.length !== 4 || choices.some((c) => !c) || new Set(choices).size !== 4 || !(a >= 0 && a <= 3)) return;
    const text = String(q?.question || '').trim().slice(0, 300);
    if (!text) return;
    const order = shuffle([0, 1, 2, 3], week.length * 97 + i * 13 + 7);
    out.push({ q: text, c: order.map((k) => choices[k]), a: order.indexOf(a), x: String(q?.explain || '').trim().slice(0, 240) });
  });
  return out.length >= 10 ? { week, subject, qs: out.slice(0, 10), made: new Date().toISOString() } : null;
}

const TOOL = {
  name: 'make_quiz',
  description: 'Write the weekly quiz.',
  input_schema: {
    type: 'object',
    properties: {
      questions: {
        type: 'array', minItems: 12, maxItems: 12,
        items: {
          type: 'object',
          properties: {
            question: { type: 'string', description: 'The question, in Indonesian (English questions for Bahasa Inggris).' },
            choices: { type: 'array', minItems: 4, maxItems: 4, items: { type: 'string' }, description: 'Four answer options, no letters in front.' },
            answer: { type: 'integer', minimum: 0, maximum: 3, description: 'Index of the one correct choice.' },
            explain: { type: 'string', description: 'One short sentence on why it is right, in Indonesian.' },
          },
          required: ['question', 'choices', 'answer', 'explain'],
        },
      },
    },
    required: ['questions'],
  },
};

const EXTRA = {
  'Arab Melayu': [
    'Arab Melayu here means Malay written in Jawi (Arabic-script) letters, taught in Riau schools as muatan lokal; the friends learned it in Pekanbaru.',
    'Mix question types: read a short word or phrase written in Arab Melayu and pick its Latin spelling; pick the correct Arab Melayu spelling of a Latin word; name a letter (for example nga ڠ, ca چ, nya ڽ, ga ݢ, pa ڤ, va ۏ); and a few on its history or use in Riau (signboards, the Gurindam Dua Belas, Raja Ali Haji).',
    'Use common everyday words (rumah, sekolah, kawan, makan, Pekanbaru, Riau, Siak). Spell them the way standard Arab Melayu / Jawi teaching in Riau does; skip any word whose spelling is commonly disputed.',
    'Put Jawi text in the question or choices as it is, unvocalised, with no transliteration next to it that would give the answer away. Write explanations in Indonesian, with the Jawi and its Latin reading.',
  ].join('\n'),
};
const system = (subject) => [
  `Write a 12-question multiple-choice quiz (the best 10 get used) on SMA (Indonesian senior high school) ${subject}, for 7 old friends who graduated in 2004 from SMA Cendana Rumbai, Pekanbaru, and now compete every week for fun.`,
  'Level: what a kelas 1–3 SMA student learned in the KBK/Kurikulum 1994 era. Mix easy, medium and a few hard ones, ordered roughly easy to hard.',
  'Each question has exactly one correct answer and three plausible wrong ones. Double-check every fact and every calculation; if a question could be argued two ways, replace it.',
  'Keep questions short enough to read on a phone. For calculations, use numbers that work out cleanly without a calculator.',
  'A light nostalgic or local touch (Riau, Pekanbaru, Sungai Siak, early-2000s) is welcome now and then, but the content must stay correct subject matter.',
  EXTRA[subject] || '',
  'Always answer by calling make_quiz.',
].filter(Boolean).join('\n');

async function stored(H, week) {
  const r = await fetch(`${SB}/rest/v1/items?coll=eq.quiz&id=eq.${encodeURIComponent(week)}&select=data`, { headers: H }).catch(() => null);
  const rows = r?.ok ? await r.json() : [];
  return rows[0]?.data || null;
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });
  const auth = req.headers.authorization || '';
  if (!auth.startsWith('Bearer ')) return res.status(401).json({ error: 'Masuk dulu.' });
  const H = { apikey: ANON, Authorization: auth, 'Content-Type': 'application/json' };

  const who = await fetch(`${SB}/rest/v1/rpc/whoami`, { method: 'POST', headers: H, body: '{}' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (!who?.member) return res.status(403).json({ error: 'Cuma buat 7 orang Bandiecoot.' });

  const week = weekKey();
  const have = await stored(H, week);
  if (have) return res.status(200).json({ quiz: have });
  if (!process.env.ANTHROPIC_API_KEY) return res.status(503).json({ error: 'Kuis belum bisa dibuat: ANTHROPIC_API_KEY belum diisi di Vercel.' });

  const subject = subjectFor(week);
  try {
    // one call, well inside Vercel's 60 s limit; fall back to Haiku if the main model is unavailable or slow
    const models = [...new Set([process.env.QUIZ_MODEL || 'claude-sonnet-5-5', 'claude-haiku-5-5'])];
    const started = Date.now();
    let quiz = null, why = '';
    for (const model of models) {
      if (quiz || Date.now() - started > 25000) break;
      const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 50000 - (Date.now() - started));
      try {
        const r = await fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST', signal: ctl.signal,
          headers: { 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
          body: JSON.stringify({
            model, max_tokens: 3500, system: system(subject),
            tools: [TOOL], tool_choice: { type: 'tool', name: TOOL.name },
            messages: [{ role: 'user', content: `Quiz for week ${week}. Subject: ${subject}.` }],
          }),
        });
        if (!r.ok) { why = `Claude ${r.status} (${model}): ${(await r.text()).slice(0, 160)}`; console.error('quiz', why); continue; }
        const j = await r.json();
        const call = (j.content || []).find((c) => c.type === 'tool_use' && c.name === TOOL.name);
        quiz = cleanQuiz(call?.input, week, subject);
        if (!quiz) why = `soal dari ${model} nggak lolos cek (${(call?.input?.questions || []).length} soal, stop: ${j.stop_reason})`;
      } catch (e) { why = e.name === 'AbortError' ? `${model} kelamaan` : String(e.message || e); console.error('quiz', why); }
      finally { clearTimeout(timer); }
    }
    if (!quiz) return res.status(502).json({ error: `Soalnya belum jadi. Coba lagi sebentar. [${why}]` });

    // Someone else may have made it at the same moment: keep whichever landed first.
    await fetch(`${SB}/rest/v1/items?on_conflict=coll,id`, {
      method: 'POST', headers: { ...H, Prefer: 'resolution=ignore-duplicates,return=minimal' },
      body: JSON.stringify({ coll: 'quiz', id: week, data: quiz }),
    });
    return res.status(200).json({ quiz: (await stored(H, week)) || quiz });
  } catch (e) {
    console.error('quiz', e);
    return res.status(502).json({ error: `Pak guru lagi error. Coba lagi sebentar. [${String(e.message || e).slice(0, 160)}]` });
  }
}
