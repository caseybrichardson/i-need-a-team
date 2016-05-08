# i-need-a-team

### Installation and Running

#### Backend
To get all the requirements you need for the project simply run `pip install -r requirements.txt` in the backend folder.

Before you can run the API, you need to initialize the SQLite store. To run the initialization for it, start python in the backend folder and run the following:

```python
from main import init_db
init_db()
```

Then to run the API, you need to pass in the API key and any other options you'd like to have. Example startup parameters are:

```bash
python main.py -k <api-key> -d -p -t -c
```

This command sets the API key for the application, turns on debugging, serves the API on 0.0.0.0, uses threading, and turns on caching.

#### Frontend
There's no fancy requirements here. For development purposes, using the SimpleHTTPServer to hand out content is good enough. Start it using:

```bash
python -m SimpleHTTPServer
```

Of course for serving out in production mode you'd want to use something like nginx (with uWSGI for the backend of course). The setup for those services should be relatively simple.