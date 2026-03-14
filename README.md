<div align="center">

# 🏛️ Public Grievance Intelligence & Resolution Platform

### **A Smart Civic Governance Solution for the Modern World**

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![Chart.js](https://img.shields.io/badge/Chart.js-4.4-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white)](https://www.chartjs.org)
[![Leaflet](https://img.shields.io/badge/Leaflet-1.9-199900?style=for-the-badge&logo=leaflet&logoColor=white)](https://leafletjs.com)
[![License](https://img.shields.io/badge/License-MIT-F4A261?style=for-the-badge)](#license)

---

> **GRIP** is a modern, full-stack civic complaint management system that bridges the gap between citizens and government. By leveraging AI-driven categorization, real-time analytics, and geotagging technology, it ensures every grievance is heard, tracked, and resolved with full transparency.

<br>

[🚀 Quick Start](#-quick-start) · [✨ Features](#-features) · [📊 Dashboard Analytics](#-pages--routes) · [🔌 API Reference](#-api-reference) · [🗂 Project Structure](#-project-structure)

</div>

---

## ✨ Features

### 🧑‍💻 Citizen Empowerment
| Feature | Description |
|---------|-------------|
| **📝 Quick-File Complaints** | Seamlessly submit civic issues with titles, descriptions, and categories. |
| **🤖 Intelligent AI Routing** | Automated category detection (Road, Garbage, Water, etc.) and priority assignment. |
| **📸 On-Spot Geotagged Evidence** | Take photos directly from the app; GPS coordinates are automatically embedded. |
| **🔍 Real-Time Tracking** | Monitor the progress of your grievance with live status updates and SLA timers. |
| **⭐ Accountability Loop** | Rate the quality of resolution and provide direct feedback to officials. |

### 🏢 Government Intelligence
| Feature | Description |
|---------|-------------|
| **📊 Executive Dashboard** | High-level metrics with interactive visualizations for total, pending, and resolved cases. |
| **🚨 Auto-Alert System** | Instant flagging for overdue tasks, mission-critical priorities, and high-sentiment issues. |
| **🗺️ Geographic Heatmaps** | Visualize complaint clusters across the city to allocate resources effectively. |
| **📥 Data Interoperability** | Export full case histories and analytics to CSV for external reporting. |

### 🔐 Administrative & Financial Control
| Feature | Description |
|---------|-------------|
| **💰 Operational Transparency** | Full budget tracking, area-wise spending analytics, and vendor performance monitoring. |
| **🛡️ Secure Access** | Role-based JWT authentication ensuring that data is only accessible to authorized personnel. |
| **📋 System Audit Logs** | Comprehensive trail of all administrative and status changes for full forensic accountability. |

---

## 🚀 Quick Start

### 📋 Prerequisites

- **Python 3.8+**
- **pip** (Python package manager)

### ⚙️ Installation & Setup

```bash
# 1. Clone the project repository
git clone https://github.com/your-username/grip-platform.git
cd grip-platform

# 2. Install required dependencies
pip install -r requirements.txt

# 3. Launch the application
python app.py

# 4. Access the platform
#    → http://localhost:5000
```

### 🔑 Access Credentials

| User Role | Default Username | Default Password |
|-----------|------------------|------------------|
| **Administrator** | `admin` | `admin123` |
| **Citizen** | *Create account on login page* | *User defined* |

---

## 📄 Platform Navigation

| Route | Functional Page | User Access |
|-------|-----------------|-------------|
| `/` | 📋 Submission Portal | Guest / All Users |
| `/login` | 🔑 Key Access & Registration | All Users |
| `/dashboard` | 📈 Intelligence Workspace | Officials & Admins |
| `/citizen_dashboard` | 👤 Personal Complaint Tracker | Registered Citizens |
| `/funds` | 💸 Financial & Vendor Portal | Officials & Admins |

---

## 🔌 API Reference

### 🔐 Authentication API
| Endpoint | Method | Action |
|----------|--------|--------|
| `/api/login` | `POST` | User credential verification and JWT issuance |
| `/api/register` | `POST` | New citizen account creation |
| `/api/me` | `GET` | Current session information retrieval |

### 📋 Grievance API
| Endpoint | Method | Action |
|----------|--------|--------|
| `/api/complaints` | `POST` | Multi-part submission of complaint text, images, and coordinates |
| `/api/complaints` | `GET` | Query complaints with advanced area/category filters |
| `/api/complaints/<id>/status` | `PUT` | Update workflow stage of a specific grievance |
| `/api/complaints/stats` | `GET` | Real-time aggregate data for intelligence charts |
| `/api/export_complaints` | `GET` | Generate and download CSV report |

### 💸 Financial & Audit API
| Endpoint | Method | Action |
|----------|--------|--------|
| `/api/funds/summary` | `GET` | High-level budget allocation and utilization summary |
| `/api/funds/area_spending` | `GET` | Financial impact analysis by geographic zone |
| `/api/audit_logs` | `GET` | Retrieve cross-platform administrative trail |

---

## 🗂 Project Architecture

```
grip-platform/
├── app.py                  # Core Engine: Flask logic, NLP Processing, Security
├── requirements.txt        # System Dependencies
├── grievance.db            # Persistent Data Storage (SQLite)
├── static/
│   └── uploads/            # Encrypted/Stored User Evidence Photos
└── templates/
    ├── index.html           # Public-Facing Submission Interface
    ├── login.html           # Centralized Authentication System
    ├── dashboard.html       # Official Analytics & Case Management
    ├── citizen_dashboard.html  # Personalized User Activity Tracking
    └── funds.html           # Financial Transparency & Vendor Registry
```

---

## 🛠️ Technological Stack

<div align="center">

| Component | Standard |
|-----------|-----------|
| **Core Architecture** | Python · Flask · RESTful API |
| **Data Integrity** | SQLite · SQLAlchemy · JWT Protection |
| **UI/UX Framework** | HTML5 · Modern CSS3 · Inter Font System |
| **Geospatial Intelligence** | Leaflet.js · OpenStreetMap · Nominatim |
| **Real-time Analytics** | Chart.js 4.4 |
| **Imaging API** | MediaDevices / WebCam API Integration |

</div>

---

## 📜 Legal & Licensing

Distributed under the **MIT License**. See `LICENSE` for more information.

---

<div align="center">

**Developed with 💡 for Modern Governance**

*Public Grievance Intelligence & Resolution Platform — Bridging the Gap.*

</div>
