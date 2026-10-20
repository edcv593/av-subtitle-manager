import os,re,time,json,sqlite3,threading,logging,secrets,urllib.request,urllib.parse,ipaddress,socket
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse
from timeline import assess,video_duration
from reliability import embedded_chinese,score,should_skip,next_retry
import ai_queue
import subtitle_files
import subtitle_quality
MEDIA=Path(os.getenv("MEDIA_ROOT","/media"));DATA=Path(os.getenv("DATA_ROOT","/data"));DATA.mkdir(parents=True,exist_ok=True)
TOKEN=os.getenv("WEB_TOKEN","");AUTO=os.getenv("AUTO_DOWNLOAD","true").lower()=="true"
INTERVAL=max(1,int(os.getenv("SCAN_HOURS","6")))*3600;RETRY=max(1,int(os.getenv("RETRY_HOURS","24")))*3600
AGE=max(0,int(os.getenv("FILE_STABLE_MINUTES","30")))*60;LIMIT=int(os.getenv("MAX_DOWNLOAD_MB","8"))*1024*1024
SKIP_C=os.getenv("SKIP_C_MARKER","true").lower()=="true"
SCORE_THRESHOLD=max(0,min(100,int(os.getenv("SCORE_THRESHOLD","80"))))
CHECK_EMBEDDED=os.getenv("CHECK_EMBEDDED","true").lower()=="true"
REMOTE_MOUNT_MODE=os.getenv("REMOTE_MOUNT_MODE","false").lower()=="true"
AI_QUEUE_ENABLED=os.getenv("AI_QUEUE_ENABLED","true").lower()=="true"
AI_AUTO_ENQUEUE=os.getenv("AI_AUTO_ENQUEUE","false").lower()=="true"
AI_WORKER_ENABLED=os.getenv("AI_WORKER_ENABLED","false").lower()=="true"
AI_MAX_PENDING=max(1,int(os.getenv("AI_MAX_PENDING","500")))
API="https://api-shoulei-ssl.xunlei.com/oracle/subtitle"
VIDEO={".mp4",".mkv",".avi",".mov",".wmv",".ts",".m4v"};SUB={".srt",".ass",".ssa",".vtt"}
logging.basicConfig(level=logging.INFO);log=logging.getLogger("subtitle");lock=threading.Lock();app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
def db():
 c=sqlite3.connect(DATA/"subtitle.db",timeout=30);c.row_factory=sqlite3.Row
 c.execute("CREATE TABLE IF NOT EXISTS videos(path TEXT PRIMARY KEY,code TEXT,status TEXT,detail TEXT,updated REAL,size INTEGER,mtime REAL,next_retry REAL DEFAULT 0)")
 c.execute("CREATE TABLE IF NOT EXISTS candidates(path TEXT,name TEXT,url TEXT,ext TEXT,PRIMARY KEY(path,url))")
 c.execute("CREATE TABLE IF NOT EXISTS retry_attempts(path TEXT PRIMARY KEY,attempts INTEGER NOT NULL DEFAULT 0)")
 ai_queue.init(c)
 c.commit();return c
def code(name):
 m=re.search(r"(?<![A-Z0-9])([A-Z]{2,8})[-_. ]*(\d{2,6})(?!\d)",Path(name).stem.upper())
 return m.group(1)+"-"+m.group(2) if m else None
def marked(name):return bool(re.search(r"(?:^|[-_.\s])C(?:$|[-_.\s])",Path(name).stem.upper()))
def sidecar(p,names=None):
 stem=p.stem.casefold()
 if names is None:names=[q.name for q in p.parent.iterdir() if q.is_file()]
 return any(Path(name).suffix.lower() in SUB and (Path(name).stem.casefold()==stem or Path(name).stem.casefold().startswith(stem+".") or Path(name).stem.casefold().startswith(stem+"-")) for name in names)
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**k):raise ValueError("Redirect blocked")
def fetch(url,limit=2097152):
 u=urllib.parse.urlsplit(url)
 if u.scheme!="https" or not u.hostname or u.username or u.password:raise ValueError("HTTPS required")
 addresses=socket.getaddrinfo(u.hostname,u.port or 443,type=socket.SOCK_STREAM)
 if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):raise ValueError("Private destination rejected")
 req=urllib.request.Request(url,headers={"User-Agent":"AVSubtitleManager/1.0"})
 with urllib.request.build_opener(NoRedirect()).open(req,timeout=35) as resp:
  data=resp.read(limit+1)
  if len(data)>limit:raise ValueError("Subtitle too large")
  return data
def search(number):
 query=urllib.parse.urlencode({"gcid":"","cid":"","name":number})
 obj=json.loads(fetch(API+"?"+query).decode("utf-8-sig"))
 if isinstance(obj,list):return obj
 if isinstance(obj,dict):
  for k in ("data","subtitles","result"):
   if isinstance(obj.get(k),list):return obj[k]
 return []
def normalize(items,number):
 out={}
 for item in items:
  if not isinstance(item,dict):continue
  name=str(item.get("name") or item.get("filename") or "");url=str(item.get("url") or item.get("download_url") or "")
  ext=str(item.get("ext") or item.get("format") or Path(urllib.parse.urlsplit(url).path).suffix).lower().lstrip(".")
  if ext not in ("srt","ass","ssa","vtt") or code(name)!=number:continue
  if not re.search(r"中文|简体|繁体|中字|CHS|CHT|(?:^|[^A-Z])ZH(?:[^A-Z]|$)|CHINESE",name.upper()):continue
  if urllib.parse.urlsplit(url).scheme!="https":continue
  out[url]={"name":name,"url":url,"ext":ext}
 return list(out.values())
def valid(data,ext):
 if not data:return False
 text=None
 for encoding in ("utf-8-sig","utf-16","gb18030"):
  try:text=data.decode(encoding);break
  except UnicodeError:pass
 if not text or len(text)<20:return False
 if ext=="srt":return bool(re.search(r"\d\d:\d\d:\d\d[,\.]\d{3}\s*-->\s*\d\d:\d\d:\d\d",text))
 if ext in ("ass","ssa"):return "[Script Info]" in text and "[Events]" in text
 return text.lstrip().startswith("WEBVTT")
def save(p,c,data=None):
 if data is None:data=fetch(c["url"],LIMIT)
 if not valid(data,c["ext"]):raise ValueError("Invalid subtitle format")
 if subtitle_quality.evaluate(data,c["ext"])["level"]=="blocked":raise ValueError("Subtitle quality blocked")
 target=p.with_name(p.stem+".zh."+c["ext"])
 with target.open("xb") as f:f.write(data)
 return str(target)
def record(c,p,number,status,detail="",retry=0):
 st=p.stat()
 c.execute("INSERT OR REPLACE INTO videos VALUES(?,?,?,?,?,?,?,?)",(str(p),number,status,detail,time.time(),st.st_size,st.st_mtime,retry));c.commit()
def maybe_ai_enqueue(c,p,directory_names=None):
 if not AI_QUEUE_ENABLED or not AI_AUTO_ENQUEUE or not code(p.name) or (SKIP_C and marked(p.name)) or sidecar(p,directory_names):return
 try:
  st=p.stat()
  if CHECK_EMBEDDED and embedded_chinese(p)[0] is not False:return
  ai_queue.enqueue(c,p,st.st_size,st.st_mtime,origin="xunlei_missing",max_pending=AI_MAX_PENDING)
 except (OSError,ValueError) as exc:log.warning("AI enqueue skipped for %s: %s",p,exc)
def schedule_retry(c,p,number,status,detail):
 row=c.execute("SELECT attempts FROM retry_attempts WHERE path=?",(str(p),)).fetchone()
 attempts=(row["attempts"] if row else 0)+1
 c.execute("INSERT OR REPLACE INTO retry_attempts VALUES(?,?)",(str(p),attempts));c.commit()
 record(c,p,number,status,detail,next_retry(status,attempts,RETRY/3600))
def reset_retry(c,p):
 c.execute("DELETE FROM retry_attempts WHERE path=?",(str(p),));c.commit()
def process(c,p,force=False,directory_names=None):
 number=code(p.name)
 st=p.stat()
 old=c.execute("SELECT * FROM videos WHERE path=?",(str(p),)).fetchone()
 if not force and time.time()-st.st_mtime<AGE:return
 if not force and should_skip(old,st):return
 if SKIP_C and marked(p.name):
  reset_retry(c,p);record(c,p,number,"skipped_c","Filename contains -C");return
 if sidecar(p,directory_names):
  reset_retry(c,p);record(c,p,number,"existing","Sidecar subtitle found");return
 if not number:
  reset_retry(c,p);record(c,p,None,"no_code","Cannot parse code");return
 if CHECK_EMBEDDED:
  found,detail=embedded_chinese(p)
  if found is True:
   reset_retry(c,p);record(c,p,number,"embedded",detail);return
  if found is None:
   schedule_retry(c,p,number,"error",detail);return
 try:
  matches=normalize(search(number),number)
  c.execute("DELETE FROM candidates WHERE path=?",(str(p),))
  for item in matches:c.execute("INSERT OR IGNORE INTO candidates VALUES(?,?,?,?)",(str(p),item["name"],item["url"],item["ext"]))
  c.commit()
  if not matches:
   schedule_retry(c,p,number,"missing","No confidently matched subtitle")
   maybe_ai_enqueue(c,p,directory_names)
  elif len(matches)>1:
   schedule_retry(c,p,number,"review",str(len(matches))+" candidates; manual review")
  elif AUTO:
   candidate=matches[0]
   data=fetch(candidate["url"],LIMIT)
   if not valid(data,candidate["ext"]) or subtitle_quality.evaluate(data,candidate["ext"])["level"]=="blocked":
    schedule_retry(c,p,number,"review","字幕格式无法验证，需人工审核")
   else:
    check=assess(data,candidate["ext"],None if REMOTE_MOUNT_MODE else video_duration(p))
    points,reason=score(candidate,check)
    if check["ok"] and not check.get("warnings") and points>=SCORE_THRESHOLD:
     dest=save(p,candidate,data);reset_retry(c,p)
     record(c,p,number,"downloaded",dest+" | score="+str(points)+" | "+reason)
    else:
     schedule_retry(c,p,number,"review","score="+str(points)+" | "+(check["reason"] if (not check["ok"] or check.get("warnings")) else reason))
  else:schedule_retry(c,p,number,"review","Automatic download disabled")
 except FileExistsError:
  reset_retry(c,p);record(c,p,number,"existing","Subtitle already exists")
 except Exception as e:
  log.warning("%s: %s",p,e);schedule_retry(c,p,number,"error",str(e)[:300])

scan_progress={"started_at":None,"last_processed_at":None,"current_file":"","processed":0,"changed":0,"errors":0,"finished_at":None}
progress_lock=threading.Lock()
def progress_snapshot():
 with progress_lock:return dict(scan_progress)
def progress_update(**fields):
 with progress_lock:scan_progress.update(fields)
def scan():
 if not lock.acquire(False):return False
 progress_update(started_at=time.time(),last_processed_at=None,current_file="",processed=0,changed=0,errors=0,finished_at=None)
 try:
  c=db()
  try:
   for root,_,files in os.walk(MEDIA):
    for name in files:
     p=Path(root)/name
     if p.suffix.lower() not in VIDEO:continue
     with progress_lock:
      scan_progress["current_file"]=p.name
     try:
      before=c.execute("SELECT updated FROM videos WHERE path=?",(str(p),)).fetchone()
      process(c,p,directory_names=files if REMOTE_MOUNT_MODE else None)
      after=c.execute("SELECT updated FROM videos WHERE path=?",(str(p),)).fetchone()
      changed=bool(after and (not before or after["updated"]!=before["updated"]))
      with progress_lock:
       scan_progress["processed"]+=1
       scan_progress["changed"]+=int(changed)
       scan_progress["last_processed_at"]=time.time()
     except Exception:
      log.exception("Scan error: %s",p)
      with progress_lock:
       scan_progress["processed"]+=1
       scan_progress["errors"]+=1
       scan_progress["last_processed_at"]=time.time()
     time.sleep(.1)
  finally:c.close()
  return True
 finally:
  progress_update(finished_at=time.time(),current_file="")
  lock.release()
def loop():
 while True:
  try:scan()
  except Exception:log.exception("Background scan failed")
  time.sleep(INTERVAL)
@app.on_event("startup")
def start():
 db().close();threading.Thread(target=loop,daemon=True).start()
def auth(req):
 if not TOKEN or TOKEN=="CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD":raise HTTPException(503,"Configure WEB_TOKEN")
 if not secrets.compare_digest(req.headers.get("x-auth-token",""),TOKEN):raise HTTPException(401,"Invalid token")
def video(c,path):
 r=c.execute("SELECT * FROM videos WHERE path=?",(path,)).fetchone()
 if not r:raise HTTPException(404,"Video not indexed")
 p=Path(path)
 if not p.is_file() or not p.resolve().is_relative_to(MEDIA.resolve()):raise HTTPException(400,"Invalid path")
 return p
@app.get("/api/status")
def status(request:Request):
 auth(request)
 with db() as c:
  return {"counts":{r["status"]:r["n"] for r in c.execute("SELECT status,count(*) n FROM videos GROUP BY status")},"scan_running":lock.locked(),"remote_mount_mode":REMOTE_MOUNT_MODE,"scan_progress":progress_snapshot(),"media":str(MEDIA),"auto":AUTO,"score_threshold":SCORE_THRESHOLD,"ai_queue_enabled":AI_QUEUE_ENABLED,"ai_auto_enqueue":AI_AUTO_ENQUEUE,"ai_worker_enabled":AI_WORKER_ENABLED}
@app.get("/api/videos")
def videos(request:Request,q:str="",status:str=""):
 auth(request)
 with db() as c:
  sql="SELECT path,code,status,detail,updated FROM videos WHERE 1=1";args=[]
  if status:sql+=" AND status=?";args.append(status)
  if q:sql+=" AND (path LIKE ? OR code LIKE ?)";args.extend(["%"+q+"%","%"+q+"%"])
  sql+=" ORDER BY updated DESC LIMIT 500"
  return {"items":[dict(r) for r in c.execute(sql,args)]}
@app.post("/api/scan")
def scan_now(request:Request):
 auth(request)
 if lock.locked():return {"ok":False,"message":"Scan already running"}
 threading.Thread(target=scan,daemon=True).start()
 return {"ok":True}
@app.post("/api/retry")
async def retry(request:Request):
 auth(request);data=await request.json()
 with db() as c:
  p=video(c,str(data.get("path","")));process(c,p,True)
  return {"status":c.execute("SELECT status FROM videos WHERE path=?",(str(p),)).fetchone()["status"]}
@app.get("/api/candidates")
def candidates(request:Request,path:str):
 auth(request)
 with db() as c:
  video(c,path)
  return {"items":[dict(r) for r in c.execute("SELECT name,url,ext FROM candidates WHERE path=?",(path,))]}
@app.get("/api/subtitles")
def subtitle_audit(request:Request,path:str):
 auth(request)
 with db() as c:
  p=video(c,path);items=[]
  for q in subtitle_files.subtitles_for(p):
   try:
    size=q.stat().st_size
    if size>LIMIT:raise ValueError("字幕过大，未读取")
    data=q.read_bytes()
    report=assess(data,q.suffix.lower().lstrip("."),None if REMOTE_MOUNT_MODE else video_duration(p))
    items.append({"name":q.name,"size":size,"valid":valid(data,q.suffix.lower().lstrip(".")),"timeline":report,"quality":subtitle_quality.evaluate(data,q.suffix.lower().lstrip("."))})
   except (OSError,ValueError) as exc:items.append({"name":q.name,"error":str(exc)[:200]})
  return {"items":items,"backups":[q.name for q in subtitle_files.backups_for(p)]}
@app.post("/api/candidates/quality")
async def candidate_quality(request:Request):
 auth(request);body=await request.json()
 with db() as c:
  p=video(c,str(body.get("path","")))
  item=c.execute("SELECT name,url,ext FROM candidates WHERE path=? AND url=?",(str(p),str(body.get("url","")))).fetchone()
  if not item:raise HTTPException(404,"候选不存在")
  try:
   payload=fetch(item["url"],LIMIT)
   if not valid(payload,item["ext"]):return {"score":0,"level":"blocked","reasons":["字幕文件格式无效"]}
   return subtitle_quality.evaluate(payload,item["ext"])
  except Exception as exc:raise HTTPException(502,"候选分析失败："+str(exc)[:160])
@app.post("/api/candidates/refresh")
async def refresh_candidates(request:Request):
 auth(request);body=await request.json()
 with db() as c:
  p=video(c,str(body.get("path","")))
  if SKIP_C and marked(p.name):raise HTTPException(400,"-C 视频已跳过")
  number=code(p.name)
  if not number:raise HTTPException(400,"无法识别番号")
  try:matches=normalize(search(number),number)
  except Exception as exc:raise HTTPException(502,"迅雷搜索失败："+str(exc)[:160])
  c.execute("DELETE FROM candidates WHERE path=?",(str(p),))
  for item in matches:c.execute("INSERT OR IGNORE INTO candidates VALUES(?,?,?,?)",(str(p),item["name"],item["url"],item["ext"]))
  c.commit()
  return {"items":matches}
@app.post("/api/subtitles/replace")
async def replace_subtitle(request:Request):
 auth(request);body=await request.json()
 with db() as c:
  p=video(c,str(body.get("path","")))
  if SKIP_C and marked(p.name):raise HTTPException(400,"-C 视频已跳过")
  item=c.execute("SELECT name,url,ext FROM candidates WHERE path=? AND url=?",(str(p),str(body.get("url","")))).fetchone()
  if not item:raise HTTPException(404,"候选不存在")
  if len(subtitle_files.subtitles_for(p))!=1:raise HTTPException(409,"必须恰好有一份外挂字幕才能安全替换")
  try:
   payload=fetch(item["url"],LIMIT)
   if not valid(payload,item["ext"]):raise ValueError("候选字幕格式无效")
   quality=subtitle_quality.evaluate(payload,item["ext"])
   if quality["level"]=="blocked":raise ValueError("字幕质量未通过："+ "；".join(quality["reasons"]))
   report=assess(payload,item["ext"],None if REMOTE_MOUNT_MODE else video_duration(p))
   target,backup=subtitle_files.replace(p,payload,item["ext"])
   reset_retry(c,p);record(c,p,code(p.name),"downloaded",str(target)+" | backup="+str(backup))
   return {"ok":True,"file":str(target),"backup":backup.name,"timeline":report}
  except (OSError,ValueError) as exc:raise HTTPException(502,"替换失败："+str(exc)[:180])
@app.post("/api/subtitles/restore")
async def restore_subtitle(request:Request):
 auth(request);body=await request.json()
 with db() as c:
  p=video(c,str(body.get("path","")))
  if SKIP_C and marked(p.name):raise HTTPException(400,"-C 视频已跳过")
  try:
   target,backup=subtitle_files.restore(p,str(body.get("backup","")))
   reset_retry(c,p);record(c,p,code(p.name),"existing","Restored "+str(target))
   return {"ok":True,"file":str(target),"backup":backup.name}
  except (OSError,ValueError) as exc:raise HTTPException(409,str(exc)[:180])
@app.post("/api/download")
async def download(request:Request):
 auth(request);data=await request.json();path=str(data.get("path",""));url=str(data.get("url",""))
 with db() as c:
  p=video(c,path)
  if marked(p.name) and SKIP_C:raise HTTPException(400,"-C video skipped")
  if sidecar(p):raise HTTPException(409,"Subtitle already exists")
  if CHECK_EMBEDDED and embedded_chinese(p)[0] is True:raise HTTPException(409,"Embedded Chinese subtitle exists")
  item=c.execute("SELECT name,url,ext FROM candidates WHERE path=? AND url=?",(path,url)).fetchone()
  if not item:raise HTTPException(404,"Candidate not found")
  try:
   data=fetch(item["url"],LIMIT)
   if not valid(data,item["ext"]):raise ValueError("Invalid subtitle format")
   quality=subtitle_quality.evaluate(data,item["ext"])
   if quality["level"]=="blocked":raise ValueError("字幕质量未通过："+ "；".join(quality["reasons"]))
   check=assess(data,item["ext"],None if REMOTE_MOUNT_MODE else video_duration(p))
   # Manual choice explicitly permits downloading a candidate that needs review.
   dest=save(p,dict(item),data);reset_retry(c,p);record(c,p,code(p.name),"downloaded",dest+" | manual | "+check["reason"])
   return {"ok":True,"file":dest,"timeline":check}
  except FileExistsError:raise HTTPException(409,"Subtitle already exists")
  except Exception as e:raise HTTPException(502,str(e)[:200])
def ai_enabled():
 if not AI_QUEUE_ENABLED:raise HTTPException(503,"AI queue disabled")
def ai_job_video(c,path):
 p=video(c,path)
 if SKIP_C and marked(p.name):raise HTTPException(400,"-C video skipped")
 if sidecar(p):raise HTTPException(409,"Subtitle already exists")
 if CHECK_EMBEDDED:
  found,detail=embedded_chinese(p)
  if found is True:raise HTTPException(409,"Embedded Chinese subtitle exists")
  if found is None:raise HTTPException(409,detail)
 return p
@app.get("/api/ai/jobs")
def ai_jobs(request:Request,status:str=""):
 auth(request);ai_enabled()
 with db() as c:
  try:return {"items":ai_queue.list_jobs(c,status)}
  except ValueError as e:raise HTTPException(400,str(e))
@app.post("/api/ai/jobs")
async def ai_add(request:Request):
 auth(request);ai_enabled();body=await request.json()
 with db() as c:
  p=ai_job_video(c,str(body.get("path","")));st=p.stat()
  try:
   job,created=ai_queue.enqueue(c,p,st.st_size,st.st_mtime,max_pending=AI_MAX_PENDING)
   return {"job":job,"created":created}
  except ValueError as e:raise HTTPException(409,str(e))
@app.post("/api/ai/jobs/{job_id}/action")
async def ai_action(job_id:int,request:Request):
 auth(request);ai_enabled();body=await request.json()
 with db() as c:
  try:return {"job":ai_queue.control(c,job_id,str(body.get("action","")))}
  except ValueError as e:raise HTTPException(409,str(e))
# Future worker API is disabled by default. No AI inference is installed or executed.
def worker_auth(request):
 auth(request);ai_enabled()
 if not AI_WORKER_ENABLED:raise HTTPException(503,"AI worker API disabled")
@app.post("/api/ai/worker/claim")
async def ai_claim(request:Request):
 worker_auth(request);body=await request.json()
 with db() as c:
  ai_queue.recover_expired(c)
  try:return {"job":ai_queue.claim(c,str(body.get("worker_id","")))}
  except ValueError as e:raise HTTPException(400,str(e))
@app.post("/api/ai/worker/{job_id}/heartbeat")
async def ai_heartbeat(job_id:int,request:Request):
 worker_auth(request);body=await request.json()
 with db() as c:
  try:return {"job":ai_queue.heartbeat(c,job_id,str(body.get("worker_id","")),body.get("progress"))}
  except ValueError as e:raise HTTPException(409,str(e))
@app.post("/api/ai/worker/{job_id}/transition")
async def ai_transition(job_id:int,request:Request):
 worker_auth(request);body=await request.json()
 with db() as c:
  try:return {"job":ai_queue.transition(c,job_id,str(body.get("worker_id","")),str(body.get("status","")),str(body.get("error","")))}
  except ValueError as e:raise HTTPException(409,str(e))
@app.get("/",response_class=HTMLResponse)
def home():
 return HTML
HTML="""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AV Subtitle Manager</title><style>body{font:15px system-ui;background:#f4f6fa;color:#182434;margin:0}.wrap{max-width:1100px;margin:30px auto;padding:0 16px}h1{font-size:25px}.panel{background:white;border:1px solid #e3e7ed;border-radius:12px;padding:20px;margin:14px 0}button,input,select{padding:9px;border:1px solid #ccd3df;border-radius:7px;font:inherit}button{cursor:pointer}input{min-width:180px}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:11px;border-bottom:1px solid #e8ebf0;word-break:break-all}.muted{color:#667}#message{margin:10px 0;color:#345}button{margin:3px}.grid{display:flex;gap:12px;flex-wrap:wrap}.stat{background:#f3f6fb;padding:14px;border-radius:9px;min-width:100px}</style><div class="wrap"><h1>AV Subtitle Manager</h1><div class="panel"><input id="token" type="password" placeholder="输入 WEB_TOKEN"><button onclick="connect()">连接</button><button onclick="scan()">立即扫描</button><p class="muted">仅供局域网使用，令牌保存在浏览器当前会话。</p><div id="message"></div></div><div class="panel"><div class="grid" id="stats"></div></div><div class="panel"><input id="q" placeholder="番号或文件名"><select id="status"><option value="">全部</option><option value="downloaded">已下载</option><option value="existing">已有字幕</option><option value="embedded">内嵌中文字幕</option><option value="skipped_c">-C 跳过</option><option value="missing">未找到</option><option value="review">待审核/时间轴疑似不匹配</option><option value="error">失败</option></select><button onclick="load()">查询</button><table><thead><tr><th>影片</th><th>番号</th><th>状态</th><th>操作</th></tr></thead><tbody id="rows"></tbody></table><div id="candidates"></div></div><div class="panel"><h2>AI 字幕任务队列</h2><p class="muted">只记录任务，不提取音频、不运行语音识别。默认关闭自动入队和 Worker。</p><button onclick="aiLoad()">刷新 AI 任务</button><select id="aiStatus"><option value="">全部</option><option value="pending">等待处理</option><option value="paused">已暂停</option><option value="reviewing">待审核</option><option value="failed">失败</option><option value="cancelled">已取消</option><option value="completed">已完成</option></select><table><thead><tr><th>影片</th><th>来源</th><th>状态</th><th>操作</th></tr></thead><tbody id="aiRows"></tbody></table></div></div><script>
let token=sessionStorage.getItem("subtitle_token")||"";document.getElementById("token").value=token;
function el(tag,text){let e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e}
function msg(t){document.getElementById("message").textContent=t}
async function api(path,method="GET",body){let r=await fetch(path,{method,headers:{"X-Auth-Token":token,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});let j=await r.json();if(!r.ok)throw Error(j.detail||r.status);return j}
function connect(){token=document.getElementById("token").value;sessionStorage.setItem("subtitle_token",token);load()}
async function load(){try{let q=document.getElementById("q").value,status=document.getElementById("status").value;let [s,v]=await Promise.all([api("/api/status"),api("/api/videos?"+new URLSearchParams({q,status}))]);let stats=document.getElementById("stats");stats.replaceChildren();for(let [k,n] of Object.entries(s.counts)){let d=el("div",k+": "+n);d.className="stat";stats.append(d)}let tbody=document.getElementById("rows");tbody.replaceChildren();for(let x of v.items){let tr=el("tr");let name=el("td",x.path.split("/").pop());name.title=x.path+"\\n"+x.detail;let code=el("td",x.code||"—");let status=el("td",x.status);let actions=el("td");if(["missing","review","error","no_code"].includes(x.status)){let b=el("button","重试");b.onclick=()=>retry(x.path);actions.append(b)}if(["review","downloaded","existing"].includes(x.status)){let b=el("button","字幕审核");b.onclick=()=>show(x.path,tr);actions.append(b)}if(["missing","review","error"].includes(x.status)){let b=el("button","加入 AI 队列");b.onclick=()=>aiAdd(x.path);actions.append(b)}tr.append(name,code,status,actions);tbody.append(tr)}msg(scanInfo(s))}catch(e){msg("刷新失败："+e.message)}}
function scanInfo(s){
 let p=s.scan_progress||{},now=Date.now()/1000;
 let elapsed=p.started_at?Math.floor(((s.scan_running?now:p.finished_at||now)-p.started_at)/60):0;
 let idle=p.last_processed_at?Math.floor((now-p.last_processed_at)):null;
 return "目录："+s.media+" · "+(s.scan_running?"正在扫描":"空闲")+
 " · 已检查 "+(p.processed||0)+" 个 · 本轮更新 "+(p.changed||0)+" 个"+
 " · 耗时 "+elapsed+" 分钟"+
 (s.scan_running&&p.current_file?" · 当前："+p.current_file:"")+
 (s.scan_running&&idle!==null?" · 距上次完成 "+idle+" 秒":"")+
 " · 状态更新 "+new Date().toLocaleTimeString()
}
let lastScanRunning=null;
async function pollStatus(){
 if(!token)return;
 try{
  let s=await api("/api/status");
  let wasRunning=lastScanRunning;
  lastScanRunning=s.scan_running;
  msg(scanInfo(s));
  let stats=document.getElementById("stats");stats.replaceChildren();
  for(let [k,n] of Object.entries(s.counts)){let d=el("div",k+": "+n);d.className="stat";stats.append(d)}
  if(wasRunning===true && !s.scan_running)await load();
 }catch(e){msg("状态更新失败："+e.message)}
}
setInterval(pollStatus,5000);
async function scan(){try{let r=await api("/api/scan","POST");msg(r.ok?"扫描已启动":r.message)}catch(e){msg(e.message)}}
async function retry(path){try{await api("/api/retry","POST",{path});load()}catch(e){msg(e.message)}}
async function show(path,tr){
 let prev=document.getElementById("activeCandidateRow");
 if(prev){let same=prev.previousElementSibling===tr;prev.remove();if(same)return}
 let detail=el("tr");detail.id="activeCandidateRow";
 let cell=el("td");cell.colSpan=4;cell.style.background="#f7f9fd";cell.style.padding="16px";
 detail.append(cell);tr.after(detail);
 async function render(){
  cell.replaceChildren(el("p","正在读取字幕和候选…"));
  try{
   let [subs,candidates]=await Promise.all([
    api("/api/subtitles?"+new URLSearchParams({path})),
    api("/api/candidates?"+new URLSearchParams({path}))
   ]);
   if(!detail.isConnected)return;
   cell.replaceChildren(el("h3",path.split("/").pop()+" · 字幕审核"));
   if(!subs.items.length)cell.append(el("p","当前没有外挂字幕。"));
   for(let sub of subs.items){
    cell.append(el("p","现有字幕："+sub.name+" · "+(sub.error||((sub.valid?"格式有效":"格式异常")+" · "+sub.timeline.reason))));
   }
   if(subs.items.length)cell.append(el("p","提示：时间轴检查不能确认对白同步，建议在播放器中实际试看。"));
   for(let name of subs.backups){
    let d=el("div","备份："+name+" ");
    let restore=el("button","恢复此备份");
    restore.onclick=async()=>{
     if(!confirm("确认恢复旧字幕？当前字幕也会保留备份。"))return;
     restore.disabled=true;
     try{let out=await api("/api/subtitles/restore","POST",{path,backup:name});msg("已恢复："+out.file);await load()}
     catch(e){cell.append(el("p","恢复失败："+e.message));restore.disabled=false}
    };
    d.append(restore);cell.append(d);
   }
   let refresh=el("button","重新搜索迅雷候选");
   refresh.onclick=async()=>{
    refresh.disabled=true;refresh.textContent="正在搜索…";
    try{await api("/api/candidates/refresh","POST",{path});await render()}
    catch(e){cell.append(el("p","搜索失败："+e.message));refresh.disabled=false;refresh.textContent="重新搜索迅雷候选"}
   };
   cell.append(refresh);
   cell.append(el("p","迅雷候选："+candidates.items.length+" 个"));
   if(!candidates.items.length)cell.append(el("p","暂无候选，可点击重新搜索。"));
   for(let x of candidates.items){
    let d=el("div");d.style.padding="8px 0";d.style.borderTop="1px solid #e3e7ed";
    d.append(el("span",x.name+" "));
    let btn=el("button",subs.items.length?"备份旧字幕并更换":"人工确认下载");
    btn.onclick=async()=>{
     if(!confirm("远程挂载模式不验证视频时长。请确认字幕与影片匹配；如有旧字幕将先备份。继续？"))return;
     btn.disabled=true;btn.textContent="正在下载并写入…";
     try{
      let endpoint=subs.items.length?"/api/subtitles/replace":"/api/download";
      let out=await api(endpoint,"POST",{path,url:x.url});
      msg("字幕保存成功："+out.file+(out.backup?"；旧字幕备份："+out.backup:""));
      await load();
     }catch(e){cell.append(el("p","操作失败："+e.message));msg("字幕操作失败："+e.message);btn.disabled=false;btn.textContent="重试下载"}
    };
    d.append(btn);cell.append(d);
   }
  }catch(e){cell.replaceChildren(el("p","字幕审核加载失败："+e.message));msg("字幕审核失败："+e.message)}
 }
 await render();
}
async function aiAdd(path){try{let r=await api("/api/ai/jobs","POST",{path});msg(r.created?"已加入 AI 队列":"任务已存在，未重复入队");aiLoad()}catch(e){msg("AI 入队失败："+e.message)}}
async function aiAction(id,action){try{await api("/api/ai/jobs/"+id+"/action","POST",{action});aiLoad()}catch(e){msg("AI 操作失败："+e.message)}}
async function aiLoad(){try{let filter=document.getElementById("aiStatus").value;let result=await api("/api/ai/jobs?"+new URLSearchParams({status:filter}));let tbody=document.getElementById("aiRows");tbody.replaceChildren();for(let j of result.items){let tr=el("tr"),name=el("td",j.video_path.split("/").pop()),origin=el("td",j.origin),status=el("td",j.status),actions=el("td");name.title=j.video_path+"\\n"+j.last_error;let available=j.status==="pending"?["pause","cancel"]:j.status==="paused"?["resume","cancel"]:j.status==="failed"?["retry","cancel"]:j.status==="reviewing"?["retry","cancel"]:j.status==="cancelled"?["retry"]:[];for(let action of available){let b=el("button",({pause:"暂停",resume:"恢复",cancel:"取消",retry:"重试"})[action]);b.onclick=()=>aiAction(j.id,action);actions.append(b)}tr.append(name,origin,status,actions);tbody.append(tr)}}catch(e){msg("AI 队列加载失败："+e.message)}}
</script></html>"""
