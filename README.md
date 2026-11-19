# ollama-cost

Koszt i saldo kredytu Ollama Cloud z oficjalnego API. Jedno polecenie, zero zależności.

Nod nie policzy tych kosztów sam: `ollama.com` jest tam dodane jako dostawca OpenAI-compatible, a dla takich Nod nie zna cen i pokazuje `No price`. Ten program czyta prawdziwe liczby z Ollamy.

## Instalacja

```bash
pipx install ollama-cost
```

albo, bez publikowania w PyPI, z tego katalogu:

```bash
pipx install .
```

## Klucz

Klucz robi się na <https://ollama.com/settings/keys>. Program czyta go w tej kolejności:

1. zmienna `OLLAMA_API_KEY`,
2. plik z `--key-file`,
3. `~/.config/ollama/api-key` (pierwsza niepusta linia).

## Użycie

```bash
ollama-cost                 # ostatnie 7 dni
ollama-cost --range 24h
ollama-cost --range 30d
ollama-cost --json          # surowe odpowiedzi API
ollama-cost --max-usd 60    # kod 3, gdy koszt przekracza próg
```

Przykład:

```
Zakres 7d, czas lokalny Europe/Warsaw
  od 2026-11-12 01:00 do 2026-11-19 01:05
  zapytania: 57 641
  tokeny: wejście 1.10 mld (cache 96%), wyjście 8.1 mln
  koszt: $47.69 (0.83 USD / 1000 zapytań)

Po modelach:
  deepseek-v4.1-flash:1017   32 900 zap.    $41.01  86%
  beam                       23 212 zap.     $6.68  14%

Kredyt:
  w planie: $12.50 z $60.00, zostało 21%, odnowienie 2026-12-15 10:30
  dokupione: $25.00
```

## Kody wyjścia

| Kod | Znaczenie |
| --- | --- |
| 0 | odczyt OK |
| 1 | błąd API lub sieci |
| 2 | brak klucza |
| 3 | przekroczony `--max-usd` |

Kod 3 jest po to, żeby dało się to wołać z crona, harmonogramu albo Noda i reagować na sam wynik.

## Co zwraca API

`GET /api/usage?range=24h|7d|30d&group_by=model` daje sumy i przedziały godzinowe lub dzienne: liczbę zapytań, tokeny wejścia, cache i wyjścia oraz koszt w USD. `GET /api/balance` daje saldo kredytu z planu i dokupionego. API nie zwraca pojedynczych zapytań, więc koszt jednego requestu to szacunek z tokenów.

Limity: `/api/balance` przyjmuje 10 zapytań na minutę. Nowe zużycie może pojawić się z opóźnieniem.

## Jako połączone CLI w Nodzie

Program czyta wyłącznie `OLLAMA_API_KEY` ze środowiska, nie dotyka plików użytkownika i nie potrzebuje katalogu domowego. Dzięki temu Nod może uruchamiać go w zamkniętym środowisku i podawać klucz z Vaulta, bez wkładania go do workspace.

Deklaracja dla Noda:

- źródło: PyPI, pakiet `ollama-cost`
- polecenie: `ollama-cost`
- zmienna: `OLLAMA_API_KEY`

## Rozwój

```bash
pipx install build
./build.sh
```
