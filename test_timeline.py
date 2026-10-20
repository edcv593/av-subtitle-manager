import unittest
from timeline import assess,stamp
class TimelineTests(unittest.TestCase):
 def test_stamp(self):
  self.assertEqual(stamp("01:02:03,400"),3723.4)
  self.assertEqual(stamp("0:01:02.30"),62.3)
 def test_valid_srt(self):
  data=b"1\n00:00:01,000 --> 00:00:02,000\nHello\n\n2\n00:00:03,000 --> 00:00:04,000\nWorld\n\n3\n00:00:05,000 --> 00:00:06,000\nEnd\n"
  self.assertTrue(assess(data,"srt",120)["ok"])
  self.assertFalse(assess(data,"srt",3)["ok"])
  self.assertTrue(assess(data,"srt",6)["ok"])
  self.assertFalse(assess(data,"srt",None)["ok"])
 def test_long_video_diagnostics(self):
  def make_cue(i,seconds):
   a=seconds;b=seconds+2
   def fmt(t):return f"{t//3600:02d}:{(t//60)%60:02d}:{t%60:02d},000"
   return f"{i}\n{fmt(a)} --> {fmt(b)}\nHello\n\n"
  data="".join(make_cue(i+1,i*10) for i in range(30)).encode()
  result=assess(data,"srt",7200)
  self.assertTrue(result["ok"])
  self.assertEqual(result["thirds"],[30,0,0])
  self.assertTrue(result["warnings"])
  self.assertGreater(result["longest_gap_seconds"],0)
 def test_bad_order(self):
  data=b"1\n00:00:50,000 --> 00:00:51,000\nA\n\n2\n00:00:40,000 --> 00:00:41,000\nB\n\n3\n00:00:30,000 --> 00:00:31,000\nC\n\n4\n00:00:20,000 --> 00:00:21,000\nD\n"
  self.assertFalse(assess(data,"srt",120)["ok"])
if __name__=="__main__":unittest.main()
