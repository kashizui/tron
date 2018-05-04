'''Tron: Trello Recurring Card Scheduler

Usage:
  tron.py [--config=<file>] daily
  tron.py [--config=<file>] weekly
  tron.py (-h | --help)
  tron.py --version

Options:
  -h --help         Show this screen.
  --version         Show version.
  --config=<file>   Config file [default: config.yml].

'''
from __future__ import print_function
import json
import os

import yaml
from docopt import docopt
import getpass
import requests

WHATS_NEXT_ID = 'hRTOsDzc' # What's Next
LIST_ID = '55b2fb01d72f8d313d8e9acc' # Today

config = {}


def get_list_by_name(board_id, list_name):
    r = requests.get('https://api.trello.com/1/boards/{id}/lists'.format(id=board_id), params={
        'token': config['token'],
        'key': config['api_key'],
    })
    r.raise_for_status()
    lists = r.json()

    try:
        return next(l for l in lists if l['name'].lower().strip() == list_name.lower().strip())
    except StopIteration:
        raise KeyError('List with name {} not found'.format(list_name))


def move_cards(source_list, target_list):
    cards = requests.get('https://api.trello.com/1/lists/{id}/cards'.format(id=source_list['id']), params={
        'token': config['token'],
        'key': config['api_key'],
    }).json()

    for card in cards:
        print('Moving:', card['name'])
        r = requests.put('https://api.trello.com/1/cards/{id}'.format(id=card['id']), params={
            'token': config['token'],
            'key': config['api_key'],
            'idList': target_list['id'],
            'position': 'top',
        })
        r.raise_for_status()


def main(args):
    global config
    print(args)

    with open(args['--config'], 'r') as config_file:
        config = yaml.load(config_file)

    if 'token' not in config:
        print('Please authorize:')
        print('https://trello.com/1/authorize?expiration=never'
              '&name=tron&scope=read,write'
              '&response_type=token&key={api_key}'.format(**config))
        config['token'] = getpass.getpass('Enter token:')

    today = get_list_by_name(WHATS_NEXT_ID, 'today')
    this_week = get_list_by_name(WHATS_NEXT_ID, 'this week')
    runway = get_list_by_name(WHATS_NEXT_ID, 'runway')

    if args['daily'] or args['weekly']:
        move_cards(today, this_week)

    if args['weekly']:
        move_cards(this_week, runway)


if __name__ == '__main__':
    main(docopt(__doc__, version='tron (prerelease)'))
