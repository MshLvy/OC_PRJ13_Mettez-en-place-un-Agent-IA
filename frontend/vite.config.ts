import {defineConfig} from 'vitest/config';
// Docker explicitly overrides the target; native development is independent.
const target = process.env.PRJ13_API_TARGET || 'http://127.0.0.1:8002';
export default defineConfig({cacheDir:process.env.PRJ13_CACHE_DIR||'node_modules/.vite',server:{host:'127.0.0.1',port:5174,strictPort:true,
  proxy:{'/api':{target,configure(proxy){proxy.on('proxyReq',(out,req)=>{
    // GET fetches may omit Origin. Preserve any supplied Origin/Forwarded headers
    // so the backend can reject forged/external requests.
    if (!req.headers.origin) out.setHeader('Origin','http://127.0.0.1:5173');
  });}}}},test:{environment:'jsdom',include:['src/**/*.spec.ts'],maxWorkers:1}});
