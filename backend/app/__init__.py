from flask import Flask, jsonify
from flask_cors import CORS


def create_app():
    app = Flask(__name__)
    CORS(app,
         # TODO when deploying, change this to the actual frontend address
         origins=['http://localhost:3000'],
         supports_credentials=True)

    app.config.from_mapping(
        SECRET_KEY='dev'#,
        # # Ensure cookies are usable in https:
        # SESSION_COOKIE_SAMESITE=None,
        # SESSION_COOKIE_SECURE=True,
    )

    from .controller import url_test
    app.register_blueprint(url_test.bp)

    return app