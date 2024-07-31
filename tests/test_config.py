from debriefly import config


def test_int():
    assert config.test.aint == 42


def test_list():
    assert len(config.test.alist) == 4
