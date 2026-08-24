# WPT-Manager – pokyny pro vývoj

## Účel projektu

WPT-Manager slouží k importu waypointů z GPX souborů exportovaných z Mapy.com, jejich úpravě a následnému exportu do GPX kompatibilního s OsmAnd.

Waypoint postupně podporuje tato data:

- `name`
- `latitude`
- `longitude`
- UUID
- `icon`
- `color`
- `background`
- krátkou poznámku `note`
- podrobný `comment`

## Současná architektura

Projekt je Python balíček `wpt_manager` a používá jednoduché členění podle odpovědností:

- `wpt_manager/main.py` obsahuje vstupní funkci aplikace.
- `wpt_manager/__main__.py` umožňuje spuštění balíčku pomocí `python -m wpt_manager`.
- `wpt_manager/models/` obsahuje datové modely. Aktuálně je zde datová třída `Waypoint`.
- `wpt_manager/io/` obsahuje import a export souborů. Aktuálně zahrnuje GPX reader, GPX writer a výjimku pro chyby při čtení GPX.
- `wpt_manager/validation/` obsahuje validační logiku waypointů.
- `tests/` obsahuje pytest testy odpovídající jednotlivým částem balíčku.
- `tests/data/` obsahuje vstupní soubory používané v testech, včetně GPX exportu z Mapy.com.
- `pyproject.toml` obsahuje build a základní metadata projektu.

Zachovávej tuto architekturu. Nevytvářej nové vrstvy, moduly nebo abstrakce bez konkrétní potřeby vycházející z požadované funkcionality.

## Pravidla pro další vývoj

- Používej Python 3.14 nebo novější.
- Veřejné funkce, metody, návratové hodnoty a datové struktury opatřuj type hints.
- Pro práci s cestami používej `pathlib`, nikoli `os.path`.
- Datové modely umisťuj do `wpt_manager/models/`.
- Import a export souborů umisťuj do `wpt_manager/io/`.
- Validaci umisťuj do `wpt_manager/validation/`.
- Pro práci s XML používej standardní `xml.etree.ElementTree`, pokud neexistuje konkrétní důvod použít externí knihovnu.
- Každá nová funkcionalita musí mít odpovídající pytest testy.
- Před dokončením každé změny spusť všechny pytest testy.
- Nepřidávej externí dependency bez skutečné potřeby.
- Adresář `.venv` se necommituje.
- Změny prováděj po malých logických krocích.

## Testování

Testy patří do `tests/` a používají pytest. Struktura a názvy testů mají odpovídat testovaným částem balíčku. Testovací data ukládej do `tests/data/`.

Před dokončením změny spusť celou testovací sadu:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Změna není dokončená, pokud nové nebo existující testy neprocházejí.
