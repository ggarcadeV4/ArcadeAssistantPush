import React from 'react'

export default class LaunchBoxErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[LaunchBoxPanel] Unhandled render error:', error, info)
  }

  handleReload = () => {
    if (typeof window !== 'undefined') {
      window.location.reload()
    }
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    return (
      <div className="lb-error-fallback" role="alert" style={{ padding: 24 }}>
        <h2>LaunchBox panel encountered an error.</h2>
        <p>Please reload the panel to recover.</p>
        <button onClick={this.handleReload} type="button">
          Reload Panel
        </button>
      </div>
    )
  }
}
