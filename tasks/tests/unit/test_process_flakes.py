import datetime as dt
from collections import defaultdict

import time_machine
from shared.django_apps.core.tests.factories import CommitFactory, RepositoryFactory
from shared.django_apps.reports.models import DailyTestRollup, Flake, TestInstance
from shared.django_apps.reports.tests.factories import (
    FlakeFactory,
    TestFactory,
    TestInstanceFactory,
)

from tasks.process_flakes import (
    ProcessFlakesTask,
    generate_flake_dict,
    get_test_instances,
    update_passed_flakes,
    upsert_failed_flake,
)


class RepoSimulator:
    def __init__(self):
        self.repo = RepositoryFactory()
        self.repo.save()
        self.test_count = 0
        self.branch_number = 0

        self.test_map = defaultdict(lambda: TestFactory(id=self.test_count))

    def create_commit(self):
        c = CommitFactory(
            repository=self.repo, merged=False, branch=str(self.branch_number)
        )
        c.save()
        self.branch_number += 1
        self.test_count = 0
        return c

    def merge(self, c):
        c.merged = True
        c.branch = self.repo.branch
        c.save()
        self.test_count = 0

    def add_test_instance(self, c, outcome=TestInstance.Outcome.PASS.value):
        ti = TestInstanceFactory(
            commitid=c.commitid,
            repoid=self.repo.repoid,
            branch=c.branch,
            outcome=outcome,
            test=self.test_map[self.test_count],
        )
        ti.save()

        rollup, _ = DailyTestRollup.objects.get_or_create(
            repoid=self.repo.repoid,
            date=dt.date.today(),
            test=self.test_map[self.test_count],
            branch=c.branch,
            defaults={
                "pass_count": 0,
                "skip_count": 0,
                "fail_count": 0,
                "flaky_fail_count": 0,
                "avg_duration_seconds": 0.0,
                "last_duration_seconds": 0.0,
                "latest_run": dt.datetime.now(tz=dt.timezone.utc),
                "commits_where_fail": [],
            },
        )

        match outcome:
            case TestInstance.Outcome.PASS.value:
                rollup.pass_count += 1
            case TestInstance.Outcome.SKIP.value:
                rollup.skip_count += 1
            case _:
                rollup.fail_count += 1

                s = set(rollup.commits_where_fail)
                s.add(c.commitid)
                rollup.commits_where_fail = list(s)

                flake = Flake.objects.filter(
                    repository_id=self.repo.repoid,
                    test=self.test_map[self.test_count],
                ).first()

                if flake:
                    rollup.flaky_fail_count += 1

        rollup.save()

        self.test_count += 1

        return ti

    def reset(self):
        self.repo = RepositoryFactory()
        self.repo.save()
        self.test_count = 0


def test_generate_flake_dict(transactional_db):
    repo = RepositoryFactory()

    flake_dict = generate_flake_dict(repo.repoid)

    assert len(flake_dict) == 0

    f = FlakeFactory(repository=repo, test__id="id", reduced_error__id=10)
    f.save()

    flake_dict = generate_flake_dict(repo.repoid)

    assert len(flake_dict) == 1
    assert ("id", 10) in flake_dict


def test_get_test_instances_when_test_is_flaky(transactional_db):
    repo = RepositoryFactory()
    commit = CommitFactory()

    ti = TestInstanceFactory(
        commitid=commit.commitid,
        repoid=repo.repoid,
        branch="main",
        outcome=TestInstance.Outcome.FAILURE.value,
    )
    ti.save()

    tis = get_test_instances(
        commit.commitid, repo.repoid, "main", flaky_tests=[ti.test_id]
    )
    assert len(tis) == 1
    assert tis[0].commitid


def test_get_test_instances_when_instance_is_failure(transactional_db):
    repo = RepositoryFactory()
    commit = CommitFactory()

    ti = TestInstanceFactory(
        commitid=commit.commitid,
        repoid=repo.repoid,
        branch="main",
        outcome=TestInstance.Outcome.FAILURE.value,
    )
    ti.save()

    tis = get_test_instances(commit.commitid, repo.repoid, "main", flaky_tests=[])
    assert len(tis) == 1
    assert tis[0].commitid


def test_get_test_instances_when_test_is_flaky_and_instance_is_skip(transactional_db):
    repo = RepositoryFactory()
    commit = CommitFactory()

    ti = TestInstanceFactory(
        commitid=commit.commitid,
        repoid=repo.repoid,
        branch="main",
        outcome=TestInstance.Outcome.SKIP.value,
    )
    ti.save()

    tis = get_test_instances(
        commit.commitid, repo.repoid, "main", flaky_tests=[ti.test_id]
    )
    assert len(tis) == 0


def test_get_test_instances_when_instance_is_pass(transactional_db):
    repo = RepositoryFactory()
    commit = CommitFactory()

    ti = TestInstanceFactory(
        commitid=commit.commitid,
        repoid=repo.repoid,
        branch="main",
        outcome=TestInstance.Outcome.PASS.value,
    )
    ti.save()

    tis = get_test_instances(commit.commitid, repo.repoid, "main", flaky_tests=[])
    assert len(tis) == 0


def test_update_passed_flakes(transactional_db):
    rs = RepoSimulator()
    c = rs.create_commit()
    ti = rs.add_test_instance(c, outcome=TestInstance.Outcome.FAILURE.value)

    f = FlakeFactory(test=ti.test, repository=rs.repo)
    f.save()
    assert f.count == 0
    assert f.recent_passes_count == 0

    update_passed_flakes(ti, f)

    assert f.count == 1
    assert f.recent_passes_count == 1


def test_upsert_failed_flakes(transactional_db):
    repo = RepositoryFactory()
    repo.save()
    commit = CommitFactory()
    commit.save()
    ti = TestInstanceFactory(
        commitid=commit.commitid, repoid=repo.repoid, branch="main"
    )
    ti.save()
    test = TestFactory()
    test.save()
    f = FlakeFactory()
    f.save()

    upsert_failed_flake(ti, f, repo.repoid)


def test_it_does_not_detect_unmerged_tests(transactional_db):
    rs = RepoSimulator()
    c1 = rs.create_commit()

    rs.add_test_instance(c1)

    rs.add_test_instance(c1)

    ProcessFlakesTask().run_impl(
        None, repo_id=rs.repo.repoid, commit_id_list=[c1.commitid], branch=c1.branch
    )

    assert len(Flake.objects.all()) == 0


def test_it_handles_only_passes(transactional_db):
    rs = RepoSimulator()
    c1 = rs.create_commit()

    rs.add_test_instance(c1)

    rs.add_test_instance(c1)

    rs.merge(c1)

    ProcessFlakesTask().run_impl(
        None, repo_id=rs.repo.repoid, commit_id_list=[c1.commitid], branch=c1.branch
    )

    assert len(Flake.objects.all()) == 0


@time_machine.travel(dt.datetime.now(tz=dt.UTC), tick=False)
def test_it_creates_flakes_from_orig_branch(transactional_db):
    rs = RepoSimulator()
    c1 = rs.create_commit()
    orig_branch = c1.branch
    rs.add_test_instance(c1)
    rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)
    rs.merge(c1)
    rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)

    ProcessFlakesTask().run_impl(
        None, repo_id=rs.repo.repoid, commit_id_list=[c1.commitid], branch=orig_branch
    )

    assert len(Flake.objects.all()) == 1
    assert Flake.objects.first().count == 1
    assert Flake.objects.first().fail_count == 1
    assert Flake.objects.first().start_date == dt.datetime.now(tz=dt.UTC)


@time_machine.travel(dt.datetime.now(tz=dt.UTC), tick=False)
def test_it_creates_flakes_from_new_branch_only(transactional_db):
    rs = RepoSimulator()
    c1 = rs.create_commit()
    orig_branch = c1.branch
    rs.add_test_instance(c1)
    rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)
    rs.merge(c1)
    rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)

    ProcessFlakesTask().run_impl(
        None, repo_id=rs.repo.repoid, commit_id_list=[c1.commitid], branch=c1.branch
    )

    assert len(Flake.objects.all()) == 1
    assert Flake.objects.first().count == 1
    assert Flake.objects.first().fail_count == 1
    assert Flake.objects.first().start_date == dt.datetime.now(dt.UTC)


@time_machine.travel(dt.datetime.now(tz=dt.UTC), tick=False)
def test_it_creates_flakes_fail_after_merge(transactional_db):
    rs = RepoSimulator()
    c1 = rs.create_commit()

    rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)
    rs.merge(c1)

    rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)

    ProcessFlakesTask().run_impl(
        None, repo_id=rs.repo.repoid, commit_id_list=[c1.commitid], branch=c1.branch
    )

    assert len(Flake.objects.all()) == 1
    flake = Flake.objects.first()
    assert flake.recent_passes_count == 0
    assert flake.count == 1
    assert flake.fail_count == 1
    assert flake.start_date == dt.datetime.now(dt.UTC)

    ProcessFlakesTask().run_impl(
        None, repo_id=rs.repo.repoid, commit_id_list=[c1.commitid], branch=c1.branch
    )

    assert len(Flake.objects.all()) == 1
    flake = Flake.objects.first()
    assert flake.recent_passes_count == 0
    assert flake.count == 2
    assert flake.fail_count == 2
    assert flake.start_date == dt.datetime.now(dt.UTC)


@time_machine.travel(dt.datetime.now(tz=dt.UTC), tick=False)
def test_it_processes_two_commits_together(transactional_db):
    rs = RepoSimulator()
    c1 = rs.create_commit()
    rs.merge(c1)
    rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)

    c2 = rs.create_commit()
    rs.merge(c2)
    rs.add_test_instance(c2, outcome=TestInstance.Outcome.FAILURE.value)

    ProcessFlakesTask().run_impl(
        None,
        repo_id=rs.repo.repoid,
        commit_id_list=[c1.commitid, c2.commitid],
        branch=c1.branch,
    )

    assert len(Flake.objects.all()) == 1
    flake = Flake.objects.first()
    assert flake.recent_passes_count == 0
    assert flake.count == 2
    assert flake.fail_count == 2
    assert flake.start_date == dt.datetime.now(dt.UTC)


@time_machine.travel(dt.datetime.now(tz=dt.UTC), tick=False)
def test_it_processes_two_commits_separately(transactional_db):
    rs = RepoSimulator()
    c1 = rs.create_commit()
    rs.merge(c1)
    rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)

    ProcessFlakesTask().run_impl(
        None,
        repo_id=rs.repo.repoid,
        commit_id_list=[c1.commitid],
        branch=c1.branch,
    )

    c2 = rs.create_commit()
    rs.merge(c2)
    rs.add_test_instance(c2, outcome=TestInstance.Outcome.FAILURE.value)

    ProcessFlakesTask().run_impl(
        None,
        repo_id=rs.repo.repoid,
        commit_id_list=[c2.commitid],
        branch=c2.branch,
    )

    assert len(Flake.objects.all()) == 1
    flake = Flake.objects.first()
    assert flake.recent_passes_count == 0
    assert flake.count == 2
    assert flake.fail_count == 2
    assert flake.start_date == dt.datetime.now(dt.UTC)


def test_it_creates_flakes_expires(transactional_db):
    with time_machine.travel(dt.datetime.now(tz=dt.UTC), tick=False) as traveller:
        rs = RepoSimulator()
        commits = []
        c1 = rs.create_commit()
        rs.merge(c1)
        rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)

        ProcessFlakesTask().run_impl(
            None,
            repo_id=rs.repo.repoid,
            commit_id_list=[c1.commitid],
            branch=rs.repo.branch,
        )

        old_time = dt.datetime.now(dt.UTC)
        traveller.shift(dt.timedelta(seconds=100))
        new_time = dt.datetime.now(dt.UTC)

        for _ in range(0, 29):
            c = rs.create_commit()
            rs.merge(c)
            rs.add_test_instance(c, outcome=TestInstance.Outcome.PASS.value)
            commits.append(c.commitid)

        ProcessFlakesTask().run_impl(
            None, repo_id=rs.repo.repoid, commit_id_list=commits, branch=rs.repo.branch
        )

        assert len(Flake.objects.all()) == 1
        flake = Flake.objects.first()
        assert flake.recent_passes_count == 29
        assert flake.count == 30
        assert flake.fail_count == 1
        assert flake.start_date == old_time
        assert flake.end_date is None

        c = rs.create_commit()
        rs.merge(c)
        rs.add_test_instance(c, outcome=TestInstance.Outcome.PASS.value)

        ProcessFlakesTask().run_impl(
            None,
            repo_id=rs.repo.repoid,
            commit_id_list=[c.commitid],
            branch=rs.repo.branch,
        )

        assert len(Flake.objects.all()) == 1
        flake = Flake.objects.first()
        assert flake.recent_passes_count == 30
        assert flake.count == 31
        assert flake.fail_count == 1
        assert flake.start_date == old_time
        assert flake.end_date == new_time


def test_it_creates_rollups(transactional_db):
    with time_machine.travel("1970-1-1T00:00:00Z"):
        rs = RepoSimulator()
        commits = []
        c1 = rs.create_commit()
        rs.merge(c1)
        rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)
        rs.add_test_instance(c1, outcome=TestInstance.Outcome.FAILURE.value)

        ProcessFlakesTask().run_impl(
            None,
            repo_id=rs.repo.repoid,
            commit_id_list=[c1.commitid],
            branch=rs.repo.branch,
        )

    with time_machine.travel("1970-1-2T00:00:00Z"):
        c2 = rs.create_commit()
        rs.merge(c2)
        rs.add_test_instance(c2, outcome=TestInstance.Outcome.FAILURE.value)
        rs.add_test_instance(c2, outcome=TestInstance.Outcome.FAILURE.value)

        ProcessFlakesTask().run_impl(
            None,
            repo_id=rs.repo.repoid,
            commit_id_list=[c2.commitid],
            branch=rs.repo.branch,
        )

        rollups = DailyTestRollup.objects.all().order_by("date")

        assert len(rollups) == 4

        assert rollups[0].fail_count == 1
        assert rollups[0].flaky_fail_count == 1
        assert rollups[0].date == dt.date.today() - dt.timedelta(days=1)

        assert rollups[1].fail_count == 1
        assert rollups[1].flaky_fail_count == 1
        assert rollups[1].date == dt.date.today() - dt.timedelta(days=1)

        assert rollups[2].fail_count == 1
        assert rollups[2].flaky_fail_count == 1
        assert rollups[2].date == dt.date.today()

        assert rollups[3].fail_count == 1
        assert rollups[3].flaky_fail_count == 1
        assert rollups[3].date == dt.date.today()
