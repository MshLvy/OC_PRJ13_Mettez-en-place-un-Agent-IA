// @vitest-environment node
import {describe,it,expect,vi,afterEach} from 'vitest';
afterEach(()=>{vi.unstubAllEnvs();vi.resetModules();});
describe('independent execution environments',()=>{
  it('defaults native development to 8002 and strict 5174',async()=>{
    vi.stubEnv('PRJ13_API_TARGET','');vi.resetModules();
    const config=(await import('../vite.config')).default as any;
    expect(config.server.port).toBe(5174);expect(config.server.strictPort).toBe(true);
    expect(config.server.proxy['/api'].target).toBe('http://127.0.0.1:8002');
  });
  it('Docker explicitly proxies to backend service without hiding Origin',async()=>{
    vi.stubEnv('PRJ13_API_TARGET','http://backend:8000');vi.resetModules();
    const config=(await import('../vite.config')).default as any;
    const proxy=config.server.proxy['/api'];expect(proxy.target).toBe('http://backend:8000');
    let listener:any;proxy.configure({on:(_:string,fn:any)=>{listener=fn;}});
    const setHeader=vi.fn();listener({setHeader},{headers:{}});
    expect(setHeader).toHaveBeenCalledWith('Origin','http://127.0.0.1:5173');
    setHeader.mockClear();listener({setHeader},{headers:{origin:'http://evil.example'}});
    expect(setHeader).not.toHaveBeenCalled();
  });
});
