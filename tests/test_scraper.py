import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from fuel_scraper import parse_mbenzin, parse_mbenzin_listing, parse_ono, validate_price, reported_date, freshness

NOW = datetime(2026, 10, 26, 18, 0, tzinfo=ZoneInfo('Europe/Prague'))

MBENZIN = '''<html><body><header>Najít nejlevnější benzín</header><h1>Kontakt Turnov</h1><p>Svobodova 2050</p>
<h2>Provozní doba</h2><h2>Benzín</h2><div>44,20 Kč Včera Aktualizovat</div>
<h2>Nafta</h2><div>47,50 Kč 24.10.2026 Aktualizovat</div>
<h2>Premium benzín</h2><div>49,20 Kč Dnes</div>
<h2>Čerpací stanice v okolí</h2><div>Jiná benzín 22,20 Nafta 23,30</div></body></html>'''
ONO = '''<body><h1>Cvikov</h1><p>NATURAL 95</p><span>42<sup>90</sup></span><p>1<sup>780</sup></p>
<p>NATURAL 95+</p><span>43<sup>50</sup></span><p>DIESEL</p><span>45<sup>90</sup></span><p>1<sup>905</sup></p><p>DIESEL+</p><span>46<sup>50</sup></span></body>'''


MBENZIN_OHRAZENICE = """<html><body><h1>Kontakt</h1><h2>Turnov</h2><div>Ohrazenice</div><h2>Benzín</h2>
<div>43,90 Kč 25.10.2026</div><h2>Nafta</h2><div>46,90 Kč 8 dní</div><h2>Premium benzín</h2>
<div>45,90</div><h2>Čerpací stanice v okolí</h2><div>Kontakt Turnov, Svobodova 2050</div>
<div>Benzín 41,00</div><div>Nafta 41,50</div></body></html>"""
MBENZIN_LISTING = """<html><body><main><h2>Nejbližší</h2>
<a>Robin Oil</a><div>Turnov, Palackého 182</div><div>CCS</div><div>200 m</div>
<div>Benzín</div><b>44,50</b><div>Nafta</div><b>46,70</b><div>LPG</div><div>–</div>
<div>CNG</div><div>–</div><div>Premium benzín</div><div>47,50</div><div>Premium diesel</div><div>–</div>
<a>Kontakt</a><div>Turnov, Svobodova 2050</div><div>Benzín</div><b>43,90</b>
<div>Nafta</div><b>46,90</b><div>LPG</div><div>22,90</div><div>CNG</div><div>45,90</div>
<div>Premium benzín</div><div>45,90</div><div>Premium diesel</div><div>47,90</div>
<a>Kontakt</a><div>Turnov, Ohrazenice</div><div>CCS</div><div>1,50 km</div>
<div>Benzín</div><b>43,90</b><div>Nafta</div><b>46,90</b><span>8 dní</span>
<div>LPG</div><div>22,90</div><div>CNG</div><div>–</div><div>Premium benzín</div><b>45,90</b><div>Premium diesel</div><div>47,90</div>
</main></body></html>"""

class ParserTests(unittest.TestCase):

    def test_realistic_detail_has_nav_price_before_address(self):
        html = """<html><body><header><div>Benzín 34,00 a nafta 38,00</div></header>
        <main><h1>Kontakt – Turnov</h1><p>Ohrazenice</p><h2>Provozní doba</h2>
        <h2>Benzín</h2><div><strong>43,90 Kč</strong> <span>24.10.2026</span></div>
        <h2>Nafta</h2><div>46,90 Kč z 18.10.2026 — nemusí být aktuální</div>
        <h2>Čerpací stanice v okolí</h2><article>Robin Oil Benzín 99,99 Nafta 99,99</article>
        </main></body></html>"""
        b, d = parse_mbenzin(html, NOW, 'Ohrazenice', 'Kontakt')
        self.assertEqual((b['price'],d['price']), (43.9,46.9))
        self.assertEqual(b['reported_date'],'2026-10-24')
        self.assertEqual(d['status'],'stale')

    def test_realistic_robinoil_title_and_heading(self):
        html = """<html><body><header>Benzín</header><h1>Robin Oil – Turnov</h1>
        <p>Palackého 182</p><h2>Benzín</h2><div>44,50 Kč 24.10.2026</div>
        <h2>Nafta</h2><div>46,70 Kč 23.10.2026</div>
        <h2>Premium benzín</h2><div>47,50 Kč</div>
        <h2>Čerpací stanice v okolí</h2><p>Kontakt</p></body></html>"""
        b, d = parse_mbenzin(html, NOW, 'Palackého 182', 'Robin Oil')
        self.assertEqual((b['price'],d['price']), (44.5,46.7))
        self.assertEqual(d['reported_date'],'2026-10-23')

    def test_address_must_not_come_only_from_nearby(self):
        html = """<html><h1>Kontakt – Turnov</h1><div>Svobodova 2050</div>
        <h2>Benzín</h2><p>43,90 Kč 24.10.2026</p><h2>Nafta</h2>
        <p>46,90 Kč</p><h2>Čerpací stanice v okolí</h2>
        <p>Turnov, Ohrazenice</p></html>"""
        with self.assertRaisesRegex(ValueError,'Nesedí adresa'):
            parse_mbenzin(html, NOW, 'Ohrazenice', 'Kontakt')

    def test_listing_inline_and_split_address(self):
        html = """<html><main><a>Robin Oil</a><p>Turnov,</p><span>Palackého 182</span>
        <span>200 m</span><div>Benzín 44,50</div><div>Nafta 46,70 3 dní</div>
        <div>LPG –</div><div>CNG –</div><div>Premium benzín 47,50</div>
        <div>Premium diesel –</div>
        <a>Kontakt</a><p>Turnov, Ohrazenice</p><div>Benzín 43,90</div>
        <div>Nafta 46,90 8 dní</div><div>LPG 22,90</div><div>CNG –</div>
        <div>Premium benzín 45,90</div><div>Premium diesel 47,90</div>
        </main></html>"""
        b, d = parse_mbenzin_listing(html, NOW, 'Turnov, Palackého 182', 'Robin Oil')
        self.assertEqual((b['price'],d['price']), (44.5,46.7))
        b2, d2 = parse_mbenzin_listing(html, NOW, 'Turnov, Ohrazenice', 'Kontakt')
        self.assertEqual((b2['price'],d2['price']), (43.9,46.9))
        self.assertEqual(d2['status'],'stale')

    def test_ohrazenice_detail_guard(self):
        n95, diesel = parse_mbenzin(MBENZIN_OHRAZENICE, NOW, 'Ohrazenice')
        self.assertEqual(n95['price'], 43.9)
        self.assertEqual(diesel['price'], 46.9)
        self.assertEqual(diesel['status'], 'stale')
        with self.assertRaises(ValueError):
            parse_mbenzin(MBENZIN_OHRAZENICE, NOW, 'Svobodova 2050')
    def test_ohrazenice_listing(self):
        b, d = parse_mbenzin_listing(MBENZIN_LISTING, NOW, 'Turnov, Ohrazenice', 'Kontakt')
        self.assertEqual(b['price'], 43.9)
        self.assertEqual(d['price'], 46.9)
        self.assertEqual(d['status'], 'stale')
    def test_robinoil_listing(self):
        b, d = parse_mbenzin_listing(MBENZIN_LISTING, NOW, 'Turnov, Palackého 182', 'Robin Oil')
        self.assertEqual(b['price'], 44.5)
        self.assertEqual(d['price'], 46.7)
    def test_listing_never_neighbor(self):
        with self.assertRaises(ValueError):
            parse_mbenzin_listing(MBENZIN_LISTING, NOW, 'Turnov, Neexistující 123', 'Kontakt')
    def test_ohrazenice_config(self):
        from pathlib import Path
        import json
        cfg = json.loads(Path('config/stations.json').read_text(encoding='utf-8'))
        kontakt = cfg['stations'][0]
        self.assertEqual(kontakt['id'], 'kontakt_turnov')  # keep Android compatibility
        self.assertTrue(kontakt['url'].endswith('/17038'))
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
