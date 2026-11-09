# DSNet consent renewal

Automatycznie odnawia zgodę na zakwaterowanie w panelu DSNet MS AGH
(https://panel.dsnet.agh.edu.pl/en/accommodation/#acc_consent) **co 48 godziny i 10 minut**.
Działa na Linuxie i Windowsie. Same dane logowania **nigdy nie trafiają do repo**.

## Wymagania

- Python 3.8+ (tylko biblioteka standardowa — bez `pip install`)
- Linux: systemd (opcjonalnie; bez niego deploy drukuje linię crona)
- Windows: PowerShell 5.1+ (Task Scheduler)

## Szybki start (bez klonowania repo)

**Linux / macOS:**

```bash
curl -sSL https://raw.githubusercontent.com/almostlight/yes-please-collect-my-mail-for-me/main/setup_credentials.sh | bash
curl -sSL https://raw.githubusercontent.com/almostlight/yes-please-collect-my-mail-for-me/main/deploy.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/almostlight/yes-please-collect-my-mail-for-me/main/setup_credentials.ps1 | iex
irm https://raw.githubusercontent.com/almostlight/yes-please-collect-my-mail-for-me/main/deploy.ps1 | iex
```

> Uwaga: adresy `raw.githubusercontent.com` działają dopiero po `git push` do gałęzi `main`.

## Z klona repo

```bash
git clone git@github.com:almostlight/yes-please-collect-my-mail-for-me.git
cd yes-please-collect-my-mail-for-me
./setup_credentials.sh     # Linux — pyta o e-mail i hasło
./deploy.sh                # instaluje harmonogram co 48h10min
```

```powershell
.\setup_credentials.ps1    # Windows
.\deploy.ps1
```

## Wprowadzanie danych logowania

`setup_credentials.sh` / `setup_credentials.ps1` pyta interaktywnie o e-mail i hasło
(hasło nie jest wyświetlane) i zapisuje je **poza repo**:

| System | Plik |
|---|---|
| Linux/macOS | `~/.config/dsnet-consent/credentials.env` (0600, katalog 0700) |
| Windows | `%APPDATA%\dsnet-consent\credentials.env` (ACL: tylko bieżący użytkownik) |

Format pliku: `DSNET_EMAIL=...` / `DSNET_PASSWORD=...`.
Skrypt odmawia nadpisania istniejącego pliku bez `--force` / `-Force`.

Alternatywnie — zmienne środowiskowe (bez pliku):

```bash
export DSNET_EMAIL=twoj@email.pl DSNET_PASSWORD=twoje-haslo
```

`renew_consent.py` na Linuxie **odmówi uruchomienia**, jeśli plik credentials ma
uprawnienia czytelne dla grupy/innych (mniej niż 0600). Pliki z danymi są też
zablokowane w `.gitignore` (`credentials.env`, `*.credentials`, `*.secret`).

## Jak to działa

`renew_consent.py` loguje się do panelu (formularz `/login_check`), otwiera
`/en/accommodation/`, znajduje kontrolkę zgody w sekcji `#acc_consent`, wysyła
ją (z tokenami CSRF i zaznaczonymi checkboxami) i sprawdza, czy zgoda przestała
być „oczekująca”. Przy awarii zapisuje migawkę strony do `last_failure.html`.

- `--dry-run` — test bez wysyłania formularza zgody
- `--if-due` — wykonaj tylko, jeśli od ostatniego sukcesu minęło ≥ 48h10min
- kody wyjścia: `0` OK/nie czas, `1` błąd odnowienia, `2` błąd konfiguracji (brak danych)

## Harmonogram (48h10min = 173400 s)

- **Linux:** systemd user timer `dsnet-consent.timer` (`OnUnitActiveSec=173400`,
  `Persistent=true`), usługa `dsnet-consent.service`. Bez systemd deploy drukuje
  zamiennik: `*/10 * * * * ... renew_consent.py --if-due` (odstęp wymusza sam skrypt).
- **Windows:** zadanie Task Scheduler `DSNet-Consent-Renewal` — start za 5 min,
  potem powtórzenie co 48h10min, uruchamia `pythonw.exe renew_consent.py --if-due`.

Oba deploy-e są **idempotentne** (można uruchamiać wielokrotnie).

## Sprawdzanie i logi

```bash
python3 renew_consent.py --dry-run                 # test ręczny
systemctl --user list-timers dsnet-consent.timer   # następne uruchomienie (Linux)
systemctl --user status dsnet-consent.service      # ostatni przebieg (Linux)
```

Logi i stan (poza repo): `~/.local/state/dsnet-consent/` (Linux) lub
`%LOCALAPPDATA%\dsnet-consent\` (Windows) — `renew_consent.log`, `last_success`,
`last_failure.html`.

## Usuwanie (undeploy)

```bash
./undeploy.sh    # lub: curl -sSL <raw>/undeploy.sh | bash
```
```powershell
.\undeploy.ps1   # lub: irm <raw>/undeploy.ps1 | iex
```

Usuwa tylko harmonogram/zadanie. Dane logowania i logi zostają — usuń ręcznie
katalogi `~/.config/dsnet-consent` i `~/.local/state/dsnet-consent`
(`%APPDATA%\dsnet-consent`, `%LOCALAPPDATA%\dsnet-consent` na Windowsie), jeśli chcesz.

## Zmienne środowiskowe (opcjonalne)

| Zmienna | Znaczenie | Domyślnie |
|---|---|---|
| `DSNET_EMAIL` / `DSNET_PASSWORD` | dane logowania zamiast pliku | — |
| `DSNET_CREDENTIALS_FILE` | własna ścieżka pliku credentials | jw. |
| `DSNET_RAW_BASE` | adres raw, z którego deploy pobiera skrypty | `raw.githubusercontent.com/almostlight/.../main` |
| `DSNET_INSTALL_DIR` | gdzie deploy odkłada `renew_consent.py` przy piped | `~/.local/share/dsnet-consent` |
| `DSNET_BASE_URL` | inny panel (np. testowy) | `https://panel.dsnet.agh.edu.pl` |
| `RENEW_INTERVAL_SECONDS` | własny odstęp | `173400` (48h10min) |

## Pliki

```
renew_consent.py        # główny skrypt (login → zgoda → weryfikacja)
setup_credentials.sh    # dane logowania, Linux (pipe-safe)
setup_credentials.ps1   # dane logowania, Windows (iex-safe)
deploy.sh               # deploy, Linux (systemd lub cron) — pipe-safe
deploy.ps1              # deploy, Windows (Task Scheduler) — iex-safe
undeploy.sh             # usunięcie harmonogramu, Linux — pipe-safe
undeploy.ps1            # usunięcie zadania, Windows — iex-safe
systemd/                # jednostki dsnet-consent.service/.timer (używane przez deploy.sh)
```
