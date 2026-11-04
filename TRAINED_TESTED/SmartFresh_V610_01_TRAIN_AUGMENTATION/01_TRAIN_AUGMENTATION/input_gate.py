"""Integration gate for sale events; not a learned model. Refunds require separate schema."""
from datetime import datetime
def gate(event,as_of,known_skus,seen_ids,expected_price_version,max_age_minutes=30):
 try:
  now=datetime.fromisoformat(as_of);at=datetime.fromisoformat(event['event_at'])
  if now.tzinfo is None or at.tzinfo is None:return 'QUARANTINE_TIMEZONE'
  if event['sku_code'] not in known_skus:return 'QUARANTINE_UNKNOWN_SKU'
  if event['event_id'] in seen_ids:return 'DROP_DUPLICATE'
  if at>now:return 'QUARANTINE_FUTURE_EVENT'
  q=event['quantity'];p=event['unit_price_vnd']
  if isinstance(q,bool) or not isinstance(q,int) or q<=0:return 'QUARANTINE_QUANTITY'
  if isinstance(p,bool) or not isinstance(p,int) or p<=0:return 'QUARANTINE_PRICE'
  if event['price_version']!=expected_price_version:return 'RECONCILE_PRICE_VERSION'
  if (now-at).total_seconds()>max_age_minutes*60:return 'HOLD_FOR_STALE_FEED'
  return 'ACCEPT'
 except (ValueError,TypeError,KeyError):return 'QUARANTINE_SCHEMA'
