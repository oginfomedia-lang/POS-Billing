// Always-focused input that receives scanner keystrokes, with product suggestions while typing a name.
// USB scanners type the code and press Enter, so a plain input handles both scanning and typing.
// Suggestions only appear for text with a letter in it (names, SKUs): scanned barcodes are digits,
// so scanning behaves exactly as before.
import { type KeyboardEvent, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listProducts } from '../../services/api/productApi';
import type { ProductOut } from '../../types/product';
import { formatRupees } from '../../utils/money';
import { IconScan, IconX } from '../common/Icons';

const MIN_CHARS = 2;
const DEBOUNCE_MS = 250;
const MAX_RESULTS = 8;

interface Props {
  onScan: (code: string) => void;
  /** A product picked from the suggestions (typed name / SKU). */
  onPick: (product: ProductOut) => void;
  /** Refocuses the input whenever it becomes true (e.g. after a dialog closes). */
  active: boolean;
  /** Store being billed, so suggestions show that branch's price and products. */
  storeId?: number | null;
}

/** Search by name/SKU only when the text isn't a plain number (a barcode being scanned or typed). */
function isSearchText(text: string): boolean {
  return text.length >= MIN_CHARS && /\D/.test(text);
}

export function BarcodeInput({ onScan, onPick, active, storeId }: Props) {
  const { t } = useTranslation();
  const [value, setValue] = useState('');
  const [results, setResults] = useState<ProductOut[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [searching, setSearching] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const requestId = useRef(0); // ignore answers to older searches

  useEffect(() => {
    if (active) ref.current?.focus();
  }, [active]);

  async function search(text: string): Promise<ProductOut[]> {
    const id = ++requestId.current;
    setSearching(true);
    try {
      const page = await listProducts({
        q: text,
        active_only: true,
        per_page: MAX_RESULTS,
        store_id: storeId ?? undefined,
      });
      if (id !== requestId.current) return [];
      setResults(page.items);
      setHighlight(0);
      setOpen(true);
      return page.items;
    } catch {
      if (id === requestId.current) setResults([]);
      return [];
    } finally {
      if (id === requestId.current) setSearching(false);
    }
  }

  // Search a moment after the cashier stops typing.
  useEffect(() => {
    const text = value.trim();
    if (!isSearchText(text)) {
      requestId.current++;
      setResults([]);
      setOpen(false);
      setSearching(false);
      return;
    }
    const timer = window.setTimeout(() => search(text), DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [value, storeId]);

  function reset() {
    requestId.current++;
    setValue('');
    setResults([]);
    setOpen(false);
    setSearching(false);
    ref.current?.focus();
  }

  function pick(product: ProductOut) {
    reset();
    onPick(product);
  }

  async function handleEnter() {
    const text = value.trim();
    if (!text) return;
    if (open && results.length > 0) {
      pick(results[Math.min(highlight, results.length - 1)]);
      return;
    }
    if (!isSearchText(text)) {
      reset();
      onScan(text); // barcode
      return;
    }
    // Enter pressed before the suggestions arrived: search now; one match = add it straight away.
    const found = await search(text);
    if (found.length === 1) pick(found[0]);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleEnter();
    } else if (e.key === 'ArrowDown' && open && results.length > 0) {
      e.preventDefault();
      setHighlight((h) => (h + 1) % results.length);
    } else if (e.key === 'ArrowUp' && open && results.length > 0) {
      e.preventDefault();
      setHighlight((h) => (h - 1 + results.length) % results.length);
    } else if (e.key === 'Escape' && (open || value)) {
      // Close the list / clear the text only — don't let Escape reach the "void bill" shortcut.
      e.preventDefault();
      e.stopPropagation();
      if (open) setOpen(false);
      else reset();
    }
  }

  const showNoResults = open && !searching && results.length === 0 && isSearchText(value.trim());

  return (
    <div className="barcode-input-wrapper">
      <div className="barcode-scanner-icon" title={t('pos.scannerActive')}>
        <IconScan size={22} />
      </div>
      <input
        ref={ref}
        className="field-input barcode-input"
        placeholder={t('pos.scanPlaceholder')}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => setOpen(false)}
        onFocus={() => results.length > 0 && isSearchText(value.trim()) && setOpen(true)}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        aria-controls="product-suggestions"
        autoComplete="off"
        autoFocus
      />
      {value ? (
        <button type="button" className="barcode-clear-btn" onClick={reset} title={t('pos.clear')}>
          <IconX size={16} />
        </button>
      ) : (
        <span className="scanner-badge">
          <span className="scanner-dot" />
          {t('pos.ready')}
        </span>
      )}

      {(open && results.length > 0) || showNoResults ? (
        <ul className="product-suggestions" id="product-suggestions" role="listbox">
          {showNoResults && <li className="suggestion-empty">{t('pos.noProductsFound', { text: value.trim() })}</li>}
          {results.map((p, i) => {
            const barcode = p.barcodes.find((b) => b.is_primary)?.barcode ?? p.barcodes[0]?.barcode;
            return (
              <li
                key={p.id}
                role="option"
                aria-selected={i === highlight}
                className={`suggestion-item${i === highlight ? ' active' : ''}`}
                // mousedown (not click) so the input doesn't lose focus and close the list first
                onMouseDown={(e) => { e.preventDefault(); pick(p); }}
                onMouseEnter={() => setHighlight(i)}
              >
                <span className="suggestion-name">
                  {p.name}
                  <span className="suggestion-meta">
                    {p.sku}{barcode ? ` · ${barcode}` : ''}{p.is_variable_weight ? ` · ${t('pos.perKg')}` : ''}
                  </span>
                </span>
                <span className="suggestion-price">{formatRupees(p.store_price ?? p.price)}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
