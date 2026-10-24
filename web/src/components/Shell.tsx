import { NavLink, Outlet, Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  AudioLines,
  History,
  Settings2,
  ArrowUpRight,
  ChevronDown,
  Headphones,
  Languages,
  PanelLeftClose,
  Gauge,
  Coins,
  Wrench,
  Server,
} from 'lucide-react';
import { Logo, Avatar, Badge } from './ui';
import { useApp } from '../state/AppContext';
import { languageName } from '../types/domain';
import { useState } from 'react';
export function Shell() {
  const { preferences, health, healthLoading } = useApp();
  const [menu, setMenu] = useState(false);
  const location = useLocation();
  return (
    <div className={`app-shell ${preferences.highContrast ? 'high-contrast' : ''}`}>
      <aside className={`sidebar ${menu ? 'sidebar-open' : ''}`}>
        <Link to="/" className="brand-link" onClick={() => setMenu(false)}>
          <Logo />
        </Link>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav aria-label="Main navigation">
          {[
            { to: '/', name: 'Overview', icon: LayoutDashboard },
            { to: '/voices', name: 'Voice studio', icon: AudioLines },
            { to: '/history', name: 'Conversations', icon: History },
            { to: '/performance', name: 'Performance', icon: Gauge },
            { to: '/usage', name: 'Usage & limits', icon: Coins },
            { to: '/development', name: 'Developer journal', icon: Wrench },
            { to: '/deployment', name: 'Deployment setup', icon: Server },
            { to: '/settings', name: 'Settings', icon: Settings2 },
          ].map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={() => setMenu(false)}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              <item.icon size={19} />
              {item.name}
              {item.to === '/' && <span className="nav-dot" />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-language">
            <span className="tiny-icon">
              <Languages size={17} />
            </span>
            <div>
              <small>YOUR LISTENING LANGUAGE</small>
              <strong>{languageName(preferences.language)}</strong>
            </div>
            <Link aria-label="Change language" to="/settings">
              <ChevronDown size={15} />
            </Link>
          </div>
          <div className="sidebar-note">
            <span className="status-dot" />
            <span>
              {healthLoading
                ? 'Checking workspace'
                : health?.mode === 'live'
                  ? 'Connected workspace'
                  : health
                    ? 'Demonstration workspace'
                    : 'Setup required'}
            </span>
          </div>
          <a
            className="sidebar-help"
            href="https://docs.gnani.ai/"
            target="_blank"
            rel="noreferrer"
          >
            Built with Indian language AI
            <ArrowUpRight size={13} />
          </a>
        </div>
      </aside>
      <div className="shell-content">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMenu(!menu)}
            >
              <PanelLeftClose size={20} />
            </button>
            <span>Workspace</span>
            <span className="crumb-slash">/</span>
            <strong>
              {location.pathname === '/voices'
                ? 'Voice studio'
                : location.pathname === '/settings'
                  ? 'Settings'
                  : location.pathname === '/performance'
                    ? 'Performance'
                    : location.pathname === '/usage'
                      ? 'Usage & limits'
                      : location.pathname === '/development'
                        ? 'Developer journal'
                        : location.pathname === '/deployment'
                          ? 'Deployment setup'
                          : location.pathname === '/history'
                            ? 'Conversations'
                            : location.pathname.startsWith('/join')
                              ? 'Ready to join'
                              : location.pathname.startsWith('/recap')
                                ? 'Conversation recap'
                                : 'Overview'}
            </strong>
          </div>
          <div className="topbar-right">
            <Badge tone={health?.mode === 'live' ? 'green' : 'orange'}>
              <span className="status-dot" />
              {health?.mode === 'live'
                ? 'Live services'
                : healthLoading
                  ? 'Connecting'
                  : 'Demo workspace'}
            </Badge>
            <Link to="/settings" className="profile-button" aria-label="Open profile settings">
              <Avatar name={preferences.name || 'You'} index={2} />
              <ChevronDown size={14} />
            </Link>
          </div>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>
            <Headphones size={13} />
            Made for conversations that matter.
          </span>
          <span>Hindi · Tamil · Bengali · English</span>
        </footer>
      </div>
    </div>
  );
}
