import config

from typing import List, Type, TypeVar
from dataclasses import dataclass, field
from github import Github, Repository

logger = config.log.get_logger("github.api")


GithubConfigType = TypeVar("GithubConfigType", bound="GithubConfig")


@dataclass
class GithubConfig:
    api_url: str = ""
    repo: str = ""
    template_path: str = ""

    @classmethod
    def create(cls: Type[GithubConfigType]) -> GithubConfigType:
        gh = config.active.integrations.get("github")
        if not gh:
            logger.error("%s.create: No GitHub config found", cls.__class__)
            return cls()
        cfg = GithubConfig(
            api_url=gh.get("api_url", "https://api.github.com"),
            repo=gh.get("repository"),
            template_path=gh.get("issue_template")
        )
        logger.debug("%s.create:%s", cls.__class__, cfg)
        return cfg


class GithubApi:
    def __init__(self):
        self.config = GithubConfig.create()
        self.github = Github(
            config.github_api_key,
            base_url=self.config.api_url,
        )
        logger.debug("%s: github: %s", self.__class__.__name__, self.github)
        self._repo = None

    @property
    def api(self) -> Github:
        return self.github

    @property
    def repo(self) -> Repository:
        if not self._repo:
            try:
                self._repo = self.github.get_repo(self.config.repo)
            except Exception as error:
                logger.error("%s: Error retrieving GitHub repository '%s': '%s'",
                             self.__class__.__name__,
                             self.config.repo,
                             error)
        logger.debug("%s: repo: %s", self.__class__.__name__, self._repo)
        return self._repo

    def test(self) -> bool:
        return self.repo is not None
