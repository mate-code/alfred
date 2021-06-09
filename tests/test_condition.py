import random
import pytest

import alfred3 as al
from alfred3.condition import ConditionInconsistency

from .util import get_exp_session, clear_db

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


@pytest.fixture
def lexp(tmp_path):
    script = "tests/res/script-hello_world.py"
    exp = get_exp_session(tmp_path, script_path=script, secrets_path=None)
    yield exp



@pytest.fixture
def strict_exp(exp):
    rd = al.ListRandomizer(("a", 10), ("b", 10), exp=exp)
    exp.condition = rd.get_condition()
    yield exp


def test_clear(exp):
    """
    Just for clearing the database in case a test breaks down with an error.
    """
    print(exp)

class TestConditionValidation:

    def test_pass_validation(self, strict_exp):
        rd = al.ListRandomizer(("a", 10), ("b", 10), exp=strict_exp)
        assert rd.get_condition()
    
    def test_change_mode(self, strict_exp):
        rd = al.ListRandomizer(("a", 10), ("b", 10), exp=strict_exp, mode="inclusive")
        assert rd.get_condition()
    
    def test_change_of_n(self, strict_exp):

        rd = al.ListRandomizer(("a", 10), ("b", 9), exp=strict_exp)
        with pytest.raises(ConditionInconsistency):
            rd.get_condition()
        
    def test_change_of_name(self, strict_exp):

        rd = al.ListRandomizer(("a", 10), ("c", 10), exp=strict_exp)
        with pytest.raises(ConditionInconsistency):
            rd.get_condition()

    def test_add_condition(self, strict_exp):

        rd = al.ListRandomizer(("a", 10), ("b", 10), ("c", 10), exp=strict_exp)
        with pytest.raises(ConditionInconsistency):
            rd.get_condition()

    def test_remove_condition(self, strict_exp):
        rd = al.ListRandomizer(("a", 10), exp=strict_exp)
        with pytest.raises(ConditionInconsistency):
            rd.get_condition()

    def test_increase_version(self, strict_exp):
        strict_exp.config.read_dict({"metadata": {"version": "0.2"}})
        assert strict_exp.version == "0.2"
        
        rd = al.ListRandomizer(("a", 10), exp=strict_exp)
        assert rd.get_condition()
    

def rd_slots(*conditions, exp, seed):
    rd = al.ListRandomizer(*conditions, exp=exp, random_seed=seed)
    rd.get_condition()

    rd_slots = [slot.condition for slot in rd.slotlist.slots]
    return rd_slots


def slots(*conditions, seed):
    slots = []
    for c, n in conditions:
        slots += [c] * n
    random.seed(seed)
    random.shuffle(slots)
    return slots


class TestConditionShuffle:

    def test_shuffle_mongo(self, exp):
        conditions = [("a", 20), ("b", 20)]
        seed1 = 123
        s1 = rd_slots(*conditions, exp=exp, seed=seed1)

        exp.config.read_dict({"metadata": {"version": "0.2"}})
        seed2 = 12345
        s2 = rd_slots(*conditions, exp=exp, seed=seed2)

        assert s1 != s2


    def test_shuffle_seed_mongo(self, exp):
        conditions = [("a", 20), ("b", 20)]
        seed = 12345
        
        s1 = rd_slots(*conditions, exp=exp, seed=seed)
        s2 = slots(*conditions, seed=seed)

        assert s1 == s2
    

    def test_shuffle_local(self, lexp):
        conditions = [("a", 20), ("b", 20)]
        seed1 = 123
        s1 = rd_slots(*conditions, exp=lexp, seed=seed1)

        lexp.config.read_dict({"metadata": {"version": "0.2"}})
        seed2 = 12345
        s2 = rd_slots(*conditions, exp=lexp, seed=seed2)

        assert s1 != s2


    def test_shuffle_seed_local(self, lexp):
        conditions = [("a", 20), ("b", 20)]
        seed = 12345

        s1 = rd_slots(*conditions, exp=lexp, seed=seed)
        s2 = slots(*conditions, seed=seed)

        assert s1 == s2


class TestConditionAllocation:
    
    def test_aborted_session(self, exp_factory):
        exp1 = exp_factory()
        seed = 12348
        exp1._session_id = "exp1"
        rd1 = al.ListRandomizer.balanced("a", "b", n=10, exp=exp1, random_seed=seed)
        exp1.condition = rd1.get_condition()

        slots = rd1.slotlist.slots
        assert exp1.condition == slots[0].condition
        assert slots[0].condition != slots[1].condition

        exp1._start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        exp1_session = rd1.slotlist.slots[0].sessions[0]
        assert not exp1_session.active(exp1)

        exp2 = exp_factory()
        exp2._session_id = "exp2"
        rd2 = al.ListRandomizer.balanced("a", "b", n=10, exp=exp2, random_seed=seed)
        exp2.condition = rd2.get_condition()
        assert exp2.condition == exp1.condition
    

    def test_active_session(self, exp_factory):
        exp1 = exp_factory()
        seed = 12348
        exp1._session_id = "exp1"
        rd1 = al.ListRandomizer.balanced("a", "b", n=10, exp=exp1, random_seed=seed)
        exp1.condition = rd1.get_condition()

        exp1._start()
        exp1._save_data(sync=True)

        exp1_session = rd1.slotlist.slots[0].sessions[0]
        assert exp1_session.active(exp1)

        exp2 = exp_factory()
        exp2._session_id = "exp2"
        rd2 = al.ListRandomizer.balanced("a", "b", n=10, exp=exp2, random_seed=seed)
        exp2.condition = rd2.get_condition()

        assert exp2.condition != exp1.condition
    

    def test_finished_session(self, exp_factory):
        exp1 = exp_factory()
        seed = 12348
        exp1._session_id = "exp1"
        rd1 = al.ListRandomizer.balanced("a", "b", n=10, exp=exp1, random_seed=seed)
        exp1.condition = rd1.get_condition()

        exp1._start()
        exp1.finish()

        slot1 = rd1.slotlist.slots[0]
        exp1_session = slot1.sessions[0]
        
        assert slot1.finished
        assert not exp1_session.active(exp1)

        exp2 = exp_factory()
        exp2._session_id = "exp2"
        rd2 = al.ListRandomizer.balanced("a", "b", n=10, exp=exp2, random_seed=seed)
        exp2.condition = rd2.get_condition()

        assert exp2.condition != exp1.condition
    

    def test_expired_session(self, exp_factory):
        exp1 = exp_factory()
        seed = 12348
        exp1._session_id = "exp1"
        rd1 = al.ListRandomizer.balanced("a", "b", n=10, exp=exp1, random_seed=seed)
        exp1.condition = rd1.get_condition()

        exp1._start()
        exp1._start_time = exp1._start_time - exp1.session_timeout - 1

        assert exp1.session_expired
        exp1._save_data(sync=True)

        slot1 = rd1.slotlist.slots[0]
        exp1_session = slot1.sessions[0]
        
        assert not slot1.finished
        assert not exp1_session.active(exp1)

        exp2 = exp_factory()
        exp2._session_id = "exp2"
        rd2 = al.ListRandomizer.balanced("a", "b", n=10, exp=exp2, random_seed=seed)
        exp2.condition = rd2.get_condition()

        assert exp2.condition == exp1.condition
    

    def test_slots_full_strict(self, exp_factory):
        exp1 = exp_factory()
        seed = 12348
        exp1._session_id = "exp1"
        rd1 = al.ListRandomizer.balanced("a", "b", n=1, exp=exp1, random_seed=seed)
        exp1.condition = rd1.get_condition()
        exp1._start()
        exp1._save_data(sync=True)

        exp2 = exp_factory()
        exp2._session_id = "exp2"
        rd2 = al.ListRandomizer.balanced("a", "b", n=1, exp=exp2, random_seed=seed)
        exp2.condition = rd2.get_condition()
        exp2._start()
        exp2._save_data(sync=True)

        exp3 = exp_factory()
        exp3._session_id = "exp3"
        rd3 = al.ListRandomizer.balanced("a", "b", n=1, exp=exp3, random_seed=seed)
        exp3.condition = rd3.get_condition()

        assert exp3.aborted
    
    def test_slots_inclusive(self, exp_factory):
        exp1 = exp_factory()
        seed = 12348
        exp1._session_id = "exp1"
        rd1 = al.ListRandomizer.balanced("a", "b", n=1, exp=exp1, random_seed=seed, mode = "inclusive")
        exp1.condition = rd1.get_condition()
        exp1._start()
        exp1.finish()

        exp2 = exp_factory()
        exp2._session_id = "exp2"
        rd2 = al.ListRandomizer.balanced("a", "b", n=1, exp=exp2, random_seed=seed, mode = "inclusive")
        exp2.condition = rd2.get_condition()
        exp2._start()

        assert exp1.condition != exp2.condition

        exp3 = exp_factory()
        exp3._session_id = "exp3"
        rd3 = al.ListRandomizer.balanced("a", "b", n=1, exp=exp3, random_seed=seed, mode = "inclusive")
        exp3.condition = rd3.get_condition()

        assert exp2.condition == exp3.condition

    
    def test_slots_full_inclusive(self, exp_factory):
        exp1 = exp_factory()
        seed = 12348
        exp1._session_id = "exp1"
        rd1 = al.ListRandomizer.balanced("a", "b", n=1, exp=exp1, random_seed=seed, mode = "inclusive")
        exp1.condition = rd1.get_condition()
        exp1._start()
        exp1.finish()

        exp2 = exp_factory()
        exp2._session_id = "exp2"
        rd2 = al.ListRandomizer.balanced("a", "b", n=1, exp=exp2, random_seed=seed, mode = "inclusive")
        exp2.condition = rd2.get_condition()
        exp2._start()
        exp2.finish()

        assert exp1.condition != exp2.condition

        exp3 = exp_factory()
        exp3._session_id = "exp3"
        rd3 = al.ListRandomizer.balanced("a", "b", n=1, exp=exp3, random_seed=seed, mode = "inclusive")
        exp3.condition = rd3.get_condition()

        assert exp3.aborted

    def test_balanced_constructor(self, exp_factory):
        exp1 = exp_factory()
        seed = 12348
        exp1._session_id = "exp1"
        rd1 = al.ListRandomizer.balanced("a", "b", n=10, exp=exp1, random_seed=seed)
        exp1.condition = rd1.get_condition()


        exp2 = exp_factory()
        exp2._session_id = "exp2"
        rd2 = al.ListRandomizer(("a", 10), ("b", 10), exp=exp2, random_seed=seed)
        exp2.condition = rd2.get_condition()

        slots1 = [s.condition for s in rd1.slotlist.slots]
        slots2 = [s.condition for s in rd2.slotlist.slots]
        assert slots1 == slots2
