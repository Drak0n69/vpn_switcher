# vpn_switcher

Минимальный сервис для переключения endpoint в экспортированных конфигурациях Amnezia VPN (`vpn://...`) и уведомления через Telegram.

Первая версия **не создаёт новый VPS и не переносит сервер AmneziaWG сама**. Сценарий такой:

1. администратор поднимает AWG на новом сервере с тем же серверным состоянием/peer'ами;
2. выполняет `/switch <новый-ip>` в Telegram или CLI-команду;
3. сервис меняет `hostName` и `Endpoint` во всех `.vpn` из `data/configs`;
   Имя файла значения не имеет: `denis-v.vpn`, `kirill-pc.vpn`, `phone.vpn` и т.д. обрабатываются одинаково;
4. новые файлы складываются в `data/output`;
5. бот пишет в группу результат.

Исходные `.vpn` не перезаписываются.

## Безопасность

`.vpn` содержит клиентские приватные ключи и PSK. Поэтому:

- `*.vpn`, `*.conf`, `.env` и `data/` исключены из Git;
- бот **не отправляет** готовые `.vpn` в Telegram;
- `/switch` работает только для `TELEGRAM_ADMIN_USER_IDS`;
- не публикуйте `.env` и реальные конфиги в issue/commit/log.

## Быстрый локальный тест без Telegram

Нужен Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp /path/to/client.vpn data/configs/
python -m app.cli inspect
python -m app.cli switch 198.51.100.20
python -m app.cli inspect --help
```

Результат появится в `data/output/`.

Проверить тесты:

```bash
pytest -q
```

## Telegram-бот через Docker

### 1. Создать бота

Создайте Telegram-бота через `@BotFather`, добавьте его в нужную группу и получите token.

```bash
cp .env.example .env
```

В `.env` сначала достаточно заполнить:

```dotenv
TELEGRAM_BOT_TOKEN=123456:ABC...
```

### 2. Узнать chat_id и user_id

Запустите сервис:

```bash
docker compose up -d --build
docker compose logs -f
```

В группе отправьте боту:

```text
/chatid
```

Он ответит:

```text
chat_id=-1001234567890
user_id=123456789
```

Остановите сервис, внесите значения в `.env`:

```dotenv
TELEGRAM_CHAT_ID=-1001234567890
TELEGRAM_ADMIN_USER_IDS=123456789
```

И перезапустите:

```bash
docker compose up -d
```

### 3. Положить исходные конфиги

```bash
mkdir -p data/configs data/output
cp /secure/path/*.vpn data/configs/
```

Файлы остаются только на сервере и не попадут в Git.

### 4. Переключить endpoint

В Telegram-группе:

```text
/status
/switch 203.0.113.42
```

Либо DNS hostname:

```text
/switch vpn.example.net
```

Новые `.vpn` появятся в:

```text
data/output/
```

## Health check

По умолчанию:

```dotenv
HEALTHCHECK_MODE=none
```

Можно включить простую проверку доступности IP/hostname:

```dotenv
HEALTHCHECK_MODE=ping
HEALTHCHECK_TIMEOUT_SECONDS=3
```

Важно: `ping` подтверждает только сетевую доступность узла. Он **не подтверждает успешный handshake AmneziaWG**. Проверку реального AWG-handshake стоит добавить отдельным этапом, когда будет понятна серверная схема Кирилла.

## Команды бота

- `/chatid` — показать `chat_id` и `user_id`;
- `/status` — текущее состояние;
- `/switch <ip|hostname>` — создать обновлённые `.vpn`;
- `/help` — помощь.

## Что дальше

Следующий шаг после проверки этого MVP:

- хранить endpoint как DNS-имя, чтобы пользователям больше не выдавать новые конфиги;
- подключить API DNS-провайдера и менять A-запись автоматически;
- добавить проверку реального AWG handshake;
- автоматизировать развёртывание AWG на новом VPS из резервной копии серверного состояния;
- после успешной проверки нового сервера переключать DNS и отправлять уведомление в Telegram.
