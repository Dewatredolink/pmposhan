import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const file = path.resolve(here, '..', 'src', 'mobile', 'androidReportingRuntime.ts');

if (!fs.existsSync(file)) {
  console.log('ANDROID_REPORTING_TYPES_PATCH_SKIPPED');
  process.exit(0);
}

let source = fs.readFileSync(file, 'utf8');
const from = 'const selected=requested.length?requested:allowed;';
const to = 'const selected:string[]=requested.length?requested:allowed;';

if (source.includes(from)) {
  source = source.split(from).join(to);
  fs.writeFileSync(file, source, 'utf8');
  console.log('PATCHED androidReportingRuntime.ts');
} else if (source.includes(to)) {
  console.log('OK      androidReportingRuntime.ts');
} else {
  throw new Error('androidReportingRuntime.ts: expected selected-columns block not found');
}

const verify = fs.readFileSync(file, 'utf8');
const count = (verify.match(/const selected:string\[\]=requested\.length\?requested:allowed;/g) || []).length;
if (count < 2) {
  throw new Error(`androidReportingRuntime.ts: expected 2 typed selected-column declarations, found ${count}`);
}

console.log('ANDROID_REPORTING_TYPES_PATCH_OK');
