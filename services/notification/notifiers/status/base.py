import logging
from contextlib import nullcontext

from shared.torngit.exceptions import TorngitClientError, TorngitError
from shared.analytics_tracking import track_event

from helpers.match import match
from helpers.environment import is_enterprise
from services.notification.notifiers.base import (
    AbstractBaseNotifier,
    Comparison,
    NotificationResult,
)
from services.repository import get_repo_provider_service
from services.urls import get_commit_url, get_compare_url
from services.yaml.reader import get_paths_from_flags
from typing import Dict


log = logging.getLogger(__name__)


class StatusNotifier(AbstractBaseNotifier):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._repository_service = None

    def is_enabled(self) -> bool:
        return True

    def store_results(self, comparison: Comparison, result: NotificationResult) -> bool:
        pass

    @property
    def name(self):
        return f"status-{self.context}"

    async def build_payload(self, comparison) -> Dict[str, str]:
        raise NotImplementedError()

    def get_upgrade_message(self) -> str:
        # TODO: this is the message in the PR author billing spec but maybe we should add the actual username?
        return "Please activate this user to display a detailed status check"

    def can_we_set_this_status(self, comparison) -> bool:
        head = comparison.head.commit
        pull = comparison.pull
        if (
            self.notifier_yaml_settings.get("only_pulls")
            or self.notifier_yaml_settings.get("base") == "pr"
        ) and not pull:
            return False
        if not match(self.notifier_yaml_settings.get("branches"), head.branch):
            return False
        return True

    async def get_diff(self, comparison: Comparison):
        repository_service = self.repository_service
        head = comparison.head.commit
        base = comparison.base.commit
        if base is None:
            return None
        pull_diff = await repository_service.get_compare(
            base.commitid, head.commitid, with_commits=False
        )
        return pull_diff["diff"]

    @property
    def repository_service(self):
        if not self._repository_service:
            self._repository_service = get_repo_provider_service(self.repository)
        return self._repository_service

    def get_notifier_filters(self) -> dict:
        return dict(
            paths=set(
                get_paths_from_flags(
                    self.current_yaml, self.notifier_yaml_settings.get("flags")
                )
                + (self.notifier_yaml_settings.get("paths") or [])
            ),
            flags=self.notifier_yaml_settings.get("flags"),
        )

    async def notify(self, comparison: Comparison):
        payload = None
        if not self.can_we_set_this_status(comparison):
            return NotificationResult(
                notification_attempted=False,
                notification_successful=None,
                explanation="not_fit_criteria",
                data_sent=None,
            )
        _filters = self.get_notifier_filters()
        base_full_commit = comparison.base
        try:
            with comparison.head.report.filter(**_filters):
                with (
                    base_full_commit.report.filter(**_filters)
                    if comparison.has_base_report()
                    else nullcontext()
                ):
                    payload = await self.build_payload(comparison)
            if (
                comparison.pull
                and self.notifier_yaml_settings.get("base") in ("pr", "auto", None)
                and comparison.base.commit is not None
            ):
                payload["url"] = get_compare_url(
                    comparison.base.commit, comparison.head.commit
                )
            else:
                payload["url"] = get_commit_url(comparison.head.commit)
            return await self.send_notification(comparison, payload)
        except TorngitClientError:
            log.warning(
                "Unable to send status notification to user due to a client-side error",
                exc_info=True,
                extra=dict(
                    repoid=comparison.head.commit.repoid,
                    commit=comparison.head.commit.commitid,
                    notifier_name=self.name,
                ),
            )
            return NotificationResult(
                notification_attempted=True,
                notification_successful=False,
                explanation="client_side_error_provider",
                data_sent=payload,
            )
        except TorngitError:
            log.warning(
                "Unable to send status notification to user due to an unexpected error",
                exc_info=True,
                extra=dict(
                    repoid=comparison.head.commit.repoid,
                    commit=comparison.head.commit.commitid,
                    notifier_name=self.name,
                ),
            )
            return NotificationResult(
                notification_attempted=True,
                notification_successful=False,
                explanation="server_side_error_provider",
                data_sent=payload,
            )

    async def status_already_exists(
        self, comparison, title, state, description
    ) -> bool:
        head = comparison.head.commit
        repository_service = self.repository_service
        statuses = await repository_service.get_commit_statuses(head.commitid)
        if statuses:
            exists = statuses.get(title)
            return (
                exists
                and exists["state"] == state
                and exists["description"] == description
            )
        return False

    def get_status_external_name(self) -> str:
        status_piece = f"/{self.title}" if self.title != "default" else ""
        return f"codecov/{self.context}{status_piece}"

    async def send_notification(self, comparison: Comparison, payload):
        title = self.get_status_external_name()
        repository_service = self.repository_service
        head = comparison.head.commit
        head_report = comparison.head.report
        state = payload["state"]
        message = payload["message"]
        url = payload["url"]
        if not await self.status_already_exists(comparison, title, state, message):
            state = (
                "success" if self.notifier_yaml_settings.get("informational") else state
            )

            # Track state in analytics
            event_name = (
                "Coverage Report Passed"
                if state == "success"
                else "Coverage Report Failed"
            )
            track_event(
                self.repository.ownerid,
                event_name,
                {"state": state, "repository_id": self.repository.repoid},
                is_enterprise(),
            )

            notification_result_data_sent = {
                "title": title,
                "state": state,
                "message": message,
            }
            try:
                res = await repository_service.set_commit_status(
                    commit=head.commitid,
                    status=state,
                    context=title,
                    coverage=float(head_report.totals.coverage),
                    description=message,
                    url=url,
                )
            except TorngitClientError:
                log.warning(
                    "Status not posted because this user can see but not set statuses on this repo",
                    extra=dict(
                        data_sent=notification_result_data_sent,
                        commitid=comparison.head.commit.commitid,
                        repoid=comparison.head.commit.repoid,
                    ),
                )
                return NotificationResult(
                    notification_attempted=True,
                    notification_successful=False,
                    explanation="no_write_permission",
                    data_sent=notification_result_data_sent,
                    data_received=None,
                )
            return NotificationResult(
                notification_attempted=True,
                notification_successful=True,
                explanation=None,
                data_sent=notification_result_data_sent,
                data_received={"id": res.get("id", "NO_ID")},
            )
        else:
            log.info(
                "Status already set",
                extra=dict(context=title, description=message, state=state),
            )
            return NotificationResult(
                notification_attempted=False,
                notification_successful=None,
                explanation="already_done",
                data_sent={"title": title, "state": state, "message": message},
            )
