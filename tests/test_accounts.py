"""Login and accounts (mocked): the demo authenticator keeps the same authenticate(credentials) interface a
real one would have."""
from liner.business.accounts import DemoAuthenticator
from liner.models import User


def test_returns_the_one_demo_user():
    auth = DemoAuthenticator("demo", "Demo bookkeeper")
    assert auth.authenticate({}) == User("demo", "Demo bookkeeper")


def test_the_same_user_comes_back_every_time():
    auth = DemoAuthenticator("demo", "Demo bookkeeper")
    assert auth.authenticate({"name": "a"}) == auth.authenticate({"name": "b"})


def test_it_does_not_depend_on_what_credentials_look_like():
    auth = DemoAuthenticator("demo", "Demo bookkeeper")
    for creds in ({}, {"password": "x"}, {"unexpected": None}):
        assert auth.authenticate(creds).id == "demo"
