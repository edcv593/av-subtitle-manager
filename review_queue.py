"""Durable, single-worker NAS subtitle proofreading queue. No media bytes are read."""
import json
import time

ACTIVE=("pending","running","paused")
STATES=("pending","running","paused","reviewing","completed","failed","cancelled")

def init(c):
 c.execute("""CREATE TABLE IF NOT EXISTS review_jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  reference_id TEXT NOT NULL DEFAULT '',
  original_sha256 TEXT NOT NULL DEFAULT '',
  offset INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  matched INTEGER NOT NULL DEFAULT 0,
  suggestions TEXT NOT NULL DEFAULT '[]',
  auto_apply INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  backup TEXT NOT NULL DEFAULT '',
  changed INTEGER NOT NULL DEFAULT 0,
  created REAL NOT NULL,
  updated REAL NOT NULL
 )""")
 if "phase" not in [row[1] for row in c.execute("PRAGMA table_info(review_jobs)")]:
  c.execute("ALTER TABLE review_jobs ADD COLUMN phase TEXT NOT NULL DEFAULT ''")
 c.execute("CREATE INDEX IF NOT EXISTS review_jobs_status_idx ON review_jobs(status,id)")
 c.execute("CREATE UNIQUE INDEX IF NOT EXISTS review_jobs_one_active ON review_jobs(video_path) WHERE status IN ('pending','running','paused')")
 c.commit()

def enqueue(c,path,reference_id="",auto_apply=False):
 now=time.time()
 existing=c.execute("SELECT * FROM review_jobs WHERE video_path=? AND status IN ('pending','running','paused') ORDER BY id DESC LIMIT 1",(path,)).fetchone()
 if existing:return dict(existing),False
 c.execute("INSERT INTO review_jobs(video_path,reference_id,auto_apply,created,updated) VALUES(?,?,?,?,?)",
           (path,reference_id,int(bool(auto_apply)),now,now))
 id=c.execute("SELECT last_insert_rowid()").fetchone()[0]
 c.commit()
 return dict(c.execute("SELECT * FROM review_jobs WHERE id=?",(id,)).fetchone()),True

def list_jobs(c,status=""):
 if status and status not in STATES:raise ValueError("未知任务状态")
 rows=c.execute("SELECT * FROM review_jobs WHERE status=? ORDER BY id DESC LIMIT 500",(status,)).fetchall() if status else c.execute("SELECT * FROM review_jobs ORDER BY id DESC LIMIT 500").fetchall()
 return [summarize(row) for row in rows]

def summarize(row):
 d=dict(row)
 d["suggestion_count"]=len(json.loads(d.pop("suggestions")))
 return d

def claim(c):
 # BEGIN IMMEDIATE prevents two processes claiming the same task.
 c.execute("BEGIN IMMEDIATE")
 row=c.execute("SELECT * FROM review_jobs WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
 if row:c.execute("UPDATE review_jobs SET status='running',phase='正在准备字幕',updated=? WHERE id=?",(time.time(),row["id"]))
 c.commit()
 return dict(row) if row else None

def set_phase(c,id,phase):
 c.execute("UPDATE review_jobs SET phase=?,updated=? WHERE id=? AND status='running'",(str(phase)[:160],time.time(),id))
 c.commit()

def checkpoint(c,id,sha,offset,total,matched,suggestions):
 row=c.execute("SELECT status FROM review_jobs WHERE id=?",(id,)).fetchone()
 if not row or row["status"]!="running":return False
 c.execute("UPDATE review_jobs SET original_sha256=?,offset=?,total=?,matched=?,suggestions=?,phase='已保存本批进度',updated=? WHERE id=? AND status='running'",
           (sha,offset,total,matched,json.dumps(suggestions,ensure_ascii=False),time.time(),id))
 c.commit()
 return True

def finish(c,id,status,error="",backup="",changed=0):
 if status not in ("reviewing","completed","failed","cancelled"):raise ValueError("无效的完成状态")
 c.execute("UPDATE review_jobs SET status=?,error=?,backup=?,changed=?,phase='',updated=? WHERE id=? AND status='running'",
           (status,error[:500],backup,changed,time.time(),id))
 c.commit()

def action(c,id,command):
 row=c.execute("SELECT * FROM review_jobs WHERE id=?",(id,)).fetchone()
 if not row:raise ValueError("任务不存在")
 current=row["status"]
 transitions={
  "pause":{"pending":"paused","running":"paused"},
  "resume":{"paused":"pending"},
  "cancel":{"pending":"cancelled","paused":"cancelled","running":"cancelled"},
  "retry":{"failed":"pending","reviewing":"pending","cancelled":"pending"},
 }
 next_status=transitions.get(command,{}).get(current)
 if not next_status:raise ValueError("当前状态不允许该操作")
 if command=="retry":
  c.execute("UPDATE review_jobs SET status=?,error='',phase='',updated=? WHERE id=?",(next_status,time.time(),id))
 else:c.execute("UPDATE review_jobs SET status=?,updated=? WHERE id=?",(next_status,time.time(),id))
 c.commit()
 return summarize(c.execute("SELECT * FROM review_jobs WHERE id=?",(id,)).fetchone())

def retry_legacy_subtitle_selection(c,paths):
 """Retry only previously blocked jobs caused by the old single-sidecar rule."""
 count=0
 for path in dict.fromkeys(paths):
  row=c.execute("SELECT id FROM review_jobs WHERE video_path=? AND status='reviewing' AND error LIKE '需要恰好一份外挂中文字幕%' ORDER BY id DESC LIMIT 1",(path,)).fetchone()
  if not row:continue
  active=c.execute("SELECT 1 FROM review_jobs WHERE video_path=? AND status IN ('pending','running','paused') LIMIT 1",(path,)).fetchone()
  if active:continue
  c.execute("UPDATE review_jobs SET status='pending',error='',phase='',updated=? WHERE id=?",(time.time(),row["id"]))
  count+=1
 c.commit()
 return count

def recover(c):
 # An interrupted running batch can be retried safely from its last checkpoint.
 c.execute("UPDATE review_jobs SET status='pending',updated=? WHERE status='running'",(time.time(),))
 c.commit()
