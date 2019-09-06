import logging
from datetime import datetime
import re

import torngit

from helpers.config import get_config, get_verify_ssl
from services.bots import get_repo_appropriate_bot_token
from database.models import Owner

log = logging.getLogger(__name__)

merged_pull = re.compile(r'.*Merged in [^\s]+ \(pull request \#(\d+)\).*').match


def get_repo_provider_service(repository, commit=None):
    _timeouts = [
        get_config('setup', 'http', 'timeouts', 'connect', default=15),
        get_config('setup', 'http', 'timeouts', 'receive', default=30)
    ]
    service = repository.owner.service
    token = get_repo_appropriate_bot_token(repository)
    adapter_params = dict(
        repo=dict(name=repository.name, using_integration=repository.using_integration or False),
        owner=dict(
            service_id=repository.service_id,
            ownerid=repository.ownerid,
            username=repository.owner.username
        ),
        token=token,
        verify_ssl=get_verify_ssl(service),
        timeouts=_timeouts
    )
    return _get_repo_provider_service_instance(repository.service, **adapter_params)


def _get_repo_provider_service_instance(service_name, **adapter_params):
    return torngit.get(
        service_name,
        **adapter_params
    )


async def update_commit_from_provider_info(repository_service, commit):
    """
        Takes the result from the torngit commit details, and updates the commit
        properties with it
    """
    db_session = commit.get_db_session()
    commitid = commit.commitid
    git_commit = await repository_service.get_commit(commitid)

    if git_commit is None:
        log.error(
            'Could not find commit on git provider',
            extra=dict(repoid=commit.repoid, commit=commit.commitid)
        )
    else:
        author_info = git_commit['author']
        commit_author = get_author_from_commit(
            db_session, repository_service.service, author_info['id'], author_info['username'],
            author_info['email'], author_info['name']
        )

        # attempt to populate commit.pullid from repository_service if we don't have it
        if not commit.pullid:
            commit.pullid = await repository_service.find_pull_request(
                commit=commitid,
                branch=commit.branch)

        # if our records or the call above returned a pullid, fetch it's details
        if commit.pullid:
            commit_updates = await repository_service.get_pull_request(
                pullid=commit.pullid
            )
            commit.branch = commit_updates['head']['branch']

        commit.message = git_commit['message']
        commit.parent = git_commit['parents'][0]
        commit.merged = False
        commit.author = commit_author
        commit.updatestamp = datetime.now()

        if repository_service.service == 'bitbucket':
            res = merged_pull(git_commit.message)
            if res:
                pullid = res.groups()[0]
                pullid = pullid
                commit.branch = (
                    await
                    repository_service.get_pull_request(pullid)
                )['base']['branch']
        log.info(
            'Updated commit with info from git provider',
            extra=dict(repoid=commit.repoid, commit=commit.commitid)
        )


def get_author_from_commit(db_session, service, author_id, username, email, name):
    author = db_session.query(Owner).filter_by(service_id=author_id, service=service).first()
    if author:
        return author
    author = Owner(
        service_id=author_id, service=service,
        username=username, name=name, email=email
    )
    db_session.add(author)
    return author


async def create_webhook_on_provider(repository_service):
    """
        Posts to the provider a webhook so we can receive updates from this
        repo
    """
    webhook_url = (
        get_config('setup', 'webhook_url') or get_config('setup', 'codecov_url')
    )
    WEBHOOK_EVENTS = {
        "github": [
            "pull_request", "delete", "push", "public", "status",
            "repository"
        ],
        "github_enterprise": [
            "pull_request", "delete", "push", "public", "status",
            "repository"
        ],
        "bitbucket": [
            "repo:push", "pullrequest:created", "pullrequest:updated",
            "pullrequest:fulfilled", "repo:commit_status_created",
            "repo:commit_status_updated"
        ],
        # https://confluence.atlassian.com/bitbucketserver/post-service-webhook-for-bitbucket-server-776640367.html
        "bitbucket_server": [],
        "gitlab": {
            "push_events": True,
            "issues_events": False,
            "merge_requests_events": True,
            "tag_push_events": False,
            "note_events": False,
            "job_events": False,
            "build_events": True,
            "pipeline_events": True,
            "wiki_events": False
        },
        "gitlab_enterprise": {
            "push_events": True,
            "issues_events": False,
            "merge_requests_events": True,
            "tag_push_events": False,
            "note_events": False,
            "job_events": False,
            "build_events": True,
            "pipeline_events": True,
            "wiki_events": False
        }
    }
    return await repository_service.post_webhook(
        f'Codecov Webhook. {webhook_url}',
        f'{webhook_url}/webhooks/{repository_service.service}',
        WEBHOOK_EVENTS[repository_service.service],
        get_config(
            repository_service.service, 'webhook_secret',
            default='ab164bf3f7d947f2a0681b215404873e')
        )
