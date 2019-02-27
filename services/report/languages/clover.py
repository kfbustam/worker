from timestring import Date

from covreports.helpers.yaml import walk
from covreports.resources import Report, ReportFile
from covreports.utils.tuples import ReportLine


def get_end_of_file(filename, xmlfile):
    """
    php reports have shown to include
    exrta coverage data that extend
    past the source code line count
    """
    if filename.endswith('.php'):
        for metrics in xmlfile.getiterator('metrics'):
            try:
                return int(metrics.attrib['loc'])
            except:
                pass


def from_xml(xml, fix, ignored_lines, sessionid, yaml):
    if walk(yaml, ('codecov', 'max_report_age'), '12h ago'):
        try:
            timestamp = xml.getiterator('coverage').next().get('generated')
            if '-' in timestamp:
                t = timestamp.split('-')
                timestamp = t[1]+'-'+t[0]+'-'+t[2]
            if timestamp and Date(timestamp) < walk(yaml, ('codecov', 'max_report_age'), '12h ago'):
                # report expired over 12 hours ago
                raise AssertionError('Clover report expired %s' % timestamp)

        except AssertionError:
            raise

        except:
            pass

    files = {}
    for f in xml.getiterator('file'):
        filename = f.attrib.get('path') or f.attrib['name']

        # skip empty file documents
        if (
            '{' in filename or
            ('/vendor/' in ('/'+filename) and filename.endswith('.php')) or
            f.find('line') is None
        ):
            continue

        if filename not in files:
            files[filename] = ReportFile(filename)

        _file = files[filename]

        # fix extra lines
        eof = get_end_of_file(filename, f)

        # process coverage
        for line in f.getiterator('line'):
            attribs = line.attrib
            ln = int(attribs['num'])
            complexity = None

            # skip line
            if ln < 1 or (eof and ln > eof):
                continue

            # [typescript] https://github.com/gotwarlost/istanbul/blob/89e338fcb1c8a7dea3b9e8f851aa55de2bc3abee/lib/report/clover.js#L108-L110
            if attribs['type'] == 'cond':
                _type = 'b'
                t, f = int(attribs['truecount']), int(attribs['falsecount'])
                if t == f == 0:
                    coverage = '0/2'
                elif t == 0 or f == 0:
                    coverage = '1/2'
                else:
                    coverage = '2/2'

            elif attribs['type'] == 'method':
                coverage = int(attribs.get('count') or 0)
                _type = 'm'
                complexity = int(attribs.get('complexity') or 0)
                # <line num="44" type="method" name="doRun" visibility="public" complexity="5" crap="5.20" count="1"/>

            else:
                coverage = int(attribs.get('count') or 0)
                _type = None

            # add line to report
            _file[ln] = ReportLine(coverage=coverage,
                                   type=_type,
                                   sessions=[[sessionid, coverage, None, None, complexity]],
                                   complexity=complexity)

    report = Report()
    map(report.append, files.values())
    report.resolve_paths([(f, fix(f)) for f in files.keys()])
    report.ignore_lines(ignored_lines)

    return report
