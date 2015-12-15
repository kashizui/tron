"""Tron: Trello Recurring Card Scheduler

Usage:
  tron.py now
  tron.py (-h | --help)
  tron.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.
  --once        Schedule once only

"""
import os
from docopt import docopt
from trello import TrelloApi

TRELLO_APP_KEY = os.environ['TRELLO_APP_KEY']
TRELLO_USER_SECRET = os.environ['TRELLO_APP_SECRET']
BOARD_ID = "hRTOsDzc" # What's Next
LIST_ID = "55b2fb01d72f8d313d8e9acc" # Today

trello = TrelloApi(TRELLO_APP_KEY)
trello.set_token("857ee85ae82e219129fcc8b49e2d66145b6f8038ada663a43bec3ff81319fc6d")

# print trello.get_token_url('tron', expires='30days', write_access=True)



#card = trello.lists.new_card(LIST_ID, "API test")

#card['id']

if __name__ == '__main__':
    arguments = docopt(__doc__, version='tron (prerelease)')
    print(arguments)
