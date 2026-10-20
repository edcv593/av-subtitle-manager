"""Library scanning policy, embedded subtitle probing, candidate ranking and retries."""
import json,random,re,subprocess,time
from pathlib import Path

SUCCESS_STATES={"downloaded","existing","embedded","skipped_c","no_code"}
RETRY_STATES={"missing","error","review"}
LANGUAGES={"chi","zho","zh","chs","cht","cmn"}
def embedded_chinese(path):
    """Return (found, detail). Unknown probe results must not silently imply absence."""
    try:
        run=subprocess.run(
            ["ffprobe","-v","error","-select_streams","s","-show_entries",
             "stream=index,codec_name:stream_tags=language,title,handler_name",
             "-of","json",str(path)],capture_output=True,text=True,timeout=35,check=True)
        obj=json.loads(run.stdout)
        for stream in obj.get("streams",[]):
            tags={str(k).lower():str(v).lower() for k,v in stream.get("tags",{}).items()}
            language=tags.get("language","").split("-")[0].split("_")[0]
            description=" ".join((tags.get("title",""),tags.get("handler_name","")))
            if language in LANGUAGES or re.search(r"中文|简体|繁体|中字|chinese|mandarin|\bchs\b|\bcht\b",description,re.I):
                return True,"Embedded Chinese subtitle track: "+str(stream.get("index","?"))
        return False,"No identified Chinese subtitle track"
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        return None,"Embedded subtitle probe failed: "+str(exc)[:140]

def score(candidate,check):
    """Conservative heuristic, not a probability or an audio synchronization check."""
    if not check.get("ok"):return 0,check.get("reason","Timeline failed")
    name=candidate.get("name","")
    points=65
    reasons=["番号匹配","时间轴检查通过"]
    if re.search(r"简体|简中|\bchs\b|\bsc\b",name,re.I):
        points+=15;reasons.append("明确简体标记")
    elif re.search(r"繁体|繁中|\bcht\b|\btc\b",name,re.I):
        points+=12;reasons.append("明确繁体标记")
    elif re.search(r"中文|中字|chinese|\bzh\b",name,re.I):
        points+=10;reasons.append("中文标记")
    if candidate.get("ext")=="srt":points+=5;reasons.append("SRT")
    if re.search(r"uncensored|uncut|cut|剪辑|删减|重制|不同版本",name,re.I):
        points-=20;reasons.append("可能存在版本差异")
    return max(0,min(points,100)),"、".join(reasons)

def should_skip(old,stat,now=None):
    """Cache terminal states, and defer retryable states until due."""
    if old is None:return False
    if old["size"]!=stat.st_size or old["mtime"]!=stat.st_mtime:return False
    if old["status"] in SUCCESS_STATES:return True
    if old["status"] in RETRY_STATES:return float(old["next_retry"] or 0)>(time.time() if now is None else now)
    return False

def retry_delay(status,attempts,base_hours=24):
    attempts=max(1,int(attempts))
    if status=="missing":hours=min(24*14,base_hours*2**min(attempts-1,4))
    elif status=="review":hours=24*7
    else:hours=min(24,2**min(attempts-1,5))
    return hours*3600

def next_retry(status,attempts,base_hours=24,now=None):
    return (time.time() if now is None else now)+retry_delay(status,attempts,base_hours)
