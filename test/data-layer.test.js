/**
 * Data-layer tests voor recepten–datum koppeling.
 * Draai met: node test/data-layer.test.js
 */

// ── Minimale state + stubs ────────────────────────────────────────────────────
let S = {
  receptDagen: {},
  receptWeek: {},
  geselecteerd: [],
  weekPers: {},
  actieveWeek: '2026-05-03', // zondag week 19 (zo 3 mei)
  recepten: [
    { id: 'r1', titel: 'Pasta', personen: 4 },
    { id: 'r2', titel: 'Dal',   personen: 2 },
  ],
  gebruiker: null, // geen Supabase in tests
};

// Stubs voor Supabase-calls (no-op)
const DB = { from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({}) }) }), delete: () => ({ eq: () => ({ eq: () => ({ eq: () => ({}) }) }) }), insert: async () => ({}) }) };
function ensureMenuVoorWeek() { return null; }
function slaWeekmenuOp() {}
function rIP() {}
function renderDpkCal() {}
function renderDpkGekozen() {}

// ── Kopieer de pure hulpfuncties uit index.html ───────────────────────────────
function dagWeekStart(dateStr) {
  const p = dateStr.split('-');
  const d = new Date(+p[0], +p[1]-1, +p[2]);
  const sun = new Date(+p[0], +p[1]-1, +p[2] - d.getDay());
  return `${sun.getFullYear()}-${String(sun.getMonth()+1).padStart(2,'0')}-${String(sun.getDate()).padStart(2,'0')}`;
}

function getDatesForRecipe(recipeId) {
  return S.receptDagen[recipeId] || [];
}

function getRecipesForWeek(weekStartStr) {
  const result = { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: [] };
  Object.entries(S.receptDagen).forEach(([rid, dates]) => {
    dates.forEach(ds => {
      if (dagWeekStart(ds) === weekStartStr) {
        const r = S.recepten.find(x => x.id === rid);
        if (r) result[new Date(ds + 'T00:00:00').getDay()].push({ ...r, geplandeDatum: ds });
      }
    });
  });
  return result;
}

async function linkRecipeToDate(recipeId, dateStr) {
  const arr = getDatesForRecipe(recipeId);
  if (arr.includes(dateStr)) return;
  S.receptDagen[recipeId] = [...arr, dateStr].sort();
  const ws = dagWeekStart(dateStr);
  S.receptWeek[recipeId] = S.receptWeek[recipeId] || ws;
  if (ws === S.actieveWeek && !S.geselecteerd.includes(recipeId)) S.geselecteerd.push(recipeId);
}

async function unlinkRecipeFromDate(recipeId, dateStr) {
  const nieuw = (S.receptDagen[recipeId] || []).filter(d => d !== dateStr);
  if (!nieuw.length) delete S.receptDagen[recipeId]; else S.receptDagen[recipeId] = nieuw;
  const ws = dagWeekStart(dateStr);
  const nogInWeek = (S.receptDagen[recipeId] || []).some(d => dagWeekStart(d) === ws);
  if (!nogInWeek) {
    if (ws === S.actieveWeek) S.geselecteerd = S.geselecteerd.filter(x => x !== recipeId);
    if (!(S.receptDagen[recipeId] || []).length) delete S.receptWeek[recipeId];
  }
}

// ── Test helpers ──────────────────────────────────────────────────────────────
let passed = 0, failed = 0;

function reset() {
  S.receptDagen = {};
  S.receptWeek = {};
  S.geselecteerd = [];
  S.weekPers = {};
}

function assert(condition, label) {
  if (condition) {
    console.log(`  ✓ ${label}`);
    passed++;
  } else {
    console.error(`  ✗ ${label}`);
    failed++;
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────
async function run() {
  console.log('\ndagWeekStart()');
  assert(dagWeekStart('2026-05-03') === '2026-05-03', 'zondag geeft zichzelf terug');
  assert(dagWeekStart('2026-05-07') === '2026-05-03', 'donderdag geeft zondag van dezelfde week');
  assert(dagWeekStart('2026-05-10') === '2026-05-10', 'volgende zondag');
  assert(dagWeekStart('2026-05-01') === '2026-04-26', 'vrijdag geeft vorige zondag');

  console.log('\nlinkRecipeToDate()');
  reset();
  await linkRecipeToDate('r1', '2026-05-06'); // woensdag week 19
  assert(getDatesForRecipe('r1').includes('2026-05-06'), 'datum opgeslagen');
  assert(S.geselecteerd.includes('r1'), 'in geselecteerd voor actieve week');
  assert(S.receptWeek['r1'] === '2026-05-03', 'receptWeek wijst naar weekstart');

  await linkRecipeToDate('r1', '2026-05-07'); // donderdag week 19
  assert(getDatesForRecipe('r1').length === 2, 'twee datums mogelijk');
  assert(getDatesForRecipe('r1')[0] === '2026-05-06', 'datums gesorteerd');

  await linkRecipeToDate('r1', '2026-05-06'); // zelfde datum
  assert(getDatesForRecipe('r1').length === 2, 'geen duplicaten');

  console.log('\nunlinkRecipeFromDate()');
  reset();
  await linkRecipeToDate('r1', '2026-05-06');
  await linkRecipeToDate('r1', '2026-05-07');
  await unlinkRecipeFromDate('r1', '2026-05-06');
  assert(getDatesForRecipe('r1').length === 1, 'één datum verwijderd');
  assert(!getDatesForRecipe('r1').includes('2026-05-06'), 'juiste datum weg');
  assert(S.geselecteerd.includes('r1'), 'nog in geselecteerd want andere dag in week');

  await unlinkRecipeFromDate('r1', '2026-05-07');
  assert(getDatesForRecipe('r1').length === 0, 'alle datums weg');
  assert(!S.geselecteerd.includes('r1'), 'uit geselecteerd verwijderd');
  assert(!S.receptWeek['r1'], 'receptWeek opgeruimd');

  console.log('\ngetRecipesForWeek()');
  reset();
  await linkRecipeToDate('r1', '2026-05-03'); // zondag
  await linkRecipeToDate('r1', '2026-05-06'); // woensdag
  await linkRecipeToDate('r2', '2026-05-06'); // woensdag, ander recept
  await linkRecipeToDate('r2', '2026-05-11'); // volgende week maandag — niet in week 19
  const week19 = getRecipesForWeek('2026-05-03');
  assert(week19[0].length === 1, 'r1 op zondag');
  assert(week19[0][0].id === 'r1', 'correct recept op zondag');
  assert(week19[3].length === 2, 'twee recepten op woensdag');
  assert(week19[1].length === 0, 'maandag leeg');
  const week20 = getRecipesForWeek('2026-05-10');
  assert(week20[1].length === 1, 'r2 op maandag week 20');

  console.log('\ngetDatesForRecipe()');
  reset();
  assert(getDatesForRecipe('r1').length === 0, 'leeg voor onbekend recept');
  await linkRecipeToDate('r1', '2026-05-06');
  await linkRecipeToDate('r1', '2026-05-08');
  const datums = getDatesForRecipe('r1');
  assert(datums.length === 2, 'twee datums terug');
  assert(datums[0] === '2026-05-06', 'gesorteerd op datum asc');

  // Samenvatting
  console.log(`\n${passed + failed} tests: ${passed} geslaagd, ${failed} gefaald\n`);
  process.exit(failed > 0 ? 1 : 0);
}

run().catch(e => { console.error(e); process.exit(1); });
