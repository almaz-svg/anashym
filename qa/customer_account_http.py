"""Independent /profile HTTP parity using only own isolated QA fixtures."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from decimal import Decimal
from mvp_http import Session, check, RESULTS

out = Path(__file__).parent
base = 'http://127.0.0.1:8000'
admin = Session(base)
admin.login('+77010000002', 'DemoAdmin2026!')
zero_path = out / 'customer-account-fixture.json'
if zero_path.exists():
    zero = json.loads(zero_path.read_text())
else:
    tag = uuid.uuid4().hex[:8]
    zero = dict(phone='+778'+str(uuid.uuid4().int)[:8], password='QaAccount2026!', tag=tag)
    user = Session(base)
    user.call('auth/csrf', expected=204)
    me = user.call('auth/register', dict(phone=zero['phone'], password=zero['password'], name='QA Customer Account '+tag, category='coffee_shop', description='Isolated customer account UI acceptance', expected_order_quantity=10, expected_order_frequency='Раз в неделю', preferred_payment_mode='deferred', requested_period_days=14), 201)
    zero['client_id'] = me['client_id']
    zero_path.write_text(json.dumps(zero, indent=2))
try:
    admin.call('clients/'+zero['client_id']+'/approve', dict(approval_status='pending'))
    user = Session(base)
    user.login(zero['phone'], zero['password'])
    pending_profile = user.call('profile')
    check('pending customer can read only own profile identity and zero summary', pending_profile['profile']['phone'] == zero['phone'] and pending_profile['profile']['approval_status'] == 'pending' and all(Decimal(value) == 0 for value in pending_profile['balance'].values()), pending_profile)
    user.call('auth/logout', {}, 204)
    user.call('auth/me', expected=401)
    check('pending customer server logout works', True)
    admin.call('clients/'+zero['client_id']+'/approve', dict(approval_status='active', deferred_approved=True, credit_limit_amount='10000.00', period_days=14))
    user.login(zero['phone'], zero['password'])
    profile = user.call('profile')
    zero_profile = profile
    check('zero customer accurate profile identity', profile['profile']['phone'] == zero['phone'])
    check('zero customer does not invent money', all(Decimal(value) == 0 for value in profile['balance'].values()) and all(Decimal(value) == 0 for value in profile['period'].values()), profile)
    admin.call('clients/'+zero['client_id']+'/approve', dict(approval_status='pending'))
    financial = json.loads((out/'customer-account-financial-fixture.json').read_text())
    money = Session(base)
    money.login(financial['phone'], financial['password'])
    balance = money.call('balance')
    profile = money.call('profile')
    payments = money.call('payments')['items']
    pending = sum((Decimal(row['amount']) for row in payments if row['status'] == 'pending'), Decimal(0))
    check('profile debt equals balance API', profile['balance']['debt_amount'] == balance['debt_amount'] == '512.50', profile['balance'])
    check('profile advance equals balance API', profile['balance']['advance_amount'] == balance['advance_amount'] == '0.00')
    check('profile pending sums actual payment records without netting debt', Decimal(profile['balance']['unconfirmed_payment_amount']) == pending == Decimal('123.25'))
    check('profile week contains actual delivered amount and zero confirmed payment', profile['period']['delivered_amount'] == profile['period']['outstanding_amount'] == '512.50' and profile['period']['paid_amount'] == '0.00', profile['period'])
    today = datetime.now(timezone(timedelta(hours=5))).date()
    monday = today - timedelta(days=today.weekday())
    check('profile default business week exact dates', profile['from'] == str(monday) and profile['to'] == str(monday+timedelta(days=6)), [profile['from'],profile['to']])
    selected = money.call(f'profile?from={today}&to={today}')
    check('profile custom period exact date and amounts', selected['from'] == selected['to'] == str(today) and selected['period']['delivered_amount'] == selected['period']['outstanding_amount'] == '512.50', selected['period'])
    previous = today-timedelta(days=1)
    empty = money.call(f'profile?from={previous}&to={previous}')
    check('empty selected period preserves overall debt and pending', empty['period']['delivered_amount'] == empty['period']['outstanding_amount'] == '0.00' and empty['balance'] == profile['balance'], empty)
    (out/'customer-account-http-evidence.json').write_text(json.dumps(dict(zero=zero_profile, financial=profile, selected=selected, empty=empty), ensure_ascii=False, indent=2), encoding='utf-8')
finally:
    (out/'customer-account-http-results.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding='utf-8')
