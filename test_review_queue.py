import sqlite3
import unittest
import review_queue as rq

class ReviewQueueTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(":memory:")
  self.c.row_factory=sqlite3.Row
  rq.init(self.c)
 def tearDown(self):self.c.close()
 def test_deduplicate_active_and_claim(self):
  first,created=rq.enqueue(self.c,"/media/a.mp4",auto_apply=True)
  self.assertTrue(created)
  same,created=rq.enqueue(self.c,"/media/a.mp4")
  self.assertFalse(created)
  self.assertEqual(first["id"],same["id"])
  claimed=rq.claim(self.c)
  self.assertEqual(claimed["id"],first["id"])
  self.assertEqual(rq.list_jobs(self.c)[0]["status"],"running")
 def test_progress_pause_resume(self):
  row,_=rq.enqueue(self.c,"/media/a.mp4")
  rq.claim(self.c)
  self.assertTrue(rq.checkpoint(self.c,row["id"],"sha",25,202,10,[{"before":"原文","after":"译文"}]))
  self.assertEqual(rq.action(self.c,row["id"],"pause")["status"],"paused")
  self.assertFalse(rq.checkpoint(self.c,row["id"],"sha",50,202,20,[]))
  self.assertEqual(rq.action(self.c,row["id"],"resume")["status"],"pending")
  self.assertEqual(rq.claim(self.c)["offset"],25)
  self.assertEqual(rq.list_jobs(self.c)[0]["suggestion_count"],1)
 def test_recovery_from_restart(self):
  row,_=rq.enqueue(self.c,"/media/a.mp4")
  rq.claim(self.c)
  rq.checkpoint(self.c,row["id"],"sha",25,202,10,[])
  rq.recover(self.c)
  self.assertEqual(rq.claim(self.c)["offset"],25)
 def test_failed_job_requires_explicit_retry(self):
  row,_=rq.enqueue(self.c,"/media/a.mp4")
  rq.claim(self.c)
  rq.finish(self.c,row["id"],"failed","No reference")
  self.assertIsNone(rq.claim(self.c))
  self.assertEqual(rq.action(self.c,row["id"],"retry")["status"],"pending")
  self.assertIsNotNone(rq.claim(self.c))
 def test_completed_job_can_be_queued_again(self):
  row,_=rq.enqueue(self.c,"/media/a.mp4")
  rq.claim(self.c)
  rq.finish(self.c,row["id"],"completed",backup="a.backup",changed=2)
  new,created=rq.enqueue(self.c,"/media/a.mp4")
  self.assertTrue(created)
  self.assertNotEqual(new["id"],row["id"])
 def test_invalid_transitions(self):
  row,_=rq.enqueue(self.c,"/media/a.mp4")
  with self.assertRaises(ValueError):rq.action(self.c,row["id"],"resume")
  with self.assertRaises(ValueError):rq.list_jobs(self.c,"unknown")

if __name__=="__main__":unittest.main()
