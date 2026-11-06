import { Component } from 'react';
import type { ReactNode, ErrorInfo } from 'react';
import { ArrowRight, RefreshCw } from 'lucide-react';
import { Logo } from './ui';
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    /* Credentials and conversation content are deliberately not logged. */
  }
  render() {
    if (this.state.failed)
      return (
        <div className="app-recovery">
          <Logo />
          <h1>Let’s reconnect your workspace.</h1>
          <p>
            Something interrupted this page. Your explicitly saved recaps are still on this device.
          </p>
          <button className="button primary" onClick={() => window.location.reload()}>
            <RefreshCw size={17} />
            Reload this page
          </button>
          <button
            className="button secondary"
            onClick={() => {
              sessionStorage.removeItem('charcha.membership');
              window.location.hash = '/';
              window.location.reload();
            }}
          >
            Return to workspace
            <ArrowRight size={16} />
          </button>
        </div>
      );
    return this.props.children;
  }
}
