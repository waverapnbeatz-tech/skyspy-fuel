import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from fuel_scraper import parse_mbenzin, parse_ono, validate_price, reported_date, freshness

NOW = datetime(2026, 10, 26, 18, 0, tzinfo=ZoneInfo('Europe/Prague'))

MBENZIN = '''<html><body><header>Najít nejlevnější benzín</header><h1>Kontakt Turnov</h1><p>Svobodova 2050</p>
<h2>Provozní doba</h2><h2>Benzín</h2><div>44,20 Kč Včera Aktualizovat</div>
<h2>Nafta</h2><div>47,50 Kč 24.10.2026 Aktualizovat</div>
<h2>Premium benzín</h2><div>49,20 Kč Dnes</div>
<h2>Čerpací stanice v okolí</h2><div>Jiná benzín 22,20 Nafta 23,30</div></body></html>'''
ONO = '''<body><h1>Cvikov</h1><p>NATURAL 95</p><span>42<sup>90</sup></span><p>1<sup>780</sup></p>
<p>NATURAL 95+</p><span>43<sup>50</sup></span><p>DIESEL</p><span>45<sup>90</sup></span><p>1<sup>905</sup></p><p>DIESEL+</p><span>46<sup>50</sup></span></body>'''

class ParserTests(unittest.TestCase):
    def test_mbenzin_prices_and_dates(self):
        n95, diesel = parse_mbenzin(MBENZIN, NOW, 'Svobodova 2050')
        self.assertEqual(n95['price'], 44.2)
        self.assertEqual(n95['reported_date'], '2026-10-25')
        self.assertEqual(n95['status'], 'fresh')
        self.assertEqual(diesel['price'], 47.5)
        self.assertEqual(diesel['reported_date'], '2026-10-24')
    def test_no_neighboring_price_fallback(self):
        html = MBENZIN.replace('44,20 Kč', '– cenu zatím nemáme')
        n95, diesel = parse_mbenzin(html, NOW, 'Svobodova 2050')
        self.assertIsNone(n95['price'])
        self.assertEqual(diesel['price'], 47.5)
    def test_address_guard(self):
        with self.assertRaises(ValueError): parse_mbenzin(MBENZIN, NOW, 'Palackého 182')
    def test_premium_not_selected(self):
        self.assertNotEqual(parse_mbenzin(MBENZIN, NOW, 'Svobodova 2050')[0]['price'], 49.2)
    def test_ono_superscript(self):
        n95, diesel = parse_ono(ONO, NOW)
        self.assertEqual(n95['price'], 42.9)
        self.assertEqual(diesel['price'], 45.9)
        self.assertEqual(n95['status'], 'unknown_date')
    def test_ono_wrong_station(self):
        with self.assertRaises(ValueError): parse_ono(ONO.replace('Cvikov', 'Plzeň'), NOW)
    def test_ono_no_super(self):
        n95, d = parse_ono(ONO.replace('42<sup>90</sup>', '42,50'), NOW)
        self.assertEqual(n95['price'], 42.5)
    def test_reject_odd_prices(self):
        with self.assertRaises(ValueError): validate_price('159,00')
        with self.assertRaises(ValueError): validate_price('1,790')
    def test_stale(self):
        self.assertEqual(freshness(reported_date('1.10.2026', NOW), NOW), 'stale')
    def test_date_missing(self):
        self.assertIsNone(reported_date('cena nebyla hlášena', NOW))

class HttpFlowTests(unittest.TestCase):
    def test_denied_robots_makes_error_without_prices(self):
        from fuel_scraper import fetch_station
        class FakeResponse:
            status_code = 403
        class Session:
            def get(self, *args, **kwargs): return FakeResponse()
        item = {
            'id':'kontakt_turnov','name':'Kontakt Turnov','location':'Turnov',
            'url':'https://www.mbenzin.cz/Ceny-benzinu-a-nafty/Turnov/Kontakt-Svobodova-2050/17039',
            'source_kind':'mbenzin','expected_address':'Svobodova 2050'
        }
        result = fetch_station(item, NOW, Session())
        self.assertIsNone(result['natural95']['price'])
        self.assertIsNone(result['diesel']['price'])
        self.assertIn('robots.txt', result['error'])
