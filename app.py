import os,re,time,json,sqlite3,threading,logging,secrets,urllib.request,urllib.parse,ipaddress,socket
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse
from timeline import assess,video_duration
from reliability import embedded_chinese,score,should_skip,next_retry
MEDIA=Path(os.getenv("MEDIA_ROOT","/media"));DATA=Path(os.getenv("DATA_ROOT","/data"));DATA.mkdir(parents=True,exist_ok=True)
TOKEN=os.getenv("WEB_TOKEN","");AUTO=os.getenv("AUTO_DOWNLOAD","true").lower()=="true"
INTERVAL=max(1,int(os.getenv("SCAN_HOURS","6")))*3600;RETRY=max(1,int(os.getenv("RETRY_HOURS","24")))*3600
AGE=max(0,int(os.getenv("FILE_STABLE_MINUTES","30")))*60;LIMIT=int(os.getenv("MAX_DOWNLOAD_MB","8"))*1024*1024
SKIP_C=os.getenv("SKIP_C_MARKER","true").lower()=="true"
SCORE_THRESHOLD=max(0,min(100,int(os.getenv("SCORE_THRESHOLD","80"))))
CHECK_EMBEDDED=os.getenv("CHECK_EMBEDDED","true").lower()=="true"
API="https://api-shoulei-ssl.xunlei.com/oracle/subtitle"
VIDEO={".mp4",".mkv",".avi",".mov",".wmv",".ts",".m4v"};SUB={".srt",".ass",".ssa",".vtt"}
logging.basicConfig(level=logging.INFO);log=logging.getLogger("subtitle");lock=threading.Lock();app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
def db():
 c=sqlite3.connect(DATA/"subtitle.db",timeout=30);c.row_factory=sqlite3.Row
 c.execute("CREATE TABLE IF NOT EXISTS videos(path TEXT PRIMARY KEY,code TEXT,status TEXT,detail TEXT,updated REAL,size INTEGER,mtime REAL,next_retry REAL DEFAULT 0)")
 c.execute("CREATE TABLE IF NOT EXISTS candidates(path TEXT,name TEXT,url TEXT,ext TEXT,PRIMARY KEY(path,url))")
 c.execute("CREATE TABLE IF NOT EXISTS retry_attempts(path TEXT PRIMARY KEY,attempts INTEGER NOT NULL DEFAULT 0)")
 c.commit();return c
def code(name):
 m=re.search(r"(?<![A-Z0-9])([A-Z]{2,8})[-_. ]*(\d{2,6})(?!\d)",Path(name).stem.upper())
 return m.group(1)+"-"+m.group(2) if m else None
def marked(name):return bool(re.search(r"(?:^|[-_.\s])C(?:$|[-_.\s])",Path(name).stem.upper()))
def sidecar(p):
 stem=p.stem.casefold()
 return any(q.is_file() and q.suffix.lower() in SUB and (q.stem.casefold()==stem or q.stem.casefold().startswith(stem+".") or q.stem.casefold().startswith(stem+"-")) for q in p.parent.iterdir())
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
 target=p.with_name(p.stem+".zh."+c["ext"])
 with target.open("xb") as f:f.write(data)
 return str(target)
def record(c,p,number,status,detail="",retry=0):
 st=p.stat()
 c.execute("INSERT OR REPLACE INTO videos VALUES(?,?,?,?,?,?,?,?)",(str(p),number,status,detail,time.time(),st.st_size,st.st_mtime,retry));c.commit()
def schedule_retry(c,p,number,status,detail):
 row=c.execute("SELECT attempts FROM retry_attempts WHERE path=?",(str(p),)).fetchone()
 attempts=(row["attempts"] if row else 0)+1
 c.execute("INSERT OR REPLACE INTO retry_attempts VALUES(?,?)",(str(p),attempts));c.commit()
 record(c,p,number,status,detail,next_retry(status,attempts,RETRY/3600))
def reset_retry(c,p):
 c.execute("DELETE FROM retry_attempts WHERE path=?",(str(p),));c.commit()
def process(c,p,force=False):
 number=code(p.name)
 st=p.stat()
 old=c.execute("SELECT * FROM videos WHERE path=?",(str(p),)).fetchone()
 if not force and time.time()-st.st_mtime<AGE:return
 if not force and should_skip(old,st):return
 if SKIP_C and marked(p.name):
  reset_retry(c,p);record(c,p,number,"skipped_c","Filename contains -C");return
 if sidecar(p):
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
  elif len(matches)>1:
   schedule_retry(c,p,number,"review",str(len(matches))+" candidates; manual review")
  elif AUTO:
   candidate=matches[0]
   data=fetch(candidate["url"],LIMIT)
   if not valid(data,candidate["ext"]):
    schedule_retry(c,p,number,"review","字幕格式无法验证，需人工审核")
   else:
    check=assess(data,candidate["ext"],video_duration(p))
    points,reason=score(candidate,check)
    if check["ok"] and points>=SCORE_THRESHOLD:
     dest=save(p,candidate,data);reset_retry(c,p)
     record(c,p,number,"downloaded",dest+" | score="+str(points)+" | "+reason)
    else:
     schedule_retry(c,p,number,"review","score="+str(points)+" | "+(check["reason"] if not check["ok"] else reason))
  else:schedule_retry(c,p,number,"review","Automatic download disabled")
 except FileExistsError:
  reset_retry(c,p);record(c,p,number,"existing","Subtitle already exists")
 except Exception as e:
  log.warning("%s: %s",p,e);schedule_retry(c,p,number,"error",str(e)[:300])

def scan():
 if not lock.acquire(False):return False
 try:
  c=db()
  try:
   for root,_,files in os.walk(MEDIA):
    for name in files:
     p=Path(root)/name
     if p.suffix.lower() not in VIDEO:continue
     try:process(c,p)
     except Exception:log.exception("Scan error: %s",p)
     time.sleep(.1)
  finally:c.close()
  return True
 finally:lock.release()
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
  return {"counts":{r["status"]:r["n"] for r in c.execute("SELECT status,count(*) n FROM videos GROUP BY status")},"scan_running":lock.locked(),"media":str(MEDIA),"auto":AUTO,"score_threshold":SCORE_THRESHOLD}
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
   check=assess(data,item["ext"],video_duration(p))
   # Manual choice explicitly permits downloading a candidate that needs review.
   dest=save(p,dict(item),data);reset_retry(c,p);record(c,p,code(p.name),"downloaded",dest+" | manual | "+check["reason"])
   return {"ok":True,"file":dest,"timeline":check}
  except FileExistsError:raise HTTPException(409,"Subtitle already exists")
  except Exception as e:raise HTTPException(502,str(e)[:200])
@app.get("/",response_class=HTMLResponse)
def home():
 return HTML
HTML="""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AV Subtitle Manager</title><style>body{font:15px system-ui;background:#f4f6fa;color:#182434;margin:0}.wrap{max-width:1100px;margin:30px auto;padding:0 16px}h1{font-size:25px}.panel{background:white;border:1px solid #e3e7ed;border-radius:12px;padding:20px;margin:14px 0}button,input,select{padding:9px;border:1px solid #ccd3df;border-radius:7px;font:inherit}button{cursor:pointer}input{min-width:180px}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:11px;border-bottom:1px solid #e8ebf0;word-break:break-all}.muted{color:#667}#message{margin:10px 0;color:#345}button{margin:3px}.grid{display:flex;gap:12px;flex-wrap:wrap}.stat{background:#f3f6fb;padding:14px;border-radius:9px;min-width:100px}</style><div class="wrap"><h1>AV Subtitle Manager</h1><div class="panel"><input id="token" type="password" placeholder="输入 WEB_TOKEN"><button onclick="connect()">连接</button><button onclick="scan()">立即扫描</button><p class="muted">仅供局域网使用，令牌保存在浏览器当前会话。</p><div id="message"></div></div><div class="panel"><div class="grid" id="stats"></div></div><div class="panel"><input id="q" placeholder="番号或文件名"><select id="status"><option value="">全部</option><option value="downloaded">已下载</option><option value="existing">已有字幕</option><option value="embedded">内嵌中文字幕</option><option value="skipped_c">-C 跳过</option><option value="missing">未找到</option><option value="review">待审核/时间轴疑似不匹配</option><option value="error">失败</option></select><button onclick="load()">查询</button><table><thead><tr><th>影片</th><th>番号</th><th>状态</th><th>操作</th></tr></thead><tbody id="rows"></tbody></table><div id="candidates"></div></div></div><script>
let token=sessionStorage.getItem("subtitle_token")||"";document.getElementById("token").value=token;
function el(tag,text){let e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e}
function msg(t){document.getElementById("message").textContent=t}
async function api(path,method="GET",body){let r=await fetch(path,{method,headers:{"X-Auth-Token":token,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});let j=await r.json();if(!r.ok)throw Error(j.detail||r.status);return j}
function connect(){token=document.getElementById("token").value;sessionStorage.setItem("subtitle_token",token);load()}
async function load(){try{let q=document.getElementById("q").value,status=document.getElementById("status").value;let [s,v]=await Promise.all([api("/api/status"),api("/api/videos?"+new URLSearchParams({q,status}))]);let stats=document.getElementById("stats");stats.replaceChildren();for(let [k,n] of Object.entries(s.counts)){let d=el("div",k+": "+n);d.className="stat";stats.append(d)}let tbody=document.getElementById("rows");tbody.replaceChildren();for(let x of v.items){let tr=el("tr");let name=el("td",x.path.split("/").pop());name.title=x.path+"\n"+x.detail;let code=el("td",x.code||"—");let status=el("td",x.status);let actions=el("td");if(["missing","review","error","no_code"].includes(x.status)){let b=el("button","重试");b.onclick=()=>retry(x.path);actions.append(b)}if(x.status==="review"){let b=el("button","候选");b.onclick=()=>show(x.path);actions.append(b)}tr.append(name,code,status,actions);tbody.append(tr)}msg("目录："+s.media+" · "+(s.scan_running?"正在扫描":"空闲"))}catch(e){msg("连接失败："+e.message)}}
async function scan(){try{let r=await api("/api/scan","POST");msg(r.ok?"扫描已启动":r.message)}catch(e){msg(e.message)}}
async function retry(path){try{await api("/api/retry","POST",{path});load()}catch(e){msg(e.message)}}
async function show(path){try{let r=await api("/api/candidates?"+new URLSearchParams({path}));let box=document.getElementById("candidates");box.replaceChildren(el("h3",path.split("/").pop()+" 候选字幕"));for(let x of r.items){let d=el("div");d.append(el("span",x.name+" "));let b=el("button","人工确认下载");b.onclick=async()=>{if(!confirm("请确认字幕与影片版本匹配。时间轴校验不通过时仍会下载，是否继续："+x.name+"？"))return;try{await api("/api/download","POST",{path,url:x.url});box.replaceChildren();load()}catch(e){msg(e.message)}};d.append(b);box.append(d)}}catch(e){msg(e.message)}}
</script></html>"""
