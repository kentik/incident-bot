import config
import logging

from github import Github, Repository

logger = logging.getLogger("github")


class GithubApi:
    def __init__(self):
        self.github = Github(
            config.github_api_key,
            base_url=config.active.integrations.get("github").get("api_url", "https://api.github.com"),
        )
        self.repo = None

    @property
    def api(self) -> Github:
        return self.github

    @property
    def repo(self) -> Repository:
        if not self.repo:
            try:
                _repo_name = config.active.integrations.get("github").get("repository")
                self.repo = self.github.get_repo(_repo_name)
            except Exception as error:
                logger.error("Error retrieving Github repository '%s': '%s'", _repo_name, error)
        return self.repo

    def test(self) -> bool:
        return self.repo != 0
