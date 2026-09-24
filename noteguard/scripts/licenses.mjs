import {readFile,writeFile} from 'node:fs/promises';
const lock=JSON.parse(await readFile('package-lock.json','utf8'));
const entries=Object.entries(lock.packages).filter(([name])=>name).map(([path,p])=>`${path.replace(/^node_modules\//,'')} | ${p.version} | ${p.license||'SEE PACKAGE LICENSE'}${p.optional?' | optional platform dependency':''}`);
await writeFile('ATTRIBUTION.txt',[
'NIGHTINGALE NOTEGUARD - ATTRIBUTION',
'Synthetic clinical data and demonstration scripts were authored for this project.',
'No external clinical dataset, trained model, model weights, remote AI, font service or image service is used.',
'Research articles inform design only; citations are in docs/research.md. No paper content is bundled as clinical data.',
'JavaScript dependency versions/licenses below are from the committed package lock, including optional platform dependencies.',
'Upstream license notices remain in installed packages. Do not treat this file as a replacement for their full terms.',
'',...entries,'',
'Document-generation / validation tooling (not shipped in the browser bundle):',
'ReportLab | BSD-3-Clause | PDF document generation',
'Pillow | HPND | synthetic scanned-page raster generation',
'pypdf | BSD-3-Clause | PDF page/text verification',
'pypdfium2 | Apache-2.0/BSD-3-Clause wrapper; PDFium BSD-style third-party notices | PDF rendering QA',
'Playwright bundled FFmpeg | LGPL-2.1-or-later build and upstream notices | demonstration video encoding',
'Node.js | MIT and bundled third-party notices | runtime/build/test tooling',
'Microsoft Edge / Chromium | vendor terms and Chromium third-party notices | local browser verification only',
'',
'Models: none. Public clinical datasets: none. External UI assets: none.',
'System fonts: Segoe UI / Arial / Georgia supplied by the host OS; font files are not redistributed.',
].join('\n'));
