import unittest
from types import SimpleNamespace
from reliability import score,should_skip,retry_delay
class ReliabilityTests(unittest.TestCase):
 def test_terminal_cache(self):
  stat=SimpleNamespace(st_size=100,st_mtime=10)
  self.assertTrue(should_skip({"status":"downloaded","size":100,"mtime":10,"next_retry":0},stat))
  self.assertFalse(should_skip({"status":"downloaded","size":101,"mtime":10,"next_retry":0},stat))
  self.assertTrue(should_skip({"status":"error","size":100,"mtime":10,"next_retry":1000},stat,now=100))
  self.assertFalse(should_skip({"status":"error","size":100,"mtime":10,"next_retry":100},stat,now=100))
 def test_scoring(self):
  good,_=score({"name":"IPX-123-简体.srt","ext":"srt"},{"ok":True})
  bad,_=score({"name":"IPX-123-剪辑.srt","ext":"srt"},{"ok":True})
  self.assertGreater(good,bad)
  self.assertEqual(score({"name":"IPX-123-简体.srt","ext":"srt"},{"ok":False,"reason":"bad"})[0],0)
 def test_backoff(self):
  self.assertGreater(retry_delay("error",3),retry_delay("error",1))
  self.assertGreater(retry_delay("missing",2),retry_delay("missing",1))
if __name__=="__main__":unittest.main()
