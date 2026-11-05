"""Past-only ×10 seasonal reference shared by POS, M2 and the fair baseline."""
from datetime import date


def anchor(day, rows, cutoff, holiday=False):
    weekday=date.fromisoformat(day).weekday()
    prior=[r for r in rows if '2022-01-02'<=r['date']<cutoff]
    same=sorted((r for r in prior if date.fromisoformat(r['date']).weekday()==weekday),
                key=lambda r:r['date'])[-8:]
    weekdays=sorted((r for r in prior if date.fromisoformat(r['date']).weekday()<5),
                    key=lambda r:r['date'])[-40:]
    if not same or not weekdays:
        raise ValueError('Thiếu lịch sử cùng thứ hoặc ngày thường để lập mốc nhu cầu.')
    def mean(values):
        return sum(float(r['sold_qty'])*(1.08 if r.get('stockout') or r.get('censored_demand_flag') else 1.)
                   for r in values)/len(values)
    ordinary=mean(weekdays)
    seasonal=mean(same)
    if weekday>=5 or holiday:
        return min(seasonal,ordinary*(1.25 if weekday==5 else 1.40))
    return .7*seasonal+.3*ordinary
