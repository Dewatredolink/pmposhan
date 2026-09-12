from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

PRIVATE_KEY_FILE = Path(os.environ.get(
    "PMPOSHAN_LICENSE_PRIVATE_KEY_FILE",
    r"C:\PMPoshan-License-Authority\PRIVATE_KEY_B64.txt",
))
OUTPUT_DIR = Path(os.environ.get(
    "PMPOSHAN_LICENSE_OUTPUT_DIR",
    r"C:\PMPoshan-License-Authority\issued",
))

app = FastAPI(title="PM POSHAN License Authority", version="1.0")


class IssueRequest(BaseModel):
    installation_id: str
    organization: str
    udise: str
    valid_from: str
    valid_until: str
    edition: str = "STANDALONE"
    max_schools: int = 1
    license_id: str | None = None


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_private_key() -> Ed25519PrivateKey:
    if not PRIVATE_KEY_FILE.exists():
        raise RuntimeError(f"PRIVATE_KEY_FILE_NOT_FOUND: {PRIVATE_KEY_FILE}")
    raw = base64.b64decode(PRIVATE_KEY_FILE.read_text(encoding="utf-8").strip(), validate=True)
    if len(raw) != 32:
        raise RuntimeError("PRIVATE_KEY_INVALID_LENGTH")
    return Ed25519PrivateKey.from_private_bytes(raw)


def next_license_id() -> str:
    return f"PM-STANDALONE-{date.today().year}-{uuid.uuid4().hex[:8].upper()}"


def validate_request(body: IssueRequest) -> None:
    try:
        uuid.UUID(body.installation_id)
    except Exception as exc:
        raise ValueError("INSTALLATION_ID_INVALID") from exc
    try:
        start = date.fromisoformat(body.valid_from)
        end = date.fromisoformat(body.valid_until)
    except Exception as exc:
        raise ValueError("LICENSE_DATE_INVALID") from exc
    if end < start:
        raise ValueError("LICENSE_DATE_RANGE_INVALID")
    if not body.organization.strip() or not body.udise.strip():
        raise ValueError("ORGANIZATION_AND_UDISE_REQUIRED")
    if body.max_schools < 1:
        raise ValueError("MAX_SCHOOLS_INVALID")


@app.post("/api/issue")
def issue_license(body: IssueRequest) -> dict[str, Any]:
    try:
        validate_request(body)
        private_key = load_private_key()
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    license_id = (body.license_id or "").strip() or next_license_id()
    payload = {
        "product": "PM_POSHAN",
        "license_id": license_id,
        "organization": body.organization.strip(),
        "installation_id": body.installation_id.strip(),
        "edition": body.edition.strip().upper() or "STANDALONE",
        "udise": body.udise.strip(),
        "valid_from": body.valid_from,
        "valid_until": body.valid_until,
        "max_schools": int(body.max_schools),
    }
    signature = private_key.sign(canonical(payload))
    package = {
        "license": payload,
        "signature": base64.b64encode(signature).decode("ascii"),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(ch for ch in license_id if ch.isalnum() or ch in "-_")
    output = OUTPUT_DIR / f"{safe_id}.license.json"
    output.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUTPUT_DIR / "issued.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "issued_at": date.today().isoformat(),
            "license_id": license_id,
            "installation_id": body.installation_id,
            "organization": body.organization,
            "udise": body.udise,
            "valid_until": body.valid_until,
            "file": str(output),
        }, ensure_ascii=False) + "\n")

    return {"ok": True, "saved_to": str(output), "package": package}


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "ok": True,
        "private_key_present": PRIVATE_KEY_FILE.exists(),
        "private_key_path": str(PRIVATE_KEY_FILE),
        "output_dir": str(OUTPUT_DIR),
    }


HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PM POSHAN License Authority</title>
<style>
body{font-family:Segoe UI,system-ui,sans-serif;margin:0;background:#eef3f9;color:#16355c}.wrap{max-width:980px;margin:36px auto;padding:0 18px}.card{background:white;border-radius:16px;padding:24px;box-shadow:0 10px 30px #16355c18;margin-bottom:18px}h1{margin:0 0 6px}.sub{color:#5a6d83;margin:0 0 20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{font-weight:600;font-size:13px}input,select,textarea{width:100%;box-sizing:border-box;margin-top:6px;padding:10px;border:1px solid #bfd0e4;border-radius:8px;font:inherit}textarea{min-height:220px;font-family:Consolas,monospace}button{background:#0e4d92;color:#fff;border:0;border-radius:8px;padding:11px 17px;font-weight:700;cursor:pointer}button.secondary{background:#60758d}.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}.ok{color:#137333}.bad{color:#b3261e}.full{grid-column:1/-1}.note{background:#fff6dc;border-left:4px solid #d69c00;padding:12px;border-radius:6px}.mono{font-family:Consolas,monospace;word-break:break-all}@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<div class="card"><h1>PM POSHAN License Authority</h1><p class="sub">Authorize standalone devices without exposing the private signing key to school installations.</p><div id="status">Checking signing key…</div></div>
<div class="card"><h2>Authorize New Device</h2><div class="note">Paste the Installation ID copied from the school device. This dashboard should run only on the license-authority computer.</div>
<div class="grid" style="margin-top:16px">
<label class="full">Installation ID<input id="installation_id" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"></label>
<label>Organization<input id="organization" value="Z.P. School Gaymukhpada"></label>
<label>UDISE<input id="udise" value="27360803502"></label>
<label>Valid From<input id="valid_from" type="date"></label>
<label>Valid Until<input id="valid_until" type="date"></label>
<label>Edition<select id="edition"><option>STANDALONE</option><option>SCHOOL</option></select></label>
<label>Maximum Schools<input id="max_schools" type="number" min="1" value="1"></label>
<label class="full">License ID (optional)<input id="license_id" placeholder="Auto-generated if blank"></label>
</div><div class="row"><button onclick="issue()">Generate Signed Activation Package</button><button class="secondary" onclick="pasteRequest()">Paste Device Request JSON</button></div>
<p id="message"></p><textarea id="output" placeholder="Signed activation package appears here"></textarea><div class="row"><button onclick="copyOutput()">Copy Package</button></div></div>
<div class="card"><h2>Admin Accounts</h2><p>After the device is activated, log in as SYSTEM_ADMIN and open <b>Settings → System Administration → User Accounts</b>. Create Headmaster, Teacher, or additional System Admin accounts there. Passwords are never embedded in device licenses.</p></div>
</div><script>
const today=new Date();const fmt=d=>d.toISOString().slice(0,10);document.getElementById('valid_from').value=fmt(today);const end=new Date(today);end.setFullYear(end.getFullYear()+1);end.setDate(end.getDate()-1);document.getElementById('valid_until').value=fmt(end);
fetch('/api/status').then(r=>r.json()).then(s=>{document.getElementById('status').innerHTML=s.private_key_present?`<span class="ok">Signing key ready</span><div class="mono">${s.private_key_path}</div>`:`<span class="bad">Private signing key not found</span><div class="mono">${s.private_key_path}</div>`});
async function issue(){const ids=['installation_id','organization','udise','valid_from','valid_until','edition','max_schools','license_id'];const data={};ids.forEach(id=>data[id]=document.getElementById(id).value);data.max_schools=Number(data.max_schools);if(!data.license_id)delete data.license_id;const r=await fetch('/api/issue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const b=await r.json();if(!r.ok){document.getElementById('message').innerHTML=`<span class="bad">${b.detail||'Failed'}</span>`;return}document.getElementById('output').value=JSON.stringify(b.package,null,2);document.getElementById('message').innerHTML=`<span class="ok">License created: ${b.saved_to}</span>`}
async function copyOutput(){await navigator.clipboard.writeText(document.getElementById('output').value);document.getElementById('message').innerHTML='<span class="ok">Activation package copied</span>'}
async function pasteRequest(){try{const text=await navigator.clipboard.readText();const j=JSON.parse(text);if(j.installation_id)document.getElementById('installation_id').value=j.installation_id;if(j.udise)document.getElementById('udise').value=j.udise;document.getElementById('message').innerHTML='<span class="ok">Device request loaded</span>'}catch(e){document.getElementById('message').innerHTML='<span class="bad">Clipboard does not contain valid device request JSON</span>'}}
</script></body></html>'''


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return HTML


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8775, log_level="warning")
