import pytest
from alfred3.quota import SessionQuota
from alfred3.testutil import get_exp_session, clear_db
from dotenv import load_dotenv

load_dotenv()

@pytest.fixture
def exp(tmp_path):
    script = "tests/res/script-hello_world.py"
    secrets = "tests/res/secrets-default.conf"
    exp = get_exp_session(tmp_path, script_path=script, secrets_path=secrets)

    yield exp

    clear_db()


@pytest.fixture
def exp_factory(tmp_path):
    def expf():
        script = "tests/res/script-hello_world.py"
        secrets = "tests/res/secrets-default.conf"
        exp = get_exp_session(tmp_path, script_path=script, secrets_path=secrets)
        return exp

    yield expf

    clear_db()


class TestQuota:

    def test_initialization(self, exp):
        quota = SessionQuota(3, exp)

        assert quota

        assert quota.nopen == 3
        assert quota.nfinished == 0
        assert quota.npending == 0
    

    def test_count_pending_count(self, exp):
        quota = SessionQuota(3, exp)

        quota.count()
        assert quota.nopen == 2
        assert quota.nfinished == 0
        assert quota.npending == 1
    
    def test_count_pending_abort(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        
        quota1 = SessionQuota(1, exp1)
        quota1.count()

        assert quota1.nopen == 0
        assert quota1.nfinished == 0
        assert quota1.npending == 1

        quota2 = SessionQuota(1, exp2)
        quota2.count()

        assert exp2.aborted

    def test_count_pending_inclusive(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        
        quota1 = SessionQuota(1, exp1, inclusive=True)
        quota1.count()

        assert quota1.nopen == 0
        assert quota1.nfinished == 0
        assert quota1.npending == 1

        quota2 = SessionQuota(1, exp2, inclusive=True)
        label = quota2.count()

        assert label == quota2.slot_label

    
    def test_count_finished(self, exp):
        quota = SessionQuota(3, exp)

        quota.count()

        exp._start()
        exp.finish()

        assert quota.nopen == 2
        assert quota.nfinished == 1
        assert quota.npending == 0
    
    def test_count_abort(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        
        quota1 = SessionQuota(1, exp1)
        quota1.count()

        exp1._start()
        exp1.finish()

        assert quota1.nopen == 0
        assert quota1.nfinished == 1
        assert quota1.npending == 0

        quota2 = SessionQuota(1, exp2)
        quota2.count()

        assert exp2.aborted
    
    def test_count_exp_version(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp2.config.read_dict({"metadata": {"version": 1}})

        quota1 = SessionQuota(1, exp1)
        quota1.count()

        exp1._start()
        exp1.finish()

        assert quota1.nopen == 0
        assert quota1.nfinished == 1
        assert quota1.npending == 0

        quota2 = SessionQuota(1, exp2)
        label = quota2.count()

        assert label == quota2.slot_label