from shared.reports.resources import LineSession, ReportFile, ReportLine
from shared.reports.types import CoverageDatapoint

from services.report.report_builder import (
    CoverageType,
    ReportBuilder,
    SpecialLabelsEnum,
)


def test_report_builder_simple_fields(mocker):
    current_yaml, sessionid, ignored_lines, path_fixer = (
        mocker.MagicMock(),
        mocker.MagicMock(),
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    builder = ReportBuilder(current_yaml, sessionid, ignored_lines, path_fixer)
    assert builder.repo_yaml == current_yaml


def test_report_builder_generate_session(mocker):
    current_yaml, sessionid, ignored_lines, path_fixer = (
        mocker.MagicMock(),
        mocker.MagicMock(),
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    filepath = "filepath"
    builder = ReportBuilder(current_yaml, sessionid, ignored_lines, path_fixer)
    builder_session = builder.create_report_builder_session(filepath)
    assert builder_session.file_class == ReportFile
    assert builder_session.path_fixer == path_fixer
    assert builder_session.sessionid == sessionid
    assert builder_session.current_yaml == current_yaml
    assert builder_session.ignored_lines == ignored_lines


def test_report_builder_session(mocker):
    current_yaml, sessionid, ignored_lines, path_fixer = (
        {"beta_groups": ["labels"]},
        mocker.MagicMock(),
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    filepath = "filepath"
    builder = ReportBuilder(current_yaml, sessionid, ignored_lines, path_fixer)
    builder_session = builder.create_report_builder_session(filepath)
    first_file = ReportFile("filename.py")
    first_file.append(2, ReportLine.create(coverage=0))
    first_file.append(
        3,
        ReportLine.create(
            coverage=0,
            datapoints=[
                CoverageDatapoint(
                    sessionid=0,
                    coverage=1,
                    coverage_type=None,
                    labels=[SpecialLabelsEnum.CODECOV_ALL_LABELS_PLACEHOLDER],
                )
            ],
        ),
    )
    first_file.append(
        10,
        ReportLine.create(
            coverage=1,
            type=None,
            sessions=[
                (
                    LineSession(
                        id=0,
                        coverage=1,
                    )
                )
            ],
            datapoints=[
                CoverageDatapoint(
                    sessionid=0,
                    coverage=1,
                    coverage_type=None,
                    labels=["some_label", "other"],
                )
            ],
            complexity=None,
        ),
    )
    builder_session.append(first_file)
    final_report = builder_session.output_report()
    assert final_report.files == ["filename.py"]
    assert sorted(final_report.get("filename.py").lines) == [
        (
            2,
            ReportLine.create(
                coverage=0, type=None, sessions=None, datapoints=None, complexity=None
            ),
        ),
        (
            3,
            ReportLine.create(
                coverage=0,
                type=None,
                sessions=None,
                datapoints=[
                    CoverageDatapoint(
                        sessionid=0, coverage=1, coverage_type=None, labels=["other"]
                    ),
                    CoverageDatapoint(
                        sessionid=0,
                        coverage=1,
                        coverage_type=None,
                        labels=["some_label"],
                    ),
                ],
                complexity=None,
            ),
        ),
        (
            10,
            ReportLine.create(
                coverage=1,
                type=None,
                sessions=[
                    LineSession(
                        id=0, coverage=1, branches=None, partials=None, complexity=None
                    )
                ],
                datapoints=[
                    CoverageDatapoint(
                        sessionid=0,
                        coverage=1,
                        coverage_type=None,
                        labels=["some_label", "other"],
                    )
                ],
                complexity=None,
            ),
        ),
    ]


def test_report_builder_session_create_line(mocker):
    current_yaml, sessionid, ignored_lines, path_fixer = (
        {"beta_groups": ["labels"]},
        45,
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    filepath = "filepath"
    builder = ReportBuilder(current_yaml, sessionid, ignored_lines, path_fixer)
    builder_session = builder.create_report_builder_session(filepath)
    line = builder_session.create_coverage_line(
        "filename.py", 1, coverage_type=CoverageType.branch
    )
    assert line == ReportLine.create(
        coverage=1,
        type="b",
        sessions=[
            LineSession(
                id=45, coverage=1, branches=None, partials=None, complexity=None
            )
        ],
        datapoints=[
            CoverageDatapoint(sessionid=45, coverage=1, coverage_type="b", labels=None)
        ],
        complexity=None,
    )