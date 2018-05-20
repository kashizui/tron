'''Tron: Trello Recurring Card Scheduler

Usage:
  tron.py [--dry-run --config=<file>] daily
  tron.py [--dry-run --config=<file>] weekly
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

from docopt import docopt
from sendgrid.helpers.mail import *
import datetime
import getpass
import pendulum
import re
import requests
import sendgrid
import yaml


def pprint(obj):
    print(json.dumps(
        obj, sort_keys=True, indent=4, separators=(',', ': ')))

def find_by_case_insensitive_key(type_name, bag, key, value):
    value = value.strip().lower()
    try:
        return next(thing for thing in bag if thing[key].strip().lower() == value)
    except StopIteration:
        raise KeyError('{} with {}={!r} not found'.format(type_name.capitalize(), key, value))


class Tron(object):
    def __init__(self, config, dry_run):
        self.config = config
        self.dry_run = dry_run
        self.now = pendulum.now()

    def trello(self, method, endpoint, params=None):
        """Thin wrapper for Trello API calls."""
        params = params or {}
        params.update({
            'token': self.config['token'],
            'key': self.config['api_key'],
        })
        r = getattr(requests, method)('https://api.trello.com/1' + endpoint, params=params)
        r.raise_for_status()
        return r

    def get_board_by_name(self, name, organization=None):
        name = name.lower().strip()
        if organization is not None:
            orgs = self.trello('get', '/members/me/organizations').json()
            org = find_by_case_insensitive_key('org', orgs, 'name', organization)
            boards = self.trello('get', '/organizations/{id}/boards'.format(id=org['id'])).json()
        else:
            boards = self.trello('get', '/members/me/boards').json()
        try:
            return next(b for b in boards if b['name'].lower().strip() == name)
        except StopIteration:
            print(boards)
            raise KeyError('Board with name {} not found'.format(name))

    def get_list_by_name(self, board_id, list_name):
        list_name = list_name.lower().strip()
        lists = self.trello('get', '/boards/{id}/lists'.format(id=board_id)).json()
        try:
            return next(l for l in lists if l['name'].lower().strip() == list_name)
        except StopIteration:
            raise KeyError('List with name {} not found'.format(list_name))


    def move_cards(self, source_list, target_list):
        cards = self.trello('get', '/lists/{id}/cards'.format(id=source_list['id'])).json()
        for card in cards:
            print('Moving "{}" from "{}" to "{}"'.format(
                card['name'], source_list['name'], target_list['name']))
            if not self.dry_run:
                self.trello('put', '/cards/{id}'.format(id=card['id']), params={
                    'idList': target_list['id'],
                    'position': 'top',
                })

    def countdown(self, list_id, slack_channel):
        cards = self.trello('get', '/lists/{id}/cards'.format(id=list_id)).json()
        cards = [c for c in cards if c['due'] is not None]
        message = []
        message.append("*DAILY COUNTDOWN*")
        cards_to_display = []
        for card in cards:
            due = pendulum.parse(card['due'])
            if not card['dueComplete'] and due > self.now:
                cards_to_display.append((due, card['name']))
        cards_to_display.sort(reverse=True)
        for due, item_name in cards_to_display:
            message.append(":black_small_square: {} is in {}.".format(
                item_name, self.now.diff_for_humans(due, absolute=True)))
        message.append('_You can add your own countdown by creating a '
                      'card with a due date in Two Boo Doos._')
        if self.dry_run:
            print('Send to Slack {}'.format(slack_channel))
            print('\n'.join(message))
        else:
            self.send_slack('\n'.join(message), slack_channel,
                    botname='countdownbot', icon=':hourglass_flowing_sand:')

    def refresh_repeating(self, list_id, slack_channel):
        # TODO: leave comment if error
        cards = self.trello('get', '/lists/{id}/cards'.format(id=list_id), params={
                # 'actions': 'updateCard',
                # 'action_since': self.now.subtract(days=2).isoformat(),
            }).json()
        to_update = []
        to_notify = []
        for card in cards:
            # Parse interval specification
            interval_spec = re.search('^!repeat (?:every )?(.*)$', card['desc']).group(1)
            interval_parts = [
                    piece.split(maxsplit=2)
                    for piece in interval_spec.split(' and ')
                ]
            interval_parsed = {
                    (unit if unit.endswith('s') else unit + 's'): int(num)
                    for num, unit in interval_parts
                }
            interval = pendulum.duration(**interval_parsed)
            if card['due'] is None:
                to_update.append((card, self.now.add(**interval_parsed)))
            elif card['dueComplete']:
                # lastCompleted = max(
                #         pendulum.parse(action['date'])
                #         for action in card['actions']
                #         if action['data']['card'].get('dueComplete')
                #     )
                # This can also just use now if this script is run daily...
                to_update.append((card, self.now.add(**interval_parsed)))
            elif pendulum.parse(card['due']) <= self.now:
                to_notify.append((card, interval))
            else:
                pass
        for card, new_due in to_update:
            print('Setting due date of {} to {}'.format(
                card['name'], new_due.to_date_string()))
            if not self.dry_run:
                self.trello('put', '/cards/{id}'.format(id=card['id']), params={
                    'due': new_due.to_date_string(),
                    'dueComplete': 'false',
                })
        if to_notify:
            self.send_slack('\n'.join([
                    'Time to {}! (at least {} has elapsed since last time)'.format(
                        card['name'].lower(), interval.in_words())
                    for card, interval in to_notify
                ]),
                slack_channel, botname='chorebot', icon=':sparkles:')

    def send_email(self, to, subject, message):
        if 'sendgrid' in self.config:
            sg = sendgrid.SendGridAPIClient(apikey=self.config['sendgrid']['api_key'])
            from_email = Email(self.config['sendgrid']['reply_to'])
            to_email = Email(to)
            content = Content("text/plain", message)
            mail = Mail(from_email, subject, to_email, content)
            response = sg.client.mail.send.post(request_body=mail.get())
            print(response.status_code)
            print(response.body)
            print(response.headers)

    def send_slack(self, message, channel='#chat', botname='tron', icon=':hamster:'):
        print('Posting as {} to {}:'.format(botname, channel))
        print(message)
        if not self.dry_run:
            r = requests.post(self.config['slack']['webhook_url'], json={
                "text": message.format(channel=channel),
                "channel": channel,
                "link_names": 1,
                "username": botname,
                "icon_emoji": icon,
            })
            r.raise_for_status()


def main(args):
    with open(args['--config'], 'r') as config_file:
        config = yaml.load(config_file)

    t = Tron(config, args['--dry-run'])

    if 'token' not in config:
        print('Please authorize:')
        print('https://trello.com/1/authorize?expiration=never'
              '&name=TronScript&scope=read,write'
              '&response_type=token&key={api_key}'.format(**config))
        config['token'] = getpass.getpass('Enter token:')

    # Fetch boards and lists by name
    whats_next = t.get_board_by_name("what's next")
    boo_board = t.get_board_by_name("boo adventures", organization="booxboo")
    twoboodoos = t.get_list_by_name(boo_board['id'], "two boo doos")
    chores = t.get_list_by_name(boo_board['id'], "chores")
    today = t.get_list_by_name(whats_next['id'], 'today')
    this_week = t.get_list_by_name(whats_next['id'], 'this week')
    runway = t.get_list_by_name(whats_next['id'], 'runway')

    t.refresh_repeating(chores['id'], '#chores')
    exit()

    if args['daily'] or args['weekly']:
        t.countdown(twoboodoos['id'], '#planning')
        t.move_cards(today, this_week)


    if args['weekly']:
        t.move_cards(this_week, runway)



if __name__ == '__main__':
    main(docopt(__doc__, version='tron (prerelease)'))
