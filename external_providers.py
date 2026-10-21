"""Best-effort public-index discovery. Never trusts search snippets as subtitle downloads."""
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

SITES={"AVSubtitles":"avsubtitles.com","Subtitle Cat":"subtitlecat.com","JAV字幕":"javzimu.com"}
DETAIL_PATTERNS={
 "AVSubtitles":re.compile(r"(?:/subtitles[.]php[?][^#]*subid=[0-9]+|/movie[0-9]+(?:/[^?#]*)?)",re.I),
 "Subtitle Cat":re.compile(r"/subs/\d+/[^?#]+\.html$",re.I),
 "JAV字幕":re.compile(r"/[^?#]+",re.I),
}
CODE_RE=re.compile(r"(?<![A-Z0-9])([A-Z]{2,8})[-_. ]*(\d{2,6})(?!\d)",re.I)

def film_code(value):
 match=CODE_RE.search(urllib.parse.unquote(value))
 return (match.group(1)+"-"+match.group(2)).upper() if match else None

def indexed_pages(number,fetch_text,max_pages=5):
 """Find likely detail pages via Bing's public RSS search; failures stay per-source."""
 found={};errors={}
 for source,domain in SITES.items():
  query="site:"+domain+" "+number
  # Keep the search query simple to avoid escaped-quote syntax regressions.
  url="https://www.bing.com/search?"+urllib.parse.urlencode({"q":query,"format":"rss"})
  try:
   data=fetch_text(url,250000)
   root=ET.fromstring(data)
   pages=[]
   for item in root.findall(".//item"):
    title=item.findtext("title","")
    link=html.unescape(item.findtext("link",""))
    parsed=urllib.parse.urlsplit(link)
    if parsed.scheme!="https" or parsed.hostname not in (domain,"www."+domain):continue
    if number not in {film_code(title),film_code(urllib.parse.unquote(parsed.path))}:continue
    if not DETAIL_PATTERNS[source].search(parsed.path+("?"+parsed.query if parsed.query else "")):continue
    if link not in pages:pages.append(link)
    if len(pages)>=max_pages:break
   found[source]=pages
  except Exception as exc:
   found[source]=[];errors[source]=str(exc)[:120]
 return found,errors

class Links(HTMLParser):
 def __init__(self):
  super().__init__();self.links=[];self.current=None
 def handle_starttag(self,tag,attrs):
  if tag=="a":self.current=dict(attrs).get("href")
 def handle_data(self,data):
  if self.current and data.strip():self.links.append((self.current,data.strip()))
 def handle_endtag(self,tag):
  if tag=="a":self.current=None

def detail_downloads(source,url,page,max_links=8):
 """Extract only explicit Chinese download links, never fabricate a URL."""
 parser=Links();parser.feed(page.decode("utf-8","replace"))
 result=[]
 for href,label in parser.links:
  target=urllib.parse.urljoin(url,html.unescape(href))
  p=urllib.parse.urlsplit(target)
  if p.scheme!="https" or p.hostname not in (SITES[source],"www."+SITES[source]):continue
  if source=="AVSubtitles":
   if not (p.path.endswith("/download_sub.php") or p.path.endswith(".zip")):continue
   if not re.search(r"zh|chinese|中文|\.zip",label+" "+target,re.I):continue
  elif source=="Subtitle Cat":
   if not re.search(r"zh-CN|zh-TW|Chinese \(Simplified\)|Chinese \(Traditional\)",label+" "+target,re.I):continue
  else:
   if not re.search(r"\.srt|\.ass|\.ssa|\.vtt|\.zip",p.path,re.I):continue
   if not re.search(r"中字|中文|字幕|zh|chs|cht",label+" "+target,re.I):continue
  if target not in result:result.append(target)
  if len(result)>=max_links:break
 return result

# Independent on-site search adapters. A source failure never blocks other sites.
SEARCH_ENDPOINTS={
 "AVSubtitles":lambda code:"https://www.avsubtitles.com/search_results.php?"+urllib.parse.urlencode({"search":code}),
 "Subtitle Cat":lambda code:"https://www.subtitlecat.com/?"+urllib.parse.urlencode({"search":code}),
 "JAV字幕":lambda code:"https://javzimu.com/api/search?"+urllib.parse.urlencode({"name":code}),
}
class SearchLinks(HTMLParser):
 def __init__(self):
  super().__init__();self.links=[];self.href=None;self.parts=[]
 def handle_starttag(self,tag,attrs):
  if tag=="a":
   self.href=dict(attrs).get("href");self.parts=[]
 def handle_data(self,data):
  if self.href is not None:self.parts.append(data)
 def handle_endtag(self,tag):
  if tag=="a" and self.href is not None:
   self.links.append((self.href," ".join(self.parts).strip()))
   self.href=None;self.parts=[]

def javzimu_results(raw,number,max_items=12):
 """Parse JAV字幕 official-style search JSON; never trust returned download URLs."""
 try:response=json.loads(raw.decode("utf-8-sig"))
 except (UnicodeError,ValueError) as exc:raise ValueError("JAV字幕搜索接口未返回有效 JSON") from exc
 if not isinstance(response,dict) or not isinstance(response.get("data"),list):raise ValueError("JAV字幕搜索接口格式发生变化")
 found=[]
 for item in response["data"]:
  if not isinstance(item,dict):continue
  name=str(item.get("name") or "")
  extra=str(item.get("extra_name") or "")
  if number not in {film_code(name),film_code(extra)}:continue
  cid=str(item.get("cid") or "")
  ext=str(item.get("ext") or "srt").lower().lstrip(".")
  if not cid or len(cid)>120 or not re.fullmatch(r"[A-Za-z0-9_-]+",cid) or ext not in ("srt","ass","ssa","vtt","zip"):continue
  url="https://javzimu.com/api/download?"+urllib.parse.urlencode({"cid":cid,"ext":ext,"name":name})
  if url not in found:found.append(url)
  if len(found)>=max_items:break
 return found

def avsubtitles_reference_pages(number,raw,max_items=12):
 """Discover explicit AVSubtitles Japanese reference detail links from search HTML."""
 parser=SearchLinks();parser.feed(raw.decode("utf-8","replace"))
 results=[]
 for href,title in parser.links:
  url=urllib.parse.urljoin("https://www.avsubtitles.com/",html.unescape(href))
  parsed=urllib.parse.urlsplit(url)
  if parsed.scheme!="https" or parsed.hostname not in ("avsubtitles.com","www.avsubtitles.com"):continue
  if not re.fullmatch(r"/movie[0-9]+/[^/?#]+/subtitles/ja/[0-9]+/?",parsed.path,re.I):continue
  # The first token is movie83051; match the actual title code in the slug.
  slug=urllib.parse.unquote(parsed.path.split("/")[2])
  if number not in {(m.group(1)+"-"+m.group(2)).upper() for m in CODE_RE.finditer(slug)}:continue
  if url not in results:results.append(url)
  if len(results)>=max_items:break
 return results

def avsubtitles_reference_downloads(url,page,max_links=8):
 """Extract real AVSubtitles download URLs, preserving the site's revid parameter."""
 parsed=urllib.parse.urlsplit(url)
 if parsed.scheme!="https" or parsed.hostname not in ("avsubtitles.com","www.avsubtitles.com") or not re.fullmatch(r"/movie[0-9]+/[^/?#]+/subtitles/ja/[0-9]+/?",parsed.path,re.I):
  raise ValueError("不是 AVSubtitles 日语字幕详情页")
 subid=parsed.path.rstrip("/").rsplit("/",1)[-1]
 text=html.unescape(page.decode("utf-8","replace")).replace("\\/","/")
 parser=Links();parser.feed(text)
 candidates=[href for href,_ in parser.links]
 # Download links can be attached to buttons or JavaScript, not just visible <a> text.
 candidates+=re.findall(r"""(?:href|data-url|data-href|window[.]location(?:[.]href)?|location[.]href)\s*[=:]\s*['"]([^'"]+)['"]""",text,re.I)
 candidates+=re.findall(r"""(?:https?://(?:www[.])?avsubtitles[.]com)?/download_sub[.]php[?][^\s'"<>\\]+""",text,re.I)
 links=[]
 for href in candidates:
  target=urllib.parse.urljoin(url,html.unescape(href).replace("&amp;","&"))
  dest=urllib.parse.urlsplit(target)
  if dest.scheme!="https" or dest.hostname not in ("avsubtitles.com","www.avsubtitles.com") or dest.username or dest.password:continue
  if dest.path.lower().endswith("/download_sub.php"):
   params=urllib.parse.parse_qs(dest.query)
   if params.get("subid")!=[subid] or not params.get("revid"):continue
  elif not dest.path.lower().endswith((".srt",".ass",".ssa",".vtt",".zip")):continue
  if target not in links:links.append(target)
  if len(links)>=max_links:break
 return links


def native_search(number,fetch_text,max_pages=5,source=None):
 """Search each provider's own HTML results, without Bing or fabricated matches."""
 found={};errors={};stats={}
 if source is not None and source not in SEARCH_ENDPOINTS:raise ValueError("Unknown subtitle source")
 for source_name,make_url in SEARCH_ENDPOINTS.items():
  if source is not None and source!=source_name:continue
  site=source_name
  url=make_url(number);pages=[];stats[site]={"search_url":url,"links_seen":0}
  try:
   raw=fetch_text(url,350000)
   if site=="JAV字幕":
    # Use the public JSON search endpoint rather than scraping the interactive search UI.
    if b"captcha" in raw.lower() or any(word in raw.decode("utf-8","replace") for word in ("验证码","图片验证","人机验证","安全验证")):
     errors[site]="站点要求人工验证码，无法在 NAS 后端继续搜索"
     found[site]=[]
     continue
    pages=javzimu_results(raw,number,max_items=max_pages)
    stats[site]["links_seen"]=len(pages)
    found[site]=pages
    continue
   parser=SearchLinks();parser.feed(raw.decode("utf-8","replace"))
   stats[site]["links_seen"]=len(parser.links)
   for href,title in parser.links:
    target=urllib.parse.urljoin(url,html.unescape(href))
    parsed=urllib.parse.urlsplit(target)
    if parsed.scheme!="https" or parsed.hostname not in (SITES[site],"www."+SITES[site]):continue
    if not DETAIL_PATTERNS[site].search(parsed.path+("?"+parsed.query if parsed.query else "")):continue
    if number not in {film_code(title),film_code(urllib.parse.unquote(parsed.path))}:
     if site!="AVSubtitles":continue
     # AVSubtitles often labels the detail anchor simply "Details".
     markup=raw.decode("utf-8","replace")
     positions=[m.start() for m in re.finditer(re.escape(href),markup,re.I)]
     if not any(number==film_code(re.sub(r"<[^>]+>"," ",markup[max(0,pos-350):pos])) for pos in positions):continue
    if target not in pages:pages.append(target)
    if len(pages)>=max_pages:break
  except Exception as exc:
   if site=="JAV字幕" and ("403" in str(exc) or "Forbidden" in str(exc)):
    errors[site]="HTTP 403：网站需要浏览器验证码或拒绝自动请求；请手动搜索并上传字幕"
   else:errors[site]=str(exc)[:160]
  found[site]=pages
 return found,errors,stats
