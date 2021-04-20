from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

from slack_sdk import WebClient
from pytz import UTC

from hunter.series import ChangePointGroup


@dataclass
class NotificationError(Exception):
    message: str


@dataclass
class SlackConfig:
    channel: str
    bot_token: str


class SlackNotification:
    test_change_point_groups: Dict[str, List[ChangePointGroup]]

    def __init__(self, change_point_groups: Dict[str, List[ChangePointGroup]]):
        self.test_change_point_groups = change_point_groups

    # A Slack message can only contain 50 blocks so
    # large summaries must be split across messages.
    def create_dispatches(self):
        dates_change_points = {}
        for test_name, change_point_groups in self.test_change_point_groups.items():
            for group in change_point_groups:
                date_str = str(
                    datetime.fromtimestamp(group.time, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
                )
                if date_str not in dates_change_points:
                    dates_change_points[date_str] = {}
                dates_change_points[date_str][test_name] = group

        dispatches = []
        cur = [self.__header()]
        for date in sorted(dates_change_points):
            if len(cur) > 47:
                dispatches.append(cur)
                cur = [self.__header()]

            tests_changes = dates_change_points[date]

            cur.append(self.__block("divider"))
            cur.append(self.__title_block(date))
            cur.append(self.__dates_change_points_summary(tests_changes))

        if len(cur) > 1:
            dispatches.append(cur)

        return dispatches

    @staticmethod
    def __block(block_type: str, content: Dict = None):
        block = {"type": block_type}
        if content:
            block.update(content)
        return block

    @classmethod
    def __text_block(cls, type, text_type, text):
        return cls.__block(
            type,
            content={
                "text": {
                    "type": text_type,
                    "text": text,
                }
            },
        )

    @classmethod
    def __header(cls):
        return cls.__text_block("header", "plain_text", "Hunter has detected change points")

    @classmethod
    def __title_block(cls, name):
        return cls.__text_block("section", "mrkdwn", f"*{name}*")

    @classmethod
    def __dates_change_points_summary(cls, test_changes: Dict[str, ChangePointGroup]):
        fields = []
        for test_name, group in test_changes.items():
            fields.append(cls.__block("mrkdwn", content={"text": f"*{test_name}*"}))
            summary = ""
            for change in group.changes:
                change_percent = change.forward_change_percent()
                summary += f"*{change.metric}*: {change_percent:+.{2}f}%\n"
            fields.append(cls.__block("mrkdwn", content={"text": summary}))

        return cls.__block(
            "section",
            content={
                "fields": fields,
            },
        )


class SlackNotifier:
    __client: WebClient
    __channel: str

    def __init__(self, conf: SlackConfig):
        self.__client = WebClient(token=conf.bot_token)
        self.__channel = conf.channel

    def notify(self, change_point_groups: Dict[str, List[ChangePointGroup]]):
        dispatches = SlackNotification(change_point_groups).create_dispatches()
        if len(dispatches) > 3:
            raise NotificationError(
                "Change point summary would produce too many Slack notifications"
            )
        for blocks in dispatches:
            self.__client.chat_postMessage(channel=self.__channel, blocks=blocks)
