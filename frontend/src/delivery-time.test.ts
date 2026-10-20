import {expect,it} from 'vitest';
import {suggestDeliveryTime} from './delivery-time';

it('suggests a future minute inside today’s delivery window',()=>{
 expect(suggestDeliveryTime('2026-10-18',{window_start:'09:00:00',window_end:'20:00:00'},new Date('2026-10-18T17:00:30+05:00'))).toBe('17:01');
});
it('starts at the window opening for a future date or early morning',()=>{
 const point={window_start:'09:00:00',window_end:'20:00:00'};
 expect(suggestDeliveryTime('2026-10-19',point,new Date('2026-10-18T17:00:00+05:00'))).toBe('09:00');
 expect(suggestDeliveryTime('2026-10-18',point,new Date('2026-10-18T07:00:00+05:00'))).toBe('09:00');
});
it('does not invent an available time after closing, in the past, or across midnight',()=>{
 const point={window_start:'09:00:00',window_end:'20:00:00'};
 expect(suggestDeliveryTime('2026-10-18',point,new Date('2026-10-18T20:00:00+05:00'))).toBe('');
 expect(suggestDeliveryTime('2026-10-18',point,new Date('2026-10-18T23:59:30+05:00'))).toBe('');
 expect(suggestDeliveryTime('2026-10-17',point,new Date('2026-10-18T17:00:00+05:00'))).toBe('');
 expect(suggestDeliveryTime('2026-10-18',{window_start:'20:00',window_end:'09:00'},new Date('2026-10-18T17:00:00+05:00'))).toBe('');
});
