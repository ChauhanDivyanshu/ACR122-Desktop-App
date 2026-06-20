# ACR122U NFC Writer

A modern, GoToTag-style desktop application to read, write, manage, and batch-process NFC tags using the ACS ACR122U USB NFC reader.

Built with Python + PySide6.

---

## ✨ Features

- 🔐 Local offline login + register system (per-user secure storage)
- 🟦 Modern GoToTag-inspired UI (Light + Dark themes)
- 📇 Single Write — URL / Text with optional password lock
- 📥 Read Card — full chip info + actions (Update, Erase, Change/Remove Password)
- 📂 CSV Batch Write — bulk write multiple cards with progress + flash alerts
- 🔁 Resume Session — continue an interrupted CSV batch
- 🔒 Password protection support (NTAG213 / NTAG215 / NTAG216)
- 💡 LED + Buzzer integrated for reader feedback
- 🪟 Cross-platform (Windows / macOS / Linux)
- 🧱 Production-grade architecture (workers, threading, signal-driven UI)
- 📦 One-click `.exe` build via PyInstaller
- 📁 Standard CSV / GoToTag-compatible CSV export

---

## 🖥 Supported NFC Chips

| Chip       | Read | Write | Password | Permanent Lock |
|------------|------|-------|----------|----------------|
| NTAG213    | ✅   | ✅   | ✅       | ✅           |
| NTAG215    | ✅   | ✅   | ✅       | ✅           |
| NTAG216    | ✅   | ✅   | ✅       | ✅           |
| MIFARE 1K  | ✅   | ❌   | ❌       | ❌           |

---

## 🧰 Hardware Required

- **ACR122U USB NFC Reader**
- ACR122U Windows driver  
  [Download from ACS](https://www.acs.com.hk/en/driver/3/acr122u-usb-nfc-reader/)
