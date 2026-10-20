"""Conservative, AV-aware subtitle text quality checks. No video/audio reads."""
import re
import hashlib
from collections import Counter
from timeline import cues,decode

CJK=re.compile(r"[\u3400-\u9fff]")
URL=re.compile(r"https?://|www\.|(?:t\.me|bit\.ly|discord\.gg)/",re.I)
PROMO=re.compile(r"加群|群号|扫码|二维码|关注公众号|字幕组招募|推广|博彩|赌场|成人视频网址|联系(?:客服|微信)|购买会员")
TAG=re.compile(r"<[^>]*>|\{\\[^}]*\}")
def lines(data,ext):
 text=decode(data)
 if text is None:return []
 if ext in ("srt","vtt"):
  blocks=re.split(r"\n\s*\n",text.replace("\r\n","\n").replace("\r","\n"))
  out=[]
  for block in blocks:
   rows=block.splitlines()
   positions=[i for i,row in enumerate(rows) if "-->" in row]
   if positions:
    content=" ".join(rows[positions[0]+1:])
    if content.strip():out.append(content)
  return out
 if ext in ("ass","ssa"):
  out=[]
  for row in text.splitlines():
   if row.lstrip().lower().startswith("dialogue:"):
    # ASS Text is the last Format field; standard layouts have 9 commas.
    fields=row.split(":",1)[1].split(",",9)
    if len(fields)==10:out.append(fields[-1].replace(r"\N"," "))
  return out
 return []
def evaluate(data,ext):
 timeline=cues(data,ext)
 raw=lines(data,ext)
 cleaned=[TAG.sub("",x).strip() for x in raw]
 cleaned=[re.sub(r"\s+"," ",x) for x in cleaned if x.strip()]
 reasons=[];warnings=[];score=100
 fingerprint=hashlib.sha256(data).hexdigest()
 if not timeline or not cleaned:
  return {"score":0,"level":"blocked","reasons":["无法解析有效字幕事件或对白"],"warnings":[],"cues":0,"chinese_ratio":0}
 if len(timeline)!=len(cleaned):
  warnings.append("部分字幕事件缺少正文或解析不完整")
 invalid=sum(1 for start,end in timeline if end<=start or start<0)
 long=sum(1 for start,end in timeline if end-start>900)
 if invalid:
  score-=min(45,15+invalid*5)
  reasons.append(f"发现{invalid}条结束时间不晚于开始时间的字幕")
 if long:
  score-=min(20,5+long*2)
  warnings.append(f"发现{long}条显示超过15分钟的字幕，可能是片头或制作信息")
 if invalid/max(len(timeline),1)>.1 and invalid>=3:
  score=min(score,60)
  reasons.append("异常时间戳比例较高，需更换或修复")
 inversions=sum(1 for i in range(1,len(timeline)) if timeline[i][0]+3<timeline[i-1][0])
 if inversions>max(2,len(timeline)*.02):
  score-=25
  reasons.append(f"字幕事件顺序异常（{inversions}处）")
 if len(cleaned)>=20:
  awkward=sum(bool(re.search(r"[。！？]\s*[。！？]",line)) for line in cleaned)
  if awkward/max(len(cleaned),1)>.2:
   score-=10;reasons.append(f"约{awkward}条字幕有重复标点，疑似机翻后处理问题")
 if len(cleaned)<3:
  score-=25;reasons.append("有效字幕事件极少，需人工确认")
 text="".join(cleaned)
 replacement=text.count("\ufffd")
 if replacement>=3:
  score-=min(60,replacement*8);reasons.append("存在明显乱码替换字符")
 # Exclude Latin, digits and punctuation from Chinese-language denominator.
 letters=sum(1 for ch in text if ch.isalpha())
 han=sum(bool(CJK.fullmatch(ch)) for ch in text)
 ratio=han/max(letters,1)
 if letters>=40 and ratio<.12:
  score-=45;reasons.append("中文字幕正文占比很低")
 elif letters>=40 and ratio<.35:
  score-=20;reasons.append("中文字幕正文占比较低")
 elif letters<40:
  warnings.append("可分析文字较少，无法可靠判定语言")
 ads=sum(bool(URL.search(x) or PROMO.search(x)) for x in cleaned)
 if ads:
  score-=min(45,15+ads*5);reasons.append(f"检测到{ads}条疑似广告或推广内容")
 counts=Counter(x for x in cleaned if len(x)>=4)
 repeats=sum(n for n in counts.values() if n>=4)
 if len(cleaned)>=12 and repeats/len(cleaned)>.5:
  score-=30;reasons.append("大量相同长句重复")
 # AV-specific: sparse cues, long silent gaps and brief vocalizations are NOT penalties.
 if len(cleaned)>=10 and len(set(cleaned))<=2:
  score-=25;reasons.append("字幕正文变化极少")
 score=max(0,min(100,score))
 level="blocked" if score<65 else "review" if score<85 else "recommended"
 if not reasons:reasons.append("未发现明显文本质量问题；不代表与视频对白同步")
 return {"score":score,"level":level,"reasons":reasons,"warnings":warnings,"cues":len(timeline),"chinese_ratio":round(ratio,3),"ads":ads}
