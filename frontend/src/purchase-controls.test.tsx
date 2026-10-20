// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {CartSummary,ProductPurchase} from './purchase-controls';
afterEach(cleanup);
it('offers an explicit add action and checkout for the selected product',()=>{
 const add=vi.fn(),checkout=vi.fn();
 const {rerender}=render(<ProductPurchase name="Капкейк" available={5} quantity={0} onAdd={add} onCheckout={checkout}/>);
 fireEvent.click(screen.getByRole('button',{name:'В корзину: Капкейк'}));expect(add).toHaveBeenCalledOnce();expect(checkout).not.toHaveBeenCalled();
 rerender(<ProductPurchase name="Капкейк" available={5} quantity={2} onAdd={add} onCheckout={checkout}/>);
 fireEvent.click(screen.getByRole('button',{name:'К оформлению: Капкейк'}));expect(checkout).toHaveBeenCalledOnce();expect(add).toHaveBeenCalledOnce();
});
it('does not allow buying stock that does not exist',()=>{
 const add=vi.fn();render(<ProductPurchase name="Капкейк" available={0} quantity={0} onAdd={add} onCheckout={()=>{}}/>);
 const button=screen.getByRole('button',{name:'В корзину: Капкейк'});
 expect(button).toHaveProperty('disabled',true);fireEvent.click(button);expect(add).not.toHaveBeenCalled();
 expect(screen.getByText('Нет в наличии')).toBeTruthy();
});
it('shows a clear checkout action only when something is selected',()=>{
 const checkout=vi.fn();const {rerender}=render(<CartSummary count={0} total={0} onCheckout={checkout}/>);
 expect(screen.queryByRole('region',{name:'Корзина'})).toBeNull();
 rerender(<CartSummary count={2} total={1260} onCheckout={checkout}/>);
 expect(screen.getByRole('region',{name:'Корзина'}).textContent?.replace(/\s/g,'')).toContain('1260');
 fireEvent.click(screen.getByRole('button',{name:'Оформить заказ'}));expect(checkout).toHaveBeenCalledOnce();
});
