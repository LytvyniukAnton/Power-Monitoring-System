# ⚡️ IoT Power Monitoring Ecosystem

A professional-grade monitoring system designed to track power grid stability using **ESP32** sensors and a **Python/Flask** backend. Built with a focus on high data integrity and DevOps operational standards.

## 🚀 Architecture
- **Sensor:** ESP32 sending real-time heartbeats via REST API.
- **Backend:** Flask application handled by **Gunicorn** workers.
- **Proxy:** **Nginx** serving as a Reverse Proxy with SSL/TLS termination.
- **Alerting:** Real-time **Telegram Bot** notifications for status changes.
- **Analytics:** Web Dashboard with **Chart.js** and Glassmorphism UI.

## 🛠 Tech Stack
- **Languages:** Python, JavaScript, C++ (Arduino/ESP32)
- **Web Server:** Nginx, Gunicorn
- **Database:** SQLite
- **Ops:** Systemd, Logrotate, Bash Automation, Dotenv

## 🌟 Key DevOps Features
- **Smart Logic:** Distinguishes between actual power outages and technical resets (WDT, Brownouts) by analyzing boot reasons.
- **Multi-Environment:** Scalable architecture supporting multiple locations (Home/Parents) on a single server.
- **Automation:** 
  - `backup.sh`: Automated database backups.
  - Log management via system-wide **Logrotate** integration.
- **Security:** API Key authentication for telemetry and Basic Auth for dashboard access.

## 📊 Dashboard on site + Telegram channel preview 
<img width="769" height="993" alt="image" src="https://github.com/user-attachments/assets/72d9489c-d07d-48b6-9e89-42f460388e1f" />

<img width="648" height="1104" alt="image" src="https://github.com/user-attachments/assets/9e37163a-9d66-4cb0-b24a-41ec6c10d1db" />

<img width="1719" height="544" alt="image" src="https://github.com/user-attachments/assets/eb847af0-76f8-441a-945a-d32b844e7d49" />

## 📂 Project Structure
- `myhome.py`: Main application logic and Telegram integration.
- `static/`: Frontend assets (CSS, JS, Charts).
- `templates/`: Jinja2 HTML templates.
- `system_state.json`: Persistent state tracking across restarts.
