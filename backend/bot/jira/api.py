import config

from atlassian import Jira

logger = config.log.get_logger("jira")


class JiraApi:
    def __init__(self):
        self.jira = Jira(
            url=config.atlassian_api_url,
            username=config.atlassian_api_username,
            password=config.atlassian_api_token,
            cloud=True,
        )

    @property
    def api(self) -> Jira:
        return self.jira

    def test(self) -> bool:
        try:
            return self.jira.get_project(
                config.active.integrations.get("atlassian")
                .get("jira")
                .get("project")
            ).get("id")
        except Exception as error:
            logger.error(f"Error authenticating to Jira: {error}")
            logger.error(f"Please check Jira configuration and try again.")
