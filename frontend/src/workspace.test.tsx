// @vitest-environment jsdom
import {describe,it,expect,vi} from 'vitest';
import {renderHook,act} from '@testing-library/react';
import {apiRequest} from './api';
import {useOperations} from './workspace';
describe('business operation retries',()=>{
 it('reuses the operation key after an ambiguous 502 and releases it after success',async()=>{
  const seen:string[]=[];let calls=0;
  vi.stubGlobal('fetch',vi.fn(async(_path:any,opts:any)=>{seen.push(opts.headers['Idempotency-Key']);calls++;return new Response(JSON.stringify(calls===1?{code:'GATEWAY',message:'retry'}:{id:'accepted'}),{status:calls===1?502:200})}));
  const {result}=renderHook(()=>useOperations());
  await act(async()=>{try{await result.current.act('/handovers',{amount:'100'})}catch{}});
  expect(result.current.error).toBeTruthy();
  await act(async()=>{await result.current.act('/handovers',{amount:'100'})});
  expect(seen[0]).toBe(seen[1]);
  await act(async()=>{await result.current.act('/handovers',{amount:'100'})});
  expect(seen[2]).not.toBe(seen[1]);vi.unstubAllGlobals();
 });
 it('lets the browser set multipart boundaries and includes CSRF',async()=>{
  document.cookie='csrftoken=proof';const body=new FormData();body.set('files',new File(['proof'],'proof.png',{type:'image/png'}));
  const fetcher=vi.fn(async(_path:any,_options:any)=>new Response(JSON.stringify({items:[]})));
  await apiRequest('/files',{method:'POST',body},fetcher as typeof fetch);
  const options=fetcher.mock.calls[0]?.[1] as any;
  expect(options.headers['Content-Type']).toBeUndefined();expect(options.headers['X-CSRFToken']).toBe('proof');expect(options.body).toBe(body);
 });
});

