# LAN File Transfer (LAN-FT) 🚀

Простий, швидкий та надійний додаток для передачі файлів і папок між комп'ютерами в локальній мережі (Windows).

A simple, fast and reliable application for transferring files and folders between computers on a local network (Windows).

[English Version Below](#-english-version)

---

## 🇺🇦 Українська версія

### ✨ Основні можливості

| Функція | Опис |
|---------|------|
| 📂 **Передача файлів і папок** | Оптимізований ZIP-стрімінг — папки будь-якого розміру без перевантаження RAM |
| 🔐 **Шифрування AES-GCM** | 256-біт, PSK зберігається у Windows Credential Manager |
| 🔍 **Автовиявлення** | Zeroconf (mDNS) + UDP-broadcast |
| 🌍 **Багатомовність** | Українська та англійська (налаштовується) |
| 🎨 **Сучасний UI** | Темна/світла тема, індикатори статусу, черга передач |
| ⏸ **Контроль передачі** | Пауза, відновлення, скасування, обмеження швидкості |
| 📋 **Історія** | Журнал усіх передач з контрольними сумами SHA-256 |
| 🔄 **Відновлення** | Автоматичне відновлення перерваних передач |

### 📦 Стек технологій

- **GUI**: Tkinter + sv-ttk (Sun Valley theme)
- **Мережа**: TCP (передача), UDP / mDNS (виявлення)
- **Безпека**: `cryptography` (AES-GCM), `keyring` (зберігання PSK)
- **Стиснення**: `zipfile` (стрімінг)
- **Збірка**: PyInstaller

### 🚀 Встановлення та запуск

```bash
# 1. Клонуйте репозиторій
git clone https://github.com/Johny97Moon/LAN-FT.git
cd LAN-FT

# 2. Створіть віртуальне середовище
python -m venv .venv
.venv\Scripts\activate

# 3. Встановіть залежності
pip install -r requirements.txt

# 4. Запустіть
python main.py
```

### 🔨 Збірка (Build)

```bash
# Простий спосіб:
build.bat

# Або вручну:
pyinstaller LAN-FT.spec --noconfirm --clean
```

Готовий файл з'явиться у `dist/LAN-FT/`.

### 🔏 Підписання коду (необов'язково)

```powershell
# PowerShell від імені адміністратора
powershell -ExecutionPolicy Bypass -File scripts\sign_exe.ps1
```

> **Примітка:** Це самопідписаний сертифікат. Для повного рівня довіри потрібен сертифікат від CA.

### 🛡️ Антивіруси (False Positives)

Файли `.exe`, створені PyInstaller, можуть помилково блокуватися антивірусом.

**Рішення:**
- Додайте папку проекту або `LAN-FT.exe` у виключення антивіруса
- Підпишіть файл сертифікатом розробника (Code Signing)

### 📁 Структура проекту

```
LAN-FT/
├── main.py                 # Точка входу
├── config/
│   └── settings.py         # Налаштування, шляхи, константи
├── models/
│   └── file_info.py        # FileInfo, TransferProgress
├── net/
│   ├── protocol.py         # JSON-протокол (length-prefixed)
│   ├── sender.py           # Відправка файлів/папок
│   ├── receiver.py         # Прийом файлів/папок
│   ├── crypto.py           # AES-128-GCM шифрування
│   └── discovery.py        # UDP broadcast + Zeroconf
├── transfer/
│   ├── manager.py          # Оркестрація send/receive/discovery
│   └── queue.py            # Черга передач з паралельністю
├── services/
│   ├── firewall_service.py # Правила брандмауера Windows
│   ├── history_service.py  # Журнал передач (JSON)
│   ├── i18n_service.py     # Інтернаціоналізація
│   ├── ip_service.py       # Визначення локальної IP
│   ├── keyring_service.py  # PSK у OS keyring
│   ├── log_service.py      # Логування
│   └── notification_service.py # Звукові + toast сповіщення
├── ui/
│   ├── main_window.py      # Головне вікно
│   ├── settings_dialog.py  # Діалог налаштувань
│   ├── callbacks.py        # UI callback handlers
│   ├── widgets.py          # Кастомні віджети
│   ├── theme.py            # Темна/світла тема (sv-ttk)
│   ├── tray.py             # Системний трей (pystray)
│   ├── toast.py            # In-app toast сповіщення
│   └── constants.py        # UI константи
├── i18n/
│   ├── ua.json             # Українська локалізація
│   └── en.json             # Англійська локалізація
├── resources/
│   └── app.ico             # Іконка програми
├── scripts/
│   └── sign_exe.ps1        # Підписання .exe
├── tests/
│   └── test_protocol.py    # Тести протоколу передачі
├── requirements.txt
├── LAN-FT.spec             # PyInstaller spec
├── build.bat               # Скрипт збірки
└── LICENSE
```

---

## 🇺🇸 English Version

### ✨ Main Features

| Feature | Description |
|---------|-------------|
| 📂 **File & Folder Transfer** | Optimized ZIP streaming — any folder size without RAM spikes |
| 🔐 **AES-GCM Encryption** | 256-bit, PSK stored in Windows Credential Manager |
| 🔍 **Auto-Discovery** | Zeroconf (mDNS) + UDP broadcast |
| 🌍 **Multi-language** | Ukrainian and English (switchable in settings) |
| 🎨 **Modern UI** | Dark/light theme, status indicators, transfer queue |
| ⏸ **Transfer Control** | Pause, resume, cancel, speed limiting |
| 📋 **History** | Transfer log with SHA-256 checksums |
| 🔄 **Resume** | Automatic resume of interrupted transfers |

### 🚀 Setup & Launch

```bash
# 1. Clone the repository
git clone https://github.com/Johny97Moon/LAN-FT.git
cd LAN-FT

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python main.py
```

### 🔨 Building from Source

```bash
# Simple:
build.bat

# Or manually:
pyinstaller LAN-FT.spec --noconfirm --clean
```

The executable will be available in `dist/LAN-FT/`.

### 🛡️ Security & Antivirus (False Positives)

Executables created with PyInstaller are often flagged by antivirus software as potential threats (False Positive).

**Tips:**
- Add the project folder or `LAN-FT.exe` to your antivirus exclusions
- For professional distribution, use a Code Signing certificate

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
