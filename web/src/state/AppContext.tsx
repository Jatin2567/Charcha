import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { Health, Membership, Preferences, Recap, VoiceProfile } from '../types/domain';
import { useAccount } from '../components/AccountGate';
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
  largeCaptions: false,
  micEnabled: false,
  highContrast: false,
};
function read<T>(store: Storage, key: string, fallback: T): T {
  try {
    const value = store.getItem(key);
    const legacy = value === null && key.startsWith('charcha.') ? store.getItem(key.replace(/^charcha\./, 'artha.')) : null;
    return JSON.parse(value ?? legacy ?? 'null') ?? fallback;
  } catch {
    return fallback;
  }
}
export function AppProvider({ children }: { children: ReactNode }) {
  const account = useAccount();
  const key = (name: string) => {
    const ephemeral = name === 'charcha.membership' || name === 'charcha.voice-profile';
    const scope = ephemeral ? account?.session_scope : account?.scope;
    return scope ? name + '.' + scope : name;
  };
  const [health, setHealth] = useState<Health | null>(null);
  const [serviceError, setServiceError] = useState('');
  const [healthLoading, setHealthLoading] = useState(true);
  const [preferences, setPrefs] = useState<Preferences>(() => ({
    ...defaults,
    ...read(localStorage, key('charcha.preferences'), {}),
  }));
  const [membership, setMember] = useState<Membership | null>(() =>
    read(sessionStorage, key('charcha.membership'), null),
  );
  const [recaps, setRecaps] = useState<Recap[]>(() => read(localStorage, key('charcha.saved-recaps'), []));
  const [latestRecap, setLatestRecap] = useState<Recap | null>(null);
  const [voiceProfile, setProfile] = useState<VoiceProfile | null>(() => {
    const saved = read<{ participant_id: string; profile: VoiceProfile } | null>(
      sessionStorage,
      key('charcha.voice-profile'),
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
      localStorage.setItem(key('charcha.preferences'), JSON.stringify(next));
      return next;
    });
  const setMembership = (value: Membership | null) => {
    if (!value || value.participant.id !== membership?.participant.id) {
      setProfile(null);
      sessionStorage.removeItem(key('charcha.voice-profile'));
    }
    setMember(value);
    if (value) sessionStorage.setItem(key('charcha.membership'), JSON.stringify(value));
    else sessionStorage.removeItem(key('charcha.membership'));
  };
  const setVoiceProfile = (profile: VoiceProfile | null) => {
    setProfile(profile);
    if (profile && membership) {
      // Safe management metadata only. Audio and embeddings never enter browser storage.
      sessionStorage.setItem(
        key('charcha.voice-profile'),
        JSON.stringify({
          participant_id: membership.participant.id,
          profile,
        }),
      );
    } else sessionStorage.removeItem(key('charcha.voice-profile'));
  };
  const saveRecap = (value: Recap) =>
    setRecaps((current) => {
      const next = [value, ...current.filter((x) => x.id !== value.id)].slice(0, 50);
      localStorage.setItem(key('charcha.saved-recaps'), JSON.stringify(next));
      return next;
    });
  const deleteRecap = (id: string) =>
    setRecaps((current) => {
      const next = current.filter((x) => x.id !== id);
      localStorage.setItem(key('charcha.saved-recaps'), JSON.stringify(next));
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
