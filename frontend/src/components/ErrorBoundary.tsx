import React from "react";

type State = { hasError: boolean; info?: string };

export default class ErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError() { return { hasError: true }; }

  componentDidCatch(err: unknown) {
    try {
      this.setState({ info: String((err as any)?.message || err) });
      // Optional: post to gateway/backend to log in A:\\logs\\frontend_errors.jsonl
      fetch("/api/frontend/log", {
        method: "POST",
        headers: { "content-type": "application/json", "x-panel": "global" },
        body: JSON.stringify({ type: "error", message: String((err as any)?.message || err), stack: (err as any)?.stack || null, url: window.location.href })
      }).catch(() => {});
    } catch {}
  }

  render() {
    if (this.state.hasError) {
      return (
        <div role="alert" style={{
          position: 'fixed', top: 16, left: 16, zIndex: 1000,
          padding: '12px 14px', border: '1px solid #b91c1c', borderRadius: 6,
          background: 'rgba(185,28,28,0.15)', color: '#fecaca', maxWidth: 360
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Panel error</div>
          <div style={{ fontSize: 12, opacity: 0.9, marginBottom: 8 }}>Something went wrong rendering this view.</div>
          {this.state.info && (
            <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 8 }}>
              <div>Error:</div>
              <code style={{ whiteSpace: 'pre-wrap' }}>{this.state.info}</code>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => this.setState({ hasError: false })}>Try Again</button>
            <a className="btn" href="/" style={{ background: 'transparent', border: '1px solid #fecaca', color: '#fecaca' }}>Go Home</a>
          </div>
        </div>
      );
    }
    return this.props.children as React.ReactElement;
  }
}
