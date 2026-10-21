import tempfile
import unittest
from pathlib import Path
import ai_provider_settings as settings

class AISettingsTests(unittest.TestCase):
 def test_save_and_mask(self):
  with tempfile.TemporaryDirectory() as tmp:
   view=settings.save(tmp,"deepseek","deepseek-flash","secret-example")
   self.assertTrue(view["has_key"])
   self.assertNotIn("api_key",view)
   self.assertEqual(settings.credentials(tmp),("secret-example","deepseek-flash","https://api.deepseek.com/chat/completions"))
   settings.save(tmp,"deepseek","deepseek-v4-pro")
   self.assertEqual(settings.credentials(tmp)[0],"secret-example")
   settings.save(tmp,"deepseek","deepseek-flash",clear_key=True)
   self.assertFalse(settings.public(tmp)["has_key"])
 def test_reject_unsupported_provider_and_model(self):
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(ValueError):settings.save(tmp,"https://127.0.0.1","model","key")
   with self.assertRaises(ValueError):settings.save(tmp,"deepseek","bad model","key")
 def test_default_settings(self):
  with tempfile.TemporaryDirectory() as tmp:
   self.assertFalse(settings.public(tmp)["has_key"])
   self.assertEqual(settings.public(tmp)["provider"],"deepseek")

if __name__=="__main__":unittest.main()
