"""Durable SQLite queue for a future external AI subtitle worker.

No audio extraction, transcription or translation is performed in this module.
"""
import sqlite3,time
STATES={"pending","claimed","extracting","transcribing","translating","reviewing","completed","failed","cancelled","paused"}
ACTIVE={"pending","claimed","extracting","transcribing","translating","reviewing","paused","failed"}
WORKING={"claimed","extracting","transcribing","translating"}
STEPS={"claimed":"extracting","extracting":"transcribing","transcribing":"translating","translating":"reviewing"}
def init(c):
 c.execute("""CREATE TABLE IF NOT EXISTS ai_jobs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 video_path TEXT NOT NULL,video_size INTEGER NOT NULL,video_mtime REAL NOT NULL,
 video_duration REAL,source_language TEXT NOT NULL DEFAULT 'ja',
 target_language TEXT NOT NULL DEFAULT 'zh',status TEXT NOT NULL DEFAULT 'pending',
 priority INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,
 next_retry REAL NOT NULL DEFAULT 0,worker_id TEXT,lease_until REAL,
 progress INTEGER NOT NULL DEFAULT 0,last_error TEXT NOT NULL DEFAULT '',
 origin TEXT NOT NULL DEFAULT 'manual',created_at REAL NOT NULL,updated_at REAL NOT NULL
 )""")
 c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_job_version ON ai_jobs(video_path,video_size,video_mtime)")
 c.execute("CREATE INDEX IF NOT EXISTS idx_ai_jobs_status ON ai_jobs(status,priority,created_at)")
 c.commit()
def enqueue(c,path,size,mtime,origin="manual",max_pending=500):
 now=time.time()
 existing=c.execute("SELECT * FROM ai_jobs WHERE video_path=? AND video_size=? AND video_mtime=?",(str(path),size,mtime)).fetchone()
 if existing:return dict(existing),False
 count=c.execute("SELECT COUNT(*) FROM ai_jobs WHERE status IN ('pending','claimed','extracting','transcribing','translating','reviewing')").fetchone()[0]
 if count>=max_pending:raise ValueError("AI queue limit reached")
 # A new file version invalidates old unfinished work.
 c.execute("UPDATE ai_jobs SET status='cancelled',last_error='Video version changed',updated_at=?,worker_id=NULL,lease_until=NULL WHERE video_path=? AND status NOT IN ('completed','cancelled')",(now,str(path)))
 c.execute("""INSERT INTO ai_jobs(video_path,video_size,video_mtime,origin,created_at,updated_at)
 VALUES(?,?,?,?,?,?)""",(str(path),size,mtime,origin,now,now))
 job=c.execute("SELECT * FROM ai_jobs WHERE id=last_insert_rowid()").fetchone()
 c.commit();return dict(job),True
def get(c,job_id):
 row=c.execute("SELECT * FROM ai_jobs WHERE id=?",(job_id,)).fetchone()
 if row is None:raise ValueError("AI task not found")
 return dict(row)
def list_jobs(c,status="",limit=200):
 if status and status not in STATES:raise ValueError("Invalid status")
 if status:
  rows=c.execute("SELECT * FROM ai_jobs WHERE status=? ORDER BY priority DESC,created_at DESC LIMIT ?",(status,limit))
 else:rows=c.execute("SELECT * FROM ai_jobs ORDER BY created_at DESC LIMIT ?",(limit,))
 return [dict(r) for r in rows]
def control(c,job_id,action):
 if action not in {"pause","resume","cancel","retry"}:raise ValueError("Invalid action")
 row=get(c,job_id);status=row["status"]
 target={"pause":"paused","resume":"pending","cancel":"cancelled","retry":"pending"}[action]
 allowed={"pause":{"pending","failed"},"resume":{"paused"},"cancel":{"pending","paused","failed","reviewing"},"retry":{"failed","cancelled","reviewing"}}
 if status not in allowed[action]:raise ValueError("Action not permitted in current state")
 now=time.time()
 c.execute("UPDATE ai_jobs SET status=?,worker_id=NULL,lease_until=NULL,next_retry=0,last_error='',updated_at=? WHERE id=?",(target,now,job_id))
 c.commit();return get(c,job_id)
def recover_expired(c,now=None):
 now=time.time() if now is None else now
 result=c.execute("""UPDATE ai_jobs SET status='pending',worker_id=NULL,lease_until=NULL,
 last_error='Worker lease expired',updated_at=?
 WHERE status IN ('claimed','extracting','transcribing','translating') AND lease_until IS NOT NULL AND lease_until<?""",(now,now))
 c.commit();return result.rowcount
def claim(c,worker_id,lease_seconds=600,now=None):
 if not worker_id or len(worker_id)>128:raise ValueError("Invalid worker id")
 now=time.time() if now is None else now
 c.execute("BEGIN IMMEDIATE")
 try:
  row=c.execute("SELECT id FROM ai_jobs WHERE status='pending' AND next_retry<=? ORDER BY priority DESC,created_at ASC LIMIT 1",(now,)).fetchone()
  if not row:c.commit();return None
  c.execute("UPDATE ai_jobs SET status='claimed',worker_id=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE id=?",(worker_id,now+lease_seconds,now,row["id"]))
  job=get(c,row["id"]);c.commit();return job
 except Exception:c.rollback();raise
def heartbeat(c,job_id,worker_id,progress=None,lease_seconds=600):
 job=get(c,job_id)
 if job["status"] not in WORKING or job["worker_id"]!=worker_id:raise ValueError("Not job owner")
 if progress is not None and (not isinstance(progress,int) or not 0<=progress<=99):raise ValueError("Invalid progress")
 now=time.time()
 c.execute("UPDATE ai_jobs SET progress=?,lease_until=?,updated_at=? WHERE id=?",(job["progress"] if progress is None else progress,now+lease_seconds,now,job_id))
 c.commit();return get(c,job_id)
def transition(c,job_id,worker_id,new_status,error=""):
 job=get(c,job_id)
 if job["worker_id"]!=worker_id or job["status"] not in WORKING:raise ValueError("Not job owner")
 if job["lease_until"] is None or job["lease_until"]<time.time():raise ValueError("Lease expired")
 allowed={STEPS[job["status"]],"failed"}
 if new_status not in allowed:raise ValueError("Invalid transition")
 now=time.time()
 if new_status=="failed":
  c.execute("UPDATE ai_jobs SET status='failed',last_error=?,worker_id=NULL,lease_until=NULL,updated_at=? WHERE id=?",(str(error)[:500],now,job_id))
 elif new_status=="reviewing":
  c.execute("UPDATE ai_jobs SET status='reviewing',worker_id=NULL,lease_until=NULL,progress=100,updated_at=? WHERE id=?",(now,job_id))
 else:
  c.execute("UPDATE ai_jobs SET status=?,updated_at=? WHERE id=?",(new_status,now,job_id))
 c.commit();return get(c,job_id)
