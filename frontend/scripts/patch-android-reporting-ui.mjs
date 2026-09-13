import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');

function read(rel) {
  const file = path.join(root, rel);
  if (!fs.existsSync(file)) throw new Error(`${rel}: file not found`);
  return {file, source: fs.readFileSync(file, 'utf8')};
}

function writeIfChanged(file, before, after, rel) {
  if (after !== before) {
    fs.writeFileSync(file, after, 'utf8');
    console.log(`PATCHED ${rel}`);
  } else {
    console.log(`OK      ${rel}`);
  }
}

// App.tsx: keep Registers & Reports separate from Rations & Requirements and
// stamp an unmistakable build marker. This patch is intentionally tolerant of
// whitespace/line-ending differences and safe to run repeatedly.
{
  const rel = 'src/App.tsx';
  const {file, source: before} = read(rel);
  let source = before;

  const separateAlready = /page==='reports'\)\s*body=<Reports\b/.test(source) && /page==='workbookRegisters'\)\s*\n?\s*body=<WorkbookRegisters\b/.test(source);
  if (!separateAlready) {
    const combined = /else if\(page==='reports'\s*\|\|\s*page==='workbookRegisters'\)\s*\r?\n?\s*body=<WorkbookRegisters\s+lang=\{lang\}\s+schools=\{schools\}\s+schoolId=\{schoolId\}\s+setSchoolId=\{setSchoolId\}\s*\/>;/m;
    if (!combined.test(source)) {
      throw new Error(`${rel}: could not locate combined reports/workbook route`);
    }
    source = source.replace(
      combined,
      "else if(page==='reports')body=<Reports lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='workbookRegisters')\n  body=<WorkbookRegisters\n    lang={lang}\n    schools={schools}\n    schoolId={schoolId}\n    setSchoolId={setSchoolId}\n/>;",
    );
  }

  if (!source.includes('Build A5-REPORTS-20260913-1840')) {
    if (source.includes('PM POSHAN v1.0 &nbsp;|&nbsp; Build 2026.09')) {
      source = source.replace('PM POSHAN v1.0 &nbsp;|&nbsp; Build 2026.09', 'PM POSHAN v1.0 &nbsp;|&nbsp; Build A5-REPORTS-20260913-1840');
    } else {
      source = source.replace(/PM POSHAN v1\.0 &nbsp;\|&nbsp; Build [^<]+/, 'PM POSHAN v1.0 &nbsp;|&nbsp; Build A5-REPORTS-20260913-1840');
    }
  }

  if (!/page==='reports'\)\s*body=<Reports\b/.test(source)) throw new Error(`${rel}: reports route verification failed`);
  if (!/page==='workbookRegisters'\)\s*\r?\n?\s*body=<WorkbookRegisters\b/.test(source)) throw new Error(`${rel}: workbook route verification failed`);
  if (!source.includes('Build A5-REPORTS-20260913-1840')) throw new Error(`${rel}: build marker verification failed`);

  writeIfChanged(file, before, source, rel);
}

function ensureImportAndButton(rel, importNeedle, importLine, buttonNeedle, buttonReplacement, importVerify, buttonVerify) {
  const {file, source: before} = read(rel);
  let source = before;

  if (!source.includes(importVerify)) {
    if (!source.includes(importNeedle)) throw new Error(`${rel}: import anchor not found`);
    source = source.replace(importNeedle, `${importNeedle}\n${importLine}`);
  }

  if (!source.includes(buttonVerify)) {
    if (!source.includes(buttonNeedle)) throw new Error(`${rel}: button anchor not found`);
    source = source.replace(buttonNeedle, buttonReplacement);
  }

  if (!source.includes(importVerify)) throw new Error(`${rel}: native print import verification failed`);
  if (!source.includes(buttonVerify)) throw new Error(`${rel}: native print button verification failed`);
  writeIfChanged(file, before, source, rel);
}

ensureImportAndButton(
  'src/pages/CustomReports.tsx',
  "import type { Lang } from '../i18n/translations';",
  "import { printCurrentView } from '../mobile/nativePrint';",
  '<button onClick={download}>⬇ Excel</button></div>',
  "<button onClick={download}>⬇ Excel</button><button onClick={()=>void printCurrentView(mr?'PM POSHAN - सानुकूल अहवाल':'PM POSHAN - Custom Report')}>{mr?'प्रिंट / PDF':'Print / PDF'}</button></div>",
  "from '../mobile/nativePrint'",
  "PM POSHAN - Custom Report",
);

ensureImportAndButton(
  'src/pages/WorkbookRegisters.tsx',
  "import { Lang } from '../i18n/translations';",
  "import { printCurrentView } from '../mobile/nativePrint';",
  '{msg&&<p>{msg}</p>}\n    </section>',
  "<div className=\"action-row\"><button className=\"primary standalone\" onClick={()=>void printCurrentView(lang==='mr'?'PM POSHAN - नोंदवही व अहवाल':'PM POSHAN - Registers & Reports')}>{lang==='mr'?'प्रिंट / PDF':'Print / PDF'}</button></div>\n      {msg&&<p>{msg}</p>}\n    </section>",
  "from '../mobile/nativePrint'",
  'PM POSHAN - Registers & Reports',
);

console.log('ANDROID_REPORTING_UI_PATCH_OK');
