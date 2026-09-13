import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');

function patchFile(rel, patches) {
  const file = path.join(root, rel);
  if (!fs.existsSync(file)) throw new Error(`${rel}: file not found`);
  let source = fs.readFileSync(file, 'utf8');
  let changed = false;
  for (const p of patches) {
    if (source.includes(p.to)) continue;
    if (!source.includes(p.from)) throw new Error(`${rel}: expected source block not found for ${p.name}`);
    source = source.replace(p.from, p.to);
    changed = true;
  }
  if (changed) fs.writeFileSync(file, source, 'utf8');
  console.log(`${changed ? 'PATCHED' : 'OK     '} ${rel}`);
}

patchFile('src/App.tsx', [
  {
    name: 'separate reports route',
    from: "else if(page==='reports' || page==='workbookRegisters')\n  body=<WorkbookRegisters\n    lang={lang}\n    schools={schools}\n    schoolId={schoolId}\n    setSchoolId={setSchoolId}\n/>;",
    to: "else if(page==='reports')body=<Reports lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='workbookRegisters')\n  body=<WorkbookRegisters\n    lang={lang}\n    schools={schools}\n    schoolId={schoolId}\n    setSchoolId={setSchoolId}\n/>;",
  },
  {
    name: 'android report build marker',
    from: 'PM POSHAN v1.0 &nbsp;|&nbsp; Build 2026.09',
    to: 'PM POSHAN v1.0 &nbsp;|&nbsp; Build A5-REPORTS-20260913-1840',
  },
]);

patchFile('src/pages/CustomReports.tsx', [
  {
    name: 'native print import',
    from: "import type { Lang } from '../i18n/translations';",
    to: "import type { Lang } from '../i18n/translations';\nimport { printCurrentView } from '../mobile/nativePrint';",
  },
  {
    name: 'custom report print button',
    from: "<button onClick={download}>⬇ Excel</button></div>",
    to: "<button onClick={download}>⬇ Excel</button><button onClick={()=>void printCurrentView(mr?'PM POSHAN - सानुकूल अहवाल':'PM POSHAN - Custom Report')}>{mr?'प्रिंट / PDF':'Print / PDF'}</button></div>",
  },
]);

patchFile('src/pages/WorkbookRegisters.tsx', [
  {
    name: 'native print import',
    from: "import { Lang } from '../i18n/translations';",
    to: "import { Lang } from '../i18n/translations';\nimport { printCurrentView } from '../mobile/nativePrint';",
  },
  {
    name: 'workbook print action',
    from: "{msg&&<p>{msg}</p>}\n    </section>",
    to: "<div className=\"action-row\"><button className=\"primary standalone\" onClick={()=>void printCurrentView(lang==='mr'?'PM POSHAN - नोंदवही व अहवाल':'PM POSHAN - Registers & Reports')}>{lang==='mr'?'प्रिंट / PDF':'Print / PDF'}</button></div>\n      {msg&&<p>{msg}</p>}\n    </section>",
  },
]);

console.log('ANDROID_REPORTING_UI_PATCH_OK');
