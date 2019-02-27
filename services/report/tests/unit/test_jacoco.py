import json
from time import time
from ddt import ddt, data
import xml.etree.cElementTree as etree

from tests.base import TestCase
from app.tasks.reports.languages import jacoco


xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.0//EN" "report.dtd">
<report name="JaCoCo Maven plug-in example for Java project">
    <sessioninfo id="Steves-MBP.local-b048b758" start="%s" dump="1411925088117" />
    <package name="base">
        <class name="base/source">
          <method name="&lt;init&gt;" line="1">
            <counter type="INSTRUCTION" missed="54" covered="0" />
            <counter type="BRANCH" missed="4" covered="0" />
            <counter type="LINE" missed="2" covered="0" />
            <counter type="COMPLEXITY" missed="3" covered="1" />
            <counter type="METHOD" missed="1" covered="0" />
          </method>
          <method name="ignore"></method>
          <method name="ignore$" line="2">
            <counter type="INSTRUCTION" missed="60" covered="22" />
            <counter type="BRANCH" missed="3" covered="3" />
            <counter type="LINE" missed="0" covered="5" />
            <counter type="COMPLEXITY" missed="3" covered="1" />
            <counter type="METHOD" missed="0" covered="1" />
          </method>
        </class>
        <sourcefile name="source.java">
            <line nr="1" mi="99" ci="99" mb="0" cb="2" />
            <line nr="2" mi="0" ci="2" mb="1" cb="1" />
            <line nr="3" mi="1" ci="0" mb="0" cb="0" />
            <line nr="4" mi="0" ci="2" mb="0" cb="0" />
        </sourcefile>
        <sourcefile name="file.java">
            <line nr="1" mi="0" ci="1" mb="0" cb="0" />
        </sourcefile>
        <sourcefile name="ignore">
            <line nr="1" mi="0" ci="1" mb="0" cb="0" />
        </sourcefile>
        <sourcefile name="empty">
        </sourcefile>
    </package>
</report>
'''

result = {
    "files": {
        "base/file.java": {
            "l": {
                "1": {
                    "c": 1,
                    "s": [[0, 1, None, None, None]]
                }
            }
        },
        "base/source.java": {
            "l": {
                "1": {
                    "c": "2/2",
                    "t": "m",
                    "C": [1, 4],
                    "s": [[0, "2/2", None, None, [1, 4]]]
                },
                "3": {
                    "c": 0,
                    "s": [[0, 0, None, None, None]]
                },
                "2": {
                    "c": "1/2",
                    "t": "m",
                    "C": [1, 4],
                    "s": [[0, "1/2", None, None, [1, 4]]]
                },
                "4": {
                    "c": 2,
                    "s": [[0, 2, None, None, None]]
                }
            }
        }
    }
}


@ddt
class Test(TestCase):
    def test_report(self):
        def fixes(path):
            if path == 'base/ignore':
                return None
            assert path in ('base/source.java', 'base/file.java', 'base/empty')
            return path

        report = jacoco.from_xml(etree.fromstring(xml % int(time())), fixes, {}, 0, None)
        report = self.v3_to_v2(report)
        print json.dumps(report, indent=2)
        self.validate.report(report)
        assert result == report

    @data(('a', 'module_a/package/file'),
          ('b', 'module_b/src/main/java/package/file'),)
    def test_multi_module(self, (module, path)):
        data = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
        <!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.0//EN" "report.dtd">
        <report name="module_%s">
            <package name="package">
                <sourcefile name="file">
                    <line nr="1" mi="0" ci="2" mb="0" cb="0" />
                </sourcefile>
            </package>
        </report>''' % module

        def fixes(path):
            if module == 'a':
                return path if 'src/main/java' not in path else None
            else:
                return path if 'src/main/java' in path else None

        report = jacoco.from_xml(etree.fromstring(data), fixes, {}, 0, None)
        report = self.v3_to_v2(report)
        assert [path] == report['files'].keys()

    @data((int(time()) - 172800), '01-01-2014')
    def test_expired(self, date):
        with self.assertRaisesRegexp(AssertionError, 'Jacoco report expired'):
            jacoco.from_xml(etree.fromstring(xml % date), None, {}, 0, None)
