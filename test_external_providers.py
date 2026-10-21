import unittest
import json
from external_providers import indexed_pages,detail_downloads,native_search,javzimu_results

class ProviderTests(unittest.TestCase):
 def test_index_filters_unrelated_and_offsite_results(self):
  rss=b'''<rss><channel>
   <item><title>SSIS-334 Chinese subtitles</title><link>https://www.avsubtitles.com/subtitles.php?subid=10845</link></item>
   <item><title>SSIS-335</title><link>https://www.avsubtitles.com/subtitles.php?subid=10846</link></item>
   <item><title>SSIS-334</title><link>https://evil.example/subtitles.php?subid=10845</link></item>
  </channel></rss>'''
  found,errors=indexed_pages("SSIS-334",lambda url,limit:rss)
  self.assertEqual(len(found["AVSubtitles"]),1)
  self.assertEqual(errors,{})
 def test_avsubtitles_modern_detail_url(self):
  rss=b'<rss><channel><item><title>Chinese subtitles for IPZZ-044</title><link>https://www.avsubtitles.com/movie11842/ipzz-044-example/subtitles/zh/32910</link></item></channel></rss>'
  found,errors=indexed_pages("IPZZ-044",lambda url,limit:rss)
  self.assertEqual(len(found["AVSubtitles"]),1)
  self.assertEqual(errors,{})

 def test_native_search_sites_are_independent(self):
  html=b'<a href="/subs/1443/T48.IPZZ-791.2.html">T48.IPZZ-791.2</a>'
  def fetch(url,limit):
   if "subtitlecat.com" in url:return html
   if "javzimu.com" in url:raise ValueError("site unavailable")
   return b'<a href="/subtitles.php?subid=32631">IPZZ-791 subtitles</a>'
  found,errors,stats=native_search("IPZZ-791",fetch)
  self.assertEqual(len(found["AVSubtitles"]),1)
  self.assertEqual(len(found["Subtitle Cat"]),1)
  self.assertEqual(found["JAV字幕"],[])
  self.assertIn("JAV字幕",errors)
  self.assertEqual(stats["Subtitle Cat"]["links_seen"],1)
 def test_javzimu_api_search_returns_download_candidates(self):
  response={"data":[
   {"name":"IPZZ-791-zh.srt","cid":"a1","ext":"srt"},
   {"name":"IPZZ-791-zh.srt","cid":"a1","ext":"srt"},
   {"name":"IPZZ-791-UC.srt","cid":"b2","ext":"srt"},
   {"name":"IPZZ-792-zh.srt","cid":"c3","ext":"srt"}]}
  seen=[]
  def fetch(url,limit):
   seen.append(url)
   return json.dumps(response).encode()
  found,errors,stats=native_search("IPZZ-791",fetch,max_pages=12,source="JAV字幕")
  self.assertEqual(len(found["JAV字幕"]),2)
  self.assertEqual(errors,{})
  self.assertEqual(stats["JAV字幕"]["links_seen"],2)
  self.assertTrue(all("/api/download?" in url for url in found["JAV字幕"]))
  self.assertIn("/api/search?name=IPZZ-791",seen[0])
 def test_javzimu_invalid_json_is_reported(self):
  found,errors,_=native_search("IPZZ-791",lambda url,limit:b"<html>blocked</html>",source="JAV字幕")
  self.assertEqual(found["JAV字幕"],[])
  self.assertIn("JAV字幕",errors)
 def test_javzimu_captcha_requires_manual_action(self):
  html="请完成图片验证以显示搜索结果".encode()
  found,errors,stats=native_search("IPZZ-791",lambda url,limit:html,source="JAV字幕")
  self.assertEqual(found["JAV字幕"],[])
  self.assertIn("验证码",errors["JAV字幕"])
  self.assertEqual(stats["JAV字幕"]["search_url"],"https://javzimu.com/api/search?name=IPZZ-791")
 def test_javzimu_403_is_explained(self):
  def denied(url,limit):raise ValueError("HTTP Error 403: Forbidden")
  found,errors,_=native_search("IPZZ-791",denied,source="JAV字幕")
  self.assertEqual(found["JAV字幕"],[])
  self.assertIn("手动搜索",errors["JAV字幕"])
 def test_avsubtitles_search_uses_confirmed_url(self):
  _,_,stats=native_search("IPZZ-791",lambda url,limit:b"",source="AVSubtitles")
  self.assertEqual(stats["AVSubtitles"]["search_url"],"https://www.avsubtitles.com/search_results.php?search=IPZZ-791")
 def test_avsubtitles_details_context(self):
  html=b'<div><h4>IPZZ-791 (2026)</h4><a href="/movie1234/example">Details</a></div>'
  found,errors,stats=native_search("IPZZ-791",lambda url,limit:html,source="AVSubtitles")
  self.assertEqual(found["AVSubtitles"],["https://www.avsubtitles.com/movie1234/example"])
 def test_avsubtitles_japanese_reference_details(self):
  from external_providers import avsubtitles_reference_pages
  html=(b'<a href="/movie83051/ipzz-791--mitsuri-nagahama-2026/subtitles/ja/136641">Japanese SRT</a>'
        b'<a href="/movie83051/ipzz-791--mitsuri-nagahama-2026/subtitles/ja/136176">Japanese SRT</a>'
        b'<a href="/movie83051/ipzz-791--mitsuri-nagahama-2026/subtitles/zh/100">Chinese SRT</a>')
  found=avsubtitles_reference_pages("IPZZ-791",html)
  self.assertEqual(len(found),2)
  self.assertTrue(found[0].endswith("/136641"))
  self.assertTrue(found[1].endswith("/136176"))
 def test_avsubtitles_japanese_detail_downloads(self):
  from external_providers import avsubtitles_reference_downloads
  url="https://www.avsubtitles.com/movie83051/ipzz-791--mitsuri-nagahama-2026/subtitles/ja/136641"
  html=(b'<a href="/download_sub.php?subid=136641&amp;revid=1">Download SRT</a>'
        b'<a href="https://evil.example/file.srt">Download</a>')
  self.assertEqual(avsubtitles_reference_downloads(url,html),["https://www.avsubtitles.com/download_sub.php?subid=136641&revid=1"])
 def test_avsubtitles_real_revid_download_url(self):
  from external_providers import avsubtitles_reference_downloads
  detail="https://www.avsubtitles.com/movie83051/ipzz-791--mitsuri-nagahama-2026/subtitles/ja/136176"
  download="https://www.avsubtitles.com/download_sub.php?subid=136176&revid=20260901093801"
  html=('<button data-url="/download_sub.php?subid=136176&amp;revid=20260901093801">Download</button>').encode()
  self.assertEqual(avsubtitles_reference_downloads(detail,html),[download])
 def test_avsubtitles_reject_mismatched_subid(self):
  from external_providers import avsubtitles_reference_downloads
  detail="https://www.avsubtitles.com/movie83051/ipzz-791--mitsuri-nagahama-2026/subtitles/ja/136176"
  html=b'<a href="/download_sub.php?subid=136641&amp;revid=20260901093801">Download</a>'
  self.assertEqual(avsubtitles_reference_downloads(detail,html),[])
 def test_avsubtitles_reject_non_japanese_detail(self):
  from external_providers import avsubtitles_reference_downloads
  with self.assertRaises(ValueError):
   avsubtitles_reference_downloads("https://www.avsubtitles.com/movie83051/ipzz-791/subtitles/zh/12",b"")
 def test_avsubtitles_zip_link(self):
  page=b'<a href="/download_sub.php?subid=10845&amp;revid=1">SSIS-334-zh.zip</a>'
  links=detail_downloads("AVSubtitles","https://www.avsubtitles.com/subtitles.php?subid=10845",page)
  self.assertEqual(links,["https://www.avsubtitles.com/download_sub.php?subid=10845&revid=1"])
 def test_reject_external_download(self):
  page=b'<a href="https://evil.example/sub.srt">Chinese (Simplified) Download</a>'
  self.assertEqual(detail_downloads("Subtitle Cat","https://www.subtitlecat.com/subs/1484/ROYD-329.html",page),[])
 def test_subtitlecat_japanese_downloads(self):
  from external_providers import subtitlecat_japanese_downloads
  url="https://www.subtitlecat.com/subs/1398/IPZZ-841.html"
  html=(b'<a href="/download/ja/123">Japanese Download</a>'
        b'<a href="/download/zh-CN/123">Chinese Download</a>'
        b'<a href="https://evil.example/download/ja/123">Japanese Download</a>')
  self.assertEqual(subtitlecat_japanese_downloads(url,html),
                   ["https://www.subtitlecat.com/download/ja/123"])
 def test_subtitlecat_rejects_offsite_or_search_page(self):
  from external_providers import subtitlecat_japanese_downloads
  with self.assertRaises(ValueError):
   subtitlecat_japanese_downloads("https://evil.example/subs/1/film.html",b"")
  with self.assertRaises(ValueError):
   subtitlecat_japanese_downloads("https://www.subtitlecat.com/?search=IPZZ-791",b"")
 def test_subtitle_cat_language(self):
  page=b'<a href="/download/zh-CN/123">Chinese (Simplified) Download</a>'
  self.assertEqual(len(detail_downloads("Subtitle Cat","https://www.subtitlecat.com/subs/1484/ROYD-329.html",page)),1)

if __name__=="__main__":unittest.main()
