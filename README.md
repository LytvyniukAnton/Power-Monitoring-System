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
- **Automation:** - `update_all.sh`: Atomic updates for multiple instances.
  - `backup.sh`: Automated database backups.
  - Log management via system-wide **Logrotate** integration.
- **Security:** API Key authentication for telemetry and Basic Auth for dashboard access.

## 📊 Dashboard Preview
*(Add your screenshot here)*

## 📂 Project Structure
- `myhome.py`: Main application logic and Telegram integration.
- `static/`: Frontend assets (CSS, JS, Charts).
- `templates/`: Jinja2 HTML templates.
- `system_state.json`: Persistent state tracking across restarts.
