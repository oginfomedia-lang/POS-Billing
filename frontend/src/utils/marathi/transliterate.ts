// Phonetic Marathi typing: Roman letters -> Devanagari, like a phone's Marathi keyboard.
//
//   transliterate('sakhar dudh')    -> 'साखर दूध'
//   suggest('sakhar')               -> ['साखर', 'सखर', 'साखार', ...]   (best first)
//
// Three layers, best first:
//   1. choices this PC's users picked before (passed in as `learned`)
//   2. a built-in list of common shop / grocery words (WORDS below)
//   3. rules: longest match first ("kh" before "k"), inherent "a", vowel signs, ् for conjuncts,
//      ं ः ँ, and alternatives for ambiguous letters (a: अ/आ, t: त/ट, n: न/ण/ं, l: ल/ळ, ...)
// Rules alone can't know every word (sakhar could be सखर or साखर), which is why suggestions exist.
//
// Capital letters pick the "hard" sounds when used inside a word: T ट, Th ठ, D ड, Dh ढ, N ण, L ळ, Sh ष,
// R / Ru ऋ, A आ, I ई, U ऊ, E ॲ, O ऑ, M ं, H ः, .n ं, .N ँ. "Sakhar" (capital first letter only) is read
// as "sakhar"; an ALL-CAPS word ("KG", "MRP") is left as typed.
//
// Self-contained (no imports) so the unit tests can run it directly with Node.

export type VowelId = 'a' | 'aa' | 'i' | 'ii' | 'u' | 'uu' | 'e' | 'ai' | 'o' | 'au' | 'ri' | 'ae' | 'ao';

/** [independent letter, vowel sign after a consonant] */
const VOWEL: Record<VowelId, readonly [string, string]> = {
  a: ['अ', ''], aa: ['आ', 'ा'], i: ['इ', 'ि'], ii: ['ई', 'ी'], u: ['उ', 'ु'], uu: ['ऊ', 'ू'],
  e: ['ए', 'े'], ai: ['ऐ', 'ै'], o: ['ओ', 'ो'], au: ['औ', 'ौ'], ri: ['ऋ', 'ृ'], ae: ['ॲ', 'ॅ'], ao: ['ऑ', 'ॉ'],
};
const VIRAMA = '्';
const ANUSVARA = 'ं';

type Token =
  | { kind: 'C'; roman: string; opts: string[] } // consonant (first option = most likely)
  | { kind: 'V'; roman: string; opts: VowelId[] } // vowel
  | { kind: 'S'; roman: string; opts: string[] }; // sign: ं ः ँ (or, for n/m before a consonant, ं or the consonant)

const CONSONANTS: [string, string[]][] = [
  ['kSh', ['क्ष']], ['ksh', ['क्ष']], ['dny', ['ज्ञ']], ['gny', ['ज्ञ']], ['chh', ['छ']],
  ['kh', ['ख']], ['gh', ['घ']], ['ch', ['च']], ['jh', ['झ']], ['Th', ['ठ']], ['Dh', ['ढ']],
  ['th', ['थ', 'ठ']], ['dh', ['ध', 'ढ']], ['ph', ['फ']], ['bh', ['भ']], ['Sh', ['ष']], ['sh', ['श', 'ष']],
  ['k', ['क']], ['q', ['क']], ['x', ['क्ष']], ['g', ['ग']], ['c', ['च']], ['j', ['ज']], ['z', ['झ', 'ज']],
  ['T', ['ट']], ['D', ['ड']], ['N', ['ण']], ['t', ['त', 'ट']], ['d', ['द', 'ड']], ['n', ['न', 'ण']],
  ['p', ['प']], ['f', ['फ']], ['b', ['ब']], ['m', ['म']], ['y', ['य']], ['r', ['र']],
  ['L', ['ळ']], ['l', ['ल', 'ळ']], ['v', ['व']], ['w', ['व']], ['s', ['स']], ['h', ['ह']],
];
const VOWELS: [string, VowelId[]][] = [
  ['aa', ['aa']], ['ai', ['ai']], ['au', ['au']], ['ou', ['au']], ['ee', ['ii']], ['ii', ['ii']],
  ['oo', ['uu']], ['uu', ['uu']], ['Ru', ['ri']],
  ['a', ['a', 'aa']], ['A', ['aa']], ['i', ['i', 'ii']], ['I', ['ii']], ['u', ['u', 'uu']], ['U', ['uu']],
  ['e', ['e']], ['E', ['ae']], ['o', ['o']], ['O', ['ao']], ['R', ['ri']],
];
const SIGNS: [string, string[]][] = [['.n', [ANUSVARA]], ['.N', ['ँ']], ['M', [ANUSVARA]], ['H', ['ः']]];

type Entry = { key: string; make: () => Token };
const TABLE: Entry[] = [
  ...CONSONANTS.map(([key, opts]): Entry => ({ key, make: () => ({ kind: 'C', roman: key, opts: [...opts] }) })),
  ...VOWELS.map(([key, opts]): Entry => ({ key, make: () => ({ kind: 'V', roman: key, opts: [...opts] }) })),
  ...SIGNS.map(([key, opts]): Entry => ({ key, make: () => ({ kind: 'S', roman: key, opts: [...opts] }) })),
].sort((a, b) => b.key.length - a.key.length);

/** Consonants before which a typed n / m is usually the nasal sign ं (kanda कांदा, limbu लिंबू, sundar सुंदर). */
const NASAL_BEFORE = /^(k|kh|g|gh|ch|chh|c|j|jh|z|t|th|T|Th|d|dh|D|Dh|p|ph|f|b|bh|s|sh|Sh)$/;

/** A word that can be typed in Marathi mode: Roman letters (and ".n" / ".N"). */
const WORD = /^[A-Za-z](?:[A-Za-z]|\.[nN])*$/;

/** Is this a Roman word to convert? Not ALL-CAPS abbreviations ("KG", "MRP"), not codes. */
export function isConvertible(word: string): boolean {
  if (!WORD.test(word)) return false;
  const letters = word.replace(/\./g, '');
  return !(letters.length > 1 && letters === letters.toUpperCase());
}

function normaliseCase(word: string): string {
  // "Sakhar" (sentence case) means "sakhar"; capitals only matter inside a word ("baTaTa").
  return /^[A-Z][a-z.]*$/.test(word) ? word.toLowerCase() : word;
}

function lex(word: string): Token[] | null {
  const w = normaliseCase(word);
  const tokens: Token[] = [];
  let i = 0;
  while (i < w.length) {
    const rest = w.slice(i);
    // Exact case first ("Th" ठ); then as lowercase, for a capital with no special meaning ("Kanda").
    const hit = TABLE.find((e) => rest.startsWith(e.key)) ?? TABLE.find((e) => rest.toLowerCase().startsWith(e.key));
    if (!hit) return null;
    tokens.push(hit.make());
    i += hit.key.length;
  }
  // Context: n / m before a consonant may be the nasal sign; a word-final a / i / u is usually long
  // (batata बटाटा, pani पाणी, limbu लिंबू).
  tokens.forEach((t, k) => {
    const next = tokens[k + 1];
    if (t.kind === 'C' && (t.roman === 'n' || t.roman === 'm' || t.roman === 'N') && next?.kind === 'C'
        && NASAL_BEFORE.test(next.roman)) {
      tokens[k] = { kind: 'S', roman: t.roman, opts: [ANUSVARA, ...t.opts] };
    }
    if (t.kind === 'V' && k === tokens.length - 1 && tokens[k - 1]?.kind === 'C') {
      // ...but after a conjunct the short a is usual: satya सत्य, anna अन्न, kshetra क्षेत्र.
      const afterConjunct = tokens[k - 2]?.kind === 'C' || /^(x|ksh|kSh|dny|gny)$/.test(tokens[k - 1].roman);
      if (t.roman === 'a' && !afterConjunct) t.opts = ['aa', 'a'];
      if (t.roman === 'i') t.opts = ['ii', 'i'];
      if (t.roman === 'u') t.opts = ['uu', 'u'];
    }
  });
  return tokens;
}

function render(tokens: Token[], pick: number[]): string {
  let out = '';
  let pending = false; // a consonant still waiting for its vowel
  tokens.forEach((t, k) => {
    const opt = t.opts[pick[k]];
    if (t.kind === 'V') {
      const [letter, sign] = VOWEL[opt as VowelId];
      out += pending ? sign : letter;
      pending = false;
    } else if (t.kind === 'S' && (opt === ANUSVARA || opt === 'ः' || opt === 'ँ')) {
      out += opt; // a waiting consonant keeps its inherent a: कं
      pending = false;
    } else {
      if (pending) out += VIRAMA; // consonant + consonant = conjunct: स्क, त्र
      out += opt;
      pending = true;
    }
  });
  return out; // a final consonant keeps its inherent a (साखर), as Marathi writes it
}

const MAX_ALTERNATIVES = 2; // spellings that differ from the most likely one in at most 2 places

/** Rule-based spellings, most likely first. */
function ruleCandidates(word: string): string[] {
  const tokens = lex(word);
  if (!tokens) return [];
  const ambiguous = tokens.map((t, k) => (t.opts.length > 1 ? k : -1)).filter((k) => k >= 0);
  const base = tokens.map(() => 0);
  const picks: number[][] = [base];
  const vary = (from: number, pick: number[], left: number) => {
    if (left === 0) return;
    for (let a = from; a < ambiguous.length; a++) {
      const pos = ambiguous[a];
      for (let o = 1; o < tokens[pos].opts.length; o++) {
        const next = [...pick];
        next[pos] = o;
        picks.push(next);
        vary(a + 1, next, left - 1);
      }
    }
  };
  vary(0, base, MAX_ALTERNATIVES);
  const cost = (p: number[]) => p.reduce((s, v) => s + (v > 0 ? 1 : 0), 0);
  picks.sort((x, y) => cost(x) - cost(y));
  return unique(picks.slice(0, 200).map((p) => render(tokens, p)));
}

// ── Common words ─────────────────────────────────────────────────────────────────────
// "roman spellings = Devanagari". Spellings are matched loosely (aa/a, ee/i, oo/u, w/v, double letters).
const WORDS = `
sakhar=साखर; tandul=तांदूळ; dudh=दूध; dahi=दही; tup=तूप; tel=तेल; mith=मीठ; pani=पाणी
batata=बटाटा; kanda=कांदा; lasun,lasoon=लसूण; ale=आले; mirchi=मिरची; bhaji=भाजी; tomato=टोमॅटो
gajar=गाजर; kobi=कोबी; palak=पालक; methi=मेथी; kothimbir=कोथिंबीर; kakdi=काकडी; vange=वांगे
bhendi=भेंडी; dodka=दोडका; karle=कारले; bhopla=भोपळा; limbu=लिंबू; amba=आंबा; keli=केळी; kel=केळ
safarchand=सफरचंद; dalimb=डाळिंब; papai,papaya=पपई; peru=पेरू; chiku=चिकू; draksha=द्राक्ष; drakshe=द्राक्षे; naral=नारळ
gahu=गहू; jvari,jowari=ज्वारी; bajri=बाजरी; nachni=नाचणी; rava=रवा; maida=मैदा; besan=बेसन
poha=पोहा; pohe=पोहे; sabudana=साबुदाणा; dal=डाळ; tur=तूर; mug,moong=मूग; masur=मसूर
harbhara=हरभरा; chana=चणा; vatana=वाटाणा; matki=मटकी; shengdana=शेंगदाणा; shengdane=शेंगदाणे
kaju=काजू; badam=बदाम; manuka=मनुका; khobre=खोबरे; gul=गूळ; chaha=चहा; kofi,coffee=कॉफी
biskit,biscuit=बिस्कीट; sabun=साबण; shampu,shampoo=शॅम्पू; agarbatti=अगरबत्ती; kapur=कापूर
masala=मसाला; halad=हळद; jire=जिरे; mohari=मोहरी; ova=ओवा; hing=हिंग; dalchini=दालचिनी
lavang=लवंग; velchi=वेलची; mire=मिरे; tikhat=तिखट; kurmure=कुरमुरे; chivda=चिवडा; farsan=फरसाण
shev=शेव; papad=पापड; lonche=लोणचे; anda,ande=अंडे; andi=अंडी; loni=लोणी; panir,paneer=पनीर
shrikhand=श्रीखंड; amrakhand=आम्रखंड; tak=ताक; bhakri=भाकरी; chapati=चपाती; poli=पोळी
varan=वरण; amti=आमटी; usal=उसळ; misal=मिसळ; vada=वडा; pav=पाव; ladu,laddu=लाडू; chakli=चकली
dhane=धणे; dhanyavad=धन्यवाद; namaskar=नमस्कार; kilo=किलो; gram=ग्रॅम; litar,liter,litre=लिटर
nag=नग; ekun=एकूण; kimmat=किंमत; rokh=रोख; vastu=वस्तू; dukan=दुकान; bajar,bazar=बाजार
grahak=ग्राहक; nav=नाव; shri,shree=श्री; ganesh=गणेश; ram=राम; krushna,krishna=कृष्ण; vitthal=विठ्ठल
pandharpur=पंढरपूर; ani=आणि; dnyan=ज्ञान; vidyarthi=विद्यार्थी; shrimant=श्रीमंत; bharat=भारत; pune=पुणे; mumbai=मुंबई; kolhapur=कोल्हापूर; satara=सातारा; nashik=नाशिक
kirana=किराणा; supar,super=सुपर; mart=मार्ट; ved=वेद; sundar=सुंदर; swachh,svachha=स्वच्छ
pudhe=पुढे; punha=पुन्हा; bhet=भेट; dya=द्या; abhari=आभारी; aahot,ahot=आहोत
taja,taza=ताजा; tazi,taji=ताजी; khas=खास; special=स्पेशल; pack,paik=पॅक; pakit=पाकीट; pishvi=पिशवी
sabudane=साबुदाणे; kokam=कोकम; chinch=चिंच; gulkand=गुलकंद; mangal=मंगल; diva=दिवा
`;

function looseKey(roman: string): string {
  return roman.toLowerCase()
    .replace(/ph/g, 'f').replace(/ksh/g, 'x').replace(/w/g, 'v').replace(/z/g, 'j')
    .replace(/aa/g, 'a').replace(/ee|ii/g, 'i').replace(/oo|uu/g, 'u')
    .replace(/([bcdfghjklmnpqrstvxy])\1/g, '$1'); // chikku = chiku, vitthal = vithal
}

const DICTIONARY = new Map<string, string[]>();
const KNOWN = new Set<string>();
for (const line of WORDS.split(/[;\n]/)) {
  const [romans, word] = line.split('=').map((s) => s?.trim());
  if (!romans || !word) continue;
  KNOWN.add(word);
  for (const r of romans.split(',')) {
    const key = looseKey(r.trim());
    DICTIONARY.set(key, unique([...(DICTIONARY.get(key) ?? []), word]));
  }
}

function unique(list: string[]): string[] {
  return [...new Set(list.filter(Boolean))];
}

export const MAX_SUGGESTIONS = 6;

/**
 * Devanagari spellings for one Roman word, best first. [] when it isn't a word to convert.
 * `learned`: { romanWordLowercase: chosenDevanagari } — what this PC's users picked before.
 */
export function suggest(word: string, learned: Record<string, string> = {}): string[] {
  if (!isConvertible(word)) return [];
  const rules = ruleCandidates(word);
  if (rules.length === 0) return [];
  const known = rules.filter((r) => KNOWN.has(r));
  return unique([
    learned[word.toLowerCase()],
    ...(DICTIONARY.get(looseKey(word)) ?? []),
    ...known,
    ...rules,
  ]).slice(0, MAX_SUGGESTIONS);
}

/** The best spelling for one word, or the word itself when it isn't convertible. */
export function preferred(word: string, learned: Record<string, string> = {}): string {
  return suggest(word, learned)[0] ?? word;
}

/**
 * Converts every Roman word in a text. Spaces, digits, punctuation and Devanagari stay as they are, and so do
 * codes, emails, URLs and amounts ("A12", "x@y.com", "www.a.in", "500g").
 */
export function transliterate(text: string, learned: Record<string, string> = {}): string {
  return text.split(/(\s+)/).map((chunk) => {
    const m = /^([^A-Za-z]*)([A-Za-z.]*[A-Za-z])([^A-Za-z]*)$/.exec(chunk);
    if (!m) return chunk; // spaces, Devanagari, or letters mixed with @ / : _ ...
    const [, lead, word, trail] = m;
    if (/[0-9@_/\\:-]/.test(lead + trail) || !isConvertible(word)) return chunk;
    return lead + preferred(word, learned) + trail;
  }).join('');
}
