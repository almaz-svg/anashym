"""Bounded local Windows/Linux WSGI server."""
import argparse
from waitress import serve
from .wsgi import application

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--threads',type=int,default=4)
    args=parser.parse_args()
    serve(application,host=args.host,port=args.port,threads=args.threads,
          backlog=1024,connection_limit=256,max_request_body_size=52*1024*1024)
