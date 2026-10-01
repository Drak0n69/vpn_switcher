# Как обновить репозиторий через веб-интерфейс GitHub

1. Распакуйте архив `vpn_switcher_delivery_v2.zip`.
2. Откройте репозиторий `vpn_switcher` на GitHub.
3. Нажмите **Add file → Upload files**.
4. Перетащите содержимое папки проекта.
5. Если `.gitignore` не загружается как скрытый файл, загрузите `gitignore.txt`, а затем в GitHub переименуйте его в `.gitignore`.
6. Убедитесь, что в репозитории нет реальных `.vpn`, `.conf`, `.env`, `recipients.yml` и runtime-файлов.
7. Сделайте commit, например:

```text
Replace endpoint patching with private config delivery bot
```

## Что удалить из старого MVP

После загрузки новой версии старые файлы могут остаться в GitHub, потому что web upload не удаляет существующие файлы автоматически.

Их можно удалить вручную:

```text
app/cli.py
app/healthcheck.py
app/switcher.py
app/telegram.py
app/vpn_config.py
tests/test_vpn_config.py
data/output/
```

Они больше не участвуют в новом флоу.

## Какое описание поставить репозиторию

```text
Private Telegram delivery of regenerated Amnezia VPN configs after server failover
```
