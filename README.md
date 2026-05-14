# MRKT Bot

> ## ВАЖНО - читать до запуска
>
> Этот проект - **учебный**. Он опубликован как демонстрация архитектуры
> асинхронного торгового бота на Python: мульти-аккаунт, пул HTTP-клиентов,
> прокси, rate-limit, pub/sub, разделение по ролям, стратегии.
>
> **Бот работает с неофициальным/закрытым API сервисов
> [tgmrkt.io](https://tgmrkt.io) и [portal-market.com](https://portal-market.com).**
> У этих площадок **нет публичного API** и нет разрешения на автоматизацию.
> Любая автоматизация нарушает их Terms of Service.
>
> Запуск этого бота против боевых маркетов почти наверняка приведёт к:
>
> - бану аккаунта,
> - инвалидации `auth`-токена,
> - заморозке/потере средств и подарков,
> - возможным юридическим последствиям.
>
> **Не используйте этот код для торговли.** Изучайте архитектуру, читайте
> код, разбирайте паттерны - и всё. Автор использует/использовал бота
> исключительно на свой страх и риск и **никакой ответственности за
> последствия запуска третьими лицами не несёт.**

---

## Что это

Асинхронный арбитражный бот для маркетплейса TON-подарков **tgmrkt.io**,
с опциональной кросс-проверкой цен через **portal-market.com** и управлением
из Telegram.

Бот умеет:

- держать активные **buy-ордера** чуть ниже флора в выбранных коллекциях;
- отправлять и снимать **офферы** по фиду маркета;
- мгновенно **выкупать** листинги, появившиеся ниже расчётной цены (_feed sniper_); **Нестабилен**
- автоматически **выставлять купленное** на продажу;
- репортить старт/стоп/итоги сессии в Telegram.

Поддерживается **мульти-аккаунт** с разделением по ролям, индивидуальными
прокси и собственными rate-limit'ами.

---

## Стек

- **Python 3.11+** (минимум 3.9)
- `asyncio` - корутины везде
- `curl-cffi` - HTTP-клиент с TLS-fingerprint браузера
- `aiogram 2.x` - Telegram-бот
- `pydantic` / `pydantic-settings` - модели и конфиг
- `tenacity` - retry с backoff
- `pyyaml` - конфиг аккаунтов

---

## Установка

```bash
git clone <repo-url>
cd "mrkt_bot"

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt  # либо вручную:
pip install "aiogram>=2.25,<3.0" "curl-cffi>=0.7" "pydantic>=2.0" \
            "pydantic-settings>=2.0" "python-dateutil>=2.9" \
            "pyyaml>=6.0" "tenacity>=8.2"
```

---

## Конфигурация

### 1. `.env`

```bash
cp .env.example .env
```

Минимально обязательные:

| Переменная    | Назначение                                               |
| ------------- | -------------------------------------------------------- |
| `BOT_TOKEN`   | токен Telegram-бота от `@BotFather`                      |
| `BOT_CHAT_ID` | id чата для нотификаций (для группы - **отрицательный**) |

Полезные:

| Переменная             | Что делает                                                |
| ---------------------- | --------------------------------------------------------- |
| `BOT_CHANNEL`          | канал для дублирования сообщений (`@channel`)             |
| `SKIP_PORTALS`         | `true` - не использовать Portals, `AUTH_PORTALS` не нужен |
| `AUTH_PORTALS`         | заголовок `Authorization: tma user=...` от Portals        |
| `PROFIT_PERCENT`       | целевая маржа для ордеров (`0.15` = 15%)                  |
| `PROFIT_PERCENT_OFFER` | целевая маржа для офферов                                 |
| `MIN_PRICE_TON`        | нижняя граница цены ордера                                |
| `MAX_PRICE_TON`        | верхняя граница цены ордера                               |
| `MAX_PRICE_OFFER_TON`  | потолок цены оффера                                       |
| `MAX_COLLECTION_STOCK` | сколько штук одной коллекции максимум держать             |
| `OFFER_EXPIRE_MINUTES` | через сколько декланить свой неотвеченный оффер           |
| `TIME_SLEEP`           | пауза между ордер-циклами, секунд                         |
| `LOG_LEVEL`            | `DEBUG` / `INFO` / `WARNING` / `ERROR`                    |
| `LOG_FILE`             | путь к файлу логов (`logs/mrkt.log`)                      |
| `ACCOUNTS_FILE`        | путь к YAML с аккаунтами (`accounts.yaml`)                |
| `CONVERT_USDT`         | курс TON→USDT для красивого репорта прибыли               |

### 2. `accounts.yaml`

```bash
cp accounts.yaml.example accounts.yaml
```

#### Роли

| Роль      | Что делает                                      |
| --------- | ----------------------------------------------- |
| `SCANNER` | read-only: фид, коллекции, листинги, top-orders |
| `ORDERER` | создаёт / отменяет ордера на покупку            |
| `OFFERER` | создаёт / отменяет / декланит офферы            |
| `BUYER`   | прямой выкуп с фида (`buy_gift`)                |
| `SELLER`  | выставляет купленное на продажу                 |
| `WALLET`  | баланс, история, активности                     |

Один аккаунт может нести сколько угодно ролей. Пул сам маршрутизирует запросы.

#### Минимум - 1 аккаунт

```yaml
accounts:
  - name: main
    auth_token: "AUTH_TOKEN_FROM_BROWSER"
    roles: [SCANNER, ORDERER, OFFERER, BUYER, SELLER, WALLET]
    rate_limit_rps: 20.0
```

#### Рекомендованно - 2 аккаунта

Сканер на отдельном IP параллельно молотит фид, трейдер пишет ордера/офферы:

```yaml
accounts:
  - name: scanner
    auth_token: "TOKEN_1"
    roles: [SCANNER, WALLET]
    proxy: "socks5://user:pass@proxy-1:1080"
    rate_limit_rps: 20.0

  - name: trader
    auth_token: "TOKEN_2"
    roles: [ORDERER, OFFERER, BUYER, SELLER]
    proxy: "socks5://user:pass@proxy-2:1080"
    rate_limit_rps: 20.0
```

> `auth_token` берётся из браузера: открой `tgmrkt.io` → DevTools →
> Network → любой запрос на `api.tgmrkt.io/v1/...` → заголовок `auth`.
> **Не публикуй и не коммить этот токен - это ключ от твоего аккаунта.**

Полный пример с 4 аккаунтами - в `accounts.yaml.example`.

---

## Запуск

Из директории `mrkt_bot/`:

```bash
python __main__.py
```

Что происходит при старте:

1. Поднимаются HTTP-сессии на каждый аккаунт (с прокси и rate-limit).
2. Опционально подключается Portals (если `SKIP_PORTALS=false`).
3. Стартует Telegram-поллер.
4. В чат прилетает `Session #N started` - бот ждёт `/start`.

---

## Управление через Telegram

В чате с ботом (`BOT_CHAT_ID` из `.env`):

| Команда    | Действие                                                                  |
| ---------- | ------------------------------------------------------------------------- |
| `/start`   | Запустить все стратегии (orders / offers / feed sniper / decline-offers). |
| `/stop`    | Остановить стратегии, отменить ордера, прислать репорт сессии.            |
| `/balance` | Подсказка по управлению.                                                  |

Сообщения из любых других чатов игнорируются.
`Ctrl+C` в консоли = graceful shutdown с финальным репортом.

---

## Структура проекта

```
mrkt_bot/
├── __main__.py             # entrypoint:  python -m mrkt_bot
├── app.py                  # Application - wiring + lifespan
├── bus.py                  # async pub/sub шина событий
├── bootstrap/
│   ├── settings.py         # pydantic-settings (.env)
│   ├── accounts.py         # YAML → list[AccountConfig]
│   └── logging.py          # JSON-файл + цветной stdout
├── transport/
│   ├── client.py           # MarketClient (одна сессия, retry, rate-limit, proxy)
│   ├── rate_limit.py       # async TokenBucket
│   ├── errors.py           # MarketError, AuthError, RateLimitedError
│   └── urls.py             # реестр endpoint'ов API
├── pool/
│   ├── account.py          # AccountConfig, Role (Flag)
│   └── pool.py             # AccountPool - round-robin + sticky routing
├── services/               # тонкие обёртки над MarketClient
│   ├── orders.py
│   ├── offers.py
│   ├── feed.py
│   ├── collections.py
│   ├── activities.py
│   ├── wallet.py
│   └── trading.py
├── domain/
│   ├── models.py           # pydantic-модели API
│   ├── events.py           # discriminated-union событий
│   └── money.py            # Nano/Ton конверторы
├── state/                  # потокобезопасные in-memory книги
│   ├── orders_book.py
│   ├── offers_book.py
│   ├── balance.py          # BalanceTracker с asyncio.Lock
│   └── inventory.py
├── strategies/
│   ├── orders.py           # цикл выставления ордеров
│   ├── offers.py           # цикл офферов по фиду
│   ├── feed_sniper.py      # мгновенный выкуп
│   └── decline_offers.py   # синк / декланинг офферов
├── scanners/
│   ├── gap.py              # gap-арбитраж
│   └── price_impact.py     # анализ price-pump
└── integrations/
    ├── portals.py          # PortalsClient (read-only флор)
    └── telegram.py         # один Bot + очередь сообщений
```

## Как это устроено

```
            ┌─────────────┐
            │ AccountPool │  ◄── role-based routing, sticky-by-collection
            └──────┬──────┘
                   │ acquire(role)
   ┌───────────────┼───────────────────┐
   ▼               ▼                   ▼
MarketClient   MarketClient        MarketClient
 scanner         trader              ...
(proxy 1)      (proxy 2)
   │               │                   │
   └─► token-bucket rate-limit ◄──────┘
                   │
                   ▼
           tgmrkt.io v1 API
```

Стратегия запрашивает у пула клиент с нужной ролью, вызывает сервис
(`OrdersService`, `OffersService`, …), ответ кладётся в общую книгу
(`OrdersBook`, `OffersBook`, `BalanceTracker`). Все книги защищены
`asyncio.Lock`'ами, поэтому стратегии безопасно работают параллельно.

---

## Логи

- `stdout` - человекочитаемый формат: `HH:MM:SS [LEVEL] mrkt.<logger>  message`
- `logs/mrkt.log` - JSON-логи с ротацией (10MB × 10), удобно скармливать в Loki / Elastic
- Иерархия логгеров:
  - `mrkt.app` - жизненный цикл приложения
  - `mrkt.client.<account>` - HTTP-вызовы конкретного аккаунта
  - `mrkt.strategy.<name>` - события стратегий
  - `mrkt.state` - изменения in-memory книг
  - `mrkt.tg` - Telegram

Поднять детальность - выставь `LOG_LEVEL=DEBUG` в `.env`.

---

## FAQ

**Где взять `auth_token`?**
`tgmrkt.io` → DevTools → Network → запрос на `api.tgmrkt.io/v1/...` → заголовок `auth`.

**Бот молчит после `/start`.**
Проверь, что `BOT_CHAT_ID` совпадает с id текущего чата (`@RawDataBot`,
`@userinfobot`). Подними `LOG_LEVEL=DEBUG`, посмотри `Unauthorized` / `403`
в логах.

**Хочу запустить без Portals.**
Поставь `SKIP_PORTALS=true` в `.env`. Цены тогда сравниваются только
с MRKT-флором.

**Как добавить третий аккаунт?**
Допиши блок в `accounts.yaml`, перезапусти бот - пул подхватит роли сам.

**Бот ловит rate-limit.**
Снизь `rate_limit_rps` у проблемного аккаунта или раскидай роли по
дополнительным аккаунтам с отдельными прокси.

---

## Безопасность

- `.env`, `accounts.yaml`, `logs/`, `*.session` - обязаны быть в `.gitignore`. **Никогда не коммить токены.**
- Если `.env` случайно попал в репозиторий - немедленно ротируй токены
  (перевыпусти `auth` через tgmrkt.io, пересоздай Telegram-бота).
- На сервере держи конфиги в `chmod 600`.

---

## Лицензия и ответственность

Код опубликован **только для изучения архитектуры**.

Использование против боевых API `tgmrkt.io` / `portal-market.com`
нарушает их Terms of Service, ведёт к бану аккаунта и потере средств.
Всё, что вы делаете с этим кодом против реальных сервисов - **на ваш
страх и риск**. Автор ответственности не несёт.
 
 
