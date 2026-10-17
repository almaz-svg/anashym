// @vitest-environment jsdom
import { describe,it,expect } from 'vitest';
import { ApiError, apiRequest, isDefinitiveFailure } from './api';
describe('API boundary',()=>{
 it('rejects an HTML fallback instead of treating it as an authenticated user',async()=>{
  const fetcher=async()=>new Response('<!doctype html><html>Application</html>',{status:200,headers:{'Content-Type':'text/html'}});
  await expect(apiRequest('/auth/me',{},fetcher as typeof fetch)).rejects.toMatchObject({code:'INVALID_API_RESPONSE',status:502});
 });
 it.each([500,502,503,504])('identifies an unavailable backend for HTTP %s',async status=>{
  const fetcher=async()=>new Response('Bad gateway',{status});
  await expect(apiRequest('/auth/login',{},fetcher as typeof fetch)).rejects.toMatchObject({code:'API_UNAVAILABLE',status});
 });
 it('accepts the empty CSRF handshake',async()=>{
  await expect(apiRequest('/auth/csrf',{},async()=>new Response(null,{status:204}))).resolves.toBeUndefined();
 });
 it('reports a missing API deployment without treating the request as a definitive rejection',async()=>{
  const fetcher=async()=>new Response('The page could not be found',{status:404});
  await expect(apiRequest('/auth/csrf',{},fetcher as typeof fetch)).rejects.toMatchObject({code:'INVALID_API_RESPONSE',status:502});
 });
 it('keeps idempotency key after ambiguous gateway failures',()=>{
  expect(isDefinitiveFailure(new ApiError(502,'SERVER_ERROR','gateway'))).toBe(false);
  expect(isDefinitiveFailure(new ApiError(409,'PRICE_CHANGED','changed'))).toBe(true);
 });
 it('retains server conflict code and field errors',async()=>{
  const fetcher=async()=>new Response(JSON.stringify({code:'PRICE_CHANGED',message:'Цена изменилась',field_errors:{items:['Обновите каталог']}}),{status:409});
  await expect(apiRequest('/orders',{},fetcher as typeof fetch)).rejects.toMatchObject({code:'PRICE_CHANGED',status:409,field_errors:{items:['Обновите каталог']}});
 });
 it('does not describe network loss as success',async()=>{
  await expect(apiRequest('/orders',{},async()=>{throw new TypeError('offline')})).rejects.toBeInstanceOf(ApiError);
 });
});
