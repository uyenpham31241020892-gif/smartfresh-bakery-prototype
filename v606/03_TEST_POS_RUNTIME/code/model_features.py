def m1_features(item,as_of):
 """Prediction covariates only. Priceapproval/action/outcome columns are excluded."""
 return dict(sku_code=item['sku_code'],time=as_of[11:16],prepared_qty=item['prepared_qty'],inventory_at_decision=item['inventory_at_decision'],sold_last_30min=item['sold_last_30min'],sold_last_60min=item['sold_last_60min'],shelf_inventory=item['shelf_inventory'],backroom_inventory=item['backroom_inventory'],previous_discount_pct=item['current_discount_pct'],baseline_announced_2100_pct=item['baseline_announced_2100_pct'])
