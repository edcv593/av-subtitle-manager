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
 def test_phase_persists_and_clears_after_completion(self):
  row,_=rq.enqueue(self.c,"/media/a.mp4")
  rq.claim(self.c)
  rq.set_phase(self.c,row["id"],"正在检索日语参考字幕")
  self.assertIn("检索",rq.list_jobs(self.c)[0]["phase"])
  rq.checkpoint(self.c,row["id"],"sha",25,202,10,[])
  self.assertEqual(rq.list_jobs(self.c)[0]["phase"],"已保存本批进度")
  rq.finish(self.c,row["id"],"completed")
  self.assertEqual(rq.list_jobs(self.c)[0]["phase"],"")
 def test_existing_schema_is_migrated(self):
  self.c.execute("DROP TABLE review_jobs")
  self.c.execute("""CREATE TABLE review_jobs(
   id INTEGER PRIMARY KEY AUTOINCREMENT, video_path TEXT NOT NULL,
   status TEXT NOT NULL DEFAULT 'pending', reference_id TEXT NOT NULL DEFAULT '',
   original_sha256 TEXT NOT NULL DEFAULT '', offset INTEGER NOT NULL DEFAULT 0,
   total INTEGER NOT NULL DEFAULT 0, matched INTEGER NOT NULL DEFAULT 0,
   suggestions TEXT NOT NULL DEFAULT '[]', auto_apply INTEGER NOT NULL DEFAULT 0,
   error TEXT NOT NULL DEFAULT '', backup TEXT NOT NULL DEFAULT '',
   changed INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL)""")
  rq.init(self.c)
  self.assertIn("phase",[r[1] for r in self.c.execute("PRAGMA table_info(review_jobs)")])
 def test_invalid_transitions(self):
  row,_=rq.enqueue(self.c,"/media/a.mp4")
  with self.assertRaises(ValueError):rq.action(self.c,row["id"],"resume")
  with self.assertRaises(ValueError):rq.list_jobs(self.c,"unknown")

if __name__=="__main__":unittest.main()
