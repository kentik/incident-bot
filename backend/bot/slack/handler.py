import asyncio
import re

import config
import requests
import slack_sdk
import variables
from typing import Any, Dict, List
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.exc import ConfigurationError
from bot.incident import actions as inc_actions, incident
from bot.incident.action_parameters import ActionParametersSlack
from bot.models.incident import db_read_all_incidents
from bot.scheduler import scheduler
from bot.shared import tools
from bot.slack.client import (
    get_user_name,
    slack_web_client,
    slack_workspace_id,
)
from bot.slack.helpers import DigestMessageTracking
from bot.slack.incident_logging import write as write_content
from bot.slack.messages import (
    help_menu,
    incident_list_message,
    job_list_message,
    pd_on_call_message,
)
from bot.github import GithubIssue
from bot.models.incident import db_read_incident
from slack_bolt import App
from slack_sdk.errors import SlackApiError

logger = config.log.get_logger("slack.handler")

## The xoxb oauth token for the bot is called here to provide bot privileges.
app = App(token=config.slack_bot_token)


@app.error
def custom_error_handler(error, body, logger):
    logger.exception(f"Error: {error}")
    logger.debug(f"Request body: {body}")


# The import statement bellow is seemingly unused, it is though needed to register Bolt UI components and callbacks
# The registrations is a side effect of the import
from . import modals

tracking = DigestMessageTracking()

"""
Handle Mentions
"""


@app.event("app_mention")
def handle_mention(body, say, logger):
    message = body["event"]["text"].split(" ")
    user = body["event"]["user"]
    logger.debug(body)

    if "help" in message:
        say(blocks=help_menu(), text="")
    elif "diag" in message:
        startup_message = config.startup_message(
            workspace=slack_workspace_id, wrap=True
        )
        say(channel=user, text=startup_message)
    elif "lsoi" in message:
        database_data = db_read_all_incidents()
        resp = incident_list_message(database_data, all=False)
        say(blocks=resp, text="")
    elif "lsai" in message:
        database_data = db_read_all_incidents()
        resp = incident_list_message(database_data, all=True)
        say(blocks=resp, text="")
    elif "pager" in message:
        if "pagerduty" in config.active.integrations:
            from bot.pagerduty import api as pd_api

            pd_oncall_data = pd_api.find_who_is_on_call()
            resp = pd_on_call_message(data=pd_oncall_data)
            logger.debug(resp)
            say(blocks=resp, text="")
        else:
            say(
                text="The PagerDuty integration is not enabled. I cannot provide information from PagerDuty as a result."
            )
    elif "scheduler" in message:
        if message[2] == "list":
            jobs = scheduler.process.list_jobs()
            resp = job_list_message(jobs)
            say(blocks=resp, text="")
        elif message[2] == "delete":
            if len(message) < 4:
                say(text="Please provide the ID of a job to delete.")
            else:
                job_title = message[3]
                delete_job = scheduler.process.delete_job(job_title)
                if delete_job != None:
                    say(f"Could not delete the job {job_title}: {delete_job}")
                else:
                    say(f"Deleted job: *{job_title}*")
    elif "ping" in message:
        say(text="pong")
    elif "version" in message:
        say(text=f"I am currently running version: {config.__version__}")
    elif len(message) == 1:
        # This is just a user mention and the bot shouldn't really do anything.
        pass
    else:
        resp = " ".join(message[1:])
        say(text=f"Sorry, I don't know the command *{resp}* yet.")


"""
Incident Management Actions
"""


def parse_action(body) -> Dict[str, Any]:
    return ActionParametersSlack(
        payload={
            "actions": body["actions"],
            "channel": body["channel"],
            "message": body["message"],
            "state": body["state"],
            "user": body["user"],
        }
    )


@app.action("incident.export_chat_logs")
def handle_incident_export_chat_logs(ack, body):
    logger.debug(body)
    ack()
    asyncio.run(inc_actions.export_chat_logs(action_parameters=parse_action(body)))


@app.action("incident.add_on_call_to_channel")
def handle_incident_add_on_call(ack, body, say):
    logger.debug(body)
    ack()
    user = body["user"]["id"]
    say(
        channel=user,
        text="Hi! If you want to page someone, use my shortcut 'Incident Bot Pager' instead!",
    )


@app.action("incident.archive_incident_channel")
def handle_incident_archive_incident_channel(ack, body):
    logger.debug(body)
    ack()
    asyncio.run(
        inc_actions.archive_incident_channel(action_parameters=parse_action(body))
    )


@app.action("incident.assign_role")
def handle_incident_assign_role(ack, body):
    logger.debug(body)
    ack()
    asyncio.run(inc_actions.assign_role(action_parameters=parse_action(body)))


@app.action("incident.claim_role")
def handle_incident_claim_role(ack, body):
    logger.debug(body)
    ack()
    asyncio.run(inc_actions.claim_role(action_parameters=parse_action(body)))


@app.action("incident.set_status")
def handle_incident_set_status(ack, body):
    logger.debug(body)
    ack()
    asyncio.run(inc_actions.set_status(action_parameters=parse_action(body)))


@app.action("incident.set_severity")
def handle_incident_set_severity(ack, body):
    logger.debug(body)
    ack()
    asyncio.run(inc_actions.set_severity(action_parameters=parse_action(body)))


"""
Reactions
"""


def make_reacji_incident(reaction, channel_id, timestamp):
    """"
    Incident creation based on the reacji channeler
    """
    if (config.active.options.get("create_from_reaction", {"enabled": False})["enabled"] or
            reaction != config.active.options.get("create_from_reaction").get("reacji")):
        # not a reacji message or incident creation based on reaction is not enabled
        return False

    # Retrieve the content of the message that was reacted to
    try:
        result = slack_web_client.conversations_history(channel=channel_id,
                                                        inclusive=True,
                                                        oldest=timestamp,
                                                        limit=1)
    except Exception as error:
        logger.error(f"Failed to retrieve a message: error: %s", error)
        return True
    # Create request parameters object
    try:
        request_parameters = incident.RequestParameters(
            channel=channel_id,
            incident_description=f"auto-{tools.random_suffix}",
            user="internal_auto_create",
            severity="sev4",
            message_reacted_to_content=result["messages"][0]["text"],
            original_message_timestamp=timestamp,
            is_security_incident=False,
            private_channel=False,
        )
    except ConfigurationError as error:
        logger.error("Failed to create incident request: error: %s", error)
        return True
    # Create an incident based on the message using the internal path
    try:
        incident.create_incident(internal=True, request_parameters=request_parameters)
    except Exception as error:
        logger.error(f"Failed to create new incident: error: %s", error)
    return True


@dataclass
class FileInfo:
    """
    Information about a file attached to a Slack message
    """
    name: str
    mimetype: str
    content: Any
    timestamp: datetime
    link: str


class MessageContent:
    """
    Representation of a Slack message for the purpose of storing pinned content
    """
    def __init__(self, message):
        self.user = get_user_name(user_id=message["user"])
        self.timestamp = datetime.fromtimestamp(float(message["ts"]), tz=timezone.utc)
        self.text = message["text"]
        self.files: List[FileInfo] = []
        for file in message.get("files", []):
            try:
                res = requests.get(
                    file["url_private"],
                    headers={"Authorization": f"Bearer {config.slack_bot_token}"},
                    params={"pub_secret": file["permalink_public"].split("-")[3]},
                )
            except Exception as exc:
                logger.error("Failed to download file '%s', error: %s", file["name"], exc)
                continue
            self.files.append(
                FileInfo(
                    name=file["name"],
                    mimetype=file["mimetype"],
                    timestamp=datetime.fromtimestamp(float(file["timestamp"]), tz=timezone.utc),
                    content=res.content,
                    link=file["url_private"]
                )
            )

    def __str__(self):
        return ",".join([f"{k}:{v}" for k,v in self.__dict__.items()])

    def store_to_db(self, incident_id, error_reporter):
        non_images = [f for f in self.files if "image" not in f.mimetype]
        if non_images:
            error_reporter(f"{len(non_images)} non-image file(s) ignored. I can currently only attach images.")

        nr_images = 0
        for file in [f for f in self.files if "image" in f.mimetype]:
            write_content(
                incident_id=incident_id,
                title=file.name,
                img=file.content,
                mimetype=file.mimetype,
                ts=tools.db_timestamp(file.timestamp),
                user=self.user,
            )
            nr_images += 1
        write_content(
            incident_id=incident_id,
            content=self.text,
            ts=tools.db_timestamp(self.timestamp),
            user=self.user,
        )
        logger.debug("reaction_added: incident_id: '%s' pinned content stored to DB, text: '%s' %d images",
                     incident_id, self.text, nr_images)

    def as_github_issue_comment(self, incident):
        try:
            issue = GithubIssue(incident)
            issue.create_comment(self.text + "\n" + "\n".join([f"[{f.name}]({f.link})" for f in self.files]))
        except RuntimeError as exc:
            logger.error("Failed to store pinned content in GitHub issue - error: '%s'", exc)


@app.event("reaction_added")
def reaction_added(event, say):
    logger.debug("reaction_added: event: %s, say: %s", event, say)
    emoji = event["reaction"]
    channel_id = event["item"]["channel"]
    ts = event["item"]["ts"]
    # Automatically create incident based on reaction with specific emoji
    logger.debug("reaction: channel_id: %s ts: %s emoji: %s", channel_id, emoji, ts)

    if make_reacji_incident(emoji, channel_id, ts):
        # reaction was from reacji, we are done
        return

    if emoji != "pushpin":
        # Not a pinned content
        return

    # Pinned content for incidents
    if emoji == "pushpin":
        channel_info = slack_web_client.conversations_info(channel=channel_id)
        if "inc-" in channel_info["channel"]["name"]:
            # Retrieve the content of the message that was reacted to
            try:
                result = slack_web_client.conversations_history(
                    channel=channel_id, inclusive=True, oldest=ts, limit=1
                )
                message = result["messages"][0]
                if "files" in message:
                    for file in message["files"]:
                        if "image" in file["mimetype"]:
                            if not file["public_url_shared"]:
                                # Make the attachment public temporarily
                                try:
                                    slack_web_client.files_sharedPublicURL(
                                        file=file["id"],
                                        token=config.slack_user_token,
                                    )
                                except SlackApiError as error:
                                    logger.error(
                                        f"Error preparing pinned file for copy: {error}"
                                    )
                            # Copy the attachment into the database
                            pub_secret = file["permalink_public"].split("-")[3]
                            res = requests.get(
                                file["url_private"],
                                headers={
                                    "Authorization": f"Bearer {config.slack_bot_token}"
                                },
                                params={"pub_secret": pub_secret},
                            )
                            write_content(
                                incident_id=channel_info["channel"]["name"],
                                title=file["name"],
                                img=res.content,
                                mimetype=file["mimetype"],
                                ts=tools.fetch_timestamp(short=True),
                                user=get_user_name(user_id=message["user"]),
                            )
                            # Revoke public access
                            try:
                                slack_web_client.files_revokePublicURL(
                                    file=file["id"],
                                    token=config.slack_user_token,
                                )
                            except SlackApiError as error:
                                logger.error(
                                    f"Error preparing pinned file for copy: {error}"
                                )
                        else:
                            say(
                                channel=channel_id,
                                text=f":wave: Hey there! It looks like that's not an image. I can currently only attach images.",
                            )
                else:
                    write_content(
                        incident_id=channel_info["channel"]["name"],
                        content=message["text"],
                        ts=tools.fetch_timestamp(short=True),
                        user=get_user_name(user_id=message["user"]),
                    )
            except Exception as error:
                logger.error(f"Error when trying to retrieve a message: {error}")
            finally:
                try:
                    slack_web_client.reactions_add(
                        channel=channel_id,
                        name="white_check_mark",
                        timestamp=ts,
                    )
                    if config.active.integrations.get("github"):
                        try:
                            incident = db_read_incident(channel_id=channel_id)
                            message.as_github_issue_comment(incident)
                        except Exception as exc:
                            logger.debug("reaction_added: Failed to lookup incident with channel_id: '%s' - error: %s", channel_id, exc)
                except Exception as error:
                    if "already_reacted" in str(error):
                        reason = "It looks like I've already pinned that content."
                    else:
                        reason = f"Something went wrong: {error}"
                        say(
                            channel=channel_id,
                            text=f":wave: Hey there! I was unable to pin that message. {reason}",
                        )


@app.event("pin_added")
def pin_added(event, say):
    logger.debug("pin_added: event: %s", event)
    channel_id = event["item"]["channel"]
    try:
        incident = db_read_incident(channel_id=channel_id)
        logger.debug("pin_added: incident '%s", incident)
    except Exception as exc:
        logger.debug("pin_added: Failed to lookup incident with channel_id: '%s' - error: %s",
                     channel_id, exc)
        # Not a channel matching any incident tracked in the DB =>  nothing to do
        return
    if event["item"]["type"] != "message":
        logger.debug("pin_added: not a message, ignoring")
        # not a pinned message => nothing to do
        return
    message = MessageContent(event["item"]["message"])
    message.store_to_db(incident.incident_id, lambda x: say(channel=channel_id, text=f":wave: {x}"))
    if config.active.integrations.get("github"):
        message.as_github_issue_comment(incident)


@app.event("message")
def handle_message_events(body):
    """
    Handle monitoring digest channel
    """
    logger.debug("handle_message_events: body: %s", body)
    if (
        # The presence of subtype indicates events like message updates, etc.
        # We don't want to act on these.
        body["event"]["channel"] == variables.digest_channel_id
        and not "subtype" in body["event"].keys()
    ):
        tracking.incr()
        if tracking.calls > 3:
            try:
                result = slack_web_client.chat_postMessage(
                    channel=body["event"]["channel"],
                    blocks=[
                        {
                            "block_id": "chatter_help_message",
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": ":wave: Hey there! I've noticed there's some conversation happening in this channel and that there are no active incidents. "
                                + "You can always start an incident and use it to investigate. In fact, all incidents start off as investigations! "
                                + "You can always mark things as resolved if there are no actual issues.",
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "actions",
                            "block_id": "chat_help_message_buttons",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Start New Incident",
                                        "emoji": True,
                                    },
                                    "value": "show_incident_modal",
                                    "action_id": "open_incident_modal",
                                    "style": "danger",
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Dismiss",
                                        "emoji": True,
                                    },
                                    "value": "placeholder",
                                    "action_id": "dismiss_message",
                                },
                            ],
                        },
                    ],
                )
                tracking.reset()
                tracking.set_message_ts(message_ts=result["message"]["ts"])
                # Retrieve the sent message
                sent_message = slack_web_client.conversations_history(
                    channel=body["event"]["channel"],
                    inclusive=True,
                    oldest=result["message"]["ts"],
                    limit=1,
                )
                # Update the sent message with its own timestamp
                existing_blocks = sent_message["messages"][0]["blocks"]
                existing_blocks[2]["elements"][1]["value"] = result["message"]["ts"]
                try:
                    slack_web_client.chat_update(
                        channel=body["event"]["channel"],
                        ts=result["message"]["ts"],
                        blocks=existing_blocks,
                        text="",
                    )
                except slack_sdk.errors.SlackApiError as error:
                    logger.error(f"Error updating message: {error}")
            except slack_sdk.errors.SlackApiError as error:
                logger.error(
                    f"Error sending help message to incident channel during increased chatter: {error}"
                )


"""
Statuspage actions
"""


@app.action(re.compile(r"^statuspage.*"))
def statuspage_action(ack, body):
    logger.debug("statuspage_action: body: %s", body)
    ack()


"""
Jira actions
"""


@app.action(re.compile(r"^jira.*"))
def jira_action(ack, body):
    logger.debug("jira_action: body: %s", body)
    ack()


"""
Other actions
"""


@app.action("dismiss_message")
def dismiss_message_action(ack, body):
    logger.debug("dismiss_message_action: body: %s", body)
    try:
        ack()
        slack_web_client.chat_delete(
            channel=body["channel"]["id"], ts=body["actions"][0]["value"]
        )
    except slack_sdk.errors.SlackApiError as error:
        logger.error(f"Error deleting message: {error}")


@app.action(re.compile(r"^incident.*"))
def incident_action(ack, body):
    logger.debug("incident_action: body: %s", body)
    ack()


@app.action(re.compile(r"^external.*"))
def external_action(ack, body):
    logger.debug("external_action: body: %s", body)
    ack()


@app.action(re.compile(r"^incident_update_modal_.*"))
def incident_update_modal_action(ack, body):
    logger.debug("incident_update_modal_action: body: %s", body)
    ack()


@app.action("open_rca")
def open_rca_action(ack, body):
    logger.debug("open_rca_action: body: %s", body)
    ack()


@app.action(re.compile(r"^open_incident_modal_.*"))
def open_incident_modal_action(ack, body):
    logger.debug("open_incident_modal_action: body: %s", body)
    ack()
