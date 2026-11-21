import os
import tempfile


os.environ["LLM_PROVIDER"] = "mock"
_TEST_DATABASE = tempfile.TemporaryDirectory(prefix="scry-x-ai-tests-")
os.environ["DATABASE_PATH"] = os.path.join(_TEST_DATABASE.name, "rules.db")
