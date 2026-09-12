import React, { useMemo, useState } from 'react';
import { publicApiFetch } from '../auth';

export type LicenseStatus = {
  active: boolean;
  installation_id: string;
  reason: string;
  school_count?: number;
  license?: Record<string, unknown> | null;
};

export async function fetchLicenseStatus(): Promise<LicenseStatus> {
  const r = await publicApiFetch('/license/status');
  if (!r.ok) throw new Error(`License status HTTP ${r.status}`);
  return r.json();
}

export default function ActivationScreen({
  status,
  onActivated,
}: {
  status: LicenseStatus;
  onActivated: () => void;
}) {
  const [packageText, setPackageText] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const reasonText = useMemo(() => {
    const map: Record<string, string> = {
      LICENSE_REQUIRED: 'This installation has not been activated.',
      LICENSE_PUBLIC_KEY_NOT_CONFIGURED: 'License public key is not configured on this server.',
      NOT_ACTIVATED: 'This installation has not been activated.',
      LICENSE_EXPIRED: 'The installed license has expired.',
      LICENSE_INSTALLATION_MISMATCH: 'The license belongs to a different installation.',
      LICENSE_SIGNATURE_INVALID: 'The license signature is invalid.',
      LICENSE_SCHOOL_LIMIT_EXCEEDED: 'The licensed school limit has been exceeded.',
    };
    return map[status.reason] || status.reason;
  }, [status.reason]);

  async function activate() {
    setMessage('');
    setBusy(true);
    try {
      const obj = JSON.parse(packageText);
      if (!obj.license || !obj.signature) throw new Error('Package must contain "license" and "signature".');
      const r = await publicApiFetch('/license/activate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(obj),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `Activation HTTP ${r.status}`);
      setMessage('Activation successful. Starting PM POSHAN…');
      onActivated();
    } catch (e: any) {
      setMessage(e?.message || 'Activation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function copyId() {
    await navigator.clipboard.writeText(status.installation_id);
    setMessage('Installation ID copied.');
  }

  return (
    <div style={{minHeight:'100vh',background:'#f3f6fb',display:'grid',placeItems:'center',padding:24,fontFamily:'system-ui'}}>
      <div style={{width:'min(760px,100%)',background:'#fff',borderRadius:16,boxShadow:'0 10px 35px rgba(0,0,0,.12)',padding:28}}>
        <div style={{fontSize:13,fontWeight:800,color:'#1e3a8a',letterSpacing:'.08em'}}>PM POSHAN • SECURE ACTIVATION</div>
        <h1 style={{margin:'8px 0'}}>Activate this installation</h1>
        <p style={{color:'#475569'}}>सिस्टम वापरण्यापूर्वी अधिकृत परवाना सक्रिय करणे आवश्यक आहे.</p>
        <div style={{background:'#f8fafc',border:'1px solid #e2e8f0',borderRadius:10,padding:16,margin:'18px 0'}}>
          <div style={{fontSize:12,color:'#64748b'}}>Installation ID</div>
          <code style={{display:'block',fontSize:16,wordBreak:'break-all',margin:'6px 0 10px'}}>{status.installation_id}</code>
          <button onClick={copyId}>Copy Installation ID</button>
          <div style={{marginTop:12,fontSize:13,color:'#b45309'}}>{reasonText}</div>
        </div>
        <label style={{fontWeight:700}}>Signed activation package</label>
        <textarea
          value={packageText}
          onChange={e => setPackageText(e.target.value)}
          placeholder='Paste the signed JSON package here'
          rows={10}
          style={{width:'100%',boxSizing:'border-box',marginTop:8,padding:12,fontFamily:'ui-monospace,monospace',border:'1px solid #cbd5e1',borderRadius:8}}
        />
        <button onClick={activate} disabled={busy || !packageText.trim()} style={{marginTop:14,padding:'11px 18px',fontWeight:700}}>
          {busy ? 'Activating…' : 'Activate PM POSHAN'}
        </button>
        {message && <p style={{marginTop:12}}>{message}</p>}
      </div>
    </div>
  );
}
