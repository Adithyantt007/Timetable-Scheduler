
Full-stack Prototype - FastAPI + React (single-file)
Files:
- backend/app.py        : FastAPI backend (SQLite)
- backend/requirements.txt
- backend/static/index.html : Frontend (React via CDN)
Run:
1. cd backend
2. pip install -r requirements.txt
3. uvicorn app:app --reload --host 0.0.0.0 --port 8000
Then open http://localhost:8000/
