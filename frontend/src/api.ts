export class ApiError extends Error {
 constructor(public status:number,public code:string,message:string,public field_errors:Record<string,string[]>={}){super(message)}
}
export const isDefinitiveFailure=(e:unknown)=>e instanceof ApiError&&e.status>=400&&e.status<500;
export async function apiRequest<T=any>(path:string,options:RequestInit={},fetcher:typeof fetch=fetch):Promise<T>{
 const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=').slice(1).join('=')||'');
 let response:Response;
 try{response=await fetcher('/api/v1'+path,{...options,credentials:'include',headers:{...(!(options.body instanceof FormData)?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRFToken':csrf}:{}),...options.headers}})}catch{throw new ApiError(0,'NETWORK_ERROR','Связь с сервером потеряна. Результат операции неизвестен. Повторите запрос с тем же ключом.');}
 if(response.status===204)return undefined as T;
 const data=await response.json().catch(()=>({}));
 if(!response.ok)throw new ApiError(response.status,data.code||'SERVER_ERROR',data.message||'Сервис временно недоступен. Попробуйте ещё раз.',data.field_errors);
 return data;
}
