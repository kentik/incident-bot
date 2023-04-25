import config
import yaml

from typing import List, Type, TypeVar
from datetime import datetime
from dataclasses import dataclass, field
from bot.github.api import GithubApi, Repository, logger
from bot.models.incident import db_read_incident


TemplateDataType = TypeVar("TemplateDataType", bound="TemplateData")

@dataclass
class TemplateData:
    title_template: str
    body_template: str
    labels: List[str] = field(default_factory=list)

    @classmethod
    def _from_string(cls: Type[TemplateDataType], data: str) -> TemplateDataType:
        parts = data.split("---\n")
        metadata = yaml.safe_load(parts[1])
        return cls(title_template=metadata["title"], body_template=parts[2], labels=metadata["labels"].split(" "))

    @classmethod
    def from_repo_path(cls: Type[TemplateDataType], repo: Repository, path: str) -> TemplateDataType:
        template = repo.get_contents(path)
        return cls._from_string(template.decoded_content.decode("utf-8"))


class GithubIssue:
    def __init__(
        self,
        incident_id: str,
        description: str,
        start_time: datetime,
        detection_time: datetime,
        regions: List[str],
        owner: str,
        detection_source: str = "manual",
        ingest_impact: bool = False,
        notifications: bool = False,

    ):
        self.repo = GithubApi().repo
        self.incident_id = incident_id
        self.incident_data = db_read_incident(channel_id=self.incident_id)
        self.template = TemplateData.from_repo(self.repo, config.active.get("github").get("issue_template"))
        self.description = description
        self.start_time = start_time
        self.detection_time = detection_time
        self.regions = regions
        self.owner = owner
        self.detection_source = detection_source
        self.ingest_impact = ingest_impact
        self.notifications = notifications
        self.issue = None

    def new(self):
        """Create Github issue"""
        title = self.template.title_template.format(
            date=self.start_time.date().isoformat(),
            incident_title=self.description)
        body = self.template.body_template.format(
            incident_start=self.start_time.isoformat(sep=" ", timespec="minutes"),
            incident_detection=self.detection_time.isoformat(sep=" ", timespec="minutes"),
            regions=self.regions,
            ingest_impact=self.ingest_impact,
            notifications=self.notifications,
            owner=self.owner,
            slack_channel=self.incident_data.channel_name,
            detection_source=self.detection_source
        )
        try:
            self.issue = self.repo.create_issue(title, body=body, labels=self.template.labels)
            return self.issue
        except Exception as error:
            logger.error("Error creating Github issue for incident '%s': '%s'", self.incident_data.incident_id, error)
