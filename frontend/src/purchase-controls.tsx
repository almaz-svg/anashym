import {ShoppingBasket,ArrowRight} from 'lucide-react';
import {t} from './preferences';
import {money} from './workspace';

export function ProductPurchase({name,available,quantity,busy,onAdd,onCheckout}:{name:string;available:number;quantity:number;busy?:boolean;onAdd:()=>void;onCheckout:()=>void}) {
    const selected=quantity>0, label=t(selected?'К оформлению':'В корзину');
    return <div className="product-action">
        {available<=0&&<p className="stock-empty">{t('Нет в наличии')}</p>}
        <button type="button" className="primary product-add-button" aria-label={label+': '+name} disabled={busy||available<=0} onClick={selected?onCheckout:onAdd}>
            <ShoppingBasket size={17} aria-hidden="true"/>{label}
        </button>
    </div>;
}

export function CartSummary({count,total,onCheckout}:{count:number;total:number;onCheckout:()=>void}) {
    if(count<=0)return null;
    return <section className="cart-summary" aria-label={t('Корзина')}>
        <span className="cart-summary-count">{t('В корзине: {{count}}',{count})}</span>
        <strong className="cart-summary-total">{money(total)}</strong>
        <button className="primary" type="button" onClick={onCheckout}>{t('Оформить заказ')}<ArrowRight size={17} aria-hidden="true"/></button>
    </section>;
}
