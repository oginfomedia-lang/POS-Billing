// Status bar notice: a new LiteRetail version has been downloaded. It installs when the app is closed,
// or now with the button (not in the middle of a bill: the cashier chooses when).
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

export function UpdateNotice() {
  const { t } = useTranslation();
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    const bridge = window.posBridge;
    if (!bridge?.onUpdateReady) return; // browser preview: no Electron
    bridge.getUpdateReady().then((info) => info && setVersion(info.version)).catch(() => undefined);
    return bridge.onUpdateReady((info) => setVersion(info.version));
  }, []);

  if (!version) return null;
  return (
    <span className="update-notice no-print" role="status">
      {t('update.ready', { version })}
      <button type="button" className="update-notice-btn" onClick={() => window.posBridge.installUpdate()}>
        {t('update.restartNow')}
      </button>
    </span>
  );
}
