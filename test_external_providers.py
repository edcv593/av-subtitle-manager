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
 def test_javzimu_captcha_requires_manual_action(self):
  html="请完成图片验证以显示搜索结果".encode()
  found,errors,stats=native_search("IPZZ-791",lambda url,limit:html,source="JAV字幕")
  self.assertEqual(found["JAV字幕"],[])
  self.assertIn("验证码",errors["JAV字幕"])
  self.assertEqual(stats["JAV字幕"]["search_url"],"https://javzimu.com/search/IPZZ-791")
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
 def test_avsubtitles_zip_link(self):
  page=b'<a href="/download_sub.php?subid=10845&amp;revid=1">SSIS-334-zh.zip</a>'
  links=detail_downloads("AVSubtitles","https://www.avsubtitles.com/subtitles.php?subid=10845",page)
  self.assertEqual(links,["https://www.avsubtitles.com/download_sub.php?subid=10845&revid=1"])
 def test_reject_external_download(self):
  page=b'<a href="https://evil.example/sub.srt">Chinese (Simplified) Download</a>'
  self.assertEqual(detail_downloads("Subtitle Cat","https://www.subtitlecat.com/subs/1484/ROYD-329.html",page),[])
 def test_subtitle_cat_language(self):
  page=b'<a href="/download/zh-CN/123">Chinese (Simplified) Download</a>'
  self.assertEqual(len(detail_downloads("Subtitle Cat","https://www.subtitlecat.com/subs/1484/ROYD-329.html",page)),1)

if __name__=="__main__":unittest.main()
