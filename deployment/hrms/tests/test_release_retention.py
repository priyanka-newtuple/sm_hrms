import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

spec = importlib.util.spec_from_file_location('prepare_release', Path(__file__).resolve().parents[1] / 'prepare_release.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(m.shutil, 'disk_usage', lambda _: SimpleNamespace(free=1000))
    releases=tmp_path/'releases'; releases.mkdir()
    for n in range(1,7):
        folder=releases/f'{n:040x}';folder.mkdir()
        (folder/'images.tar.gz').write_bytes(b'archive')
        (folder/'compose.yml').write_text('preserve')
        import os
        os.utime(folder,(n,n))
    (tmp_path/'current').write_text(str(releases/f'{1:040x}'))
    (tmp_path/'previous-release').write_text(str(releases/f'{2:040x}'))
    (tmp_path/'production.env').write_text('preserve')
    (tmp_path/'backups').mkdir();(tmp_path/'backups'/'db.sql.gz').write_bytes(b'backup')
    return releases


def test_only_obsolete_archive_removed_current_rollback_recent_and_data_preserved(tmp_path,monkeypatch):
    r=setup(tmp_path,monkeypatch)
    assert m.prepare(tmp_path,'a'*40,10,reserve_bytes=100)==7
    for n in (1,2,4,5,6): assert (r/f'{n:040x}'/'images.tar.gz').exists()
    assert not (r/f'{3:040x}'/'images.tar.gz').exists()
    assert (r/f'{3:040x}'/'compose.yml').exists()
    assert (tmp_path/'production.env').read_text()=='preserve'
    assert (tmp_path/'backups'/'db.sql.gz').read_bytes()==b'backup'
    assert m.prepare(tmp_path,'a'*40,10,reserve_bytes=100)==0


def test_missing_space_fails_without_deleting_protected_files(tmp_path,monkeypatch):
    r=setup(tmp_path,monkeypatch)
    with pytest.raises(RuntimeError,match='Insufficient space'):
        m.prepare(tmp_path,'a'*40,1001,reserve_bytes=100)
    assert (r/f'{1:040x}'/'images.tar.gz').exists()
    assert (tmp_path/'backups'/'db.sql.gz').exists()


def test_unsafe_pointer_prevents_any_cleanup(tmp_path,monkeypatch):
    r=setup(tmp_path,monkeypatch)
    (tmp_path/'previous-release').write_text(str(tmp_path))
    with pytest.raises(ValueError,match='pointer'):m.prepare(tmp_path,'a'*40,10,reserve_bytes=100)
    assert (r/f'{3:040x}'/'images.tar.gz').exists()


def test_incoming_release_is_protected(tmp_path,monkeypatch):
    r=setup(tmp_path,monkeypatch)
    assert m.prepare(tmp_path,f'{3:040x}',10,reserve_bytes=100)==0
    assert (r/f'{3:040x}'/'images.tar.gz').exists()


def test_image_cleanup_is_hrms_only_and_protects_all_containers(monkeypatch):
    calls = []
    def output(args, **kwargs):
        if args[1:3] == ['ps', '-aq']: return 'stopped-container\n'
        if args[1] == 'inspect': return 'sha256:used\n'
        return '\n'.join([
            'sm-hrms-platform ' + 'a'*40 + ' sha256:rollback',
            'sm-hrms-application ' + 'b'*40 + ' sha256:used',
            'sm-hrms-platform-web ' + 'c'*40 + ' sha256:unused',
            'another-product ' + 'd'*40 + ' sha256:other',
            'sm-hrms-platform latest sha256:local'])
    monkeypatch.setattr(m.subprocess, 'check_output', output)
    monkeypatch.setattr(m.subprocess, 'run', lambda args, **kwargs: calls.append(args) or SimpleNamespace(returncode=0))
    m.remove_unused_hrms_images({'a'*40})
    assert calls == [['docker', 'image', 'rm', 'sm-hrms-platform-web:' + 'c'*40]]
