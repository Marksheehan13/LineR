"""Start the prototype: python run.py   (then open http://127.0.0.1:5000)"""
import logging

from liner.app import create_app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Local use only: bound to 127.0.0.1, one demo user, no login (see README and the technical document).
    create_app().run(host="127.0.0.1", port=5000, debug=False)
