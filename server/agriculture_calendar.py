"""Public date presentation only; no application or account dependencies."""
from copy import deepcopy
from functools import lru_cache
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo



def _lunar_label(lunar):
    return lunar.getYearInChinese()+'年'+lunar.getMonthInChinese()+'月'+lunar.getDayInChinese()


@lru_cache(maxsize=32)
def _nodes(start, solar_type):
    festivals = {(1,1):'春节', (1,15):'元宵节', (2,2):'龙抬头',
                 (5,5):'端午节', (7,7):'七夕', (7,15):'中元节',
                 (8,15):'中秋节', (9,9):'重阳节', (12,8):'腊八节',
                 (12,23):'小年（北方）', (12,24):'小年（南方）'}
    result = []
    for offset in range(367):
        date = start + timedelta(days=offset)
        lunar = solar_type.fromYmd(date.year, date.month, date.day).getLunar()
        names = []
        term = lunar.getJieQi()
        if term:
            names.append(('solarTerm', term))
        festival = festivals.get((lunar.getMonth(), lunar.getDay()))
        tomorrow = date + timedelta(days=1)
        following = solar_type.fromYmd(tomorrow.year, tomorrow.month, tomorrow.day).getLunar()
        if following.getMonth() == 1 and following.getDay() == 1:
            festival = '除夕'
        if festival:
            names.append(('lunarFestival', festival))
        for kind, name in names:
            result.append(dict(id=f'{date.isoformat()}:{kind}:{name}', type=kind,
                               name=name, date=date.isoformat(), lunarDate=_lunar_label(lunar), daysUntil=offset))
    return sorted(result, key=lambda node: (node['date'], node['id']))

def presentation(at=None):
    day = (at or datetime.now(ZoneInfo('Asia/Shanghai'))).astimezone(ZoneInfo('Asia/Shanghai'))
    calendar = dict(status='unavailable', date=day.date().isoformat(), timezone='Asia/Shanghai', sourceVersion='lunar_python:1.4.8', nodes=[])
    try:
        from lunar_python import Solar
        lunar = Solar.fromYmd(day.year, day.month, day.day).getLunar()
        nodes = deepcopy(_nodes(day.date(), Solar))
        # The view is day-based: on a solar-term day, "next" means a later day.
        next_term = next((node['name'] for node in nodes if node['type'] == 'solarTerm' and node['daysUntil'] > 0), '')
        calendar.update(status='available', nodes=nodes, lunarDate=_lunar_label(lunar), jieQi=lunar.getJieQi(), season=lunar.getPrevJieQi().getName(), nextJieQi=next_term, yi=lunar.getDayYi(), ji=lunar.getDayJi())
    except (ImportError, ValueError, AttributeError):
        pass
    return dict(calendar=calendar, weather=dict(mode='demo', label='天气样例', location='园区天气', condition='多云', temperature=24, precipitationProbability=30, low=18, high=26, unit='℃', forecast=[dict(label='今天', condition='多云', icon='cloudSun', low=18, high=26), dict(label='明天', condition='小雨', icon='rain', low=17, high=22), dict(label='后天', condition='阴', icon='cloudSun', low=16, high=23)]))
