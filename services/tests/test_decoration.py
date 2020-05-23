import os
import pytest

from celery_config import new_user_activated_task_name
from database.tests.factories import (
    CommitFactory,
    OwnerFactory,
    PullFactory,
    RepositoryFactory,
)
from services.decoration import Decoration, get_decoration_type_and_reason
from services.repository import EnrichedPull


@pytest.fixture
def enriched_pull(dbsession):
    repository = RepositoryFactory.create(
        owner__username="codecov",
        owner__unencrypted_oauth_token="testtlxuu2kfef3km1fbecdlmnb2nvpikvmoadi3",
        owner__plan="users-pr-inappm",
        name="example-python",
        image_token="abcdefghij",
        private=True,
    )
    dbsession.add(repository)
    dbsession.flush()
    base_commit = CommitFactory.create(repository=repository)
    head_commit = CommitFactory.create(repository=repository)
    pull = PullFactory.create(
        repository=repository,
        base=base_commit.commitid,
        head=head_commit.commitid,
        state="merged",
    )
    dbsession.add(base_commit)
    dbsession.add(head_commit)
    dbsession.add(pull)
    dbsession.flush()
    provider_pull = {
        "author": {"id": "7123", "username": "tomcat"},
        "base": {
            "branch": "master",
            "commitid": "b92edba44fdd29fcc506317cc3ddeae1a723dd08",
        },
        "head": {
            "branch": "reason/some-testing",
            "commitid": "a06aef4356ca35b34c5486269585288489e578db",
        },
        "number": "1",
        "id": "1",
        "state": "open",
        "title": "Creating new code for reasons no one knows",
    }
    return EnrichedPull(database_pull=pull, provider_pull=provider_pull)


@pytest.fixture
def gitlab_root_group(dbsession):
    root_group = OwnerFactory.create(
        username="root_group",
        service="gitlab",
        unencrypted_oauth_token="testtlxuu2kfef3km1fbecdlmnb2nvpikvmoadi3",
        plan="users-pr-inappm",
        plan_activated_users=[],
    )
    dbsession.add(root_group)
    dbsession.flush()
    return root_group


@pytest.fixture
def gitlab_enriched_pull_subgroup(dbsession, gitlab_root_group):
    subgroup = OwnerFactory.create(
        username="subgroup",
        service="gitlab",
        unencrypted_oauth_token="testtlxuu2kfef3km1fbecdlmnb2nvpikvmoadi3",
        plan=None,
        parent_service_id=gitlab_root_group.service_id,
    )
    dbsession.add(subgroup)
    dbsession.flush()

    repository = RepositoryFactory.create(
        owner=subgroup, name="example-python", image_token="abcdefghij", private=True,
    )
    dbsession.add(repository)
    dbsession.flush()
    base_commit = CommitFactory.create(repository=repository)
    head_commit = CommitFactory.create(repository=repository)
    pull = PullFactory.create(
        repository=repository,
        base=base_commit.commitid,
        head=head_commit.commitid,
        state="merged",
    )
    dbsession.add(base_commit)
    dbsession.add(head_commit)
    dbsession.add(pull)
    dbsession.flush()
    provider_pull = {
        "author": {"id": "7123", "username": "tomcat"},
        "base": {
            "branch": "master",
            "commitid": "b92edba44fdd29fcc506317cc3ddeae1a723dd08",
        },
        "head": {
            "branch": "reason/some-testing",
            "commitid": "a06aef4356ca35b34c5486269585288489e578db",
        },
        "number": "1",
        "id": "1",
        "state": "open",
        "title": "Creating new code for reasons no one knows",
    }
    return EnrichedPull(database_pull=pull, provider_pull=provider_pull)


@pytest.fixture
def gitlab_enriched_pull_root(dbsession, gitlab_root_group):
    repository = RepositoryFactory.create(
        owner=gitlab_root_group,
        name="example-python",
        image_token="abcdefghij",
        private=True,
    )
    dbsession.add(repository)
    dbsession.flush()
    base_commit = CommitFactory.create(repository=repository)
    head_commit = CommitFactory.create(repository=repository)
    pull = PullFactory.create(
        repository=repository,
        base=base_commit.commitid,
        head=head_commit.commitid,
        state="merged",
    )
    dbsession.add(base_commit)
    dbsession.add(head_commit)
    dbsession.add(pull)
    dbsession.flush()
    provider_pull = {
        "author": {"id": "7123", "username": "tomcat"},
        "base": {
            "branch": "master",
            "commitid": "b92edba44fdd29fcc506317cc3ddeae1a723dd08",
        },
        "head": {
            "branch": "reason/some-testing",
            "commitid": "a06aef4356ca35b34c5486269585288489e578db",
        },
        "number": "1",
        "id": "1",
        "state": "open",
        "title": "Creating new code for reasons no one knows",
    }
    return EnrichedPull(database_pull=pull, provider_pull=provider_pull)


class TestDecorationServiceTestCase(object):
    def test_get_decoration_type_no_pull(self, mocker):
        decoration_type, reason = get_decoration_type_and_reason(None)

        assert decoration_type == Decoration.standard
        assert reason == "No pull"

    def test_get_decoration_type_no_provider_pull(self, mocker, enriched_pull):
        enriched_pull.provider_pull = None

        decoration_type, reason = get_decoration_type_and_reason(enriched_pull)

        assert decoration_type == Decoration.standard
        assert reason == "Can't determine PR author - no pull info from provider"

    def test_get_decoration_type_public_repo(self, dbsession, mocker, enriched_pull):
        enriched_pull.database_pull.repository.private = False
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(enriched_pull)

        assert decoration_type == Decoration.standard
        assert reason == "Public repo"

    def test_get_decoration_type_not_pr_plan(self, dbsession, mocker, enriched_pull):
        enriched_pull.database_pull.repository.owner.plan = "users-inappm"
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(enriched_pull)

        assert decoration_type == Decoration.standard
        assert reason == "Org not on PR plan"

    def test_get_decoration_type_pr_author_not_in_db(self, mocker, enriched_pull):
        enriched_pull.provider_pull["author"]["id"] = "190"

        decoration_type, reason = get_decoration_type_and_reason(enriched_pull)

        assert decoration_type == Decoration.upgrade
        assert reason == "PR author not found in database"

    def test_get_decoration_type_pr_author_auto_activate_success(
        self, dbsession, mocker, enriched_pull, with_sql_functions
    ):
        mocked_send_task = mocker.patch(
            "services.decoration.celery_app.send_task", return_value=False
        )

        enriched_pull.database_pull.repository.owner.plan_user_count = 10
        enriched_pull.database_pull.repository.owner.plan_activated_users = []
        enriched_pull.database_pull.repository.owner.plan_auto_activate = True

        pr_author = OwnerFactory.create(
            username=enriched_pull.provider_pull["author"]["username"],
            service_id=enriched_pull.provider_pull["author"]["id"],
        )
        dbsession.add(pr_author)
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(enriched_pull)
        dbsession.commit()

        assert mocked_send_task.call_count == 1
        mocked_send_task.assert_called_with(
            new_user_activated_task_name,
            args=None,
            kwargs=dict(
                org_ownerid=enriched_pull.database_pull.repository.owner.ownerid,
                user_ownerid=pr_author.ownerid,
            ),
        )
        assert decoration_type == Decoration.standard
        assert reason == "PR author auto activation success"
        assert enriched_pull.database_pull.repository.owner.plan_activated_users == [
            pr_author.ownerid
        ]

    def test_get_decoration_type_pr_author_auto_activate_failure(
        self, dbsession, mocker, enriched_pull, with_sql_functions
    ):
        # already at max user count
        existing_activated_users = [1234, 5678, 9012]
        enriched_pull.database_pull.repository.owner.plan_user_count = 3
        enriched_pull.database_pull.repository.owner.plan_activated_users = (
            existing_activated_users
        )
        enriched_pull.database_pull.repository.owner.plan_auto_activate = True

        pr_author = OwnerFactory.create(
            username=enriched_pull.provider_pull["author"]["username"],
            service_id=enriched_pull.provider_pull["author"]["id"],
        )
        dbsession.add(pr_author)
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(enriched_pull)
        dbsession.commit()

        assert decoration_type == Decoration.upgrade
        assert reason == "PR author auto activation failed"
        assert (
            pr_author.ownerid
            not in enriched_pull.database_pull.repository.owner.plan_activated_users
        )
        assert (
            enriched_pull.database_pull.repository.owner.plan_activated_users
            == existing_activated_users
        )

    def test_get_decoration_type_pr_author_manual_activation_required(
        self, dbsession, mocker, enriched_pull, with_sql_functions
    ):
        enriched_pull.database_pull.repository.owner.plan_user_count = 3
        enriched_pull.database_pull.repository.owner.plan_activated_users = []
        enriched_pull.database_pull.repository.owner.plan_auto_activate = False

        pr_author = OwnerFactory.create(
            username=enriched_pull.provider_pull["author"]["username"],
            service_id=enriched_pull.provider_pull["author"]["id"],
        )
        dbsession.add(pr_author)
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(enriched_pull)
        dbsession.commit()

        assert decoration_type == Decoration.upgrade
        assert reason == "User must be manually activated"
        assert (
            pr_author.ownerid
            not in enriched_pull.database_pull.repository.owner.plan_activated_users
        )

    def test_get_decoration_type_pr_author_already_active(
        self, dbsession, mocker, enriched_pull
    ):
        pr_author = OwnerFactory.create(
            username=enriched_pull.provider_pull["author"]["username"],
            service_id=enriched_pull.provider_pull["author"]["id"],
        )
        dbsession.add(pr_author)
        dbsession.flush()
        enriched_pull.database_pull.repository.owner.plan_user_count = 3
        enriched_pull.database_pull.repository.owner.plan_activated_users = [
            pr_author.ownerid
        ]
        enriched_pull.database_pull.repository.owner.plan_auto_activate = False
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(enriched_pull)
        dbsession.commit()

        assert decoration_type == Decoration.standard
        assert reason == "User is currently activated"


class TestDecorationServiceGitLabTestCase(object):
    def test_get_decoration_type_not_pr_plan_gitlab_subgroup(
        self,
        dbsession,
        mocker,
        gitlab_root_group,
        gitlab_enriched_pull_subgroup,
        with_sql_functions,
    ):
        gitlab_root_group.plan = "users-inappm"
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(
            gitlab_enriched_pull_subgroup
        )

        assert decoration_type == Decoration.standard
        assert reason == "Org not on PR plan"

    def test_get_decoration_type_pr_author_not_in_db_gitlab_subgroup(
        self,
        mocker,
        gitlab_root_group,
        gitlab_enriched_pull_subgroup,
        with_sql_functions,
    ):
        gitlab_enriched_pull_subgroup.provider_pull["author"]["id"] = "190"

        decoration_type, reason = get_decoration_type_and_reason(
            gitlab_enriched_pull_subgroup
        )

        assert decoration_type == Decoration.upgrade
        assert reason == "PR author not found in database"

    def test_get_decoration_type_pr_author_auto_activate_success_gitlab_root(
        self,
        dbsession,
        mocker,
        gitlab_root_group,
        gitlab_enriched_pull_root,
        with_sql_functions,
    ):
        mocked_send_task = mocker.patch(
            "services.decoration.celery_app.send_task", return_value=False
        )

        gitlab_root_group.plan_user_count = 10
        gitlab_root_group.plan_activated_users = []
        gitlab_root_group.plan_auto_activate = True

        pr_author = OwnerFactory.create(
            username=gitlab_enriched_pull_root.provider_pull["author"]["username"],
            service="gitlab",
            service_id=gitlab_enriched_pull_root.provider_pull["author"]["id"],
        )
        dbsession.add(pr_author)
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(
            gitlab_enriched_pull_root
        )
        dbsession.commit()

        assert mocked_send_task.call_count == 1
        mocked_send_task.assert_called_with(
            new_user_activated_task_name,
            args=None,
            kwargs=dict(
                org_ownerid=gitlab_enriched_pull_root.database_pull.repository.owner.ownerid,
                user_ownerid=pr_author.ownerid,
            ),
        )
        assert decoration_type == Decoration.standard
        assert reason == "PR author auto activation success"
        assert gitlab_root_group.plan_activated_users == [pr_author.ownerid]

    def test_get_decoration_type_pr_author_auto_activate_success_gitlab_subgroup(
        self,
        dbsession,
        mocker,
        gitlab_root_group,
        gitlab_enriched_pull_subgroup,
        with_sql_functions,
    ):
        mocked_send_task = mocker.patch(
            "services.decoration.celery_app.send_task", return_value=False
        )

        gitlab_root_group.plan_user_count = 10
        gitlab_root_group.plan_activated_users = []
        gitlab_root_group.plan_auto_activate = True

        pr_author = OwnerFactory.create(
            username=gitlab_enriched_pull_subgroup.provider_pull["author"]["username"],
            service="gitlab",
            service_id=gitlab_enriched_pull_subgroup.provider_pull["author"]["id"],
        )
        dbsession.add(pr_author)
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(
            gitlab_enriched_pull_subgroup
        )
        dbsession.commit()

        assert mocked_send_task.call_count == 1
        mocked_send_task.assert_called_with(
            new_user_activated_task_name,
            args=None,
            kwargs=dict(
                org_ownerid=gitlab_enriched_pull_subgroup.database_pull.repository.owner.ownerid,
                user_ownerid=pr_author.ownerid,
            ),
        )
        assert decoration_type == Decoration.standard
        assert reason == "PR author auto activation success"
        assert gitlab_root_group.plan_activated_users == [pr_author.ownerid]

    def test_get_decoration_type_pr_author_auto_activate_failure_gitlab_subgroup(
        self,
        dbsession,
        mocker,
        gitlab_root_group,
        gitlab_enriched_pull_subgroup,
        with_sql_functions,
    ):
        # already at max user count
        existing_activated_users = [1234, 5678, 9012]
        gitlab_root_group.plan_user_count = 3
        gitlab_root_group.plan_activated_users = existing_activated_users
        gitlab_root_group.plan_auto_activate = True

        pr_author = OwnerFactory.create(
            username=gitlab_enriched_pull_subgroup.provider_pull["author"]["username"],
            service="gitlab",
            service_id=gitlab_enriched_pull_subgroup.provider_pull["author"]["id"],
        )
        dbsession.add(pr_author)
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(
            gitlab_enriched_pull_subgroup
        )
        dbsession.commit()

        assert decoration_type == Decoration.upgrade
        assert reason == "PR author auto activation failed"
        assert pr_author.ownerid not in gitlab_root_group.plan_activated_users
        assert gitlab_root_group.plan_activated_users == existing_activated_users
        # shouldn't be in subgroup plan_activated_users either
        assert (
            pr_author.ownerid
            not in gitlab_enriched_pull_subgroup.database_pull.repository.owner.plan_activated_users
        )

    def test_get_decoration_type_pr_author_manual_activation_required_gitlab_subgroup(
        self,
        dbsession,
        mocker,
        gitlab_root_group,
        gitlab_enriched_pull_subgroup,
        with_sql_functions,
    ):
        gitlab_root_group.plan_user_count = 3
        gitlab_root_group.plan_activated_users = []
        gitlab_root_group.plan_auto_activate = False

        pr_author = OwnerFactory.create(
            username=gitlab_enriched_pull_subgroup.provider_pull["author"]["username"],
            service="gitlab",
            service_id=gitlab_enriched_pull_subgroup.provider_pull["author"]["id"],
        )
        dbsession.add(pr_author)
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(
            gitlab_enriched_pull_subgroup
        )
        dbsession.commit()

        assert decoration_type == Decoration.upgrade
        assert reason == "User must be manually activated"
        assert pr_author.ownerid not in gitlab_root_group.plan_activated_users
        # shouldn't be in subgroup plan_activated_users either
        assert (
            pr_author.ownerid
            not in gitlab_enriched_pull_subgroup.database_pull.repository.owner.plan_activated_users
        )

    def test_get_decoration_type_pr_author_already_active_subgroup(
        self,
        dbsession,
        mocker,
        gitlab_root_group,
        gitlab_enriched_pull_subgroup,
        with_sql_functions,
    ):
        pr_author = OwnerFactory.create(
            username=gitlab_enriched_pull_subgroup.provider_pull["author"]["username"],
            service="gitlab",
            service_id=gitlab_enriched_pull_subgroup.provider_pull["author"]["id"],
        )
        dbsession.add(pr_author)
        dbsession.flush()
        gitlab_root_group.plan_user_count = 3
        gitlab_root_group.plan_activated_users = [pr_author.ownerid]
        gitlab_root_group.plan_auto_activate = False
        dbsession.flush()

        decoration_type, reason = get_decoration_type_and_reason(
            gitlab_enriched_pull_subgroup
        )
        dbsession.commit()

        assert decoration_type == Decoration.standard
        assert reason == "User is currently activated"
