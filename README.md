# Emergency Vehicle Detection System (Smart Traffic Sentinel)

This project uses a **FastAPI** backend for video processing and YOLOv8 detection, and a **Next.js** frontend for the dashboard.

## Prerequisites

- **Python 3.9+** installed.
- **Node.js** and **npm** installed.
- **VS Code** (recommended).

## How to Run in VS Code

You need to run **two** separate terminals: one for the backend and one for the frontend.

### 1. Start the Backend (Python/FastAPI)

1.  Open a Terminal in VS Code (`Ctrl + ~`).
2.  Navigate to the backend directory:
    ```powershell
    cd backend
    ```
3.  Activate the virtual environment:
    ```powershell
    .\venv\Scripts\Activate
    ```
    *(If you don't have a venv yet, run `python -m venv venv` first, then activate it and run `pip install -r requirements.txt`)*.
4.  Run the application:
    ```powershell
    python main.py
    ```
    *You should see output indicating the server is running on `http://0.0.0.0:8000`.*

### 2. Start the Frontend (Next.js)

1.  Open a **New** Terminal (click the `+` icon in the terminal panel).
2.  Navigate to the frontend directory:
    ```powershell
    cd frontend
    ```
3.  Install dependencies (only needed the first time):
    ```powershell
    npm install
    ```
4.  Start the development server:
    ```powershell
    npm run dev
    ```
5.  Open your browser and visit: **http://localhost:3000**

## Features

- **Real-time Video**: Upload detection videos directly from the dashboard.
- **Emergency Detection**: Automatically detects ambulances/fire trucks and switches signals.
- **Manual Control**: "Force Green" and "Simulate Emergency" buttons for testing.
- **Clear Video**: Use the "X" button to clear a video feed.

## Troubleshooting

- **Video not loading?** Ensure the backend is running and you are accessing `http://localhost:3000` (IPv4 issue on some Windows machines).
- **Backend crash?** Check the backend terminal for error logs.
