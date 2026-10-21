// Run: npm test   (Node's built-in test runner; no extra packages)
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isConvertible, MAX_SUGGESTIONS, preferred, suggest, transliterate } from '../../src/utils/marathi/transliterate.ts';

test('common grocery words come out as written in Marathi', () => {
  const words: Record<string, string> = {
    sakhar: 'साखर', tandul: 'तांदूळ', dudh: 'दूध', batata: 'बटाटा', pani: 'पाणी', namaskar: 'नमस्कार',
    bhaji: 'भाजी', mirchi: 'मिरची', tomato: 'टोमॅटो', kanda: 'कांदा', tel: 'तेल', gahu: 'गहू', halad: 'हळद',
    limbu: 'लिंबू', shengdane: 'शेंगदाणे', kothimbir: 'कोथिंबीर', ani: 'आणि',
  };
  for (const [roman, marathi] of Object.entries(words)) assert.equal(preferred(roman), marathi, roman);
});

test('loose spellings of the same word', () => {
  assert.equal(preferred('saakhar'), 'साखर');
  assert.equal(preferred('doodh'), 'दूध');
  assert.equal(preferred('paanee'), 'पाणी');
  assert.equal(preferred('chikku'), 'चिकू');
  assert.equal(preferred('Sakhar'), 'साखर'); // sentence case
});

test('rules: inherent a, conjuncts, final consonant without halant', () => {
  const words: Record<string, string> = {
    kamal: 'कमल', ghar: 'घर', prem: 'प्रेम', pustak: 'पुस्तक', chhatri: 'छत्री', satya: 'सत्य', anna: 'अन्न',
    kshetra: 'क्षेत्र', sundar: 'सुंदर', bhakt: 'भक्त', umbar: 'उंबर', ilaj: 'इलज',
  };
  for (const [roman, marathi] of Object.entries(words)) assert.equal(preferred(roman), marathi, roman);
});

test('vowel signs (matras) and independent vowels', () => {
  const words: Record<string, string> = {
    kaa: 'का', kee: 'की', koo: 'कू', ke: 'के', kai: 'कै', ko: 'को', kau: 'कौ', kRu: 'कृ', kE: 'कॅ', kO: 'कॉ',
    a: 'अ', aa: 'आ', i: 'इ', ee: 'ई', u: 'उ', oo: 'ऊ', e: 'ए', ai: 'ऐ', o: 'ओ', au: 'औ',
  };
  for (const [roman, marathi] of Object.entries(words)) assert.equal(preferred(roman), marathi, roman);
  // A word-final i / u after a consonant is long by default; the short one is offered too.
  assert.deepEqual(suggest('ki').slice(0, 2), ['की', 'कि']);
  assert.deepEqual(suggest('ku').slice(0, 2), ['कू', 'कु']);
});

test('aspirated consonants', () => {
  const words: Record<string, string> = {
    kham: 'खम', gham: 'घम', cham: 'चम', chham: 'छम', jham: 'झम', pham: 'फम', bham: 'भम', tham: 'थम', dham: 'धम',
  };
  for (const [roman, marathi] of Object.entries(words)) assert.equal(preferred(roman), marathi, roman);
  assert.ok(suggest('dhol').includes('ढोल')); // retroflex offered as an alternative
});

test('retroflex and other Marathi sounds: capitals pick them', () => {
  const words: Record<string, string> = {
    baTaTa: 'बटाटा', DabA: 'डबा', Dabba: 'दब्ब' /* sentence case = lowercase */, gaNit: 'गणित', kaLas: 'कळस', Thak: 'थक', ThaThar: 'ठठर',
    kShatriy: 'क्षत्रिय', dnyaan: 'ज्ञान', shrI: 'श्री', traa: 'त्रा', viShay: 'विषय',
  };
  for (const [roman, marathi] of Object.entries(words)) assert.equal(preferred(roman), marathi, roman);
  // "Thak" is sentence case, so it reads as "thak" (थ); inside a word "Th" is ठ.
  assert.ok(suggest('lal').includes('लळ')); // ळ offered for l
  assert.ok(suggest('pani').includes('पनी'));
});

test('anusvara, chandrabindu and visarga', () => {
  assert.equal(preferred('ga.nga'), 'गंगा');
  assert.equal(preferred('gaMgA'), 'गंगा');
  assert.equal(preferred('duHkh'), 'दुःख');
  assert.equal(preferred('cha.Nd'), 'चँद');
  assert.equal(preferred('anna'), 'अन्न'); // n before n stays a consonant
  assert.ok(suggest('kanda').includes('कन्दा')); // the conjunct spelling is offered too
});

test('spaces, punctuation and numbers are kept; mixed text', () => {
  assert.equal(transliterate('2 kilo sakhar, 1 litre dudh.'), '2 किलो साखर, 1 लिटर दूध.');
  assert.equal(transliterate('साखर dudh'), 'साखर दूध');
  assert.equal(transliterate('  ghar  (prem)!  '), '  घर  (प्रेम)!  ');
  assert.equal(transliterate(''), '');
});

test('codes, emails, URLs, amounts and ALL-CAPS words are not converted', () => {
  for (const text of ['A12', 'abc@x.com', 'www.shop.in', '500g', 'SKU-0012', 'a/b', 'KG', 'MRP', 'http://x.in'])
    assert.equal(transliterate(text), text, text);
  assert.equal(isConvertible('KG'), false);
  assert.equal(isConvertible('sakhar'), true);
  assert.equal(isConvertible('sakhar1'), false);
  assert.equal(isConvertible('साखर'), false);
});

test('empty and unusual input gives no suggestions', () => {
  for (const word of ['', '123', 'sa-k', 'ñ', '...', ' ', 'साखर']) assert.deepEqual(suggest(word), [], JSON.stringify(word));
  assert.equal(preferred('123'), '123');
});

test('suggestions: best first, alternatives, no duplicates, limited', () => {
  const list = suggest('sakhar');
  assert.equal(list[0], 'साखर');
  assert.ok(list.includes('सखर'));
  assert.equal(new Set(list).size, list.length);
  assert.ok(list.length <= MAX_SUGGESTIONS);
  // A spelling picked before on this PC comes first.
  assert.equal(suggest('sakhar', { sakhar: 'सखर' })[0], 'सखर');
  assert.equal(preferred('Sakhar', { sakhar: 'सखर' }), 'सखर');
});
