import config
import yaml

from typing import List, Optional,Type, TypeVar
from datetime import datetime
from dataclasses import dataclass, field
from bot.github.api import GithubApi, Repository
from bot.models.incident import db_read_incident, db_update_incident_rca_col


logger = config.log.get_logger("github.issue")


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
        channel_id: str,
        description: str,
        start_time: datetime,
        detection_time: datetime,
        regions: List[str],
        owner: str,
        detection_source: str = "manual",
        ingest_impacted: bool = False,
        notifications_impacted: bool = False,

    ):
        self.api = GithubApi()
        self.incident = db_read_incident(channel_id=channel_id)
        template = TemplateData.from_repo_path(self.api.repo, self.api.config.template_path)
        title = self.incident.channel_description
        try:
            title = template.title_template.format(
                date=start_time.date().isoformat(),
                incident_title=title)
        except NameError as exc:
            raise RuntimeError(
                f"Incident id: {self.incident_id} - Failed to format GitHub issue title. Unknown macro: {exc}"
            )
        try:
            body = template.body_template.format(
                description=description,
                incident_start=start_time.isoformat(sep=" ", timespec="minutes"),
                incident_detection=detection_time.isoformat(sep=" ", timespec="minutes"),
                regions=" ".join(regions),
                ingest_impacted=ingest_impacted,
                notifications_impact=notifications_impacted,
                owner=owner,
                slack_channel_name=self.incident.channel_name,
                slack_channel_id=self.incident.channel_id,
                detection_source=detection_source
            )
        except NameError as exc:
            raise RuntimeError(
                f"Incident id: {self.incident_id} - Failed to format GitHub issue body. Unknown macro: {exc}"
            )
        try:
            self.issue = self.api.repo.create_issue(title, body=body, labels=template.labels)
            logger.debug("%s: incident: %s issue: %s", self.__class__.__name__, self.incident_id, self.issue)
        except Exception as exc:
            raise RuntimeError(f"{self.__class__.__name__}: repo.create_issue raised: '{exc}")
        try:
            db_update_incident_rca_col(channel_id=self.incident.channel_id, rca=self.issue.html_url)
            logger.debug("%s: incident: %s db_update succeeded", self.__class__.__name__, self.incident_id)
        except Exception as exc:
            raise RuntimeError(f"{self.__class__.__name__}: db_update_incident_rca_col raised: '{exc}")
        logger.debug("%s", self)

    @property
    def incident_id(self) -> Optional[str]:
        if self.incident:
            return self.incident.incident_id
        else:
            return None

    @property
    def title(self) -> str:
        return self.issue.title

    @property
    def number(self) -> str:
        return self.issue.number

    @property
    def link(self) -> str:
        return self.issue.html_url

    @property
    def repository(self):
        return self.issue.repository.full_name

    def __repr__(self):
        attrs = ",".join([f"{k}={v}" for k, v in self.__dict__.items() if not hasattr(v, "__dict__")])
        return f"{self.__class__.__name__}(incident_id={self.incident_id},{attrs})"
