"""Fresh invited staff: cash wallet, shifts, invitations and session revocation."""
import json,uuid
from decimal import Decimal
from mvp_http import Session,check,OUT,RESULTS

def run():
 base='http://127.0.0.1:8000';admin=Session(base);admin.login('+77010000002','DemoAdmin2026!')
 def invite(role):
  phone='+776'+str(uuid.uuid4().int)[:8];staff=admin.call('staff',dict(phone=phone,name='QA '+role+' '+uuid.uuid4().hex[:6],role=role),201)
  s=Session(base);s.call('auth/csrf',expected=204);body=dict(token=staff['invitation_token'],password='QaStaffInvite2026!');s.call('auth/accept-invitation',body);s.call('auth/accept-invitation',body,422);s.login(phone,body['password']);check(role+' invitation one-time activation and login',True);return s,staff
 courier,c=invite('courier');cashier,k=invite('cashier')
 f=json.loads((OUT/'mvp-edge-fixture.json').read_text());customer=Session(base);customer.login(f['phone'],f['password']);balance=customer.call('balance')['balance_amount']
 cashier.call('shifts',dict(action='open',opening_amount='10000'))
 cashier.call('shifts',dict(action='open'),409);check('one open shift invariant',True)
 cashier.call('cash-movements',dict(courier_id=c['id'],amount='10000',direction='issue',reason='QA float to isolated courier'),201)
 wallet=courier.call('cash');check('courier wallet receives float10000',Decimal(wallet['cash_amount'])==10000)
 hand=courier.call('handovers',dict(amount='7000'),201);wallet=courier.call('cash');check('pending handover reserves7000 available3000',Decimal(wallet['available_amount'])==3000 and Decimal(wallet['pending_handover_amount'])==7000)
 courier.call('handovers',dict(amount='4000'),409);check('cannot oversubscribe handover available wallet',True)
 cashier.call('handovers/'+hand['id']+'/confirm',dict(amount='6500'),422);check('handover discrepancy requires reason',True)
 cashier.call('handovers/'+hand['id']+'/confirm',dict(amount='6500',reason='QA actual counted6500'))
 check('only actual6500 leaves courier wallet',Decimal(courier.call('cash')['cash_amount'])==3500)
 check('float and handover do not change client debt',customer.call('balance')['balance_amount']==balance)
 hand=courier.call('handovers',dict(amount='3500'),201);cashier.call('handovers/'+hand['id']+'/reject',dict(reason='QA rejected pending transfer'));check('rejection releases reservation',Decimal(courier.call('cash')['available_amount'])==3500)
 cashier.call('shifts',dict(action='close',actual_amount='6400'),422);check('shift discrepancy requires reason',True)
 closed=cashier.call('shifts',dict(action='close',actual_amount='6400',reason='QA counted discrepancy'))
 check('shift stores expected6500 actual6400 discrepancy-100',Decimal(closed['expected_amount'])==6500 and Decimal(closed['counted_amount'])==6400 and Decimal(closed['discrepancy'])==-100)
 cashier.call('cash-movements',dict(courier_id=c['id'],amount='3500',direction='return',reason='QA returns remaining isolated float'),201)
 check('isolated float cleanup returns wallet to zero',Decimal(courier.call('cash')['cash_amount'])==0)
 admin.call('staff/'+c['id']+'/role',dict(role='accountant'))
 courier.call('auth/me',expected=401);check('changing own QA staff role revokes old session',True)

if __name__=='__main__':
 try:run()
 except Exception as e:RESULTS.append(dict(name='runner failure',pass_=False,detail=str(e)));raise
 finally:(OUT/'mvp-cash-staff-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
