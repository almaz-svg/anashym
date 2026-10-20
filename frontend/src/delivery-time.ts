type DeliveryWindow={window_start?:string;window_end?:string};

export function suggestDeliveryTime(day:string,point:DeliveryWindow,now=new Date()):string {
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Almaty',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now);
 const part=(name:string)=>parts.find(p=>p.type===name)?.value||'';
 const today=`${part('year')}-${part('month')}-${part('day')}`;
 if(day<today)return '';
 const start=(point.window_start||'09:00').slice(0,5),end=(point.window_end||'20:00').slice(0,5);
 if(start>=end)return '';
 const opening=Number(start.slice(0,2))*60+Number(start.slice(3));
 const closing=Number(end.slice(0,2))*60+Number(end.slice(3));
 const minute=day===today?Math.max(opening,Number(part('hour'))*60+Number(part('minute'))+1):opening;
 return minute>closing||minute>=1440?'':`${String(Math.floor(minute/60)).padStart(2,'0')}:${String(minute%60).padStart(2,'0')}`;
}
