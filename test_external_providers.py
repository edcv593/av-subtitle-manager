import unittest
from external_providers import indexed_pages,detail_downloads

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
