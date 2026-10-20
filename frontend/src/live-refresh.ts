import {useEffect,useRef} from 'react';

/** Refresh visible views without overlapping requests or applying results to another scope. */
export function useLiveRefresh(refresh:(isCurrent:()=>boolean)=>Promise<unknown>|void,enabled=true,interval=5000,scope='') {
    const latest=useRef(refresh);
    latest.current=refresh;
    useEffect(()=>{
        if(!enabled)return;
        let stopped=false,pending=false;
        async function run(){
            if(stopped||pending||document.visibilityState==='hidden')return;
            pending=true;
            try{await latest.current(()=>!stopped)}finally{pending=false}
        }
        const trigger=()=>{void run().catch(()=>{/* The caller presents its scoped request error. */})};
        const timer=setInterval(trigger,interval);
        window.addEventListener('focus',trigger);
        window.addEventListener('bakery:data-changed',trigger);
        document.addEventListener('visibilitychange',trigger);
        return()=>{stopped=true;clearInterval(timer);window.removeEventListener('focus',trigger);window.removeEventListener('bakery:data-changed',trigger);document.removeEventListener('visibilitychange',trigger)};
    },[enabled,interval,scope]);
}
