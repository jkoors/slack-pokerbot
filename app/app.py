"""
Agile Scrum Pokerbot for Slack

Hosted on AWS Lambda.

:Author: Nate Yolles <yolles@adobe.com>
:Homepage: https://github.com/nateyolles/slack-pokerbot
"""

import boto3
import logging
from urlparse import parse_qs
import json
import urllib2
import datetime

# Start Configuration
SLACK_TOKENS = ('<insert your Slack token>', '<additional Slack token>')
IMAGE_LOCATION = '<insert your image path> (e.g. http://www.my-site.com/images/)'
COMPOSITE_IMAGE = []
VALID_VOTES = {}
SESSION_ESTIMATES = {}
# End Configuration

logger = logging.getLogger()
logger.setLevel(logging.INFO)

poker_data = {}

def lambda_handler(event, context):
    """The function that AWS Lambda is configured to run on POST request to the
    configuration path. This function handles the main functions of the Pokerbot
    including starting the game, voting, calculating and ending the game.
    """
    dynamodb = boto3.resource("dynamodb")
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

    if post_data['text'] == None:
        return create_ephemeral('Type */pokerbot help* for pokerbot commands.')

    command_arguments = post_data['text'].split(' ')
    sub_command = command_arguments[0]

    if sub_command == 'setup':

        valid_sizes = {'fibonacci' : {
                        0 : IMAGE_LOCATION + '0.png',
                        1 : IMAGE_LOCATION + '1.png',
                        2 : IMAGE_LOCATION + '2.png',
                        3 : IMAGE_LOCATION + '3.png',
                        5 : IMAGE_LOCATION + '5.png',
                        8 : IMAGE_LOCATION + '8.png',
                        13 : IMAGE_LOCATION + '13.png',
                        20 : IMAGE_LOCATION + '20.png',
                        40 : IMAGE_LOCATION + '40.png',
                        100 : IMAGE_LOCATION + '100.png',
                        '?' : IMAGE_LOCATION + 'unsure.png'
                    },
                        'simple_fibonacci' : {
                        1 : IMAGE_LOCATION + '1.png',
                        3 : IMAGE_LOCATION + '3.png',
                        5 : IMAGE_LOCATION + '5.png',
                        8 : IMAGE_LOCATION + '8.png',
                        '?' : IMAGE_LOCATION + 'unsure.png'
                    },
                        't_shirt_size' : {
                        's' : IMAGE_LOCATION + 'small.png',
                        'm' : IMAGE_LOCATION + 'medium.png',
                        'l' : IMAGE_LOCATION + 'large.png',
                        'xl' : IMAGE_LOCATION + 'extralarge.png',
                        '?' : IMAGE_LOCATION + 'unsure.png',
                    },
                    'man_hours' : {
                        1 : IMAGE_LOCATION + 'one.png',
                        2 : IMAGE_LOCATION + 'two.png',
                        3 : IMAGE_LOCATION + 'three.png',
                        4 : IMAGE_LOCATION + 'four.png',
                        5 : IMAGE_LOCATION + 'five.png',
                        6 : IMAGE_LOCATION + 'six.png',
                        7 : IMAGE_LOCATION + 'seven.png',
                        8 : IMAGE_LOCATION + 'eight.png',
                        '2d' : IMAGE_LOCATION + 'twod.png',
                        '3d' : IMAGE_LOCATION + 'threed.png',
                        '4d' : IMAGE_LOCATION + 'fourd.png',
                        '5d' : IMAGE_LOCATION + 'fived.png',
                        '1.5w' : IMAGE_LOCATION + 'weekhalf.png',
                        '2w' : IMAGE_LOCATION + 'twow.png',
                        '?' : IMAGE_LOCATION + 'unsure.png',
                    }
                    
                }

        setup_sub_command = command_arguments[1]

        f = valid_sizes['fibonnaci']
        s = valid_sizes['simple_fibonacci']
        t = valid_sizes['t_shirt_size']
        m = valid_sizes['man_hours']

        sizes = [f, s, t, m]

        if len(command_arguments) < 2:
            return create_ephemeral("You must enter a size format </pokerbot setup [f, s, t, m].")
        
        if setup_sub_command not in sizes:
            return create_ephemeral("Your choices are f, s, t or m in format /pokerbot setup <choice>.")
        else:
            if setup_sub_command == f:
                VALID_VOTES.update(f)
                COMPOSITE_IMAGE.append(IMAGE_LOCATION + 'composite.png')
            elif setup_sub_command == s:
                VALID_VOTES.update(valid_sizes['simple_fibonnaci'])
                COMPOSITE_IMAGE.append(IMAGE_LOCATION + 'scomposite.png')
            elif setup_sub_command == t:
                VALID_VOTES.update(valid_sizes['t_shirt_size'])
                COMPOSITE_IMAGE.append(IMAGE_LOCATION + 'scomposite.png')
            elif setup_sub_command == m:
                VALID_VOTES.update(valid_sizes['man_hours'])
                COMPOSITE_IMAGE.append(IMAGE_LOCATION + 'mcomposite.png')
    
        table = dynamodb.Table("pokerbot_config")
        
        response = table.update_item(
            Key={
                'channel': post_data["channel_name"],
            },
            UpdateExpression="set size = :s",
            ExpressionAttributeValues={
                ':s': setup_sub_command,
            },
            ReturnValues="UPDATED_NEW"
        )

    elif sub_command == 'start':
        
        table = dynamodb.Table("pokerbot_sessions")
        
        response = table.update_item(
            Key={
                'channel': post_data["channel_name"],
                'date': datetime.date.today(),
            },
            UpdateExpression="set start_time = :s",
            ExpressionAttributeValues={
                ':s': datetime.datetime.now(),
            },
            ReturnValues="UPDATED_NEW"
        )

        return create_ephemeral("Your session is now being recorded, you can run deal command.")


    elif sub_command == 'deal': /pokerbot deal PRODENG-11521
        if post_data['team_id'] not in poker_data.keys():
            poker_data[post_data['team_id']] = {}
        
        if len(command_arguments) < 2:
            return create_ephemeral("You did not enter a JIRA ticket number.")

        ticket_number = command_arguments[1]

        poker_data[post_data['team_id']][post_data['channel_id']] = {}

        poker_data[post_data['team_id']][post_data['channel_id']]['ticket'] = ticket_number

        message = Message('*The planning poker game has started* for {}.'.format(ticket_number))
        message.add_attachment('Vote by typing */pokerbot vote <size>*.', None, COMPOSITE_IMAGE)

        return message.get_message()


    elif sub_command == 'vote':
        if (post_data['team_id'] not in poker_data.keys() or
                post_data['channel_id'] not in poker_data[post_data['team_id']].keys()):
            return create_ephemeral("The poker planning game hasn't started yet.")

        if len(command_arguments) < 2:
            return create_ephemeral("Your vote was not counted. You didn't enter a size.")

        vote_sub_command = command_arguments[1]
        vote = None

        if vote not in VALID_VOTES:
            return create_ephemeral("Your vote was not counted. Please enter a valid poker planning size.")

        already_voted = poker_data[post_data['team_id']][post_data['channel_id']].has_key(post_data['user_id'])

        poker_data[post_data['team_id']][post_data['channel_id']][post_data['user_id']] = {
            'vote' : vote,
            'name' : post_data['user_name']
        }

        if already_voted:
            return create_ephemeral("You changed your vote to *%s*." % (vote))
        else:
            message = Message('%s voted' % (post_data['user_name']))
            send_delayed_message(post_data['response_url'], message)

            return create_ephemeral("You voted *%s*." % (vote))

    elif sub_command == 'tally':
        if (post_data['team_id'] not in poker_data.keys() or
                post_data['channel_id'] not in poker_data[post_data['team_id']].keys()):
            return create_ephemeral("The poker planning game hasn't started yet.")

        message = None
        names = []

        for player in poker_data[post_data['team_id']][post_data['channel_id']]:
            names.append(poker_data[post_data['team_id']][post_data['channel_id']][player]['name'])

        if len(names) == 0:
            message = Message('No one has voted yet.')
        elif len(names) == 1:
            message = Message('%s has voted.' % names[0])
        else:
            message = Message('%s have voted.' % ', '.join(sorted(names)))

        return message.get_message()

    elif sub_command == 'reveal':
        if (post_data['team_id'] not in poker_data.keys() or
                post_data['channel_id'] not in poker_data[post_data['team_id']].keys()):
            return create_ephemeral("The poker planning game hasn't started yet.")

        votes = {}

        ticket_number = poker_data[post_data['team_id']][post_data['channel_id']]['ticket']
        del poker_data[post_data['team_id']][post_data['channel_id']]['ticket']

        for player in poker_data[post_data['team_id']][post_data['channel_id']]:
            player_vote = poker_data[post_data['team_id']][post_data['channel_id']][player]['vote']
            player_name = poker_data[post_data['team_id']][post_data['channel_id']][player]['name']

            if not votes.has_key(player_vote):
                votes[player_vote] = []

            votes[player_vote].append(player_name)
        
        del poker_data[post_data['team_id']][post_data['channel_id']]

        vote_set = set(votes.keys())

        if len(vote_set) == 1 : 
            estimate = VALID_VOTES.get(vote_set.pop()
            message = Message('*Congratulations!*')
            message.add_attachment('Everyone selected the same number.', 'good', estimate))
            
            table = dynamodb.Table("pokerbot_sessions")
        
            response = table.update_item(
                Key={
                    'channel': post_data["channel_name"],
                    'date': datetime.date.today(),
                },
                UpdateExpression="set {} = :e".format(ticket_number),
                ExpressionAttributeValues={
                    ':e': estimate,
                },
                ReturnValues="UPDATED_NEW"
            )

            return message.get_message()
            
        else:
            message = Message('*No winner yet.* Discuss and continue voting.')

            for vote in votes:
                message.add_attachment(", ".join(votes[vote]), 'warning', VALID_VOTES[vote], True)

            return message.get_message()
        

    elif sub_command == 'end':
        
        table = dynamodb.Table("pokerbot_sessions")
        
        response = table.update_item(
            Key={
                'channel': post_data["channel_name"],
                'date': datetime.date.today(),
            },
            UpdateExpression="set end_time = :s",
            ExpressionAttributeValues={
                ':s': datetime.datetime.now(),
            },
            ReturnValues="UPDATED_NEW"
        )
        
        message = Message('*Session has ended, see results below:*')

        for item in response.Items:
            message.add_attachment('{key}:{value}'.format(key=item, value=response.Items[item]), 'good')

        return message.get_message()
        
    elif sub_command == 'help':
        return create_ephemeral('Pokerbot helps you play Agile/Scrum poker planning.\n\n' +
                              'Use the following commands:\n' +
                              ' /pokerbot setup\n' +
                              ' /pokerbot start\n' +
                              ' /pokerbot deal\n' +
                              ' /pokerbot vote\n' +
                              ' /pokerbot tally\n' +
                              ' /pokerbot reveal\n' +
                              ' /pokerbot end')

    else:
        return create_ephemeral('Invalid command. Type */pokerbot help* for pokerbot commands.')

def create_ephemeral(text):
    """Send private response to user initiating action

    :param text: text in the message
    """
    message = {}
    message['text'] = text

    return message

def send_delayed_message(url, message):
    """Send a delayed in_channel message.

    You can send up to 5 messages per user command.
    """

    req = urllib2.Request(url)
    req.add_header('Content-Type', 'application/json')

    try:
        response = urllib2.urlopen(req, json.dumps(message.get_message()))
    except urllib2.URLError:
        logger.error("Could not send delayed message to %s", url)

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
        return self.__message
