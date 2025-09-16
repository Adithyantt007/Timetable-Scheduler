from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import sqlite3
import random

DB = "scheduler.db"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
SLOTS_PER_DAY = 6

app = FastAPI(title="Timetable Scheduler")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Serve static frontend
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ---------- DB helpers ----------
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def dict_from_row(row):
    return dict(row)

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS rooms(room_id TEXT PRIMARY KEY, room_name TEXT, capacity INTEGER, type TEXT, resources TEXT);
        CREATE TABLE IF NOT EXISTS batches(batch_id TEXT PRIMARY KEY, department TEXT, year INTEGER, section TEXT, size INTEGER, shift INTEGER);
        CREATE TABLE IF NOT EXISTS faculties(fac_id TEXT PRIMARY KEY, fac_name TEXT);
        CREATE TABLE IF NOT EXISTS subjects(sub_id TEXT PRIMARY KEY, sub_name TEXT, faculty_id TEXT);
        CREATE TABLE IF NOT EXISTS timetable(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT, day TEXT, slot INTEGER, subject_id TEXT, faculty_id TEXT, room_id TEXT);
    """)
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()

# ---------- Pydantic Models ----------
class RoomIn(BaseModel):
    room_id: str
    room_name: str
    capacity: int
    type: str = "Lecture"
    resources: str = ""

class FacultyIn(BaseModel):
    faculty_id: str
    name: str

class SubjectIn(BaseModel):
    subject_id: str
    name: str
    faculty_id: str

class BatchIn(BaseModel):
    batch_id: str
    department: str = ""
    year: int = 1
    section: str = ""
    size: int = 0
    shift: int = 1

# ---------- API Endpoints ----------
# Rooms
@app.get("/api/rooms")
def get_rooms():
    conn = get_db()
    rows = conn.execute("SELECT * FROM rooms").fetchall()
    conn.close()
    return [dict_from_row(r) for r in rows]

@app.post("/api/rooms")
def add_room(r: RoomIn):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO rooms(room_id,room_name,capacity,type,resources) VALUES (?,?,?,?,?)",
                 (r.room_id, r.room_name, r.capacity, r.type, r.resources))
    conn.commit()
    conn.close()
    return {"status":"ok"}

@app.delete("/api/rooms/{room_id}")
def delete_room(room_id: str):
    conn = get_db()
    conn.execute("DELETE FROM rooms WHERE room_id=?", (room_id,))
    conn.commit()
    conn.close()
    return {"status":"deleted"}

# Faculty
@app.get("/api/faculty")
def get_faculty():
    conn = get_db()
    rows = conn.execute("SELECT * FROM faculties").fetchall()
    conn.close()
    return [dict_from_row(r) for r in rows]

@app.post("/api/faculty")
def add_faculty(f: FacultyIn):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO faculties(fac_id,fac_name) VALUES (?,?)", (f.faculty_id,f.name))
    conn.commit()
    conn.close()
    return {"status":"ok"}

@app.delete("/api/faculty/{fac_id}")
def delete_faculty(fac_id: str):
    conn = get_db()
    conn.execute("DELETE FROM faculties WHERE fac_id=?", (fac_id,))
    conn.commit()
    conn.close()
    return {"status":"deleted"}

# Subjects
@app.get("/api/subjects")
def get_subjects():
    conn = get_db()
    rows = conn.execute("SELECT * FROM subjects").fetchall()
    conn.close()
    return [dict_from_row(r) for r in rows]

@app.post("/api/subjects")
def add_subject(s: SubjectIn):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO subjects(sub_id,sub_name,faculty_id) VALUES (?,?,?)",
                 (s.subject_id,s.name,s.faculty_id))
    conn.commit()
    conn.close()
    return {"status":"ok"}

@app.delete("/api/subjects/{sub_id}")
def delete_subject(sub_id: str):
    conn = get_db()
    conn.execute("DELETE FROM subjects WHERE sub_id=?", (sub_id,))
    conn.commit()
    conn.close()
    return {"status":"deleted"}

# Batches
@app.get("/api/batches")
def get_batches():
    conn = get_db()
    rows = conn.execute("SELECT * FROM batches").fetchall()
    conn.close()
    return [dict_from_row(r) for r in rows]

@app.post("/api/batches")
def add_batch(b: BatchIn):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO batches(batch_id,department,year,section,size,shift) VALUES (?,?,?,?,?,?)",
                 (b.batch_id,b.department,b.year,b.section,b.size,b.shift))
    conn.commit()
    conn.close()
    return {"status":"ok"}

@app.delete("/api/batches/{batch_id}")
def delete_batch(batch_id: str):
    conn = get_db()
    conn.execute("DELETE FROM batches WHERE batch_id=?", (batch_id,))
    conn.commit()
    conn.close()
    return {"status":"deleted"}

# Serve index.html
@app.get("/")
def root():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"msg":"Place index.html in the static folder."}
# ---------- Timetable Generation ----------
@app.post("/api/generate")
def generate_timetable():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM timetable")

    batches = [dict(r) for r in conn.execute("SELECT * FROM batches").fetchall()]
    subjects = [dict(r) for r in conn.execute("SELECT * FROM subjects").fetchall()]
    faculties = {f["fac_id"]: f["fac_name"] for f in conn.execute("SELECT * FROM faculties").fetchall()}
    rooms = [r["room_id"] for r in conn.execute("SELECT * FROM rooms").fetchall()]

    unscheduled = 0

    global_fac_slot = {fid: {day: [False]*SLOTS_PER_DAY for day in DAYS} for fid in faculties.keys()}
    global_room_slot = {r: {day: [False]*SLOTS_PER_DAY for day in DAYS} for r in rooms}

    for batch in batches:
        for day in DAYS:
            for slot in range(SLOTS_PER_DAY):
                subjects_shuffled = subjects.copy()
                random.shuffle(subjects_shuffled)
                placed = False
                for subject in subjects_shuffled:
                    fac_id = subject["faculty_id"]
                    free_room = next((r for r in rooms if not global_room_slot[r][day][slot]), None)
                    if free_room and not global_fac_slot[fac_id][day][slot]:
                        cur.execute("""
                            INSERT INTO timetable (batch_id, day, slot, subject_id, faculty_id, room_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (batch["batch_id"], day, slot+1, subject["sub_id"], fac_id, free_room))
                        global_fac_slot[fac_id][day][slot] = True
                        global_room_slot[free_room][day][slot] = True
                        placed = True
                        break
                if not placed:
                    unscheduled += 1

    conn.commit()
    conn.close()

    total_slots = len(batches) * len(DAYS) * SLOTS_PER_DAY
    scheduled = total_slots - unscheduled

    return {"status": "ok", "scheduled": scheduled, "unscheduled": unscheduled}





@app.get("/api/timetable/batch/{batch_id}")
def get_timetable_batch(batch_id: str):
    conn = get_db()
    rows = conn.execute("""
        SELECT t.day, t.slot,
               r.room_name AS room,
               s.sub_name AS subject,
               f.fac_name AS faculty
        FROM timetable t
        JOIN rooms r ON t.room_id = r.room_id
        JOIN subjects s ON t.subject_id = s.sub_id
        JOIN faculties f ON t.faculty_id = f.fac_id
        WHERE t.batch_id = ?
    """, (batch_id,)).fetchall()
    conn.close()

    timetable = {day: [None]*SLOTS_PER_DAY for day in DAYS}
    for row in rows:
        row = dict(row)
        timetable[row["day"]][row["slot"]-1] = {
            "subject": row["subject"],
            "faculty": row["faculty"],
            "room": row["room"]
        }

    return timetable

