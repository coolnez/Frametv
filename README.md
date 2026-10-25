# FrameTV — простой пульт для Samsung The Frame

Управление телевизором Samsung The Frame (проверялось под 2020, `QE65LS03TAU`, Tizen 5.5)
**по домашней сети, без перепрошивки**:

- 🖼 Art Mode / 📺 ТВ одной кнопкой, включение (Wake-on-LAN) и полное выключение
- ⭐ избранные приложения (YouTube, Netflix, Кинопоиск, …) — запуск с телефона
- 🖼 картины: загрузить своё фото с паспарту, показать, удалить, яркость, слайд-шоу
- 🏛 каталоги: работы **Samsung** на телевизоре + открытые коллекции музеев мира
  (Art Institute of Chicago, Metropolitan Museum, Cleveland Museum of Art) — поиск и показ в один тап
- 🎮 пульт: стрелки, OK, назад, домой, громкость
- веб-страница для телефона + командная строка + JSON API для автоматизаций

> Про перепрошивку: кастомных прошивок для Tizen 2020 нет, и ставить их опасно.
> Как безопасно обновить официальную прошивку (по сети или с USB) — в [docs/firmware.md](docs/firmware.md).

## 1. Подготовка телевизора

1. **Фиксированный IP**: в роутере закрепите IP за телевизором (DHCP-резервация), например `192.168.1.50`.
   IP виден в `Настройки → Общие → Сеть → Состояние сети`.
2. **Включение по сети**: `Настройки → Общие → Сеть → Экспертные настройки → Включение с мобильного` → **Вкл**.
3. **MAC-адрес**: `Настройки → Поддержка → Об этом ТВ`. Берите проводной MAC, если ТВ подключён кабелем, иначе Wi-Fi MAC.
4. Компьютер/Raspberry Pi с программой должен быть в той же сети.

## 2. Установка

Нужен Python 3.10+ (Windows, macOS, Linux, Raspberry Pi).

```bash
git clone <этот репозиторий> frametv && cd frametv
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install .
```

## 3. Сопряжение

```bash
frametv setup 192.168.1.50 --mac AA:BB:CC:DD:EE:FF
```

На экране ТВ появится запрос — нажмите **«Разрешить»**. Токен сохранится в `~/.frametv/token.txt`,
повторно спрашивать не будет. (Если запрос не появился: `Настройки → Общие → Диспетчер внешних
устройств → Диспетчер подключения устройств` — разрешите доступ.)

## 4. Веб-пульт для телефона

```bash
frametv serve            # http://<IP компьютера>:8080 — откройте с телефона
frametv serve --demo     # попробовать интерфейс без телевизора
```

На iPhone/Android: «Поделиться → На экран “Домой”» — получится иконка-приложение.

Вкладка **Приложения** показывает всё, что установлено на ТВ; ☆ добавляет приложение
на главный экран пульта. Так добавляются Кинопоиск, Okko, Wink, Start, ivi и т.д. — их ID
различаются по регионам, поэтому берутся прямо с вашего телевизора.

Защитить доступ паролем: `FRAMETV_API_TOKEN=секрет frametv serve` — страница спросит его один раз.

## 5. Каталоги картин

| Источник | Что это | Ключ API |
|---|---|---|
| `samsung` | Работы Samsung Art Store и предустановленные картины, **уже находящиеся на ТВ** (ID `SAM-…`) | не нужен |
| `aic` | Art Institute of Chicago — работы в public domain | не нужен |
| `met` | The Metropolitan Museum of Art — работы в public domain (Open Access) | не нужен |
| `cleveland` | Cleveland Museum of Art — работы с лицензией CC0 | не нужен |

- Каталог Samsung Art Store локальный API показывает только то, что уже скачано на ТВ;
  купить/подписаться и скачать новые работы Samsung можно только в самом телевизоре
  (раздел Art), если сервис доступен в вашем регионе.
- Картина из музея скачивается, при необходимости уменьшается до 3840×2160 (`pip install ".[images]"`),
  загружается в «Мои фото» и показывается. Повторная отправка той же работы не загружает её заново.
- Берутся только работы в public domain / CC0 — их можно законно показывать дома.

Проверить, что музеи доступны из вашей сети (телевизор не нужен):

```bash
frametv catalog-check
# [OK ] aic        Water Lilies (412 KB)
# [OK ] met        ...
# [OK ] cleveland  ...
```

## 6. Командная строка

```bash
frametv status                    # включён ли, Art Mode, текущая картина
frametv art                       # режим картины
frametv tv                        # обычный ТВ
frametv on | off                  # включить / выключить полностью
frametv apps                      # все приложения с их ID
frametv fav-add 3201710015067     # в избранное по ID из `frametv apps`
frametv launch youtube            # по имени из избранного или по ID
frametv key home                  # кнопка пульта (up/down/enter/volup/...)
frametv art-upload photo.jpg --matte shadowbox_polar
frametv art-list
frametv brightness 6              # яркость Art Mode 1..10
frametv slideshow 60              # менять картину каждый час (0 — выкл)
frametv samsung-art               # работы Samsung на ТВ
frametv art-search met "van gogh" # поиск в музее: aic | met | cleveland
frametv art-send met 436532       # показать работу по ID из поиска
frametv art-random aic landscape  # случайная работа по теме
```

Примеры автоматизаций (cron): утром — Art Mode, ночью — выключить:

```
0 7  * * *  /path/to/.venv/bin/frametv art
30 0 * * *  /path/to/.venv/bin/frametv off
0 9  * * *  /path/to/.venv/bin/frametv art-random met impressionism --matte shadowbox_polar
```

## Настройки

`~/.frametv/config.json` (создаётся `frametv setup`) или переменные окружения:

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `FRAMETV_HOST` | IP телевизора | — |
| `FRAMETV_MAC` | MAC для Wake-on-LAN | — |
| `FRAMETV_PORT` | 8002 (WSS) или 8001 | 8002 |
| `FRAMETV_TOKEN_FILE` | файл токена сопряжения | `~/.frametv/token.txt` |
| `FRAMETV_API_TOKEN` | пароль веб-пульта | пусто (без пароля) |
| `FRAMETV_CONFIG` | путь к config.json | `~/.frametv/config.json` |

## HTTP API

`GET /api/status`, `POST /api/power/on|off`, `POST /api/mode/art|tv`, `POST /api/key/{KEY}`,
`GET /api/apps`, `GET|POST /api/favorites`, `DELETE /api/favorites/{id}`,
`POST /api/apps/{id}/launch|close`, `GET /api/art`, `POST /api/art/{id}/show`,
`POST /api/art/upload?filename=x.jpg&matte=none` (тело — сам файл), `DELETE /api/art/{id}`,
`POST /api/art/brightness {"value":6}`, `POST /api/art/slideshow {"minutes":60}`,
`GET /api/catalogs`, `GET /api/catalogs/samsung/items`, `GET /api/art/{id}/thumbnail`,
`GET /api/catalogs/{aic|met|cleveland}/search?q=monet`,
`POST /api/catalogs/{source}/items/{id}/send {"matte":"none"}`, `POST /api/catalogs/{source}/random {"query":"sea"}`.
Интерактивная документация: `http://<host>:8080/api/docs`.

## Разработка

```bash
pip install -e ".[dev]"   # включает Pillow
pytest
```

Устройство проекта — [docs/architecture.md](docs/architecture.md).

## Частые проблемы

| Симптом | Что сделать |
|---|---|
| `status` → `unreachable` | ТВ в глубоком сне или другой IP. `frametv on`, проверьте IP/резервацию. |
| `on` не включает | Включите «Включение с мобильного»; проверьте MAC (проводной vs Wi-Fi). |
| Каждый раз спрашивает «Разрешить» | Проверьте, что `~/.frametv/token.txt` создаётся и не удаляется. |
| Приложение не запускается | ID из `frametv apps`; часть приложений запускается только с `NATIVE_LAUNCH`. |
| После обновления прошивки не работает Art | Удалите токен, повторите `frametv setup`. |
| `catalog-check` → `ERR` | Нет доступа к сайту музея из вашей сети (фильтр, VPN, блокировка) — остальные каталоги работают независимо. |
| Картина из музея не загружается | Установите `pip install ".[images]"` — большие оригиналы будут уменьшены до 4K. |
