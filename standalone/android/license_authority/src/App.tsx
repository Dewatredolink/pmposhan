import { useEffect, useMemo, useState } from 'react';
import { Preferences } from '@capacitor/preferences';
import {
  EXPECTED_PUBLIC_KEY_B64,
  encryptAuthoritySeed,
  issueLicense,
  type EncryptedAuthorityKey,
  type LicenseRequest,
} from './crypto';
import './styles.css';

const KEY_RECORD = 'pmposhan.authority.key.v1';
const HISTORY = 'pmposhan.authority.history.v1';

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function defaultEnd(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  d.setDate(d.getDate() - 1);
  return isoDate(d);
}

function friendlyError(error: unknown): string {
  const code = error instanceof Error ? error.message : String(error);
  const messages: Record<string, string> = {
    PRIVATE_KEY_BASE64_INVALID: 'The signing-key text is not valid Base64. Use only the exact protected PRIVATE_KEY_B64.txt content or load that .txt file locally.',
    PRIVATE_KEY_INVALID_LENGTH: 'The decoded signing key is not a 32-byte Ed25519 seed. Use the protected authority seed file created for PM POSHAN.',
    PRIVATE_KEY_PUBLIC_KEY_MISMATCH: 'This is not the PM POSHAN authority signing key. The derived public key does not match the trusted public key.',
    AUTHORITY_PIN_TOO_SHORT: 'Authority PIN must be at least 8 characters.',
    AUTHORITY_PIN_INVALID: 'Authority PIN is incorrect.',
  };
  return messages[code] || code;
}

async function loadAuthorityKey(): Promise<EncryptedAuthorityKey | null> {
  const { value } = await Preferences.get({ key: KEY_RECORD });
  if (!value) return null;
  return JSON.parse(value) as EncryptedAuthorityKey;
}

export default function App() {
  const [keyRecord, setKeyRecord] = useState<EncryptedAuthorityKey | null>(null);
  const [seedText, setSeedText] = useState('');
  const [importPin, setImportPin] = useState('');
  const [importPin2, setImportPin2] = useState('');
  const [signPin, setSignPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [output, setOutput] = useState('');
  const [form, setForm] = useState<LicenseRequest>({
    installation_id: '',
    organization: '',
    udise: '',
    valid_from: isoDate(new Date()),
    valid_until: defaultEnd(),
    edition: 'STANDALONE',
    max_schools: 1,
    license_id: '',
  });

  useEffect(() => {
    loadAuthorityKey().then(setKeyRecord).catch(e => setMessage(friendlyError(e)));
  }, []);

  const keyStatus = useMemo(() => keyRecord?.public_key_b64 === EXPECTED_PUBLIC_KEY_B64, [keyRecord]);

  async function loadKeyFile(event: React.ChangeEvent<HTMLInputElement>) {
    setMessage('');
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 16384) throw new Error('KEY_FILE_TOO_LARGE');
      const text = await file.text();
      setSeedText(text);
      setMessage('Key text loaded locally from the selected file. It has not been uploaded anywhere.');
    } catch (e) {
      setMessage(e instanceof Error && e.message === 'KEY_FILE_TOO_LARGE' ? 'The selected key file is unexpectedly large.' : friendlyError(e));
    } finally {
      event.target.value = '';
    }
  }

  async function importKey() {
    setMessage('');
    if (importPin !== importPin2) {
      setMessage('PIN values do not match.');
      return;
    }
    setBusy(true);
    try {
      const record = await encryptAuthoritySeed(seedText, importPin);
      await Preferences.set({ key: KEY_RECORD, value: JSON.stringify(record) });
      setKeyRecord(record);
      setSeedText('');
      setImportPin('');
      setImportPin2('');
      setMessage('Signing key imported and encrypted on this Android device. Delete any temporary plaintext copy from the phone after confirming this status.');
    } catch (e) {
      setMessage(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeKey() {
    if (!confirm('Remove the encrypted signing key from this Android authority device?')) return;
    await Preferences.remove({ key: KEY_RECORD });
    setKeyRecord(null);
    setMessage('Signing key removed from this device.');
  }

  async function pasteDeviceRequest() {
    setMessage('');
    try {
      const text = await navigator.clipboard.readText();
      const request = JSON.parse(text);
      setForm(current => ({
        ...current,
        installation_id: String(request.installation_id || current.installation_id),
        udise: String(request.udise || current.udise),
        organization: String(request.organization || current.organization),
      }));
      setMessage('Device request loaded from clipboard.');
    } catch {
      setMessage('Clipboard does not contain valid device request JSON.');
    }
  }

  async function generate() {
    setMessage('');
    setOutput('');
    if (!keyRecord) {
      setMessage('Import the authority signing key first.');
      return;
    }
    setBusy(true);
    try {
      const pkg = await issueLicense(form, keyRecord, signPin);
      const text = JSON.stringify(pkg, null, 2);
      setOutput(text);
      const { value } = await Preferences.get({ key: HISTORY });
      const history = value ? JSON.parse(value) : [];
      history.unshift({
        issued_at: new Date().toISOString(),
        license_id: pkg.license.license_id,
        installation_id: pkg.license.installation_id,
        organization: pkg.license.organization,
        udise: pkg.license.udise,
        valid_until: pkg.license.valid_until,
      });
      await Preferences.set({ key: HISTORY, value: JSON.stringify(history.slice(0, 100)) });
      setSignPin('');
      setMessage(`License created: ${pkg.license.license_id}`);
    } catch (e) {
      setMessage(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  async function copyOutput() {
    if (!output) return;
    await navigator.clipboard.writeText(output);
    setMessage('Signed activation package copied.');
  }

  return <main className="app-shell">
    <section className="card hero">
      <div className="eyebrow">PM POSHAN • LICENSE AUTHORITY</div>
      <h1>Android Device Authorization</h1>
      <p>Generate signed activation packages on a trusted authority phone or tablet. The private key is never bundled in the APK.</p>
      <div className={keyStatus ? 'status ok' : 'status bad'}>
        {keyStatus ? 'Signing key ready' : 'Signing key not imported'}
      </div>
      <div className="mono tiny">Trusted public key: {EXPECTED_PUBLIC_KEY_B64}</div>
    </section>

    {!keyRecord && <section className="card">
      <h2>1. Import Authority Signing Key</h2>
      <div className="warning">Do this only on your trusted authority device. Never send the private key through chat or include it in source code.</div>
      <label>Private Ed25519 seed (Base64, 32 bytes)
        <textarea rows={4} value={seedText} onChange={e => setSeedText(e.target.value)} placeholder="Paste locally from your protected authority key file" />
      </label>
      <label style={{display:'block',marginTop:10}}>Or load protected key text file locally
        <input type="file" accept=".txt,text/plain" onChange={loadKeyFile} />
      </label>
      <div className="grid">
        <label>Authority PIN<input type="password" value={importPin} onChange={e => setImportPin(e.target.value)} placeholder="Minimum 8 characters" /></label>
        <label>Confirm PIN<input type="password" value={importPin2} onChange={e => setImportPin2(e.target.value)} /></label>
      </div>
      <button disabled={busy || !seedText.trim() || !importPin} onClick={importKey}>Encrypt & Store Key</button>
    </section>}

    {keyRecord && <section className="card">
      <div className="title-row"><h2>2. Authorize New PM POSHAN Device</h2><button className="danger secondary" onClick={removeKey}>Remove Key</button></div>
      <button className="secondary" onClick={pasteDeviceRequest}>Paste Device Request JSON</button>
      <div className="grid top-gap">
        <label className="full">Installation ID<input value={form.installation_id} onChange={e => setForm({...form, installation_id:e.target.value})} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" /></label>
        <label>Organization<input value={form.organization} onChange={e => setForm({...form, organization:e.target.value})} /></label>
        <label>UDISE<input value={form.udise} onChange={e => setForm({...form, udise:e.target.value})} /></label>
        <label>Valid From<input type="date" value={form.valid_from} onChange={e => setForm({...form, valid_from:e.target.value})} /></label>
        <label>Valid Until<input type="date" value={form.valid_until} onChange={e => setForm({...form, valid_until:e.target.value})} /></label>
        <label>Edition<select value={form.edition} onChange={e => setForm({...form, edition:e.target.value})}><option value="STANDALONE">STANDALONE</option><option value="SCHOOL">SCHOOL</option></select></label>
        <label>Maximum Schools<input type="number" min={1} value={form.max_schools} onChange={e => setForm({...form, max_schools:Number(e.target.value)})} /></label>
        <label className="full">License ID (optional)<input value={form.license_id || ''} onChange={e => setForm({...form, license_id:e.target.value})} placeholder="Auto-generated if blank" /></label>
        <label className="full">Authority PIN<input type="password" value={signPin} onChange={e => setSignPin(e.target.value)} placeholder="Required for each signing operation" /></label>
      </div>
      <button disabled={busy || !signPin} onClick={generate}>{busy ? 'Signing…' : 'Generate Signed Activation Package'}</button>
      <textarea className="output" rows={12} value={output} readOnly placeholder="Signed activation package appears here" />
      <button className="secondary" disabled={!output} onClick={copyOutput}>Copy Package</button>
    </section>}

    {message && <div className="message">{message}</div>}
  </main>;
}
