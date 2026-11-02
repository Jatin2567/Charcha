import { StrictMode, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './state/AppContext';
import { Shell } from './components/Shell';
import { ErrorBoundary } from './components/ErrorBoundary';
import { installLinkPrefetch, pages, preloadAllWhenIdle } from './routes';
import { RouteFallback } from './components/RouteFallback';
import './styles.css';
import './theme.css';
const P = {
  home: pages['/'],
  join: pages['/join'],
  voices: pages['/voices'],
  settings: pages['/settings'],
  performance: pages['/performance'],
  tests: pages['/tests'],
  audio: pages['/audio-lab'],
  usage: pages['/usage'],
  development: pages['/development'],
  deployment: pages['/deployment'],
  history: pages['/history'],
  recap: pages['/recap'],
  room: pages['/room'],
};
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <HashRouter>
        <AppProvider>
          <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route element={<Shell />}>
              <Route index element={<P.home />} />
              <Route path="join/:code" element={<P.join />} />
              <Route path="voices" element={<P.voices />} />
              <Route path="settings" element={<P.settings />} />
              <Route path="performance" element={<P.performance />} />
              <Route path="tests" element={<P.tests />} />
              <Route path="audio-lab" element={<P.audio />} />
              <Route path="usage" element={<P.usage />} />
              <Route path="development" element={<P.development />} />
              <Route path="deployment" element={<P.deployment />} />
              <Route path="history" element={<P.history />} />
              <Route path="recap/:id" element={<P.recap />} />
            </Route>
            <Route path="room/:code" element={<P.room />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </AppProvider>
      </HashRouter>
    </ErrorBoundary>
  </StrictMode>,
);
installLinkPrefetch();
preloadAllWhenIdle();
