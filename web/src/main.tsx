import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './state/AppContext';
import { Shell } from './components/Shell';
import { Home } from './pages/Home';
import { Prejoin } from './pages/Prejoin';
import { Meeting } from './pages/Meeting';
import { Settings } from './pages/Settings';
import { Performance } from './pages/Performance';
import { Usage } from './pages/Usage';
import { DeveloperJournal } from './pages/DeveloperJournal';
import { Deployment } from './pages/Deployment';
import { TestLab } from './pages/TestLab';
import { AudioLab } from './pages/AudioLab';
import { VoiceStudio } from './pages/VoiceStudio';
import { RecapPage, HistoryPage } from './pages/Recap';
import { ErrorBoundary } from './components/ErrorBoundary';
import './styles.css';
import './theme.css';
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <HashRouter>
        <AppProvider>
          <Routes>
            <Route element={<Shell />}>
              <Route index element={<Home />} />
              <Route path="join/:code" element={<Prejoin />} />
              <Route path="voices" element={<VoiceStudio />} />
              <Route path="settings" element={<Settings />} />
              <Route path="performance" element={<Performance />} />
              <Route path="tests" element={<TestLab />} />
              <Route path="audio-lab" element={<AudioLab />} />
              <Route path="usage" element={<Usage />} />
              <Route path="development" element={<DeveloperJournal />} />
              <Route path="deployment" element={<Deployment />} />
              <Route path="history" element={<HistoryPage />} />
              <Route path="recap/:id" element={<RecapPage />} />
            </Route>
            <Route path="room/:code" element={<Meeting />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppProvider>
      </HashRouter>
    </ErrorBoundary>
  </StrictMode>,
);
