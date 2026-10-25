# FrameTV — простой пульт для Samsung The Frame

Управление телевизором Samsung The Frame (проверялось под 2020, `QE65LS03TAU`, Tizen 5.5)
**по домашней сети, без перепрошивки**:

- 🖼 Art Mode / 📺 ТВ одной кнопкой, включение (Wake-on-LAN) и полное выключение
- ⭐ избранные приложения (YouTube, Netflix, Кинопоиск, …) — запуск с телефона
- 🖼 картины: загрузить своё фото с паспарту, показать, удалить, яркость, слайд-шоу
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

## 5. Командная строка

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
```

Примеры автоматизаций (cron): утром — Art Mode, ночью — выключить:

```
0 7  * * *  /path/to/.venv/bin/frametv art
30 0 * * *  /path/to/.venv/bin/frametv off
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
`POST /api/art/brightness {"value":6}`, `POST /api/art/slideshow {"minutes":60}`.
Интерактивная документация: `http://<host>:8080/api/docs`.

## Разработка

```bash
pip install -e ".[dev]"
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
