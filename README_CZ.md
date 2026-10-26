# SKYSPY FUEL – automatické ceny bez API

Balíček obsahuje **sběrač cen**, automatické spouštění přes GitHub Actions,
veřejnou stránku GitHub Pages a zdrojový kód přidaný do SKYSPY Android.

## Stanice

1. Kontakt Turnov – Svobodova 2050, mBenzin.cz
2. RobinOil Turnov – Palackého 182, mBenzin.cz
3. Tank ONO Cvikov – oficiální mobilní ceník Tank ONO

U mBenzin jde o ceny nahlášené uživateli. ONO datum zveřejnění na své
mobilní stránce neuvádí; takové ceny jsou v JSON označeny `unknown_date`.
**Čas načtení stránky není totéž jako datum změny ceny.**

## 1. Jak zprovoznit automatické získávání cen

1. Vytvoř na GitHubu **veřejný** repozitář `skyspy-fuel` (bez automatického README).
2. Nahraj do něj **celý obsah** složky `skyspy_fuel_project` včetně skryté
   `.github/workflows/refresh-fuel.yml`, složek `config`, `docs`, `tests` a Python souborů.
   Můžeš použít GitHub Desktop (Add existing repository → Publish repository),
   nebo přes terminál v této složce:

   ```bash
   git init
   git add .
   git commit -m "SKYSPY FUEL"
   git branch -M main
   git remote add origin https://github.com/TVUJ_UCET/skyspy-fuel.git
   git push -u origin main
   ```

   Pokud GitHub hlásí chybějící identitu, nastav v Gitu uživatelské jméno
   a e-mail. Do příkazu doplň svůj účet GitHub.
3. Na stránce repozitáře otevři **Settings → Pages → Build and deployment → Source → GitHub Actions**.
4. Otevři **Actions → SKYSPY FUEL - aktualizace cen → Run workflow**.
   První běh publikuje výsledky. Další se spouštějí kolem **17. minuty každé hodiny**.
5. Ve webovém prohlížeči zkontroluj:
   - `https://TVUJ_UCET.github.io/skyspy-fuel/` – kontrolní stránka cen
   - `https://TVUJ_UCET.github.io/skyspy-fuel/prices.json` – výstup pro Android

### Důležité

- Pokud zdroj nepovoluje robotům čtení, odpoví chybou, nebo změní HTML,
  sběrač cenu **nevymýšlí**. U příslušné stanice se zobrazí `--,--`.
- `robots.txt` se kontroluje před každým stažením. Respektuj i podmínky
  jednotlivých webů. Sběrač neobchází přihlášení ani ochranu proti botům.
- Automatické spouštění na GitHubu se může opozdit; stav běhu vidíš v Actions.
- Z webů pro **Kontakt** a **RobinOil** získáváme spotřebitelsky hlášené ceny;
  nemusí odpovídat aktuální ceně na stojanu.
- V tomto prostředí nešlo zdrojové weby přímo stáhnout z Pythonu; parsery
  byly ověřené lokálními jednotkovými testy, ale skutečná dostupnost stránek
  z GitHub Actions se musí ověřit při prvním spuštění. Není tedy tvrzeno,
  že automatické čtení už běží na internetu.

## 2. Jak zapnout zobrazení v SKYSPY Android

Balíček `SKYSPY_ANDROID_FUEL_SOURCE.zip` obsahuje celý Android projekt založený
na pozdější dostupné verzi `SKYSPY_ANDROID_NASTAVENI_TAPO_IP.zip`.

1. Rozbal ZIP a projekt otevři v **Android Studio**.
2. Projekt vyžaduje původní uživatelem dodaný archiv `Bahnschrift-Font-Family*.zip`
   ve složce Downloads/Plocha či vedle projektu. Fonty nejsou v tomto balíčku
   (viz stávající instrukce projektu).
3. Sestav a nainstaluj APK stejně jako dosud.
4. Na hlavní obrazovce se panel kvality vzduchu **po 15 sekundách střídá**
   s panelem PALIVA. Klepnutím do panelu můžeš přepnout ručně.
5. Když se zobrazí PALIVA, klepni v pravém dolním rohu na **NASTAVIT**.
6. Vlož adresu `https://TVUJ_UCET.github.io/skyspy-fuel/prices.json`
   a dej **Uložit**.

Aplikace každých 15 minut stáhne malý JSON. Když je zdrojový JSON starší
24 hodin, údaje se skryjí. Staré jednotlivé ceny jsou označeny `*`.
Ceny ONO bez publikovaného data jsou označeny `†`. Nejlevnější platná cena
je zvýrazněná zeleně. Neaktualizují se data během sleep mode na obrazovce,
ale další obnovení běží v běžném režimu aplikace.

## 3. Samostatné spuštění sběrače pro vývoj

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python fuel_scraper.py
```

Výstup: `docs/prices.json`. Toto je veřejný datový soubor, ne vyžadovaná
oficiální API služba. Pokud web začne blokovat scraping, změň zdroj po
ověření oprávnění a aktualizuj parser, **nikoliv** náhodný kus HTML.

## Struktura výstupu

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-26T18:00:00+01:00",
  "timezone": "Europe/Prague",
  "unit": "Kč/l",
  "stations": [
    {
      "id": "kontakt_turnov",
      "name": "Kontakt Turnov",
      "checked_at": "2026-10-26T18:00:00+01:00",
      "natural95": {"price": null, "reported_date": null, "status": "missing"},
      "diesel": {"price": null, "reported_date": null, "status": "missing"}
    }
  ]
}
```

Výše uvedený JSON je pouze ukázka struktury. Není to aktuální cena.

## Co se v Androidu změnilo

- `app/src/main/java/cz/skyspy/app/data/FuelPricesRepository.kt` – čtení JSON, ukládání URL
- `app/src/main/java/cz/skyspy/app/ui/components/FuelAirPanel.kt` – grafický panel
- `app/src/main/java/cz/skyspy/app/ui/screens/WeatherScreen.kt` – výměna jednoho
  `AirQualityWidget` za `FuelAirPanel`; NEWS ticker, radary, hodiny, počasí
  a spodní hodinová předpověď zůstávají rozložením nedotčené.

Automatické stahování ještě vyžaduje první nasazení GitHub repozitáře
pod tvým účtem. V tomto balíčku není hotové APK a projekt není sestavený
na fyzickém zařízení.
