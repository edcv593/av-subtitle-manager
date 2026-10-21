"""Best-effort public-index discovery. Never trusts search snippets as subtitle downloads."""
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

SITES={"AVSubtitles":"avsubtitles.com","Subtitle Cat":"subtitlecat.com","JAV字幕":"javzimu.com"}
DETAIL_PATTERNS={
 "AVSubtitles":re.compile(r"(?:/subtitles[.]php[?][^#]*subid=[0-9]+|/movie[0-9]+/[^?#]+/subtitles/[^?#]+/[0-9]+)",re.I),
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
 "AVSubtitles":lambda code:"https://www.avsubtitles.com/search_results.php?"+urllib.parse.urlencode({"search":code,"scope":"title"}),
 "Subtitle Cat":lambda code:"https://www.subtitlecat.com/?"+urllib.parse.urlencode({"search":code}),
 "JAV字幕":lambda code:"https://javzimu.com/?"+urllib.parse.urlencode({"s":code}),
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

def native_search(number,fetch_text,max_pages=5,source=None):
 """Search each provider's own HTML results, without Bing or fabricated matches."""
 found={};errors={};stats={}
 if source is not None and source not in SEARCH_ENDPOINTS:raise ValueError("Unknown subtitle source")
 for source_name,make_url in SEARCH_ENDPOINTS.items():
  if source is not None and source!=source_name:continue
  site=source_name
  source=site
  url=make_url(number);pages=[];stats[source]={"search_url":url,"links_seen":0}
  try:
   raw=fetch_text(url,350000)
   parser=SearchLinks();parser.feed(raw.decode("utf-8","replace"))
   stats[source]["links_seen"]=len(parser.links)
   for href,title in parser.links:
    target=urllib.parse.urljoin(url,html.unescape(href))
    parsed=urllib.parse.urlsplit(target)
    if parsed.scheme!="https" or parsed.hostname not in (SITES[source],"www."+SITES[source]):continue
    if not DETAIL_PATTERNS[source].search(parsed.path+("?"+parsed.query if parsed.query else "")):continue
    if number not in {film_code(title),film_code(urllib.parse.unquote(parsed.path))}:continue
    if target not in pages:pages.append(target)
    if len(pages)>=max_pages:break
  except Exception as exc:errors[source]=str(exc)[:160]
  found[source]=pages
 return found,errors,stats
