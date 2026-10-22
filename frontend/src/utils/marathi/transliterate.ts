// Phonetic Marathi typing: Roman letters -> Devanagari, like a phone's Marathi keyboard.
//
//   transliterate('sakhar dudh')    -> 'साखर दूध'
//   suggest('sakhar')               -> ['साखर', 'सखर', 'साखार', ...]   (best first)
//
// Layers, best first:
//   1. choices this PC's users picked before (passed in as `learned`)
//   2. a built-in list of common shop words: Marathi (WORDS) and English / brands (ENGLISH_WORDS)
//   3. rules: longest match first ("kh" before "k"), inherent "a", vowel signs, ् for conjuncts,
//      ं ः ँ, and alternatives for ambiguous letters (a: अ/आ, d: ड/द, t: त/ट, n: न/ण/ं, l: ल/ळ, ...)
//   4. English pronunciation (englishSpellings): c = क / स, silent final e, double letters, cat = कॅट,
//      shop = शॉप, butter = बटर. First for words that look English (kitkat, colgate, soap), else offered too.
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
  ['T', ['ट']], ['D', ['ड']], ['N', ['ण']], ['t', ['त', 'ट']], ['d', ['ड', 'द']], ['n', ['न', 'ण']],
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

/** keepCase: the word is an internal spelling (englishSpellings) whose capitals are meant (E ॲ, T ट). */
function lex(word: string, keepCase = false): Token[] | null {
  const w = keepCase ? word : normaliseCase(word);
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
function ruleCandidates(word: string, keepCase = false): string[] {
  const tokens = lex(word, keepCase);
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
dev=देव; desh=देश; don=दोन; daha=दहा; divas=दिवस; dar=दर; darvaja,darwaja=दरवाजा; dagad=दगड; dukh,duhkh=दुःख
mandir=मंदिर; udya=उद्या; dabba,daba=डबा; doke=डोके; dosa=डोसा; gadi=गाडी; sadi=साडी; vadi=वडी
dhan=धन; dhobi=धोबी; dhol=ढोल; dhaba=ढाबा; dhag=ढग; kadhi=कढी; padva,padwa=पाडवा
`;

// English shop words and brands, as Marathi shops write them.
const ENGLISH_WORDS = `
kitkat=किटकॅट; apple=ॲपल; omlet,omelette=ऑम्लेट; cell=सेल; phone=फोन; cellphone=सेलफोन; mobile=मोबाइल
charger=चार्जर; battery=बॅटरी; bulb=बल्ब; chocolate=चॉकलेट; cadbury=कॅडबरी; maggi=मॅगी; colgate=कोलगेट
pepsi=पेप्सी; coca=कोका; cola=कोला; cocacola=कोकाकोला; sprite=स्प्राइट; fanta=फँटा; thumsup=थम्सअप
bread=ब्रेड; butter=बटर; cheese=चीज; cake=केक; soap=सोप; oil=ऑइल; rice=राइस; toothpaste=टूथपेस्ट
toothbrush=टूथब्रश; brush=ब्रश; paste=पेस्ट; powder=पावडर; cream=क्रीम; lotion=लोशन; conditioner=कंडिशनर
detergent=डिटर्जंट; surf=सर्फ; tide=टाइड; rin=रिन; vim=विम; harpic=हार्पिक; lizol=लायझॉल; dettol=डेटॉल
lifebuoy=लाइफबॉय; lux=लक्स; dove=डव्ह; parle=पार्ले; britannia=ब्रिटानिया; goodday=गुडडे; marie=मारी
oreo=ओरिओ; bourbon=बोरबॉन; lays=लेज; kurkure=कुरकुरे; haldiram=हल्दीराम; amul=अमूल; gokul=गोकुळ
nestle=नेस्ले; tata=टाटा; tea=टी; sugar=शुगर; salt=सॉल्ट; milk=मिल्क; water=वॉटर; bottle=बॉटल; juice=ज्यूस
jam=जॅम; sauce=सॉस; ketchup=केचप; noodles=नूडल्स; pasta=पास्ता; pizza=पिझ्झा; burger=बर्गर; sandwich=सँडविच
icecream=आइस्क्रीम; ice=आइस; candy=कँडी; toffee=टॉफी; chips=चिप्स; cookie,cookies=कुकीज; egg=एग; eggs=एग्ज
banana=बनाना; mango=मँगो; orange=ऑरेंज; grapes=ग्रेप्स; lemon=लेमन; potato=पोटॅटो; onion=अनियन; carrot=कॅरट
cabbage=कॅबेज; ginger=जिंजर; garlic=गार्लिक; corn=कॉर्न; oats=ओट्स; cornflakes=कॉर्नफ्लेक्स; honey=हनी
packet=पॅकेट; box=बॉक्स; bag=बॅग; carrybag=कॅरीबॅग; plastic=प्लास्टिक; paper=पेपर; pen=पेन; pencil=पेन्सिल
notebook=नोटबुक; book=बुक; copy=कॉपी; eraser=इरेजर; scale=स्केल; glue=ग्लू; tape=टेप; cable=केबल; wire=वायर
switch=स्विच; plug=प्लग; fan=फॅन; light=लाइट; tube=ट्यूब; earphone=इअरफोन; headphone=हेडफोन; sim=सिम
card=कार्ड; recharge=रिचार्ज; cover=कव्हर; glass=ग्लास; cup=कप; plate=प्लेट; spoon=स्पून; bucket=बकेट
tissue=टिश्यू; napkin=नॅपकिन; diaper=डायपर; pampers=पॅम्पर्स; whisper=व्हिस्पर; razor=रेझर; blade=ब्लेड
gillette=जिलेट; perfume=परफ्यूम; deo=डिओ; deodorant=डिओडरंट; hair=हेअर; face=फेस; wash=वॉश; facewash=फेसवॉश
handwash=हँडवॉश; body=बॉडी; baby=बेबी; kids=किड्स; family=फॅमिली; offer=ऑफर; free=फ्री; combo=कॉम्बो
discount=डिस्काउंट; total=टोटल; cash=कॅश; bill=बिल; change=चेंज; thanks=थँक्स; welcome=वेलकम; shop=शॉप
store=स्टोअर; mall=मॉल; market=मार्केट; fresh=फ्रेश; best=बेस्ट; new=न्यू; big=बिग; small=स्मॉल; large=लार्ज
medium=मीडियम; extra=एक्स्ट्रा; premium=प्रीमियम; gold=गोल्ड; silver=सिल्व्हर; classic=क्लासिक; original=ओरिजिनल
cat=कॅट; mat=मॅट; bat=बॅट; hat=हॅट; doll=डॉल; ball=बॉल; toy=टॉय; game=गेम; gift=गिफ्ट; party=पार्टी
birthday=बर्थडे; candle=कँडल; matchbox=मॅचबॉक्स; lighter=लायटर; mosquito=मॉस्किटो; coil=कॉइल
goodnight=गुडनाइट; allout=ऑलआउट; munch=मंच; perk=पर्क; fivestar=फाइव्हस्टार; boost=बूस्ट; bournvita=बोर्नव्हिटा
horlicks=हॉर्लिक्स; complan=कॉम्प्लान; maaza=माझा; frooti=फ्रूटी; slice=स्लाइस; bisleri=बिसलेरी; dairy=डेअरी
show=शो; cow=काउ; now=नाउ; how=हाउ; window=विंडो; yellow=यलो; pillow=पिलो; oil=ऑइल; tiffin=टिफिन
`;

/** Spellings only English words use; Marathi typed in Roman letters doesn't (it writes च as ch, not c). */
const ENGLISH_HINT = /c(?!h)|ck|q|ea|oa|oy|tion|ow$|[^aeiou]y$|[^aeiou]{2}er$|(?:bb|pp|tt|gg|ff)(?:le|er|y)$|[bpt]le$|(?:ile|ake|ike|ime|ite|ope|ute|ube)$/;

/**
 * How an English word is said, spelt in this file's Roman scheme (capitals = ॅ ऑ ट ड ...), 1–3 versions
 * (a word-final "ow" can be ो, ौ or ाउ). kitkat -> kiTkET, apple -> Epal, phone -> fon, butter -> baTar.
 */
function englishSpellings(word: string): string[] {
  let w = word.toLowerCase()
    .replace(/tion|sion/g, 'sh@n').replace(/ture$/, 'ch@r')
    .replace(/ck/g, 'k+').replace(/ph/g, 'f') // ck closes the vowel like a double letter: jacket जॅकेट.replace(/qu/g, 'kv').replace(/q/g, 'k').replace(/x/g, 'ks')
    .replace(/wh/g, 'v').replace(/c(?=[eiy])/g, 's').replace(/c(?!h)/g, 'k').replace(/g(?=e$)/, 'j')
    .replace(/([bdfgklmnprstvz])\1/g, '$1+') // a doubled letter closes the vowel before it: butter = but+er
    .replace(/([^aeiouy@+])le$|([^aeiouy@])\+le$/, (_m, a, b) => `${a ?? `${b}+`}@l`) // apple -> ap+@l
    .replace(/er$/, '@r');
  const ow = /ow$/.test(w);
  if (ow) w = w.slice(0, -2) + '#';
  const parts = w.match(/[aeiouy@#]+|[^aeiouy@#]+/g) ?? [];
  let out = '';
  for (let k = 0; k < parts.length; k++) {
    let p = parts[k];
    if (!/^[aeiouy@#]/.test(p)) { out += englishConsonants(p); continue; }
    if (k === 0 && p.length > 1 && p[0] === 'y') { out += 'y'; p = p.slice(1); } // yoga
    const next = parts[k + 1];
    const last = k === parts.length - 1;
    // "magic e": one consonant (or st), then a final e: cake केक, rice राइस, phone फोन, paste पेस्ट
    const magic = next !== undefined && parts[k + 2] === 'e' && k + 2 === parts.length - 1
      && /^(?:[^aeiouy+]|st)$/.test(next);
    const closed = !magic && next !== undefined && (next.includes('+') || next.replace('+', '').length > 1
      || k + 1 === parts.length - 1);
    out += englishVowel(p, { last, closed, magic, beforeR: next?.startsWith('r') ?? false });
    if (magic) { out += englishConsonants(next); k += 2; }
  }
  return ow ? ['o', 'au', 'aau'].map((v) => out.replace('#', v)) : [out];
}

function englishConsonants(p: string): string {
  return p.replace(/\+/g, '').replace(/th|sh|ch|kh|gh|dh|bh|t|d|w/g, (c) => ({ t: 'T', d: 'D', w: 'v' } as Record<string, string>)[c] ?? c);
}

function englishVowel(p: string, at: { last: boolean; closed: boolean; magic: boolean; beforeR: boolean }): string {
  const pairs: Record<string, string> = { ee: 'I', ea: 'I', ie: 'I', oo: 'U', oa: 'o', oe: 'o', ai: 'e', ay: 'e', ei: 'e',
    ey: at.last ? 'I' : 'e', oi: 'Oi', oy: 'Oy', ou: 'au', au: 'O', '@': 'a', '#': '#' };
  if (pairs[p]) return pairs[p];
  const v = p[0];
  if (at.magic) return ({ a: 'e', e: 'I', i: 'aai', o: 'o', u: 'yU', y: 'aai' } as Record<string, string>)[v] ?? v;
  if (v === 'a') return at.beforeR ? 'aa' : at.closed ? 'E' : at.last ? 'aa' : 'a'; // car कार, cat कॅट, pizza पिझ्झा
  if (v === 'e') return at.last ? '' : 'e'; // a final e is silent: large लार्ज
  if (v === 'i') return at.last ? 'I' : 'i';
  if (v === 'o') return at.closed && !at.beforeR ? 'O' : 'o'; // shop शॉप, omlet ऑम्लेट
  if (v === 'u') return at.closed ? 'a' : at.last ? 'U' : 'u'; // butter बटर, bulb बल्ब
  if (v === 'y') return at.last ? 'I' : 'i'; // candy कँडी, gym जिम
  return p;
}

/** Each English version's best spelling, then their next best (dhow: धो धौ धाउ, then ढो ढौ ढाउ). */
function englishCandidates(word: string): string[] {
  const lists = englishSpellings(word).map((s) => ruleCandidates(s, true));
  return unique([...lists.map((l) => l[0] ?? ''), ...lists.map((l) => l[1] ?? '')]);
}

function looseKey(roman: string): string {
  return roman.toLowerCase()
    .replace(/ph/g, 'f').replace(/ksh/g, 'x').replace(/w/g, 'v').replace(/z/g, 'j')
    .replace(/aa/g, 'a').replace(/ee|ii/g, 'i').replace(/oo|uu/g, 'u')
    .replace(/([bcdfghjklmnpqrstvxy])\1/g, '$1'); // chikku = chiku, vitthal = vithal
}

const DICTIONARY = new Map<string, string[]>();
const KNOWN = new Set<string>();
for (const line of `${WORDS}\n${ENGLISH_WORDS}`.split(/[;\n]/)) {
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
  const english = englishCandidates(word);
  const listed = DICTIONARY.get(looseKey(word)) ?? [];
  // Looks English (colgate, jacket): its English reading leads. A listed Marathi word keeps its Marathi
  // alternatives and gets the English reading last. Otherwise the English reading is the second choice (sat: सत, सॅट).
  const ordered = ENGLISH_HINT.test(word.toLowerCase())
    ? [...english, ...rules]
    : listed.length ? [...rules, ...english] : [rules[0], ...english, ...rules.slice(1)];
  return unique([
    learned[word.toLowerCase()],
    ...listed,
    ...known,
    ...ordered,
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
