"""
Agile Scrum Pokerbot for Slack

Hosted on AWS Lambda.

:Author: Nate Yolles <yolles@adobe.com>
:Homepage: https://github.com/nateyolles/slack-pokerbot
"""

import boto3
from boto3.dynamodb.conditions import Key
import logging
from urlparse import parse_qs
import json
import requests
import datetime
import os
import time

# Start Configuration
SLACK_TOKENS = os.getenv('SLACK_TOKEN')
IMAGE_LOCATION = os.getenv('IMAGE_LOCATION')
TABLE_NAME = os.getenv('TABLE_NAME')
# End Configuration

valid_sizes = {
    'f' : {
        '0' : IMAGE_LOCATION + '0.png',
        '1' : IMAGE_LOCATION + '1.png',
        '2' : IMAGE_LOCATION + '2.png',
        '3' : IMAGE_LOCATION + '3.png',
        '5' : IMAGE_LOCATION + '5.png',
        '8' : IMAGE_LOCATION + '8.png',
        '13' : IMAGE_LOCATION + '13.png',
        '20' : IMAGE_LOCATION + '20.png',
        '40' : IMAGE_LOCATION + '40.png',
        '100' : IMAGE_LOCATION + '100.png',
        '?' : IMAGE_LOCATION + 'unsure.png'
    },
    's' : {
        '1' : IMAGE_LOCATION + '1.png',
        '3' : IMAGE_LOCATION + '3.png',
        '5' : IMAGE_LOCATION + '5.png',
        '8' : IMAGE_LOCATION + '8.png',
        '?' : IMAGE_LOCATION + 'unsure.png'
    },
    't' : {
        's' : IMAGE_LOCATION + 'small.png',
        'm' : IMAGE_LOCATION + 'medium.png',
        'l' : IMAGE_LOCATION + 'large.png',
        'xl' : IMAGE_LOCATION + 'extralarge.png',
        '?' : IMAGE_LOCATION + 'unsure.png',
    },
    'm' : {
        '1' : IMAGE_LOCATION + 'one.png',
        '2' : IMAGE_LOCATION + 'two.png',
        '3' : IMAGE_LOCATION + 'three.png',
        '4' : IMAGE_LOCATION + 'four.png',
        '5' : IMAGE_LOCATION + 'five.png',
        '6' : IMAGE_LOCATION + 'six.png',
        '7' : IMAGE_LOCATION + 'seven.png',
        '8' : IMAGE_LOCATION + 'eight.png',
        '2d' : IMAGE_LOCATION + 'twod.png',
        '3d' : IMAGE_LOCATION + 'threed.png',
        '4d' : IMAGE_LOCATION + 'fourd.png',
        '5d' : IMAGE_LOCATION + 'fived.png',
        '1.5w' : IMAGE_LOCATION + 'weekhalf.png',
        '2w' : IMAGE_LOCATION + 'twow.png',
        '?' : IMAGE_LOCATION + 'unsure.png',
    }
}

logger = logging.getLogger()
logger.setLevel(logging.INFO)

poker_data = {}

def lambda_handler(event, context):
    """The function that AWS Lambda is configured to run on POST request to the
    configuration path. This function handles the main functions of the Pokerbot
    including starting the game, voting, calculating and ending the game.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TABLE_NAME)
    
    req_body = event['body']
    params = parse_qs(req_body)
    token = params['token'][0]

    if token not in SLACK_TOKENS:
        logger.error("Request token (%s) does not match expected.", token)
        raise Exception("Invalid request token")

    post_data = {
        'team_id' : params['team_id'][0],
        'team_domain' : params['team_domain'][0],
        'channel_id' : params['channel_id'][0],
        'channel_name' : params['channel_name'][0],
        'user_id' : params['user_id'][0],
        'user_name' : params['user_name'][0],
        'command' : params['command'][0],
        'text' : params['text'][0] if 'text' in params.keys() else None,
        'response_url' : params['response_url'][0]
    }

    logger.info("post_data: %s", post_data)

    if post_data['text'] == None:
        return create_ephemeral('Type */poker help* for pokerbot commands.')

    command_arguments = post_data['text'].split(' ')
    sub_command = command_arguments[0]
    logger.info("sub_command: %s", sub_command)

    team_and_channel = "%s|%s" % (post_data["team_id"], post_data["channel_id"])

    if sub_command == 'setup':

        setup_sub_command = command_arguments[1]

        sizes = ['f', 's', 't', 'm']

        if len(command_arguments) < 2:
            return create_ephemeral("You must enter a size format </poker setup [f, s, t, m].")
        
        if setup_sub_command not in sizes:
            return create_ephemeral("Your choices are f, s, t or m in format /poker setup <choice>.")
    
        logger.info('Updating table with config...')
        table.put_item(
            Item={
                'TeamAndChannel': team_and_channel,
                'Key': 'Config',
                'Attributes': {
                    'Size': setup_sub_command
                }
            }
        )
        return create_ephemeral("Size has been set for channel.")

    elif sub_command == 'deal':
        if len(command_arguments) < 2:
            return create_ephemeral("You did not enter a JIRA ticket number.")

        ticket_number = command_arguments[1]

        size = table.get_item(
            Key={
                'TeamAndChannel': team_and_channel,
                'Key': 'Config'
            }
        )["Item"]["Attributes"]["Size"]

        table.put_item(
            Item={
                'TeamAndChannel': team_and_channel,
                'Key': 'Session|%d' % time.time(),
                'Attributes': {
                    'TicketNumber': ticket_number,
                    'Votes': {}
                }
            }
        )

        COMPOSITE_IMAGE = None
        if size == 'f':
            COMPOSITE_IMAGE = IMAGE_LOCATION + 'composite.png'
        if size == 's':
            COMPOSITE_IMAGE = IMAGE_LOCATION + 'scomposite.png'
        if size == 't':
            COMPOSITE_IMAGE = IMAGE_LOCATION + 'scomposite.png'
        if size == 'm':
            COMPOSITE_IMAGE = IMAGE_LOCATION + 'mcomposite.png'

        logger.info('Size: %s COMPOSITE_IMAGE: %s' % (size, COMPOSITE_IMAGE))
        message = Message('*The planning poker game has started* for: %s' % ticket_number)
        message.add_attachment('Vote by typing */poker vote <size>*.', None, COMPOSITE_IMAGE)

        return message.get_message()

    elif sub_command == 'vote':
        res = table.query(
            KeyConditionExpression = Key('TeamAndChannel').eq(team_and_channel) & Key('Key').begins_with('Session|'),
            ScanIndexForward = False,
            Limit = 1
        )
        if len(res["Items"]) == 0:
            return create_ephemeral("The poker planning game hasn't started yet.")

        session = res["Items"][0]

        if len(command_arguments) < 2:
            return create_ephemeral("Your vote was not counted. You didn't enter a size.")
        
        size = table.get_item(
            Key={
                'TeamAndChannel': team_and_channel,
                'Key': 'Config'
            }
        )["Item"]["Attributes"]["Size"]

        vote = command_arguments[1]

        logger.info('Size: %s Vote: %s' % (size, vote))

        if vote not in valid_sizes[size]:
            return create_ephemeral("Your vote was not counted. Please enter a valid poker planning size.")

        logger.info('Adding vote %s for %s' % (vote, post_data["user_name"]))

        table.update_item(
            Key={
                'TeamAndChannel': session['TeamAndChannel'],
                'Key': session['Key']
            },
            UpdateExpression="set Attributes.Votes.#USERID = :vote",
            ExpressionAttributeNames={
                '#USERID': post_data["user_id"]
            },
            ExpressionAttributeValues={
                ':vote': [ post_data["user_name"], vote ]
            }
        )

        already_voted = post_data["user_id"] in session['Attributes']['Votes']

        logger.info('Already voted: %s' % already_voted)

        if already_voted:
            return create_ephemeral("You changed your vote to *%s*." % (vote))
        else:
            message = Message('%s voted' % (post_data['user_name']))
            send_delayed_message(post_data['response_url'], message)

            return create_ephemeral("You voted *%s*." % (vote))

    elif sub_command == 'tally':
        res = table.query(
            KeyConditionExpression = Key('TeamAndChannel').eq(team_and_channel) & Key('Key').begins_with('Session|'),
            ScanIndexForward = False,
            Limit = 1
        )
        if len(res["Items"]) == 0:
            return create_ephemeral("The poker planning game hasn't started yet.")

        session = res["Items"][0]

        message = None
        names = []

        for key, vote in session["Attributes"]["Votes"].iteritems():
            names.append(vote[0])

        if len(names) == 0:
            message = Message('No one has voted yet.')
        elif len(names) == 1:
            message = Message('%s has voted.' % names[0])
        else:
            message = Message('%s have voted.' % ', '.join(sorted(names)))

        return message.get_message()

    elif sub_command == 'reveal':
        res = table.query(
            KeyConditionExpression = Key('TeamAndChannel').eq(team_and_channel) & Key('Key').begins_with('Session|'),
            ScanIndexForward = False,
            Limit = 1
        )
        if len(res["Items"]) == 0:
            return create_ephemeral("The poker planning game hasn't started yet.")
        
        session = res["Items"][0]

        size = table.get_item(
            Key={
                'TeamAndChannel': team_and_channel,
                'Key': 'Config'
            }
        )["Item"]["Attributes"]["Size"]

        votes = {}

        ticket_number = session["Attributes"]["TicketNumber"]

        for key, vote in session["Attributes"]["Votes"].iteritems():
            player_name = vote[0]
            player_vote = vote[1]

            if not votes.has_key(player_vote):
                votes[player_vote] = []

            votes[player_vote].append(player_name)

        vote_set = set(votes.keys())

        if len(vote_set) == 1 : 
            estimate = valid_sizes[size].get(vote_set.pop())
            message = Message('*Congratulations!*')
            message.add_attachment('Everyone selected the same number.', 'good', estimate)

            return message.get_message()
            
        else:
            message = Message('*No winner yet.* Discuss and continue voting.')

            for vote in votes:
                message.add_attachment(", ".join(votes[vote]), 'warning', valid_sizes[size][vote], True)

            return message.get_message()
        
    elif sub_command == 'help':
        return create_ephemeral('Pokerbot helps you play Agile/Scrum poker planning.\n\n' +
                              'Use the following commands:\n' +
                              ' /poker setup\n' +
                              ' /poker deal\n' +
                              ' /poker vote\n' +
                              ' /poker tally\n' +
                              ' /poker end')

    else:
        return create_ephemeral('Invalid command. Type */poker help* for pokerbot commands.')

def create_ephemeral(text):
    """Send private response to user initiating action

    :param text: text in the message
    """
    
    return {
      "statusCode": 200,
        "body": json.dumps({
          "text": text
      }),
    }

def send_delayed_message(url, message):
    """Send a delayed in_channel message.

    You can send up to 5 messages per user command.
    """
    r = requests.post(url, json = message.body())
    logger.info('send_delayed_message status_code: %s' % r.status_code)

class Message():
    """Public Slack message

    see `Slack message formatting <https://api.slack.com/docs/formatting>`_
    """

    def __init__(self, text):
        """Message constructor.

        :param text: text in the message
        :param color: color of the Slack message side bar
        """
        self.__message = {}
        self.__message['response_type'] = 'in_channel'
        self.__message['text'] = text
    
    def body(self):
        return self.__message;

    def add_attachment(self, text, color=None, image=None, thumbnail=False):
        """Add attachment to Slack message.

        :param text: text in the attachment
        :param image: image in the attachment
        :param thumbnail: image will be thubmanail if True, full size if False
        """
        if not self.__message.has_key('attachments'):
            self.__message['attachments'] = []

        attachment = {}
        attachment['text'] = text

        if color != None:
            attachment['color'] = color

        if image != None:
            if thumbnail:
                attachment['thumb_url'] = image
            else:
                attachment['image_url'] = image

        self.__message['attachments'].append(attachment)

    def get_message(self):
        """Get the Slack message.

        :returns: the Slack message in format ready to return to Slack client
        """
        body = json.dumps(self.__message)
        logger.info("returning: %s", body)
        
        return {
          "statusCode": 200,
          "body": body,
        }
