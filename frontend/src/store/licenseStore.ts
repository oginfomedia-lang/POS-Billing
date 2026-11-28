// The shop licence's plan, saved by LicenseGuard, so menus show only what the plan includes.
// The server enforces the plan on every request; this only keeps locked pages out of sight.
import { create } from 'zustand';
import type { LicenseStatus } from '../services/api/licenseApi';

interface LicenseState {
  status: LicenseStatus | null;
  setStatus: (status: LicenseStatus) => void;
}

export const useLicenseStore = create<LicenseState>((set) => ({
  status: null,
  setStatus: (status) => set({ status }),
}));

/** Returns a check: is `feature` in this shop's plan? No feature, no licence needed (development) or a
 * server from before plans (no feature list) = yes. */
export function useHasFeature(): (feature?: string) => boolean {
  const status = useLicenseStore((s) => s.status);
  return (feature) => !feature || !status || status.required === false || status.features === undefined
    || status.features.includes(feature);
}
