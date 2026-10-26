from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from auth.manager import AuthServiceManager
from mail.manager import MailServiceManager
from mail.services.base import load_default_email_provider
from user.db_models import User


@pytest.mark.parametrize('selected', ['smtp', 'missing'])
def test_default_never_falls_back_to_live_provider(monkeypatch, selected):
    import mail.manager as module
    smtp = Mock()
    smtp.resolve_credentials.return_value = None
    monkeypatch.setattr(module, 'load_default_email_provider', lambda db, org: selected)
    monkeypatch.setattr(module, 'get_service', lambda provider: smtp if provider == 'smtp' else None)
    fallback = Mock(side_effect=AssertionError('Must not fall back to another provider'))
    monkeypatch.setattr(module, 'auto_services', fallback)
    assert not MailServiceManager().send_email(Mock(), 'org', 'a@example.com', 'Test', '<p>Test</p>').success
    fallback.assert_not_called()


def test_explicit_provider_takes_precedence(monkeypatch):
    import mail.manager as module
    selected = Mock()
    selected.resolve_credentials.return_value = SimpleNamespace(from_email='test@example.com', from_name=None, reply_to=None)
    selected.send.return_value = SimpleNamespace(success=True)
    monkeypatch.setattr(module, 'load_default_email_provider', Mock(side_effect=AssertionError('Explicit choice must win')))
    monkeypatch.setattr(module, 'get_service', lambda p: selected if p == 'smtp' else None)
    assert MailServiceManager().send_email(Mock(), 'org', 'a@example.com', 'Test', '<p>Test</p>', provider='smtp').success
    selected.send.assert_called_once()


def test_smtp_default_wins_over_configured_azure(monkeypatch):
    import mail.manager as module
    smtp, azure = Mock(), Mock()
    smtp.resolve_credentials.return_value = SimpleNamespace(from_email='test@example.com', from_name=None, reply_to=None)
    smtp.send.return_value = SimpleNamespace(success=True)
    monkeypatch.setattr(module, 'load_default_email_provider', lambda db, org: 'smtp')
    monkeypatch.setattr(module, 'get_service', lambda p: {'smtp': smtp, 'azure_communication': azure}[p])
    monkeypatch.setattr(module, 'auto_services', lambda: [azure, smtp])
    assert MailServiceManager().send_email(Mock(), 'org', 'a@example.com', 'Test', 'Test').success
    smtp.send.assert_called_once()
    azure.resolve_credentials.assert_not_called()


def test_unconfigured_tenant_keeps_legacy_provider_selection(monkeypatch):
    import mail.manager as module
    monkeypatch.setattr(module, 'load_default_email_provider', lambda db, org: None)
    fallback = Mock(return_value=[])
    monkeypatch.setattr(module, 'auto_services', fallback)
    assert not MailServiceManager().send_email(Mock(), 'org', 'a@example.com', 'Test', 'Test').success
    fallback.assert_called_once()


def test_default_lookup_is_tenant_scoped():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE integration_capability_defaults (id TEXT, organization_id TEXT, capability TEXT, provider TEXT, created_at DATETIME, updated_at DATETIME)'))
        conn.execute(text("INSERT INTO integration_capability_defaults VALUES ('1','a','communication','smtp',NULL,NULL),('2','b','communication','azure_communication',NULL,NULL)"))
    with Session(engine) as db:
        assert load_default_email_provider(db, 'a') == 'smtp'
        assert load_default_email_provider(db, 'b') == 'azure_communication'
        assert load_default_email_provider(db, 'c') is None


def test_approval_notifies_only_active_tenant_admins():
    engine = create_engine('sqlite://')
    table = User.__tablename__
    with engine.begin() as conn:
        conn.execute(text(f'CREATE TABLE "{table}" (email TEXT, organization_id TEXT, role TEXT, status TEXT)'))
        conn.execute(text(f'INSERT INTO "{table}" VALUES (:email,:org,:role,:status)'), [
            {'email': email, 'org': org, 'role': role, 'status': status}
            for email, org, role, status in [
                ('admin@example.com', 'a', 'admin', 'active'),
                ('super@example.com', 'a', 'superadmin', 'active'),
                ('other@example.com', 'b', 'superadmin', 'active'),
                ('pending@example.com', 'a', 'superadmin', 'pending'),
                ('employee@example.com', 'a', 'viewer', 'active'),
            ]])
    with Session(engine) as session:
        db = SimpleNamespace(query=lambda model: session.query(model.email))
        notifications = Mock()
        manager = SimpleNamespace(notifications_manager=notifications)
        AuthServiceManager._notify_admins_new_user(manager, db, 'new@example.com', 'New User', 'a')
        assert set(notifications.notify_admins_new_user.call_args.kwargs['admin_emails']) == {'admin@example.com', 'super@example.com'}
