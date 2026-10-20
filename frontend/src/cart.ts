export type CartProduct = {id:string;price_amount:string;available_qty:number;preorder_available_qty:number;active?:boolean;name?:string};
export function previewCart(products:CartProduct[],quantities:Record<string,number>) {
 const selected=products.filter(product=>(quantities[product.id]||0)>0);
 return {count:selected.reduce((sum,product)=>sum+quantities[product.id],0),total:selected.reduce((sum,product)=>sum+Math.round(Number(product.price_amount)*100)*quantities[product.id],0)/100};
}
export function reconcileCart(products:CartProduct[],quantities:Record<string,number>,preorder:boolean) {
 const next:Record<string,number>={};
 for(const product of products){const requested=quantities[product.id]||0;const available=preorder?product.preorder_available_qty:product.available_qty;if(product.active!==false&&requested>0&&available>0)next[product.id]=Math.min(requested,available)}
 return {quantities:next,total:products.reduce((sum,product)=>sum+Math.round(Number(product.price_amount)*100)*(next[product.id]||0),0)/100};
}
