import re
from services.notification.changes import get_changes
from services.urls import get_pull_url, get_commit_url
from itertools import starmap
from base64 import b64encode
from collections import namedtuple
from services.yaml.reader import read_yaml_field, round_number, get_minimum_precision
from shared.helpers.yaml import walk
from shared.reports.resources import Report, ReportTotals
from decimal import Decimal
from services.urls import get_pull_graph_url
from typing import Sequence, List
from services.notification.changes import Change

null = namedtuple("_", ["totals"])(None)
zero_change_regex = re.compile("0.0+%?")


class MessageMixin(object):
    def create_message(self, comparison, diff, pull_dict, message_type="comment"):
        changes = get_changes(comparison.base.report, comparison.head.report, diff)
        base_report = comparison.base.report
        head_report = comparison.head.report
        pull = comparison.pull
        if message_type == "checks":
            settings = read_yaml_field(self.current_yaml, ("comment",))
        else:
            settings = self.notifier_yaml_settings

        yaml = self.current_yaml
        current_yaml = self.current_yaml

        links = {
            "pull": get_pull_url(pull),
            "base": get_commit_url(comparison.base.commit)
            if comparison.base.commit is not None
            else None,
        }

        # flags
        base_flags = base_report.flags if base_report else {}
        head_flags = head_report.flags if head_report else {}
        missing_flags = set(base_flags.keys()) - set(head_flags.keys())
        flags = []
        for name, flag in head_flags.items():
            flags.append(
                {
                    "name": name,
                    "before": base_flags.get(name, null).totals,
                    "after": flag.totals,
                    "diff": flag.apply_diff(diff) if walk(diff, ("files",)) else None,
                }
            )

        for flag in missing_flags:
            flags.append(
                {"name": flag, "before": base_flags[flag], "after": None, "diff": None}
            )

        # bool: show complexity
        if read_yaml_field(self.current_yaml, ("codecov", "ui", "hide_complexity")):
            show_complexity = False
        else:
            show_complexity = bool(
                (base_report.totals if base_report else ReportTotals()).complexity
                or (head_report.totals if head_report else ReportTotals()).complexity
            )

        # table layout
        table_header = (
            "| Coverage \u0394 |"
            + (" Complexity \u0394 |" if show_complexity else "")
            + " |"
        )
        table_layout = "|---|---|---|" + ("---|" if show_complexity else "")

        change = (
            Decimal(head_report.totals.coverage) - Decimal(base_report.totals.coverage)
            if base_report and head_report
            else Decimal(0)
        )
        if base_report and head_report:
            message_internal = "> Merging [#{pull}]({links[pull]}?src=pr&el=desc) into [{base}]({links[base]}&el=desc) will **{message}** coverage{coverage}.".format(
                pull=pull.pullid,
                base=pull_dict["base"]["branch"],
                # ternary operator, see https://stackoverflow.com/questions/394809/does-python-have-a-ternary-conditional-operator
                message={False: "decrease", "na": "not change", True: "increase"}[
                    (change > 0) if change != 0 else "na"
                ],
                coverage={
                    True: " by `{0}%`".format(round_number(yaml, abs(change))),
                    False: "",
                }[(change != 0)],
                links=links,
            )
        else:
            message_internal = "> :exclamation: No coverage uploaded for pull request {what} (`{branch}@{commit}`). [Click here to learn what that means](https://docs.codecov.io/docs/error-reference#section-missing-{what}-commit).".format(
                what="base" if not base_report else "head",
                branch=pull_dict["base" if not base_report else "head"]["branch"],
                commit=pull_dict["base" if not base_report else "head"]["commitid"][:7],
            )
        diff_totals = head_report.apply_diff(diff)
        message = [
            f'# [Codecov]({links["pull"]}?src=pr&el=h1) Report',
            message_internal,
            (
                "> The diff coverage is `{0}%`.".format(
                    round_number(yaml, Decimal(diff_totals.coverage))
                )
                if diff_totals and diff_totals.coverage is not None
                else "> The diff coverage is `n/a`."
            ),
            "",
        ]
        write = message.append

        if base_report is None:
            base_report = Report()

        if head_report:

            def make_metrics(before, after, relative):
                coverage_good = None
                icon = " |"
                if after is None:
                    # e.g. missing flags
                    coverage = " `?` |"
                    complexity = " `?` |" if show_complexity else ""

                elif after is False:
                    # e.g. file deleted
                    coverage = " |"
                    complexity = " |" if show_complexity else ""

                else:
                    if type(before) is list:
                        before = ReportTotals(*before)
                    if type(after) is list:
                        after = ReportTotals(*after)

                    layout = " `{absolute} <{relative}> ({impact})` |"

                    coverage_change = (
                        (float(after.coverage) - float(before.coverage))
                        if before
                        else None
                    )
                    coverage_good = (coverage_change > 0) if before else None
                    coverage = layout.format(
                        absolute=format_number_to_str(
                            yaml, after.coverage, style="{0}%"
                        ),
                        relative=format_number_to_str(
                            yaml,
                            relative.coverage if relative else 0,
                            style="{0}%",
                            if_null="\xF8",
                        ),
                        impact=format_number_to_str(
                            yaml,
                            coverage_change,
                            style="{0}%",
                            if_zero="\xF8",
                            if_null="\xF8",
                            plus=True,
                        )
                        if before
                        else "?"
                        if before is None
                        else "\xF8",
                    )

                    if show_complexity:
                        is_string = isinstance(
                            relative.complexity if relative else "", str
                        )
                        style = "{0}%" if is_string else "{0}"
                        complexity_change = (
                            Decimal(after.complexity) - Decimal(before.complexity)
                            if before
                            else None
                        )
                        complexity_good = (complexity_change < 0) if before else None
                        complexity = layout.format(
                            absolute=style.format(
                                format_number_to_str(yaml, after.complexity)
                            ),
                            relative=style.format(
                                format_number_to_str(
                                    yaml,
                                    relative.complexity if relative else 0,
                                    if_null="\xF8",
                                )
                            ),
                            impact=style.format(
                                format_number_to_str(
                                    yaml,
                                    complexity_change,
                                    if_zero="\xF8",
                                    if_null="\xF8",
                                    plus=True,
                                )
                                if before
                                else "?"
                            ),
                        )

                        show_up_arrow = coverage_good and complexity_good
                        show_down_arrow = (
                            coverage_good is False and coverage_change != 0
                        ) and (complexity_good is False and complexity_change != 0)
                        icon = (
                            " :arrow_up: |"
                            if show_up_arrow
                            else " :arrow_down: |"
                            if show_down_arrow
                            else " |"
                        )

                    else:
                        complexity = ""
                        icon = (
                            " :arrow_up: |"
                            if coverage_good
                            else " :arrow_down: |"
                            if coverage_good is False and coverage_change != 0
                            else " |"
                        )

                return "".join(("|", coverage, complexity, icon))

            # loop through layouts
            for layout in map(
                lambda l: l.strip(), (settings["layout"] or "").split(",")
            ):
                if layout.startswith("flag") and flags:
                    write("| Flag " + table_header)
                    write(table_layout)
                    for flag in sorted(flags, key=lambda f: f["name"]):
                        write(
                            "| #{name} {metrics}".format(
                                name=flag["name"],
                                metrics=make_metrics(
                                    flag["before"], flag["after"], flag["diff"]
                                ),
                            )
                        )

                elif layout == "diff":
                    write("```diff")
                    lines = diff_to_string(
                        current_yaml,
                        pull_dict["base"][
                            "branch"
                        ],  # important because base may be null
                        base_report.totals if base_report else None,
                        "#%s" % pull.pullid,
                        head_report.totals,
                    )
                    for l in lines:
                        write(l)
                    write("```")

                elif layout.startswith(("files", "tree")):

                    # create list of files changed in diff
                    files_in_diff = [
                        (
                            _diff["type"],
                            path,
                            make_metrics(
                                base_report.get(path, null).totals or False,
                                head_report.get(path, null).totals or False,
                                _diff["totals"],
                            ),
                            Decimal(_diff["totals"].coverage)
                            if _diff["totals"].coverage is not None
                            else None,
                        )
                        for path, _diff in (diff["files"] if diff else {}).items()
                        if _diff.get("totals")
                    ]

                    if files_in_diff or changes:
                        # add table headers
                        write(
                            "| [Impacted Files]({0}?src=pr&el=tree) {1}".format(
                                links["pull"], table_header
                            )
                        )
                        write(table_layout)

                        # get limit of results to show
                        limit = int(layout.split(":")[1] if ":" in layout else 10)
                        mentioned = []

                        def tree_cell(typ, path, metrics, _=None):
                            if path not in mentioned:
                                # mentioned: for files that are in diff and changes
                                mentioned.append(path)
                                return "| {rm}[{path}]({compare}/diff?src=pr&el=tree#diff-{hash}){rm} {metrics}".format(
                                    rm="~~" if typ == "deleted" else "",
                                    path=escape_markdown(ellipsis(path, 50, False)),
                                    compare=links["pull"],
                                    hash=b64encode(path.encode()).decode(),
                                    metrics=metrics,
                                )

                        # add to comment
                        for line in starmap(
                            tree_cell,
                            sorted(files_in_diff, key=lambda a: a[3] or Decimal("0"))[
                                :limit
                            ],
                        ):
                            write(line)

                        # reduce limit
                        limit = limit - len(files_in_diff)

                        # append changes
                        if limit > 0 and changes:
                            most_important_changes = sort_by_importance(changes)[:limit]
                            for change in most_important_changes:
                                celled = tree_cell(
                                    "changed",
                                    change.path,
                                    make_metrics(
                                        base_report.get(change.path, null).totals
                                        or False,
                                        head_report.get(change.path, null).totals
                                        or False,
                                        None,
                                    ),
                                )
                                write(celled)

                        remaining = len(changes or []) - limit
                        if remaining > 0:
                            write(
                                "| ... and [{n} more]({href}/diff?src=pr&el=tree-more) | |".format(
                                    n=remaining, href=links["pull"]
                                )
                            )

                elif layout == "reach":
                    write(
                        "[![Impacted file tree graph]({})]({}?src=pr&el=tree)".format(
                            get_pull_graph_url(
                                pull,
                                "tree.svg",
                                width=650,
                                height=150,
                                src="pr",
                                token=pull.repository.image_token,
                            ),
                            links["pull"],
                        )
                    )

                elif layout == "footer":
                    write("------")
                    write("")
                    write(
                        "[Continue to review full report at Codecov]({0}?src=pr&el=continue).".format(
                            links["pull"]
                        )
                    )
                    write(
                        "> **Legend** - [Click here to learn more](https://docs.codecov.io/docs/codecov-delta)"
                    )
                    write(
                        "> `\u0394 = absolute <relative> (impact)`, `\xF8 = not affected`, `? = missing data`"
                    )
                    write(
                        "> Powered by [Codecov]({pull}?src=pr&el=footer). Last update [{base}...{head}]({pull}?src=pr&el=lastupdated). Read the [comment docs]({comment}).".format(
                            pull=links["pull"],
                            base=pull_dict["base"]["commitid"][:7],
                            head=pull_dict["head"]["commitid"][:7],
                            comment="https://docs.codecov.io/docs/pull-request-comments",
                        )
                    )

                write("")  # nl at end of each layout

        return [m for m in message if m is not None]


def format_number_to_str(
    yml, value, if_zero=None, if_null=None, plus=False, style="{0}"
) -> str:
    if value is None:
        return if_null
    precision = get_minimum_precision(yml)
    value = Decimal(value)
    res = round_number(yml, value)

    if if_zero and value == 0:
        return if_zero

    if res == 0 and value != 0:
        # <.01
        return style.format(
            "%s<%s"
            % ("+" if plus and value > 0 else "" if value > 0 else "-", precision)
        )

    if plus and res > Decimal("0"):
        res = "+" + str(res)
    return style.format(res)


def add_plus_sign(value: str) -> str:
    if value in ("", "0", "0%") or zero_change_regex.fullmatch(value):
        return ""
    elif value[0] != "-":
        return "+%s" % value
    else:
        return value


def list_to_text_table(rows, padding=0) -> List[str]:
    """
    Assumes align left.

    list_to_text_table(
      [
          ('|##', 'master|', 'stable|', '+/-|', '##|'),
          ('+', '1|', '2|', '+1', ''),
      ], 2) == ['##   master   stable   +/-   ##',
                '+         1        2    +1     ']

    """
    # (2, 6, 6, 3, 2)
    column_w = list(
        map(
            max,
            zip(*map(lambda row: map(lambda cell: len(cell.strip("|")), row), rows)),
        )
    )

    def _fill(a):
        w, cell = a
        return "{text:{fill}{align}{width}}".format(
            text=cell.strip("|"),
            fill=" ",
            align=(("^" if cell[:1] == "|" else ">") if cell[-1:] == "|" else "<"),
            width=w,
        )

    # now they are filled with spaces
    spacing = (" " * padding).join
    return list(map(lambda row: spacing(map(_fill, zip(column_w, row))), rows))


def diff_to_string(current_yaml, base_title, base, head_title, head) -> List[str]:
    """
    ('master', {},
     'stable', {},
     ('ui', before, after), ...})
    """

    def F(value):
        if value is None:
            return "?"
        elif isinstance(value, str):
            return "%s%%" % round_number(current_yaml, Decimal(value))
        else:
            return value

    def _row(title, c1, c2, plus="+", minus="-", neutral=" "):
        if c1 == c2 == 0:
            return ("", "", "", "", "")
        else:
            # TODO if coverage format to smallest string or precision
            if c1 is None or c2 is None:
                change = ""
            elif isinstance(c2, str):
                change = F(str(float(c2) - float(c1)))
            else:
                change = str(c2 - c1)
            change_is_zero = change in ("0", "0%", "") or zero_change_regex.fullmatch(
                change
            )
            sign = neutral if change_is_zero else plus if change[0] != "-" else minus
            return (
                "%s %s" % (sign, title),
                "%s|" % F(c1),
                "%s|" % F(c2),
                "%s|" % add_plus_sign(change),
                "",
            )

    c = int(isinstance(base.complexity, str)) if base else 0
    # create a spaced table with data
    table = list_to_text_table(
        [
            ("|##", "%s|" % base_title, "%s|" % head_title, "+/-|", "##|"),
            _row("Coverage", base.coverage if base else None, head.coverage, "+", "-"),
            _row(
                "Complexity",
                base.complexity if base else None,
                head.complexity,
                "-+"[c],
                "+-"[c],
            ),
            _row("Files", base.files if base else None, head.files, " ", " "),
            _row("Lines", base.lines if base else None, head.lines, " ", " "),
            _row("Branches", base.branches if base else None, head.branches, " ", " "),
            _row("Hits", base.hits if base else None, head.hits, "+", "-"),
            _row("Misses", base.misses if base else None, head.misses, "-", "+"),
            _row("Partials", base.partials if base else None, head.partials, "-", "+"),
        ],
        3,
    )
    row_w = len(table[0])

    spacer = ["=" * row_w]

    title = "@@%s@@" % "{text:{fill}{align}{width}}".format(
        text="Coverage Diff", fill=" ", align="^", width=row_w - 4, strip=True
    )

    table = (
        [title, table[0]]
        + spacer
        + table[1:3]
        + spacer  # coverage, complexity
        + table[3:6]
        + spacer  # files, lines, branches
        + table[6:9]  # hits, misses, partials
    )

    # no complexity included
    if head.complexity in (None, 0):
        table.pop(4)

    return "\n".join(filter(lambda row: row.strip(" "), table)).strip("=").split("\n")


def sort_by_importance(changes: Sequence[Change]) -> List[Change]:
    return sorted(
        changes or [],
        key=lambda c: (float((c.totals or ReportTotals()).coverage), c.new, c.deleted),
    )


def ellipsis(text, length, cut_from="left") -> str:
    if cut_from == "right":
        return (text[:length] + "...") if len(text) > length else text
    elif cut_from is None:
        return (
            (text[: (length / 2)] + "..." + text[(length / -2) :])
            if len(text) > length
            else text
        )
    else:
        return ("..." + text[len(text) - length :]) if len(text) > length else text


def escape_markdown(value: str) -> str:
    return value.replace("`", "\\`").replace("*", "\\*").replace("_", "\\_")