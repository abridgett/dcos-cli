import base64
import contextlib
import json

import pkg_resources
import six
from dcos import subcommand

import pytest

from .common import (assert_command, assert_lines, delete_zk_node,
                     delete_zk_nodes, exec_command, file_bytes, file_json,
                     get_services, package_install, package_uninstall,
                     service_shutdown, wait_for_service, watch_all_deployments)


def setup_module(module):
    assert_command(
        ['dcos', 'package', 'repo', 'remove', '--repo-name=Universe'])
    repo = "https://github.com/mesosphere/universe/archive/cli-test-4.zip"
    assert_command(['dcos', 'package', 'repo', 'add', 'test4', repo])


def teardown_module(module):
    assert_command(
        ['dcos', 'package', 'repo', 'remove', '--repo-name=test4'])
    repo = "https://universe.mesosphere.com/repo"
    assert_command(['dcos', 'package', 'repo', 'add', 'Universe', repo])


@pytest.fixture(scope="module")
def zk_znode(request):
    request.addfinalizer(delete_zk_nodes)
    return request


def test_package():
    stdout = pkg_resources.resource_string(
        'tests',
        'data/help/package.txt')
    assert_command(['dcos', 'package', '--help'],
                   stdout=stdout)


def test_info():
    assert_command(['dcos', 'package', '--info'],
                   stdout=b'Install and manage DCOS packages\n')


def test_version():
    assert_command(['dcos', 'package', '--version'],
                   stdout=b'dcos-package version SNAPSHOT\n')


def test_repo_list():
    repo_list = b"""\
test4: https://github.com/mesosphere/universe/archive/cli-test-4.zip
"""
    assert_command(['dcos', 'package', 'repo', 'list'], stdout=repo_list)


def test_repo_add():
    repo = \
        "https://github.com/mesosphere/universe/archive/cli-test-3.zip"
    repo_list = b"""\
test4: https://github.com/mesosphere/universe/archive/cli-test-4.zip
test: https://github.com/mesosphere/universe/archive/cli-test-3.zip
"""
    args = ["test", repo]
    _repo_add(args, repo_list)


def test_repo_add_index():
    repo = \
        "https://github.com/mesosphere/universe/archive/cli-test-2.zip"
    repo_list = b"""\
test4: https://github.com/mesosphere/universe/archive/cli-test-4.zip
test2: https://github.com/mesosphere/universe/archive/cli-test-2.zip
test: https://github.com/mesosphere/universe/archive/cli-test-3.zip
"""
    args = ["test2", repo, '--index=1']
    _repo_add(args, repo_list)


def test_repo_remove_by_repo_name():
    repo_list = b"""\
test4: https://github.com/mesosphere/universe/archive/cli-test-4.zip
test2: https://github.com/mesosphere/universe/archive/cli-test-2.zip
"""
    _repo_remove(['--repo-name=test'], repo_list)


def test_repo_remove_by_package_repo():
    repo = \
        "https://github.com/mesosphere/universe/archive/cli-test-2.zip"
    repo_list = b"""\
test4: https://github.com/mesosphere/universe/archive/cli-test-4.zip
"""
    _repo_remove(['--repo-url={}'.format(repo)], repo_list)


def test_repo_empty():
    assert_command(
        ['dcos', 'package', 'repo', 'remove', '--repo-name=test4'])

    returncode, stdout, stderr = exec_command(
        ['dcos', 'package', 'repo', 'list'])
    stderr_msg = (b"There are currently no repos configured. "
                  b"Please use `dcos package repo add` to add a repo\n")
    assert returncode == 1
    assert stdout == b''
    assert stderr == stderr_msg

    repo = \
        "https://github.com/mesosphere/universe/archive/cli-test-4.zip"
    repo_list = b"""\
test4: https://github.com/mesosphere/universe/archive/cli-test-4.zip
"""
    _repo_add(["test4", repo], repo_list)


def test_describe_nonexistent():
    assert_command(['dcos', 'package', 'describe', 'xyzzy'],
                   stderr=b'Package [xyzzy] not found\n',
                   returncode=1)


def test_describe_nonexistent_version():
    stderr = b'Version [a.b.c] of package [marathon] not found\n'
    assert_command(['dcos', 'package', 'describe', 'marathon',
                    '--package-version=a.b.c'],
                   stderr=stderr,
                   returncode=1)


def test_describe():
    stdout = file_json(
        'tests/data/package/json/test_describe_marathon.json')

    returncode_, stdout_, stderr_ = exec_command(
        ['dcos', 'package', 'describe', 'marathon'])

    assert returncode_ == 0
    output = json.loads(stdout_.decode('utf-8'))
    assert _remove_nulls(output) == json.loads(stdout.decode('utf-8'))
    assert stderr_ == b''


def test_describe_cli():
    stdout = file_json(
        'tests/data/package/json/test_describe_cli_cassandra.json')
    assert_command(['dcos', 'package', 'describe', 'cassandra', '--cli'],
                   stdout=stdout)


def test_describe_app():
    stdout = file_bytes(
        'tests/data/package/json/test_describe_app_marathon.json')
    assert_command(['dcos', 'package', 'describe', 'marathon', '--app'],
                   stdout=stdout)


def test_describe_config():
    stdout = file_json(
        'tests/data/package/json/test_describe_marathon_config.json')
    assert_command(['dcos', 'package', 'describe', 'marathon', '--config'],
                   stdout=stdout)


def test_describe_render():
    # DCOS_PACKAGE_METADATA label will need to be changed after issue 431
    stdout = file_json(
        'tests/data/package/json/test_describe_marathon_app_render.json')
    stdout = json.loads(stdout.decode('utf-8'))
    expected_labels = stdout.pop("labels", None)

    returncode, stdout_, stderr = exec_command(
        ['dcos', 'package', 'describe', 'marathon', '--app', '--render'])

    stdout_ = json.loads(stdout_.decode('utf-8'))
    actual_labels = stdout_.pop("labels", None)

    for label, value in expected_labels.items():
        assert value == actual_labels.get(label)

    assert stdout == stdout_
    assert stderr == b''
    assert returncode == 0


def test_describe_package_version():
    stdout = file_json(
        'tests/data/package/json/test_describe_marathon_package_version.json')

    returncode_, stdout_, stderr_ = exec_command(
        ['dcos', 'package', 'describe', 'marathon',
            '--package-version=0.11.1'])

    assert returncode_ == 0
    output = json.loads(stdout_.decode('utf-8'))
    assert _remove_nulls(output) == json.loads(stdout.decode('utf-8'))
    assert stderr_ == b''


def test_describe_package_version_missing():
    stderr = b'Version [bogus] of package [marathon] not found\n'
    assert_command(
        ['dcos', 'package', 'describe', 'marathon', '--package-version=bogus'],
        returncode=1,
        stderr=stderr)


def test_describe_package_versions():
    stdout = file_bytes(
        'tests/data/package/json/test_describe_marathon_package_versions.json')
    assert_command(
        ['dcos', 'package', 'describe', 'marathon', '--package-versions'],
        stdout=stdout)


def test_describe_package_versions_others():
    stderr = (b'If --package-versions is provided, no other option can be '
              b'provided\n')
    assert_command(
        ['dcos', 'package', 'describe', 'marathon', '--package-versions',
         '--app'],
        returncode=1,
        stderr=stderr)


def test_describe_options():
    stdout = file_json(
        'tests/data/package/json/test_describe_app_options.json')
    stdout = json.loads(stdout.decode('utf-8'))
    expected_labels = stdout.pop("labels", None)

    returncode, stdout_, stderr = exec_command(
        ['dcos', 'package', 'describe', '--app', '--options',
         'tests/data/package/marathon.json', 'marathon'])

    stdout_ = json.loads(stdout_.decode('utf-8'))
    actual_labels = stdout_.pop("labels", None)

    for label, value in expected_labels.items():
        assert value == actual_labels.get(label)

    assert stdout == stdout_
    assert stderr == b''
    assert returncode == 0


def test_describe_app_cli():
    stdout = file_bytes(
        'tests/data/package/json/test_describe_app_cli.json')
    assert_command(
        ['dcos', 'package', 'describe', 'cassandra', '--app', '--cli'],
        stdout=stdout)


def test_describe_specific_version():
    stdout = file_bytes(
        'tests/data/package/json/test_describe_marathon_0.11.1.json')

    returncode_, stdout_, stderr_ = exec_command(
        ['dcos', 'package', 'describe', '--package-version=0.11.1',
         'marathon'])

    assert returncode_ == 0
    output = json.loads(stdout_.decode('utf-8'))
    assert _remove_nulls(output) == json.loads(stdout.decode('utf-8'))
    assert stderr_ == b''


def test_bad_install():
    args = ['--options=tests/data/package/chronos-bad.json', '--yes']
    stdout = b""
    stderr = """\
Please create a JSON file with the appropriate options, and pass the \
/path/to/file as an --options argument.
"""
    _install_bad_chronos(args=args,
                         stdout=stdout,
                         stderr=stderr)


def test_install(zk_znode):
    _install_chronos()
    watch_all_deployments()
    wait_for_service('chronos')
    _uninstall_chronos()
    watch_all_deployments()
    services = get_services(args=['--inactive'])
    assert len([service for service in services
                if service['name'] == 'chronos']) == 0


def test_bad_install_marathon_msg():
    stdout = (b'A sample pre-installation message\n'
              b'Installing Marathon app for package [helloworld] version '
              b'[0.1.0] with app id [/foo]\n'
              b'Installing CLI subcommand for package [helloworld] '
              b'version [0.1.0]\n'
              b'New command available: dcos helloworld\n'
              b'A sample post-installation message\n')

    _install_helloworld(['--yes', '--app-id=/foo'],
                        stdout=stdout)

    stdout2 = (b'A sample pre-installation message\n'
               b'Installing Marathon app for package [helloworld] version '
               b'[0.1.0] with app id [/foo/bar]\n')

    stderr = (b'Object is not valid\n'
              b'Groups and Applications may not have the same '
              b'identifier: /foo\n')

    _install_helloworld(['--yes', '--app-id=/foo/bar'],
                        stdout=stdout2,
                        stderr=stderr,
                        returncode=1)
    _uninstall_helloworld()


def test_install_missing_options_file():
    """Test that a missing options file results in the expected stderr
    message."""
    assert_command(
        ['dcos', 'package', 'install', 'chronos', '--yes',
         '--options=asdf.json'],
        returncode=1,
        stderr=b"Error opening file [asdf.json]: No such file or directory\n")


def test_install_specific_version():
    stdout = (b'We recommend a minimum of one node with at least 2 '
              b'CPU\'s and 1GB of RAM available for the Marathon Service.\n'
              b'Installing Marathon app for package [marathon] '
              b'version [0.11.1]\n'
              b'Marathon DCOS Service has been successfully installed!\n\n'
              b'\tDocumentation: https://mesosphere.github.io/marathon\n'
              b'\tIssues: https:/github.com/mesosphere/marathon/issues\n\n')

    uninstall_stderr = (
        b'Uninstalled package [marathon] version [0.11.1]\n'
        b'The Marathon DCOS Service has been uninstalled and will no '
        b'longer run.\nPlease follow the instructions at http://docs.'
        b'mesosphere.com/services/marathon/#uninstall to clean up any '
        b'persisted state\n'
    )

    with _package('marathon',
                  stdout=stdout,
                  uninstall_stderr=uninstall_stderr,
                  args=['--yes', '--package-version=0.11.1']):

        returncode, stdout, stderr = exec_command(
            ['dcos', 'package', 'list', 'marathon', '--json'])
        assert returncode == 0
        assert stderr == b''
        assert json.loads(stdout.decode('utf-8'))[0]['version'] == "0.11.1"


def test_install_bad_package_version():
    stderr = b'Version [a.b.c] of package [cassandra] not found\n'
    assert_command(
        ['dcos', 'package', 'install', 'cassandra',
         '--package-version=a.b.c'],
        returncode=1,
        stderr=stderr)


def test_package_metadata():
    _install_helloworld()

    # test marathon labels
    expected_metadata = b"""eyJ3ZWJzaXRlIjoiaHR0cHM6Ly9naXRodWIuY29tL21lc29zcG\
hlcmUvZGNvcy1oZWxsb3dvcmxkIiwibmFtZSI6ImhlbGxvd29ybGQiLCJwb3N0SW5zdGFsbE5vdGVz\
IjoiQSBzYW1wbGUgcG9zdC1pbnN0YWxsYXRpb24gbWVzc2FnZSIsImRlc2NyaXB0aW9uIjoiRXhhbX\
BsZSBEQ09TIGFwcGxpY2F0aW9uIHBhY2thZ2UiLCJwYWNrYWdpbmdWZXJzaW9uIjoiMi4wIiwidGFn\
cyI6WyJtZXNvc3BoZXJlIiwiZXhhbXBsZSIsInN1YmNvbW1hbmQiXSwibWFpbnRhaW5lciI6InN1cH\
BvcnRAbWVzb3NwaGVyZS5pbyIsInZlcnNpb24iOiIwLjEuMCIsInByZUluc3RhbGxOb3RlcyI6IkEg\
c2FtcGxlIHByZS1pbnN0YWxsYXRpb24gbWVzc2FnZSJ9"""

    expected_command = b"""eyJwaXAiOlsiZGNvczwxLjAiLCJnaXQraHR0cHM6Ly9naXRodWI\
uY29tL21lc29zcGhlcmUvZGNvcy1oZWxsb3dvcmxkLmdpdCNkY29zLWhlbGxvd29ybGQ9MC4xLjAiX\
X0="""

    expected_source = b"""https://github.com/mesosphere/universe/archive/\
cli-test-4.zip"""

    expected_labels = {
        'DCOS_PACKAGE_REGISTRY_VERSION': b'2.0',
        'DCOS_PACKAGE_NAME': b'helloworld',
        'DCOS_PACKAGE_VERSION': b'0.1.0',
        'DCOS_PACKAGE_SOURCE': expected_source,
        'DCOS_PACKAGE_RELEASE': b'0',
    }

    app_labels = _get_app_labels('helloworld')
    for label, value in expected_labels.items():
        assert value == six.b(app_labels.get(label))

    # these labels are different for cosmos b/c of null problem
    # we have cosmos tests for test, and will fix in issue 431
    assert expected_metadata == six.b(
        app_labels.get('DCOS_PACKAGE_METADATA'))
    assert expected_command == six.b(
        app_labels.get('DCOS_PACKAGE_COMMAND'))

    # test local package.json
    package = {
        "description": "Example DCOS application package",
        "maintainer": "support@mesosphere.io",
        "name": "helloworld",
        "packagingVersion": "2.0",
        "postInstallNotes": "A sample post-installation message",
        "preInstallNotes": "A sample pre-installation message",
        "tags": ["mesosphere", "example", "subcommand"],
        "version": "0.1.0",
        "website": "https://github.com/mesosphere/dcos-helloworld",
    }

    helloworld_subcommand = subcommand.InstalledSubcommand("helloworld")

    # test local package.json
    assert _remove_nulls(helloworld_subcommand.package_json()) == package

    # uninstall helloworld
    _uninstall_helloworld()


def test_images_in_metadata():
    package_install('cassandra')

    labels = _get_app_labels('/cassandra/dcos')
    dcos_package_metadata = labels.get("DCOS_PACKAGE_METADATA")
    images = json.loads(
        base64.b64decode(dcos_package_metadata).decode('utf-8'))["images"]
    assert images.get("icon-small") is not None
    assert images.get("icon-medium") is not None
    assert images.get("icon-large") is not None

    # uninstall
    stderr = (b'Uninstalled package [cassandra] version [0.2.0-1]\n'
              b'The Apache Cassandra DCOS Service has been uninstalled and '
              b'will no longer run.\n'
              b'Please follow the instructions at http://docs.mesosphere.com/'
              b'services/cassandra/#uninstall to clean up any persisted '
              b'state\n')

    package_uninstall('cassandra', stderr=stderr)
    assert_command(['dcos', 'marathon', 'group', 'remove', '/cassandra'])
    delete_zk_node('cassandra-mesos')


def test_install_with_id(zk_znode):
    args = ['--app-id=chronos-1', '--yes']
    stdout = (b'Installing Marathon app for package [chronos] version [2.4.0] '
              b'with app id [chronos-1]\n')
    _install_chronos(args=args, stdout=stdout)

    args = ['--app-id=chronos-2', '--yes']
    stdout = (b'Installing Marathon app for package [chronos] version [2.4.0] '
              b'with app id [chronos-2]\n')
    _install_chronos(args=args, stdout=stdout)


def test_install_missing_package():
    stderr = b'Package [missing-package] not found\n'
    assert_command(['dcos', 'package', 'install', 'missing-package'],
                   returncode=1,
                   stderr=stderr)


def test_uninstall_with_id(zk_znode):
    _uninstall_chronos(args=['--app-id=chronos-1'])


def test_uninstall_all(zk_znode):
    _uninstall_chronos(args=['--all'])


def test_uninstall_missing():
    stderr = 'Package [chronos] is not installed\n'
    _uninstall_chronos(returncode=1, stderr=stderr)

    stderr = 'Package [chronos] with id [/chronos-1] is not installed\n'
    _uninstall_chronos(
        args=['--app-id=chronos-1'],
        returncode=1,
        stderr=stderr)


def test_uninstall_subcommand():
    _install_helloworld()
    _uninstall_helloworld()
    _list()


def test_uninstall_cli():
    _install_helloworld()
    _uninstall_cli_helloworld(args=['--cli'])

    stdout = b"""
  {
    "apps": [
      "/helloworld"
    ],
    "description": "Example DCOS application package",
    "maintainer": "support@mesosphere.io",
    "name": "helloworld",
    "packagingVersion": "2.0",
    "postInstallNotes": "A sample post-installation message",
    "preInstallNotes": "A sample pre-installation message",
    "tags": [
      "mesosphere",
      "example",
      "subcommand"
    ],
    "version": "0.1.0",
    "website": "https://github.com/mesosphere/dcos-helloworld"
  }
"""
    returncode_, stdout_, stderr_ = exec_command(
        ['dcos', 'package', 'list', '--json'])
    assert stderr_ == b''
    assert returncode_ == 0
    output = json.loads(stdout_.decode('utf-8'))[0]
    assert _remove_nulls(output) == json.loads(stdout.decode('utf-8'))
    _uninstall_helloworld()


def test_uninstall_multiple_apps():
    stdout = (b'A sample pre-installation message\n'
              b'Installing Marathon app for package [helloworld] version '
              b'[0.1.0] with app id [/helloworld-1]\n'
              b'Installing CLI subcommand for package [helloworld] '
              b'version [0.1.0]\n'
              b'New command available: dcos helloworld\n'
              b'A sample post-installation message\n')

    _install_helloworld(['--yes', '--app-id=/helloworld-1'],
                        stdout=stdout)

    stdout = (b'A sample pre-installation message\n'
              b'Installing Marathon app for package [helloworld] version '
              b'[0.1.0] with app id [/helloworld-2]\n'
              b'Installing CLI subcommand for package [helloworld] '
              b'version [0.1.0]\n'
              b'New command available: dcos helloworld\n'
              b'A sample post-installation message\n')

    _install_helloworld(['--yes', '--app-id=/helloworld-2'],
                        stdout=stdout)

    stderr = (b"Multiple apps named [helloworld] are installed: "
              b"[/helloworld-1, /helloworld-2].\n"
              b"Please use --app-id to specify the ID of the app "
              b"to uninstall, or use --all to uninstall all apps.\n")
    returncode = 1

    _uninstall_helloworld(stderr=stderr,
                          returncode=returncode,
                          uninstalled=b'')

    _uninstall_helloworld(args=['--all'], stdout=b'', stderr=b'', returncode=0)

    watch_all_deployments()


def test_list(zk_znode):
    _list()
    _list(args=['xyzzy', '--json'])
    _list(args=['--app-id=/xyzzy', '--json'])

    _install_chronos()

    expected_output = file_json(
        'tests/data/package/json/test_list_chronos.json')

    _list_remove_nulls(stdout=expected_output)
    _list_remove_nulls(args=['--json', 'chronos'], stdout=expected_output)
    _list_remove_nulls(args=['--json', '--app-id=/chronos'],
                       stdout=expected_output)
    _list(args=['--json', 'ceci-nest-pas-une-package'])
    _list(args=['--json', '--app-id=/ceci-nest-pas-une-package'])

    _uninstall_chronos()


def test_list_table():
    with _helloworld():
        assert_lines(['dcos', 'package', 'list'], 2)


def test_install_yes():
    with open('tests/data/package/assume_yes.txt') as yes_file:
        _install_helloworld(
            args=[],
            stdin=yes_file,
            stdout=b'A sample pre-installation message\n'
                   b'Continue installing? [yes/no] '
                   b'Installing Marathon app for package [helloworld] version '
                   b'[0.1.0]\n'
                   b'Installing CLI subcommand for package [helloworld] '
                   b'version [0.1.0]\n'
                   b'New command available: dcos helloworld\n'
                   b'A sample post-installation message\n')
        _uninstall_helloworld()


def test_install_no():
    with open('tests/data/package/assume_no.txt') as no_file:
        _install_helloworld(
            args=[],
            stdin=no_file,
            stdout=b'A sample pre-installation message\n'
                   b'Continue installing? [yes/no] Exiting installation.\n')


def test_list_cli():
    stdout = b"""
  {
    "apps": [
      "/helloworld"
    ],
    "command": {
      "name": "helloworld"
    },
    "description": "Example DCOS application package",
    "maintainer": "support@mesosphere.io",
    "name": "helloworld",
    "packagingVersion": "2.0",
    "postInstallNotes": "A sample post-installation message",
    "preInstallNotes": "A sample pre-installation message",
    "tags": [
      "mesosphere",
      "example",
      "subcommand"
    ],
    "version": "0.1.0",
    "website": "https://github.com/mesosphere/dcos-helloworld"
  }
"""
    _install_helloworld()
    _list_remove_nulls(stdout=stdout)
    _uninstall_helloworld()

    stdout = (b"A sample pre-installation message\n"
              b"Installing CLI subcommand for package [helloworld] " +
              b"version [0.1.0]\n"
              b"New command available: dcos helloworld\n"
              b"A sample post-installation message\n")
    _install_helloworld(args=['--cli', '--yes'], stdout=stdout)

    stdout = b"""\
  {
    "command": {
      "name": "helloworld"
    },
    "description": "Example DCOS application package",
    "maintainer": "support@mesosphere.io",
    "name": "helloworld",
    "packagingVersion": "2.0",
    "postInstallNotes": "A sample post-installation message",
    "preInstallNotes": "A sample pre-installation message",
    "tags": [
      "mesosphere",
      "example",
      "subcommand"
    ],
    "version": "0.1.0",
    "website": "https://github.com/mesosphere/dcos-helloworld"
  }
"""
    _list_remove_nulls(stdout=stdout)
    _uninstall_cli_helloworld()


def test_uninstall_multiple_frameworknames(zk_znode):
    _install_chronos(
        args=['--yes', '--options=tests/data/package/chronos-1.json'])
    _install_chronos(
        args=['--yes', '--options=tests/data/package/chronos-2.json'])

    watch_all_deployments()

    expected_output = file_json(
        'tests/data/package/json/test_list_chronos_two_users.json')

    # issue 431
    _list_remove_nulls(stdout=expected_output)
    _list_remove_nulls(args=['--json', 'chronos'], stdout=expected_output)
    _list_remove_nulls(args=['--json', '--app-id=/chronos-user-1'],
                       stdout=file_json(
        'tests/data/package/json/test_list_chronos_user_1.json'))

    _list_remove_nulls(args=['--json', '--app-id=/chronos-user-2'],
                       stdout=file_json(
        'tests/data/package/json/test_list_chronos_user_2.json'))

    _uninstall_chronos(
        args=['--app-id=chronos-user-1'],
        returncode=1,
        stderr='Uninstalled package [chronos] version [2.4.0]\n'
               'Unable to shutdown [chronos] service framework with name '
               '[chronos-user] because there are multiple framework ids '
               'matching this name: ')

    _uninstall_chronos(
        args=['--app-id=chronos-user-2'],
        returncode=1,
        stderr='Uninstalled package [chronos] version [2.4.0]\n'
               'Unable to shutdown [chronos] service framework with name '
               '[chronos-user] because there are multiple framework ids '
               'matching this name: ')

    for framework in get_services(args=['--inactive']):
        if framework['name'] == 'chronos-user':
            service_shutdown(framework['id'])


def test_search():
    returncode, stdout, stderr = exec_command(
        ['dcos', 'package', 'search', 'cron', '--json'])

    assert returncode == 0
    assert b'chronos' in stdout
    assert stderr == b''

    returncode, stdout, stderr = exec_command(
        ['dcos', 'package', 'search', 'xyzzy', '--json'])

    assert returncode == 0
    assert b'"packages": []' in stdout
    assert stderr == b''

    returncode, stdout, stderr = exec_command(
        ['dcos', 'package', 'search', 'xyzzy'])

    assert returncode == 1
    assert b'' == stdout
    assert stderr == b'No packages found.\n'

    returncode, stdout, stderr = exec_command(
        ['dcos', 'package', 'search', '--json'])

    registries = json.loads(stdout.decode('utf-8'))
    # assert the number of packages is gte the number at the time
    # this test was written
    assert len(registries['packages']) >= 5

    assert returncode == 0
    assert stderr == b''


def test_search_table():
    returncode, stdout, stderr = exec_command(
        ['dcos', 'package', 'search'])

    assert returncode == 0
    assert b'chronos' in stdout
    assert len(stdout.decode('utf-8').split('\n')) > 5
    assert stderr == b''


def test_search_ends_with_wildcard():
    returncode, stdout, stderr = exec_command(
        ['dcos', 'package', 'search', 'c*', '--json'])

    assert returncode == 0
    assert b'chronos' in stdout
    assert b'cassandra' in stdout
    assert stderr == b''

    registries = json.loads(stdout.decode('utf-8'))
    # cosmos matches wildcards in name/description/tags
    # so will find more results (3 instead of 2)
    assert len(registries['packages']) >= 2


def test_search_start_with_wildcard():
    returncode, stdout, stderr = exec_command(
        ['dcos', 'package', 'search', '*nos', '--json'])

    assert returncode == 0
    assert b'chronos' in stdout
    assert stderr == b''

    registries = json.loads(stdout.decode('utf-8'))
    assert len(registries['packages']) == 1


def test_search_middle_with_wildcard():
    returncode, stdout, stderr = exec_command(
        ['dcos', 'package', 'search', 'c*s', '--json'])

    assert returncode == 0
    assert b'chronos' in stdout
    assert stderr == b''

    registries = json.loads(stdout.decode('utf-8'))
    assert len(registries['packages']) == 1


def _get_app_labels(app_id):
    returncode, stdout, stderr = exec_command(
        ['dcos', 'marathon', 'app', 'show', app_id])

    assert returncode == 0
    assert stderr == b''

    app_json = json.loads(stdout.decode('utf-8'))
    return app_json.get('labels')


def _install_helloworld(
        args=['--yes'],
        stdout=b'A sample pre-installation message\n'
               b'Installing Marathon app for package [helloworld] '
               b'version [0.1.0]\n'
               b'Installing CLI subcommand for package [helloworld] '
               b'version [0.1.0]\n'
               b'New command available: dcos helloworld\n'
               b'A sample post-installation message\n',
        stderr=b'',
        returncode=0,
        stdin=None):
    assert_command(
        ['dcos', 'package', 'install', 'helloworld'] + args,
        stdout=stdout,
        returncode=returncode,
        stdin=stdin,
        stderr=stderr)


def _uninstall_helloworld(
        args=[],
        stdout=b'',
        stderr=b'',
        returncode=0,
        uninstalled=b'Uninstalled package [helloworld] version [0.1.0]\n'):
    assert_command(['dcos', 'package', 'uninstall', 'helloworld'] + args,
                   stdout=stdout,
                   stderr=uninstalled+stderr,
                   returncode=returncode)


def _uninstall_cli_helloworld(
        args=[],
        stdout=b'',
        stderr=b'',
        returncode=0):
    assert_command(['dcos', 'package', 'uninstall', 'helloworld'] + args,
                   stdout=stdout,
                   stderr=stderr,
                   returncode=returncode)


def _uninstall_chronos(args=[], returncode=0, stdout=b'', stderr=''):
    result_returncode, result_stdout, result_stderr = exec_command(
        ['dcos', 'package', 'uninstall', 'chronos'] + args)

    assert result_returncode == returncode
    assert result_stdout == stdout
    assert result_stderr.decode('utf-8').startswith(stderr)


def _install_bad_chronos(args=['--yes'],
                         stdout=b'',
                         stderr=''):
    cmd = ['dcos', 'package', 'install', 'chronos'] + args
    returncode_, stdout_, stderr_ = exec_command(cmd)
    assert returncode_ == 1
    assert stderr in stderr_.decode('utf-8')
    preInstallNotes = (b'We recommend a minimum of one node with at least 1 '
                       b'CPU and 2GB of RAM available for the Chronos '
                       b'Service.\n')
    assert stdout_ == preInstallNotes


def _install_chronos(
        args=['--yes'],
        returncode=0,
        stdout=b'Installing Marathon app for package [chronos] '
               b'version [2.4.0]\n',
        stderr=b'',
        preInstallNotes=b'We recommend a minimum of one node with at least 1 '
                        b'CPU and 2GB of RAM available for the Chronos '
                        b'Service.\n',
        postInstallNotes=b'Chronos DCOS Service has been successfully '
                         b'''installed!

\tDocumentation: http://mesos.github.io/chronos
\tIssues: https://github.com/mesos/chronos/issues\n''',
        stdin=None):

    cmd = ['dcos', 'package', 'install', 'chronos'] + args
    assert_command(
        cmd,
        returncode,
        preInstallNotes + stdout + postInstallNotes,
        stderr,
        stdin=stdin)


def _list(args=['--json'],
          stdout=b'[]\n'):
    assert_command(['dcos', 'package', 'list'] + args,
                   stdout=stdout)


def _list_remove_nulls(args=['--json'], stdout=b'[]\n'):
    returncode_, stdout_, stderr_ = exec_command(
        ['dcos', 'package', 'list'] + args)

    assert returncode_ == 0
    output = json.loads(stdout_.decode('utf-8'))[0]
    assert _remove_nulls(output) == json.loads(stdout.decode('utf-8'))
    assert stderr_ == b''


def _helloworld():
    stdout = b'''A sample pre-installation message
Installing Marathon app for package [helloworld] version [0.1.0]
Installing CLI subcommand for package [helloworld] version [0.1.0]
New command available: dcos helloworld
A sample post-installation message
'''

    stderr = b'Uninstalled package [helloworld] version [0.1.0]\n'
    return _package('helloworld',
                    stdout=stdout,
                    uninstall_stderr=stderr)


@contextlib.contextmanager
def _package(name,
             stdout=b'',
             uninstall_stderr=b'',
             args=['--yes']):
    """Context manager that installs a package on entrace, and uninstalls it on
    exit.

    :param name: package name
    :type name: str
    :param stdout: Expected stdout
    :type stdout: str
    :param uninstall_stderr: Expected stderr
    :type uninstall_stderr: str
    :param args: extra CLI args
    :type args: [str]
    :rtype: None
    """

    assert_command(['dcos', 'package', 'install', name] + args,
                   stdout=stdout)
    try:
        yield
    finally:
        assert_command(
            ['dcos', 'package', 'uninstall', name],
            stderr=uninstall_stderr)
        watch_all_deployments()


def _repo_add(args=[], repo_list=[]):
    assert_command(['dcos', 'package', 'repo', 'add'] + args)
    assert_command(['dcos', 'package', 'repo', 'list'], stdout=repo_list)


def _repo_remove(args=[], repo_list=[]):
    assert_command(['dcos', 'package', 'repo', 'remove'] + args)
    assert_command(['dcos', 'package', 'repo', 'list'], stdout=repo_list)


# issue 431
def _remove_nulls(output):
    """Remove nulls from dict. Temporary until we fix this in cosmos

    :param output: dict with possible null values
    :type output: dict
    :returns: dict without null
    :rtype: dict
    """

    return {k: v for k, v in output.items() if v}
