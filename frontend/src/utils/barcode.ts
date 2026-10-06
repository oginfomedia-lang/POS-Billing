// EAN-13 / EAN-8 bar patterns for printing labels (no external library).
// A pattern is a string of modules: '1' = bar, '0' = space. EAN-13 is 95 modules, EAN-8 is 67.

const L = ['0001101', '0011001', '0010011', '0111101', '0100011', '0110001', '0101111', '0111011', '0110111', '0001011'];
const G = ['0100111', '0110011', '0011011', '0100001', '0011101', '0111001', '0000101', '0010001', '0001001', '0010111'];
const R = ['1110010', '1100110', '1101100', '1000010', '1011100', '1001110', '1010000', '1000100', '1001000', '1110100'];
// Which of the left-hand digits use the G set, chosen by the first (implicit) digit of an EAN-13.
const PARITY = ['LLLLLL', 'LLGLGG', 'LLGGLG', 'LLGGGL', 'LGLLGG', 'LGGLLG', 'LGGGLL', 'LGLGLG', 'LGLGGL', 'LGGLGL'];

/** GS1 check digit for the given digits (without the check digit). */
export function eanCheckDigit(body: string): number {
  let sum = 0;
  for (let i = 0; i < body.length; i++) {
    // Weights 3,1,3,1… counted from the rightmost digit.
    const weight = (body.length - i) % 2 === 1 ? 3 : 1;
    sum += Number(body[i]) * weight;
  }
  return (10 - (sum % 10)) % 10;
}

function isValidEan(code: string, length: number): boolean {
  return code.length === length && /^\d+$/.test(code) && eanCheckDigit(code.slice(0, -1)) === Number(code[length - 1]);
}

export type PrintableFormat = 'EAN-13' | 'EAN-8';

export interface BarPattern {
  format: PrintableFormat;
  modules: string;
}

/** Returns the bar pattern, or null if the code isn't a valid EAN-13 / EAN-8 (wrong length or check digit). */
export function encodeBarcode(code: string): BarPattern | null {
  if (isValidEan(code, 13)) {
    const digits = code.split('').map(Number);
    const parity = PARITY[digits[0]];
    let left = '';
    for (let i = 0; i < 6; i++) left += (parity[i] === 'L' ? L : G)[digits[i + 1]];
    let right = '';
    for (let i = 7; i < 13; i++) right += R[digits[i]];
    return { format: 'EAN-13', modules: `101${left}01010${right}101` };
  }
  if (isValidEan(code, 8)) {
    const digits = code.split('').map(Number);
    const left = digits.slice(0, 4).map((d) => L[d]).join('');
    const right = digits.slice(4).map((d) => R[d]).join('');
    return { format: 'EAN-8', modules: `101${left}01010${right}101` };
  }
  return null;
}
