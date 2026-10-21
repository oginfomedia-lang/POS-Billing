// The editing steps MarathiInput performs on each key, tested without a browser.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { preferred } from '../../src/utils/marathi/transliterate.ts';
import { commitWord, undoCommit, wordBeforeCaret } from '../../src/utils/marathi/typing.ts';

test('finds the Roman word ending at the caret', () => {
  assert.deepEqual(wordBeforeCaret('mala sakhar', 11), { start: 5, end: 11, word: 'sakhar' });
  assert.deepEqual(wordBeforeCaret('साखर dudh', 9), { start: 5, end: 9, word: 'dudh' });
  assert.deepEqual(wordBeforeCaret('ga.nga', 6), { start: 0, end: 6, word: 'ga.nga' });
  assert.equal(wordBeforeCaret('sakhar', 3), null); // caret in the middle of the word
  assert.equal(wordBeforeCaret('sakhar ', 7), null); // after a space
  assert.equal(wordBeforeCaret('sakhar.', 7), null); // after a full stop
  assert.equal(wordBeforeCaret('', 0), null);
  assert.equal(wordBeforeCaret('साखर', 4), null);
});

test('codes, emails and URLs are never picked up', () => {
  assert.equal(wordBeforeCaret('SKU-ab', 6), null);
  assert.equal(wordBeforeCaret('ab12cd', 6), null);
  assert.equal(wordBeforeCaret('x@shop', 6), null);
  assert.equal(wordBeforeCaret('www.shop', 8), null);
  assert.equal(wordBeforeCaret('http://x', 8), null);
});

test('Space converts the word and adds one space, never two', () => {
  const w = wordBeforeCaret('mala sakhar', 11)!;
  const res = commitWord('mala sakhar', w, 'साखर', true);
  assert.equal(res.value, 'mala साखर ');
  assert.equal(res.caret, 10);

  // A space already after the caret (word typed in the middle of text): just move past it.
  const mid = 'sakhar dudh';
  const w2 = wordBeforeCaret(mid, 6)!;
  const res2 = commitWord(mid, w2, 'साखर', true);
  assert.equal(res2.value, 'साखर dudh');
  assert.equal(res2.caret, 5);
});

test('leaving the box converts without adding a space', () => {
  const w = wordBeforeCaret('dudh', 4)!;
  const res = commitWord('dudh', w, preferred('dudh'), false);
  assert.deepEqual([res.value, res.caret], ['दूध', 3]);
});

test('Backspace straight after a conversion brings the typed letters back', () => {
  const text = 'mala sakhar';
  const done = commitWord(text, wordBeforeCaret(text, 11)!, 'साखर', true);
  const undone = undoCommit(done.value, done.caret, done.commit);
  assert.deepEqual(undone, { value: 'mala sakhar', caret: 11 });

  // In the middle of text, with the space that was already there kept.
  const mid = 'sakhar dudh';
  const done2 = commitWord(mid, wordBeforeCaret(mid, 6)!, 'साखर', true);
  assert.deepEqual(undoCommit(done2.value, done2.caret, done2.commit), { value: 'sakhar dudh', caret: 6 });
});

test('Backspace works normally once anything else changed', () => {
  const done = commitWord('sakhar', wordBeforeCaret('sakhar', 6)!, 'साखर', true);
  assert.equal(undoCommit(done.value + 'x', done.caret + 1, done.commit), null); // typed more
  assert.equal(undoCommit(done.value, done.caret - 1, done.commit), null); // caret moved
  assert.equal(undoCommit('other', 5, done.commit), null);
});

test('full typing sequence: type, Space, type, Space, Backspace', () => {
  let value = 'sakhar';
  let step = commitWord(value, wordBeforeCaret(value, value.length)!, preferred('sakhar'), true);
  value = step.value + 'dudh';
  step = commitWord(value, wordBeforeCaret(value, value.length)!, preferred('dudh'), true);
  assert.equal(step.value, 'साखर दूध ');
  const back = undoCommit(step.value, step.caret, step.commit)!;
  assert.deepEqual(back, { value: 'साखर dudh', caret: 9 });
});

test('separate boxes keep separate state (each conversion carries its own undo record)', () => {
  const a = commitWord('sakhar', wordBeforeCaret('sakhar', 6)!, 'साखर', true);
  const b = commitWord('dudh', wordBeforeCaret('dudh', 4)!, 'दूध', true);
  assert.equal(undoCommit(b.value, b.caret, a.commit), null); // box A's record can't undo box B
  assert.deepEqual(undoCommit(a.value, a.caret, a.commit), { value: 'sakhar', caret: 6 });
});
