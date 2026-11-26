import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({command,mode}) => {
  const env=loadEnv(mode,process.cwd(),'VITE_');
  if(command==='build' && env.VITE_DEMO_MODE!=='true') {
    if(!env.VITE_API_URL) throw new Error('Live builds require an explicit VITE_API_URL.');
    let url: URL;
    try {url=new URL(env.VITE_API_URL);} catch {throw new Error('VITE_API_URL must be a valid API base URL.');}
    const local=['localhost','127.0.0.1','[::1]'].includes(url.hostname);
    if((url.protocol!=='https:' && !(local && url.protocol==='http:')) || url.username || url.password || url.search || url.hash)
      throw new Error('VITE_API_URL must use HTTPS (or local test HTTP) without credentials, query or fragment.');
  }
  return {
    plugins:[react()],
    build:{rollupOptions:{output:{
      // Split heavy third-party libraries from application code so the entry chunk stays small and cacheable.
      manualChunks(id: string) {
        if (!id.includes('node_modules')) return undefined;
        if (/node_modules\/(recharts|d3-[^/]+|victory-vendor|recharts-scale|decimal\.js-light|eventemitter3|fast-equals|lodash)\//.test(id)) return 'vendor-charts';
        if (/node_modules\/(react|react-dom|react-router|react-router-dom|@remix-run|scheduler)\//.test(id)) return 'vendor-react';
        return 'vendor';
      },
    }}},
    resolve:{alias:{'@':path.resolve(__dirname,'./src')}},
    server:{
      port:3000,
      open:false,
      host:'127.0.0.1',
      watch:{ignored:['**/.venv/**','**/.venv-gpu/**','**/storage_uploads/**']},
      // Same-origin /api proxy avoids WSL/Windows localhost mismatches when the
      // browser cannot reach the FastAPI process on :8000 directly.
      proxy:{
        '/api':{
          // scripts/start-all.sh sets this when the backend runs on a non-default port.
          target:process.env.LUMENEIOS_BACKEND_URL || 'http://127.0.0.1:8000',
          changeOrigin:true,
        },
      },
    },
  };
});
