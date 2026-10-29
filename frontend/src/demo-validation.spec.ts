import {readFileSync} from 'node:fs';
import {describe,it,expect} from 'vitest';
import {validateAnalysis} from './analysis';
const fixture=JSON.parse(readFileSync('tests/fixtures/analysis-synthetic.json','utf8')).data;
describe('Sources moteur strictes par mode démo',()=>{
 it.each(['simulation','live'])('refuse le score de l’autre mode : %s',mode=>{const d=structuredClone(fixture);if(mode==='live')d.tools.explorer.result.source_mode='live';else d.tools.engine.result.source_mode='synthetic_fixture';const policy={explorer:mode==='live'?'live' as const:'synthetic_fixture' as const,engine:true,engineSource:mode==='live'?'local_engine' as const:'synthetic_fixture' as const};expect(validateAnalysis(d,d.fen_normalized,policy)).toBe(d);d.tools.engine.result.source_mode=mode==='live'?'synthetic_fixture':'local_engine';expect(()=>validateAnalysis(d,d.fen_normalized,policy)).toThrow('Provenance moteur incohérente');});
});
