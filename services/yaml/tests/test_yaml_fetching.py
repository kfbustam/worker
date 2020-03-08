from asyncio import Future

import pytest

from tests.base import BaseTestCase
from database.tests.factories import CommitFactory
from services.yaml.fetcher import determine_commit_yaml_location, fetch_commit_yaml_from_provider


sample_yaml = """
codecov:
  notify:
    require_ci_to_pass: yes
"""


class TestYamlSavingService(BaseTestCase):

    @pytest.mark.asyncio
    async def test_determine_commit_yaml_location(self, mocker):
        mocked_result = [
            {'name': '.gitignore', 'path': '.gitignore', 'type': 'file'},
            {'name': '.travis.yml', 'path': '.travis.yml', 'type': 'file'},
            {'name': 'README.rst', 'path': 'README.rst', 'type': 'file'},
            {'name': 'awesome', 'path': 'awesome', 'type': 'folder'},
            {'name': 'codecov', 'path': 'codecov', 'type': 'file'},
            {'name': 'codecov.yaml', 'path': 'codecov.yaml', 'type': 'file'},
            {'name': 'tests', 'path': 'tests', 'type': 'folder'}
        ]
        f = Future()
        f.set_result(mocked_result)
        valid_handler = mocker.MagicMock(
            list_top_level_files=mocker.MagicMock(
                return_value=f
            )
        )
        commit = CommitFactory.create()
        res = await determine_commit_yaml_location(commit, valid_handler)
        assert res == 'codecov.yaml'

    @pytest.mark.asyncio
    async def test_determine_commit_yaml_nested_folder(self, mocker):
        mocked_result = [
            {'name': ".gitignore", "path": ".gitignore", "type": "file"},
            {"name": ".travis.yml", "path": ".travis.yml", "type": "file"},
            {"name": "README.rst", "path": "README.rst", "type": "file"},
            {"name": ".github", "path": ".github", "type": "folder"},
            {"name": "codecov", "path": "codecov", "type": "file"},
            {"name": "tests", "path": "tests", "type": "folder"}
        ]
        files_inside_folder = [
            {"name": "code.py", "path": ".github/code.py", "type": "file"},
            {"name": "__init__.py", "path": ".github/__init__.py", "type": "file"},
            {"name": "anotha_folder", "path": ".github/anotha_folder", "type": "folder"},
            {"name": "codecov", "path": ".github/codecov", "type": "folder"},
            {"name": "codecov.yaml", "path": ".github/codecov.yaml", "type": "file"},
        ]
        f = Future()
        list_file_future = Future()
        f.set_result(mocked_result)
        list_file_future.set_result(files_inside_folder)
        valid_handler = mocker.MagicMock(
            list_top_level_files=mocker.MagicMock(
                return_value=f
            ),
            list_files=mocker.MagicMock(
                return_value=list_file_future
            )
        )
        commit = CommitFactory.create()
        res = await determine_commit_yaml_location(commit, valid_handler)
        assert res == ".github/codecov.yaml"

    @pytest.mark.asyncio
    async def test_determine_commit_yaml_location_multiple(self, mocker):
        mocked_result = [
            {'name': 'READMEs', 'path': 'README.rst', 'type': 'folder'},
            {'name': 'codecov.yml', 'path': 'codecov.yml', 'type': 'file'},
            {'name': '.codecov.yml', 'path': '.codecov.yml', 'type': 'file'},
            {'name': 'codecov.yaml', 'path': 'codecov.yaml', 'type': 'file'},
            {'name': 'tests', 'path': 'tests', 'type': 'folder'}
        ]
        f = Future()
        f.set_result(mocked_result)
        valid_handler = mocker.MagicMock(
            list_top_level_files=mocker.MagicMock(
                return_value=f
            )
        )
        commit = CommitFactory.create()
        res = await determine_commit_yaml_location(commit, valid_handler)
        assert res == 'codecov.yml'

    @pytest.mark.asyncio
    async def test_fetch_commit_yaml_from_provider(self, mocker):
        mocked_list_files_result = [
            {'name': '.gitignore', 'path': '.gitignore', 'type': 'file'},
            {'name': '.travis.yml', 'path': '.travis.yml', 'type': 'file'},
            {'name': 'README.rst', 'path': 'README.rst', 'type': 'file'},
            {'name': 'awesome', 'path': 'awesome', 'type': 'folder'},
            {'name': 'codecov', 'path': 'codecov', 'type': 'file'},
            {'name': 'codecov.yaml', 'path': 'codecov.yaml', 'type': 'file'},
            {'name': 'tests', 'path': 'tests', 'type': 'folder'}
        ]
        list_files_future = Future()
        list_files_future.set_result(mocked_list_files_result)
        contents_result = {
            "content": sample_yaml
        }
        contents_result_future = Future()
        contents_result_future.set_result(contents_result)
        valid_handler = mocker.MagicMock(
            list_top_level_files=mocker.MagicMock(
                return_value=list_files_future
            ),
            get_source=mocker.MagicMock(
                return_value=contents_result_future
            ),
        )
        commit = CommitFactory.create()
        res = await fetch_commit_yaml_from_provider(commit, valid_handler)
        assert res == {'codecov': {'notify': {}, 'require_ci_to_pass': True}}
        valid_handler.list_top_level_files.assert_called_with(commit.commitid)
        valid_handler.get_source.assert_called_with('codecov.yaml', commit.commitid)
