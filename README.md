# IoT Power Monitoring with ESP32 and Flask

## Overview

This repository contains a small but production-tested IoT monitoring system
used to track power availability and stability using **ESP32** devices and a
**Python (Flask)** backend.

ESP32 devices periodically send encrypted HTTPS heartbeat requests to the backend.
The server analyzes this data to distinguish real power outages from technical
resets (watchdog, brownout, manual reboot) and sends notifications via
**Telegram** when the system state changes.

The project is used in real conditions to monitor power status at multiple
locations using a single server.

> [!NOTE]  
> This project focuses on backend logic and monitoring reliability rather than
> on ESP32 firmware or infrastructure-as-code.

---

## Architecture Overview

- **ESP32**
  - Sends periodic HTTPS POST heartbeats
  - Includes uptime, boot ID, reset reason, and IP address
  - Uses API key authentication

- **Backend**
  - Flask application running behind Gunicorn
  - Processes telemetry and tracks system state
  - Detects meaningful power state changes

- **Alerting**
  - Telegram bot sends notifications only on real events
  - Avoids false alerts caused by simple device reboots

- **Web Dashboard**
  - Displays current status and historical data
  - Uses Chart.js for basic visualization

---

## Repository Structure

```text
.
├─ myhome.py              # Main Flask application and Telegram logic
├─ templates/
│  └─ index.html          # Web dashboard template
├─ static/
│  ├─ css/
│  │  └─ main.css         # Dashboard styling
│  └─ js/
│     ├─ api.js           # Backend API communication
│     ├─ chart.js         # Chart rendering logic
│     ├─ state.js         # Client-side state handling
│     └─ ui.js            # UI updates and interactions
├─ .gitignore
└─ README.md
```

> [!TIP]  
> Runtime-generated data such as databases, logs, backups, and system state files
> are intentionally excluded from version control.

---

## How It Works

1. **Heartbeat ingestion**
   - ESP32 devices send periodic HTTPS POST requests to the backend.
   - Each request contains:
     - Uptime
     - Boot ID
     - Reset reason
     - Device identifier
     - API key

2. **State analysis**
   - The backend compares incoming data with previously known state.
   - It determines whether:
     - Power was actually lost
     - The device rebooted without power loss
     - Power was restored after an outage

3. **State persistence**
   - The last known system state is stored locally to survive service restarts.
   - This prevents false alerts after backend redeployments.

4. **Notifications**
   - Telegram messages are sent only when a meaningful transition occurs:
     - Power loss
     - Power restoration
     - Abnormal reset events

---

## Tech Stack

- **Backend:** Python, Flask  
- **Web Server:** Gunicorn (behind Nginx)  
- **Frontend:** Jinja2, Chart.js, vanilla CSS and JavaScript  
- **Storage:** SQLite (runtime)  
- **Embedded:** ESP32 (Arduino / C++)  
- **Operations:** systemd, Bash scripts  

---

## Deployment Notes

This repository contains application code only.

In production, the application is typically deployed using:
- Gunicorn with a single worker (required due to shared in-memory state)
- systemd for process supervision
- Nginx as a reverse proxy with TLS termination

These components are intentionally not included in the repository, as they are
environment-specific.

---

## Security Model

- HTTPS communication between ESP32 devices and backend
- API key authentication for telemetry endpoints
- Environment-based secrets via `.env`
- Dashboard access protected at the web server level

> [!IMPORTANT]  
> This project is designed for personal or small-scale deployments.
> Additional security hardening is recommended for public exposure.

---

## Possible Improvements

- Prometheus metrics endpoint
- PostgreSQL instead of SQLite
- Per-device rate limiting
- Device registration and access control
- Centralized logging (Loki / ELK)

---

## Screenshots of the web dashboard and Telegram notifications are provided below
---
<img width="769" height="993" alt="image" src="https://github.com/user-attachments/assets/72d9489c-d07d-48b6-9e89-42f460388e1f" />
---
<img width="648" height="1104" alt="image" src="https://github.com/user-attachments/assets/9e37163a-9d66-4cb0-b24a-41ec6c10d1db" />
---
<img width="1719" height="544" alt="image" src="https://github.com/user-attachments/assets/eb847af0-76f8-441a-945a-d32b844e7d49" />
---
