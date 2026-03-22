# 🎮 Minecraft Server Panel

![GitHub License](https://img.shields.io/github/license/xKanzy/minecraft-panel-web?style=flat-square)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/xKanzy/minecraft-panel-web?style=flat-square)
![OS Support](https://img.shields.io/badge/ОС-Windows%20%7C%20Linux-blue?style=flat-square)

Современная веб-панель управления для серверов Minecraft. Управляйте своим сервером из любой точки мира: запуск/остановка, консоль, плагины, моды, бэкапы и файловый менеджер — всё это в стильной темной теме с полной поддержкой русского и английского языков.

![Dashboard Preview](https://via.placeholder.com/800x400?text=Minecraft+Panel+Dashboard+Preview)

---

## ✨ Особенности

* 🔐 **Авторизация и роли** — поддержка нескольких аккаунтов, разделение на админов/пользователей, смена пароля.
* 🚀 **Управление сервером** — мгновенный старт/стоп/рестарт с консолью в реальном времени (SSE).
* 👥 **Онлайн игроки** — живой список игроков, возможность кикать, банить и выдавать/забирать права оператора (OP).
* 📦 **Плагины и моды** — удобный поиск и установка напрямую через **Modrinth** и **CurseForge**.
* 📂 **Файловый менеджер** — полноценный браузер файлов: просмотр, редактирование, загрузка и удаление.
* 💾 **Резервное копирование** — создание и восстановление бэкапов мира в один клик.
* 📊 **Статистика** — графики нагрузки на CPU, RAM и использование диска в реальном времени.
* 🌐 **Мультиязычность** — переключение между русским и английским языками на лету.
* 🔔 **Интеграция с Discord** — уведомления через вебхуки о событиях сервера (старт/стоп, вход/выход игроков, команды).

---

## 📥 Скачать

Вы можете выбрать подходящую версию на странице [Releases](https://github.com/xKanzy/minecraft-panel-web/releases).

| ОС | Фиксированный порт (8081) | Авто-выбор порта |
| :--- | :--- | :--- |
| **Linux (x64)** | [`minecraft_panel_x64_linux`](https://github.com/xKanzy/minecraft-panel-web/releases) | [`linux_find_free_port`](https://github.com/xKanzy/minecraft-panel-web/releases) |
| **Windows (x64)** | [`minecraft_panel_x64.exe`](https://github.com/xKanzy/minecraft-panel-web/releases) | [`win_find_free_port.exe`](https://github.com/xKanzy/minecraft-panel-web/releases) |

---

### ⚙️ Конфигурация

Все настройки хранятся в файле config.json по путям:

    Linux: ~/.config/minecraft_panel/config.json

    Windows: %APPDATA%\MinecraftPanel\config.json

**Основные параметры:**

   * Путь к серверу — папка, где находится ваш server.jar.

   * Команда Java — обычно java или путь к конкретной версии (например, java17).

   * Аргументы Java — флаги запуска, например: -Xmx2048M -Xms1024M -jar server.jar nogui.

   * Discord Webhook — ссылка на вебхук вашего канала для получения отчетов.

   * CurseForge API Key — ключ для поиска плагинов (можно получить на [console.curseforge.com](https://console.curseforge.com/#/)).
    
---

### 💬 Уведомления в Discord

Чтобы включить интеграцию:

   1. Создайте вебхук в настройках вашего Discord-канала.

   2. Скопируйте URL вебхука.

   3. В панели управления перейдите в Settings и вставьте URL.

   4. Выберите интервал отчетов и типы событий (вход игроков, команды и т.д.).

   5. Нажмите Save Changes.
    
---

## 🚀 Быстрый старт

### Способ 1: Использование готового файла (рекомендуется)
1. Скачайте файл для вашей ОС из таблицы выше.
2. Запустите его:
   * **Linux**: `chmod +x minecraft_panel_x64_linux && ./minecraft_panel_x64_linux`
   * **Windows**: Просто запустите загруженный `.exe` файл.
3. Откройте в браузере: `http://localhost:8081` (или порт, указанный в консоли).
4. Пройдите первичную настройку (укажите путь к папке с сервером).
5. Войдите в систему: логин **admin** / пароль **admin** (смените в настройках сразу после входа!).

### Способ 2: Запуск из исходного кода
```bash
# Клонируйте репозиторий
git clone [https://github.com/xKanzy/minecraft-panel-web.git](https://github.com/xKanzy/minecraft-panel-web.git)
cd minecraft-panel-web

# Настройте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Для Linux/Mac
# или .\venv\Scripts\activate для Windows

# Установите зависимости и запустите 
pip install -r requirements.txt
python app.py
