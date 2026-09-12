import React from 'react';

type Props = {
  children: React.ReactNode;
};

type State = {
  error: Error | null;
};

export default class AppErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('PM POSHAN page render failed', error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div style={{padding:16,fontFamily:'system-ui',background:'#eef5fa',minHeight:'100vh'}}>
        <div style={{maxWidth:680,margin:'24px auto',background:'#fff',border:'1px solid #d8e6ef',borderRadius:14,padding:20}}>
          <h2 style={{marginTop:0,color:'#0e3764'}}>This page could not open / हे पृष्ठ उघडू शकले नाही</h2>
          <p style={{color:'#475569'}}>
            The Android version is still being ported module-by-module. The app has recovered instead of showing a blank screen.
          </p>
          <pre style={{whiteSpace:'pre-wrap',wordBreak:'break-word',background:'#f8fafc',padding:12,borderRadius:8,fontSize:12}}>
            {this.state.error.message}
          </pre>
          <button
            onClick={() => { this.setState({error:null}); window.location.reload(); }}
            style={{marginTop:12,padding:'10px 16px',border:0,borderRadius:8,background:'#126fd1',color:'#fff',fontWeight:700}}
          >
            Return to PM POSHAN / परत जा
          </button>
        </div>
      </div>
    );
  }
}
