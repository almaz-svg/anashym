"""Create a separate UI acceptance client using real business HTTP APIs only.

Never modifies demo clients, never edits database rows, never deletes ledger
history. Reuses its recorded fixture on later runs. Servers must already run.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from mvp_http import Session

output = Path(__file__).with_name('customer-account-financial-fixture.json')
if output.exists():
    fixture = json.loads(output.read_text())
    print(json.dumps({'reused': True, 'client_id': fixture['client_id']}))
    raise SystemExit(0)

base = 'http://127.0.0.1:8000'
tag = uuid.uuid4().hex[:10]
phone = '+778' + str(uuid.uuid4().int)[:8]
password = 'QaAccountMoney2026!'
customer, admin, courier = (Session(base) for _ in range(3))
customer.call('auth/csrf', expected=204)
client = customer.call('auth/register', dict(phone=phone, password=password,
    name='QA Account Money ' + tag, category='coffee_shop', description='Isolated browser finance acceptance',
    expected_order_quantity=1, expected_order_frequency='Раз в неделю', preferred_payment_mode='deferred', requested_period_days=14), 201)
fixture = dict(phone=phone, password=password, client_id=client['client_id'], tag=tag)
# Save identity immediately so a failure cannot leave an unidentified record.
output.with_suffix('.incomplete.json').write_text(json.dumps(fixture, indent=2))
admin.login('+77010000002', 'DemoAdmin2026!')
admin.call('clients/' + client['client_id'] + '/approve', dict(approval_status='active', deferred_approved=True, credit_limit_amount='10000.00', period_days=14))
customer.login(phone, password)
point = customer.call('delivery-points', dict(address='QA account acceptance address', recipient='QA', phone=phone), 201)
product = admin.call('products', dict(name='QA Account ' + tag, description='Isolated UI money fixture', price_amount='512.50', preparation_minutes=1), 201)
now = datetime.now(timezone.utc)
admin.call('batches', dict(product_id=product['id'], manufactured_at=(now-timedelta(hours=1)).isoformat(), expires_at=(now+timedelta(days=3)).isoformat(), quantity=1), 201)
day = now.astimezone(timezone(timedelta(hours=5))).date()
order = customer.call('orders', dict(kind='regular', delivery_point_id=point['id'], requested_delivery_at=str(day)+'T18:00:00+05:00', payment_mode='deferred', items=[dict(product_id=product['id'], quantity=1, expected_unit_price='512.50')]), 201)
courier_id = courier.login('+77010000003', 'DemoStaff2026!')['user_id']
for state in ['accepted', 'preparing', 'ready', 'out_for_delivery']:
    order = admin.call('orders/' + order['id'] + '/transition', dict(status=state, courier_id=courier_id, version=order['version']))
photo = courier.upload(order['id'])
courier.call('orders/' + order['id'] + '/delivery', dict(items=[dict(product_id=product['id'], quantity=1)], photo_ids=[photo], version=order['version']))
pending = customer.call('payments', dict(method='kaspi', amount='123.25', reference='QA-ACCOUNT-PENDING-' + tag), 201)
balance = customer.call('balance')
assert balance['debt_amount'] == '512.50', balance
assert balance['advance_amount'] == '0.00', balance
fixture.update(order_id=order['id'], product_id=product['id'], pending_payment_id=pending['id'], expected_debt='512.50', expected_pending='123.25')
output.write_text(json.dumps(fixture, indent=2))
print(json.dumps({'created': True, 'client_id': fixture['client_id'], 'debt': '512.50', 'pending': '123.25'}))
