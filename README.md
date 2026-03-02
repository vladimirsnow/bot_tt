# Telegram бот: TikTok, Reels, Shorts

Бот читает сообщения в группе и автоматически отправляет медиа из ссылок:

- TikTok: видео без водяного знака
- фото-карусель (если в TikTok посте фотографии)
- Instagram Reels: видео
- YouTube Shorts: видео
- отправка в Telegram сначала идет напрямую по URL (быстрее), локальное скачивание только как fallback
- после отправки медиа удаляются только локальные файлы на ПК (в Telegram сообщения остаются)

## Краткий гайд по установке

### Windows 11

Что скачать:

1. Python 3.12+ с https://www.python.org/downloads/windows/ (при установке включите `Add python.exe to PATH`)
2. FFmpeg (например, через `winget install Gyan.FFmpeg` в PowerShell)

Фул-команда (скачать + установить + применить `AUTO_START`):

```powershell
git clone REPO_URL tiktok-bot
cd tiktok-bot
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
```

После этого:

1. Откройте `.env`
2. Укажите `BOT_TOKEN=...`
3. Поставьте `AUTO_START=true` или `AUTO_START=false`
4. Запустите снова `.\bootstrap.ps1` (применит автозапуск по флагу)

### Linux (Pop!_OS / Ubuntu)

Что установить:

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg curl
```

Фул-команда (скачать + установить + применить `AUTO_START`):

```bash
git clone REPO_URL tiktok-bot
cd tiktok-bot
./bootstrap.sh
```

После этого:

1. Откройте `.env`
2. Укажите `BOT_TOKEN=...`
3. Поставьте `AUTO_START=true` или `AUTO_START=false`
4. Запустите снова `./bootstrap.sh` (применит автозапуск по флагу)

### Один файл для включения/выключения автозапуска

В `.env` есть поле:

```env
AUTO_START=true
```

- `AUTO_START=true` -> бот включается в автозапуск
- `AUTO_START=false` -> автозапуск отключается

После изменения значения просто перезапустите bootstrap:

- Linux: `./bootstrap.sh`
- Windows: `.\bootstrap.ps1`

## Тихий запуск (без открытой консоли)

Добавлены скрипты для запуска в фоне с автозапуском:

- Linux: `./start_hidden.sh`
- Windows PowerShell: `.\start_hidden.ps1`
- Windows double-click: `start_hidden.bat`

Что делают эти скрипты:

- автоматически ставят `AUTO_START=true` в `.env`
- тихо запускают bootstrap (установка зависимостей + автозапуск)
- запускают бота в фоне без открытого окна терминала

Важно: это не «невидимый» процесс для ОС. В `systemctl`/Task Manager процесс будет виден.

## Подготовка к флешке и запуск на любом ПК

Перед копированием на флешку очистите проект от локального мусора:

- Linux:

```bash
./prepare_flash.sh
```

- Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\prepare_flash.ps1
```

Это удалит:

- `.venv`
- `__pycache__`, `*.pyc`, `*.pyo`
- временные медиа в `downloads`
- `*.log`

После копирования на другой ПК просто снова выполните bootstrap:

- Linux: `./bootstrap.sh`
- Windows: `.\bootstrap.ps1`

Важно: один `BOT_TOKEN` нельзя запускать одновременно на нескольких ПК в режиме polling.
Если поднять несколько копий сразу, будет конфликт `getUpdates`.

## 1. Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполните `BOT_TOKEN` в `.env`.

## 2. Важная настройка в BotFather

Чтобы бот видел **все сообщения группы**, отключите Privacy Mode:

1. Откройте `@BotFather`
2. Команда `/mybots`
3. Выберите вашего бота
4. `Bot Settings` -> `Group Privacy` -> `Turn off`

Без этого бот не сможет читать все сообщения в группе.

## 3. Запуск

```bash
source .venv/bin/activate
python bot.py
```

Команда `/status` покажет текущие параметры запуска бота.

## 4. Как это работает

- бот отслеживает группы и личный чат (`group`, `supergroup`, `private`)
- ищет ссылки TikTok / Instagram Reels / YouTube Shorts в тексте и в `text_link`
- TikTok получает через API `tikwm.com`
- Reels и Shorts скачивает через `yt-dlp`
- несколько ссылок из одного сообщения обрабатывает параллельно
- сначала отправляет медиа напрямую по URL (самый быстрый путь)
- если direct-отправка недоступна, скачивает локально и отправляет из `downloads`
- локальные файлы после отправки удаляются из папки `downloads`

## 5. Переменные окружения

- `BOT_TOKEN` - токен Telegram бота
- `MAX_FILE_MB` - максимальный размер скачиваемого файла в МБ
- `downloads` - папка для fallback-скачивания (основной путь отправки идет напрямую по URL)
- `IMAGE_DOWNLOAD_CONCURRENCY` - скорость загрузки фото-каруселей
- `LINK_PROCESS_CONCURRENCY` - скорость обработки нескольких ссылок в одном сообщении
- `YT_DLP_COOKIE_FILE` - путь к cookies-файлу для `yt-dlp` (опционально, иногда нужен для Instagram)

## 6. Автозапуск после перезагрузки

```bash
./install_autostart.sh
```

Проверка:

```bash
systemctl --user status tiktok-bot.service
journalctl --user -u tiktok-bot.service -f
```

Важно: не запускайте одновременно `python bot.py` вручную и `systemd`-сервис.
Иначе будет конфликт `getUpdates` (`TelegramConflictError`) и бот начнет работать с задержками.

Удаление автозапуска:

```bash
./uninstall_autostart.sh
```

Для Windows автозапуск проще делать через `Task Scheduler` (Планировщик заданий): запуск `python` с аргументом `bot.py` из папки проекта.

## 7. Если бот не реагирует на ссылки

1. Убедитесь, что бот добавлен в группу.
2. В `@BotFather` отключён `Group Privacy` (`Turn off`).
3. Бот запущен и отвечает на `/status`.
4. Проверьте логи: `journalctl --user -u tiktok-bot.service -f` (если запущен как service).

## 8. Ограничения

- бот использует сторонний API (TikWM), при недоступности API загрузка не сработает
- если файл больше `MAX_FILE_MB`, бот пропустит его
