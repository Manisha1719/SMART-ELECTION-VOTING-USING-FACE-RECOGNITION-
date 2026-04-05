import os
from flask import Flask, render_template
from main import main
from api import api



app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = 'smart_voting'

app.register_blueprint(api, url_prefix='/api')
app.register_blueprint(main)

if __name__ == '__main__':
  port = int(os.getenv('PORT', 5500))
  app.run(host='0.0.0.0', port=port, debug=True)