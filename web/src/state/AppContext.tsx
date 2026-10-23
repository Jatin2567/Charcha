import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { Health, Membership, Preferences, Recap, VoiceProfile } from '../types/domain';
import { checkHealth } from '../services/api';
interface AppContextValue {
  health: Health | null;
  serviceError: string;
  healthLoading: boolean;
  refreshHealth: () => Promise<void>;
  preferences: Preferences;
  setPreferences: (patch: Partial<Preferences>) => void;
  membership: Membership | null;
  setMembership: (value: Membership | null) => void;
  recaps: Recap[];
  saveRecap: (value: Recap) => void;
  deleteRecap: (id: string) => void;
  latestRecap: Recap | null;
  setLatestRecap: (r: Recap | null) => void;
  voiceProfile: VoiceProfile | null;
  setVoiceProfile: (p: VoiceProfile | null) => void;
}
const AppContext = createContext<AppContextValue | null>(null);
const defaults: Preferences = {
  name: '',
  language: 'en',
  inputDevice: 'default',
  outputDevice: 'default',
  autoCaptions: true,
  micEnabled: false,
  highContrast: false,
};
function read<T>(store: Storage, key: string, fallback: T): T {
  try {
    return JSON.parse(store.getItem(key) || 'null') ?? fallback;
  } catch {
    return fallback;
  }
}
export function AppProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [serviceError, setServiceError] = useState('');
  const [healthLoading, setHealthLoading] = useState(true);
  const [preferences, setPrefs] = useState<Preferences>(() => ({
    ...defaults,
    ...read(localStorage, 'artha.preferences', {}),
  }));
  const [membership, setMember] = useState<Membership | null>(() =>
    read(sessionStorage, 'artha.membership', null),
  );
  const [recaps, setRecaps] = useState<Recap[]>(() => read(localStorage, 'artha.saved-recaps', []));
  const [latestRecap, setLatestRecap] = useState<Recap | null>(null);
  const [voiceProfile, setProfile] = useState<VoiceProfile | null>(() => {
    const saved = read<{ participant_id: string; profile: VoiceProfile } | null>(
      sessionStorage,
      'artha.voice-profile',
      null,
    );
    return saved?.participant_id === membership?.participant.id ? (saved?.profile ?? null) : null;
  });
  const refreshHealth = async () => {
    setHealthLoading(true);
    try {
      setHealth(await checkHealth());
      setServiceError('');
    } catch (e) {
      setServiceError((e as Error).message);
      setHealth(null);
    } finally {
      setHealthLoading(false);
    }
  };
  useEffect(() => {
    void refreshHealth();
  }, []);
  const setPreferences = (patch: Partial<Preferences>) =>
    setPrefs((current) => {
      const next = { ...current, ...patch };
      localStorage.setItem('artha.preferences', JSON.stringify(next));
      return next;
    });
  const setMembership = (value: Membership | null) => {
    if (!value || value.participant.id !== membership?.participant.id) {
      setProfile(null);
      sessionStorage.removeItem('artha.voice-profile');
    }
    setMember(value);
    if (value) sessionStorage.setItem('artha.membership', JSON.stringify(value));
    else sessionStorage.removeItem('artha.membership');
  };
  const setVoiceProfile = (profile: VoiceProfile | null) => {
    setProfile(profile);
    if (profile && membership) {
      // Safe management metadata only. Audio and embeddings never enter browser storage.
      sessionStorage.setItem(
        'artha.voice-profile',
        JSON.stringify({
          participant_id: membership.participant.id,
          profile,
        }),
      );
    } else sessionStorage.removeItem('artha.voice-profile');
  };
  const saveRecap = (value: Recap) =>
    setRecaps((current) => {
      const next = [value, ...current.filter((x) => x.id !== value.id)].slice(0, 50);
      localStorage.setItem('artha.saved-recaps', JSON.stringify(next));
      return next;
    });
  const deleteRecap = (id: string) =>
    setRecaps((current) => {
      const next = current.filter((x) => x.id !== id);
      localStorage.setItem('artha.saved-recaps', JSON.stringify(next));
      return next;
    });
  return (
    <AppContext.Provider
      value={{
        health,
        serviceError,
        healthLoading,
        refreshHealth,
        preferences,
        setPreferences,
        membership,
        setMembership,
        recaps,
        saveRecap,
        deleteRecap,
        latestRecap,
        setLatestRecap,
        voiceProfile,
        setVoiceProfile,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error('App provider missing');
  return value;
}
