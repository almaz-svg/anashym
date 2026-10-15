// @vitest-environment jsdom
import { describe,it,expect } from 'vitest';
import { ApiError, apiRequest, isDefinitiveFailure } from './api';
describe('API boundary',()=>{
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
