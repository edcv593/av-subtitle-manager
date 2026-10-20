import sqlite3,unittest
from ai_queue import init,enqueue,get,list_jobs,control,claim,heartbeat,transition,recover_expired
class QueueTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(":memory:")
  self.c.row_factory=sqlite3.Row
  init(self.c)
 def tearDown(self):self.c.close()
 def test_enqueue_deduplicates(self):
  a,created=enqueue(self.c,"/media/IPX-123.mp4",100,5)
  b,again=enqueue(self.c,"/media/IPX-123.mp4",100,5)
  self.assertTrue(created);self.assertFalse(again);self.assertEqual(a["id"],b["id"])
  newer,_=enqueue(self.c,"/media/IPX-123.mp4",101,6)
  self.assertEqual(get(self.c,a["id"])["status"],"cancelled")
  self.assertEqual(newer["status"],"pending")
 def test_control(self):
  job,_=enqueue(self.c,"/media/A.mp4",100,1)
  self.assertEqual(control(self.c,job["id"],"pause")["status"],"paused")
  self.assertEqual(control(self.c,job["id"],"resume")["status"],"pending")
  self.assertEqual(control(self.c,job["id"],"cancel")["status"],"cancelled")
  self.assertEqual(control(self.c,job["id"],"retry")["status"],"pending")
 def test_worker_lease(self):
  job,_=enqueue(self.c,"/media/B.mp4",100,1)
  claimed=claim(self.c,"worker-1")
  self.assertEqual(claimed["id"],job["id"])
  self.assertIsNone(claim(self.c,"worker-2"))
  self.assertEqual(heartbeat(self.c,job["id"],"worker-1",20)["progress"],20)
  for state in ("extracting","transcribing","translating","reviewing"):
   self.assertEqual(transition(self.c,job["id"],"worker-1",state)["status"],state)
 def test_recovery(self):
  job,_=enqueue(self.c,"/media/C.mp4",100,1)
  claim(self.c,"worker-1")
  self.c.execute("UPDATE ai_jobs SET lease_until=1 WHERE id=?",(job["id"],))
  self.c.commit()
  self.assertEqual(recover_expired(self.c),1)
  self.assertEqual(get(self.c,job["id"])["status"],"pending")
 def test_limits(self):
  enqueue(self.c,"/media/A.mp4",100,1,max_pending=1)
  with self.assertRaises(ValueError):enqueue(self.c,"/media/B.mp4",100,1,max_pending=1)
if __name__=="__main__":unittest.main()
