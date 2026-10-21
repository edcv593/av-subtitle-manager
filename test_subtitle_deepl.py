import json, tempfile, unittest
from pathlib import Path
import urllib.error
import deepl_settings
import subtitle_deepl

class DeepLTests(unittest.TestCase):
 def test_api_free_translation(self):
  seen=[]
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,n):return json.dumps({"translations":[{"text":"你好"}]}).encode()
  def open_request(req,timeout):
   seen.append(req)
   return Response()
  self.assertEqual(subtitle_deepl.translate("こんにちは","test:fx",opener=open_request),"你好")
  self.assertEqual(seen[0].full_url,"https://api-free.deepl.com/v2/translate")
  self.assertIn("DeepL-Auth-Key test:fx",seen[0].get_header("Authorization"))
  body=json.loads(seen[0].data)
  self.assertEqual(body["source_lang"],"JA")
  self.assertEqual(body["target_lang"],"ZH")
 def test_pro_endpoint(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,n):return b'{"translations":[{"text":"谢谢"}]}'
  url=[]
  def opener(req,timeout):url.append(req.full_url);return Response()
  self.assertEqual(subtitle_deepl.translate("ありがとう","key","pro",opener),"谢谢")
  self.assertEqual(url,["https://api.deepl.com/v2/translate"])
 def test_quota_error(self):
  def fail(req,timeout):raise urllib.error.HTTPError(req.full_url,456,"Quota exceeded",None,None)
  with self.assertRaisesRegex(ValueError,"额度"):subtitle_deepl.translate("こんにちは","key",opener=fail)
 def test_save_key_never_public(self):
  with tempfile.TemporaryDirectory() as directory:
   x=deepl_settings.save(directory,"free","secret:fx")
   self.assertTrue(x["has_key"]);self.assertNotIn("api_key",x)
   self.assertEqual(deepl_settings.credentials(directory),("secret:fx","free"))
   self.assertTrue(deepl_settings.save(directory,"pro","")["has_key"])
   self.assertEqual(deepl_settings.credentials(directory),("secret:fx","pro"))
   self.assertFalse(deepl_settings.save(directory,"pro",clear_key=True)["has_key"])
 def test_invalid_plan_rejected(self):
  with self.assertRaises(ValueError):subtitle_deepl.translate("こんにちは","key","other")
if __name__=="__main__":unittest.main()
