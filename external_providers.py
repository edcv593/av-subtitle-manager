"""Best-effort public-index discovery. Never trusts search snippets as subtitle downloads."""
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

SITES={"AVSubtitles":"avsubtitles.com","Subtitle Cat":"subtitlecat.com","JAV字幕":"javzimu.com"}
DETAIL_PATTERNS={
 "AVSubtitles":re.compile(r"(?:/subtitles\\.php\\?[^#]*subid=\\d+|/movie\\d+/[^?#]+/subtitles/[^?#]+/\\d+)",re.I),
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
  query="site:"+domain+" \\""+number+"\\""
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
