
<div align="center">

<img src="https://via.placeholder.com/1200x300/003B57/FFFFFF?text=GRIP+-+Public+Grievance+Intelligence+%26+Resolution+Platform" alt="GRIP Platform Banner" style="border-radius: 10px; margin-bottom: 20px;">

# 🏛️ GRIP: Public Grievance Intelligence & Resolution Platform

**A Smart Civic Governance Solution for the Modern World**

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](http://makeapullrequest.com)
[![License](https://img.shields.io/badge/License-MIT-F4A261?style=for-the-badge)](#license)

> **GRIP** is a modern, full-stack civic complaint management system bridging the gap between citizens and government. By leveraging AI-driven categorization, real-time analytics, and geotagging technology, it ensures every grievance is heard, tracked, and resolved with full transparency.

[Report Bug](https://github.com/your-username/grip-platform/issues) · [Request Feature](https://github.com/your-username/grip-platform/issues)

</div>

---

## 📑 Table of Contents
- [✨ Features](#-features)
- [🚀 Quick Start](#-quick-start)
- [📄 Platform Navigation](#-platform-navigation)
- [🔌 API Reference](#-api-reference)
- [🗂 Project Architecture](#-project-architecture)
- [🛠️ Technological Stack](#-technological-stack)
- [📜 License](#-license)

---

## ✨ Features

### 🧑‍💻 Citizen Empowerment
| Feature | Description |
|:---|:---|
| **📝 Quick-File Complaints** | Seamlessly submit civic issues with titles, descriptions, and categories. |
| **🤖 Intelligent AI Routing** | Automated category detection (Road, Garbage, Water, etc.) and priority assignment. |
| **📸 On-Spot Geotagged Evidence** | Take photos directly from the app; GPS coordinates are automatically embedded. |
| **🔍 Real-Time Tracking** | Monitor the progress of your grievance with live status updates and SLA timers. |
| **⭐ Accountability Loop** | Rate the quality of resolution and provide direct feedback to officials. |

### 🏢 Government Intelligence
| Feature | Description |
|:---|:---|
| **📊 Executive Dashboard** | High-level metrics with interactive visualizations for total, pending, and resolved cases. |
| **🚨 Auto-Alert System** | Instant flagging for overdue tasks, mission-critical priorities, and high-sentiment issues. |
| **🗺️ Geographic Heatmaps** | Visualize complaint clusters across the city to allocate resources effectively. |
| **📥 Data Interoperability** | Export full case histories and analytics to CSV for external reporting. |

### 🔐 Administrative & Financial Control
| Feature | Description |
|:---|:---|
| **💰 Operational Transparency** | Full budget tracking, area-wise spending analytics, and vendor performance monitoring. |
| **🛡️ Secure Access** | Role-based JWT authentication ensuring that data is only accessible to authorized personnel. |
| **📋 System Audit Logs** | Comprehensive trail of all administrative and status changes for full forensic accountability. |

---

## 🚀 Quick Start

### 📋 Prerequisites
Ensure you have the following installed on your local machine:
- **Python 3.8+**
- **pip** (Python package manager)

### ⚙️ Installation & Setup

**1. Clone the repository**
```bash
git clone https://github.com/syed-adnan-01/grip-website.git

```

**2. Install dependencies**

```bash
pip install -r requirements.txt

```

**3. Launch the application**

```bash
python app.py

```

**4. Access the platform**
Open your browser and navigate to `http://localhost:5000`

> **Note on Credentials:** Use `admin` / `admin123` for Administrator access. Citizens can create accounts directly on the login page.

---

## 📄 Platform Navigation

| Route | Functional Page | User Access |
| --- | --- | --- |
| `/` | 📋 Submission Portal | Guest / All Users |
| `/login` | 🔑 Key Access & Registration | All Users |
| `/dashboard` | 📈 Intelligence Workspace | Officials & Admins |
| `/citizen_dashboard` | 👤 Personal Complaint Tracker | Registered Citizens |
| `/funds` | 💸 Financial & Vendor Portal | Officials & Admins |

---

## 🔌 API Reference & Architecture

<details>
<summary><b>Click to expand API Endpoints</b></summary>

### 🔐 Authentication API

| Endpoint | Method | Action |
| --- | --- | --- |
| `/api/login` | `POST` | User credential verification and JWT issuance |
| `/api/register` | `POST` | New citizen account creation |
| `/api/me` | `GET` | Current session information retrieval |

### 📋 Grievance API

| Endpoint | Method | Action |
| --- | --- | --- |
| `/api/complaints` | `POST` | Multi-part submission of complaint text, images, and coordinates |
| `/api/complaints` | `GET` | Query complaints with advanced area/category filters |
| `/api/complaints/<id>/status` | `PUT` | Update workflow stage of a specific grievance |
| `/api/complaints/stats` | `GET` | Real-time aggregate data for intelligence charts |
| `/api/export_complaints` | `GET` | Generate and download CSV report |

### 💸 Financial & Audit API

| Endpoint | Method | Action |
| --- | --- | --- |
| `/api/funds/summary` | `GET` | High-level budget allocation and utilization summary |
| `/api/funds/area_spending` | `GET` | Financial impact analysis by geographic zone |
| `/api/audit_logs` | `GET` | Retrieve cross-platform administrative trail |

</details>

<details>
<summary><b>Click to expand Project Architecture</b></summary>

```text
grip-platform/
├── app.py                  # Core Engine: Flask logic, NLP Processing, Security
├── requirements.txt        # System Dependencies
├── grievance.db            # Persistent Data Storage (SQLite)
├── static/
│   └── uploads/            # Encrypted/Stored User Evidence Photos
└── templates/
    ├── index.html          # Public-Facing Submission Interface
    ├── login.html          # Centralized Authentication System
    ├── dashboard.html      # Official Analytics & Case Management
    ├── citizen_dashboard.html # Personalized User Activity Tracking
    └── funds.html          # Financial Transparency & Vendor Registry

```

</details>

---

## 🛠️ Technological Stack

<div align="center">

</div>

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.

---

<div align="center">
<b>Developed with 💡 for Modern Governance</b>




<i>Public Grievance Intelligence & Resolution Platform — Bridging the Gap.</i>
</div>

```

