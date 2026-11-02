"""Independent civil-date and official almanac acceptance checks."""
import sys
from datetime import datetime, timezone, date
from unittest.mock import patch
from server import agriculture_calendar as cal


def calendar(day):
    return cal.presentation(datetime.fromisoformat(day).replace(tzinfo=timezone.utc))['calendar']



import unittest

class AlmanacIndependentTests(unittest.TestCase):

    def test_official_new_year_and_eve_across_years(self):
        nodes = calendar('2026-02-01')['nodes']
        for name, day in [('春节','2026-02-17'),('除夕','2026-02-16'),('春节','2027-02-06'),('除夕','2027-02-05')]:
            # HKO 2026/2027 official Gregorian-lunar tables.
            if (date.fromisoformat(day)-date(2026,2,1)).days <= 366:
                assert any(n['name']==name and n['date']==day for n in nodes)
        later = calendar('2026-10-31')['nodes']
        assert next(n for n in later if n['type']=='lunarFestival')['name']=='腊八节'
        assert any(n['name']=='除夕' and n['date']=='2027-02-05' for n in later)


    def test_civil_midnight_bounds_ids_and_isolation(self):
        before=cal.presentation(datetime(2026,10,30,15,59,tzinfo=timezone.utc))['calendar']
        after=cal.presentation(datetime(2026,10,30,16,0,tzinfo=timezone.utc))['calendar']
        assert before['date']=='2026-10-30'
        assert after['date']=='2026-10-31'
        nodes=after['nodes']
        assert nodes==sorted(nodes,key=lambda n:(n['date'],n['id'])) or [n['date'] for n in nodes]==sorted(n['date'] for n in nodes)
        assert len({n['id'] for n in nodes})==len(nodes)
        for n in nodes:
            assert n['daysUntil']==(date.fromisoformat(n['date'])-date(2026,10,31)).days
            assert 0 <= n['daysUntil'] <= 366
            assert n['lunarDate']
        nodes[0]['name']='污染'
        assert calendar('2026-10-31')['nodes'][0]['name']!='污染'


    def test_same_day_nodes_kept_and_leap_month_not_festival(self):
        nodes=calendar('2020-05-01')['nodes']
        assert not any(n['type']=='lunarFestival' and n['date']=='2020-06-25' and n['name']!='端午节' for n in nodes)
        # 2020 leap fourth month must not create a second fixed lunar festival.
        assert len([n for n in nodes if n['name']=='端午节'])==1
        nodes=calendar('2020-10-01')['nodes']
        assert any(n['name']=='中秋节' and n['daysUntil']==0 for n in nodes)
        # 2023 Qingming and leap-month dates are handled by the same date authority.
        nodes=calendar('2023-01-01')['nodes']
        assert len([n for n in nodes if n['name']=='龙抬头'])==1


    def test_missing_library_returns_explicit_empty_nodes(self):
        with patch.dict(sys.modules, {'lunar_python':None}):
            result=calendar('2042-04-17')
        assert result['status']=='unavailable'
        assert result['nodes']==[]


    def test_inclusive_366_day_horizon_and_same_day_types(self):
        included=calendar('2025-11-06')['nodes']
        assert any(n['name']=='立冬' and n['date']=='2026-11-07' and n['daysUntil']==366 for n in included)
        assert not any(n['date']=='2026-11-07' for n in calendar('2025-11-05')['nodes'])
        same=[n for n in calendar('2026-03-20')['nodes'] if n['date']=='2026-03-20']
        assert {n['name'] for n in same}=={'龙抬头','春分'}
        assert {n['type'] for n in same}=={'solarTerm','lunarFestival'}


    def test_value_error_fallback(self):
        from lunar_python import Solar
        with patch.object(Solar,'fromYmd',side_effect=ValueError('invalid calendar')):
            result=calendar('2026-10-31')
        assert result['nodes']==[] and result['status']=='unavailable'

    def test_next_term_excludes_today(self):
        for day, today, following in [('2026-11-07','立冬','小雪'),('2026-11-22','小雪','大雪')]:
            result=calendar(day)
            assert result['jieQi']==today
            assert result['nextJieQi']==following
