import {SessionRecord} from './sessions';
import {state} from './videos-fixtures';
export function savedSession():SessionRecord{return {schema_version:1,id:'c'.repeat(32),opening:'sicilienne',fen:state.fen,history:[],snapshot:state.snapshot,created_at:'2026-10-29T10:00:00+00:00',updated_at:'2026-10-29T10:00:00+00:00',exchanges:[]};}
