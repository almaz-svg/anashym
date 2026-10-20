import {describe,it,expect} from 'vitest';
import {reconcileCart,previewCart} from './cart';
describe('server price reconciliation',()=>{
 it('prices every requested unit in the cart preview without silently reducing quantities',()=>{
  expect(previewCart([{id:'cake',price_amount:'400.00',available_qty:2,preorder_available_qty:2}],{cake:5,unknown:1})).toEqual({count:5,total:2000});
 });
 it('prices retained quantities from the refreshed catalog and removes unavailable products',()=>{
  expect(reconcileCart([{id:'cake',price_amount:'120.35',available_qty:2,preorder_available_qty:8},{id:'archived',price_amount:'40',available_qty:9,preorder_available_qty:9,active:false}],{cake:4,removed:1,archived:2},false)).toEqual({quantities:{cake:2},total:240.7});
 });
 it('uses quota availability for preorders',()=>{expect(reconcileCart([{id:'cake',price_amount:'100',available_qty:0,preorder_available_qty:3}],{cake:2},true)).toEqual({quantities:{cake:2},total:200})});
});
