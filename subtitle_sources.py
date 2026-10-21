"""Choose a Chinese base subtitle using quality and Japanese timeline evidence."""
from pathlib import Path

import subtitle_compare
import subtitle_quality
import timeline

def evaluate_chinese(data,ext,reference=None,reference_ext=None):
 """Return comparable metrics or None; Japanese-only subtitles are rejected."""
 if not data or len(data)>4*1024*1024:return None
 try:
  quality=subtitle_quality.evaluate(data,ext)
  rows=subtitle_compare.entries(data,ext)
 except (ValueError,TypeError,UnicodeError):return None
 if quality["level"]=="blocked" or len(rows)<3:return None
 han=sum(bool(subtitle_compare.HAN.search(row["text"])) for row in rows)
 kana=sum(bool(subtitle_compare.JAPANESE.search(row["text"])) for row in rows)
 if han/len(rows)<0.45 or kana/len(rows)>0.08:return None
 aligned=0;coverage=None
 if reference is not None:
  try:
   ref=subtitle_compare.entries(reference,reference_ext)
   aligned=sum(1 for match in subtitle_compare.match(rows,ref) if match["reference"])
   coverage=round(aligned/len(rows),3)
  except (ValueError,TypeError):coverage=0
 # Quality dominates; alignment breaks ties and rejects severe mismatch.
 score=quality["score"]+(min(12,round((coverage or 0)*12)) if reference is not None else 0)
 return {"score":score,"quality":quality["score"],"cues":len(rows),"matched":aligned,"coverage":coverage}

def choose(candidates,reference=None,reference_ext=None):
 """Candidate: {name, data, ext, source}; deterministic and deduplicated."""
 import hashlib
 evaluated=[];seen=set()
 for candidate in candidates:
  data=candidate["data"];ext=candidate["ext"]
  sha=hashlib.sha256(data).hexdigest()
  if sha in seen:continue
  seen.add(sha)
  metrics=evaluate_chinese(data,ext,reference,reference_ext)
  if metrics is None:continue
  if reference is not None and metrics["coverage"]<0.10:continue
  evaluated.append({**candidate,**metrics,"sha256":sha})
 evaluated.sort(key=lambda item:(item["score"],item["matched"],item["cues"],item["sha256"]),reverse=True)
 return evaluated[0] if evaluated else None
