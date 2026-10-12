"""Keeping a performance cycle moving when people leave, join, change manager or are slow to respond."""
from datetime import date, timedelta

import pytest

from hrms_app.errors import AppError
from hrms_app.performance import FEEDBACK, REVIEW
from test_performance import act, actor, goal, open_cycle, system  # noqa: F401  (fixture)

E1, E2, NEW_BOSS, HR2, REVIEWER2, CHIEF_ASSESSOR = ('00000000-0000-0000-0000-00000000000%d' % i for i in range(1, 7))
HR, OTHER_HR = actor('hr', 'hrms_hr_full'), actor(HR2, 'hrms_hr_full', 'hrms_performance_approver')
EMPLOYEE, MANAGER = actor('employee'), actor('manager')


def second_participant(system):
    _, platform, _ = system
    cycle = platform.rows['cycle']['data']
    cycle['participants'].append({**cycle['participants'][0], 'employee_id': 'employee-2-record',
                                  'employee_name': 'Second Employee', 'employee_user_id': 'employee-2'})


def reviews(platform, user='employee'):
    return next(r['entity_id'] for r in platform.rows.values() if r['kind'] == REVIEW and r['data']['employee_user_id'] == user)


def to_self_review(service, review):
    goal(service, review)
    act(service, EMPLOYEE, review, 'submit_goals')
    act(service, MANAGER, review, 'approve_goals')


def to_published(system):
    service, _, _ = system
    review = open_cycle(system)
    to_self_review(service, review)
    act(service, HR, 'cycle', 'start_reviews')
    act(service, EMPLOYEE, review, 'submit_self', dict(summary='Self', rating=4))
    act(service, MANAGER, review, 'submit_manager', dict(summary='Manager', rating=3))
    act(service, HR, 'cycle', 'start_calibration')
    act(service, HR, review, 'calibrate', dict(comment='Calibrated', rating=3))
    act(service, HR, 'cycle', 'publish')
    return review


def people(service):
    users = [dict(id=u, name=u.title(), capabilities=['performance:manage'] if u.startswith('hr') else [])
             for u in ('hr', HR2, 'admin', 'manager', 'employee', 'employee-2', 'reviewer', REVIEWER2, NEW_BOSS, CHIEF_ASSESSOR)]
    users[1]['capabilities'] = ['performance:manage']
    service.user_options = lambda project_policy=None: users
    service.options = lambda who: dict(
        users=users, calibrators=[u for u in users if u['capabilities']],
        approvers=[u for u in users if u['id'] in {'admin', HR2} and u['id'] != who.user_id],
        employees=[dict(id=E1, name='Joiner', employee_user_id='employee-3', manager_user_id='manager', manager_name='Manager'),
                   dict(id=E2, name='Chief', employee_user_id='employee-4', manager_user_id=None, manager_name=None)])


# PF-1: a leaver no longer blocks the cycle
def test_withdrawing_a_participant_lets_the_cycle_move_on(system):
    service, platform, _ = system
    second_participant(system)
    review = open_cycle(system)
    to_self_review(service, review)
    with pytest.raises(AppError, match='approved goals'):
        act(service, HR, 'cycle', 'start_reviews')
    leaver = reviews(platform, 'employee-2')
    act(service, HR, leaver, 'withdraw', dict(comment='Left the company'))
    act(service, HR, 'cycle', 'start_reviews')
    assert platform.rows['cycle']['state'] == 'review'
    shown = next(r for r in service.dashboard(HR)['reviews'] if r['id'] == leaver)
    assert shown['state'] == 'withdrawn' and shown['actions'] == []


def test_employees_cannot_withdraw_themselves(system):
    service, _, _ = system
    review = open_cycle(system)
    with pytest.raises(AppError):
        act(service, EMPLOYEE, review, 'withdraw', dict(comment='No thanks'))


# PF-2: feedback that never arrives can be cancelled or passed to someone else
def feedback_requested(system):
    service, platform, _ = system
    review = open_cycle(system)
    to_self_review(service, review)
    act(service, HR, 'cycle', 'start_reviews')
    act(service, EMPLOYEE, review, 'submit_self', dict(summary='Self', rating=4))
    platform.add(FEEDBACK, dict(review_id=review, project_reference='Apollo', reviewer_user_id='reviewer',
                                reviewer_name='Reviewer'), entity_id='feedback')
    return review


def test_cancelled_feedback_no_longer_holds_up_the_manager_review(system):
    service, platform, _ = system
    review = feedback_requested(system)
    act(service, MANAGER, 'feedback', 'cancel_feedback', dict(comment='Reviewer is on long leave'))
    act(service, MANAGER, review, 'submit_manager', dict(summary='Manager', rating=3))
    assert platform.rows[review]['state'] == 'calibration'
    assert service.dashboard(actor('reviewer'))['assigned_feedback'] == []


def test_feedback_can_be_passed_to_another_reviewer(system):
    service, platform, _ = system
    people(service)
    feedback_requested(system)
    act(service, HR, 'feedback', 'reassign_feedback', dict(reviewer_user_id=REVIEWER2, comment='Moved projects'))
    assert platform.rows['feedback']['data']['reviewer_user_id'] == REVIEWER2
    assert service.dashboard(actor('reviewer'))['assigned_feedback'] == []
    assert service.dashboard(actor(REVIEWER2))['assigned_feedback'][0]['actions'][0] == 'submit_feedback'


def test_the_employee_cannot_cancel_feedback_about_themselves(system):
    service, _, _ = system
    feedback_requested(system)
    with pytest.raises(AppError):
        act(service, EMPLOYEE, 'feedback', 'cancel_feedback', dict(comment='Not needed'))


# PF-4: acknowledgement is not consent, so HR can close without it
def test_hr_can_close_with_reviews_still_unacknowledged(system):
    service, platform, _ = system
    to_published(system)
    act(service, HR, 'cycle', 'close')
    assert platform.rows['cycle']['state'] == 'closed'
    assert platform.rows['cycle']['data']['unacknowledged_count'] == 1


# PF-5: a cycle cannot run ahead of its own dates
def test_reviews_cannot_start_before_the_cycle_begins(system):
    service, platform, _ = system
    review = open_cycle(system)
    to_self_review(service, review)
    platform.rows['cycle']['data']['start_date'] = (date.today() + timedelta(days=30)).isoformat()
    with pytest.raises(AppError, match='once the cycle begins'):
        act(service, HR, 'cycle', 'start_reviews')


def test_a_cycle_whose_end_date_has_passed_cannot_be_created(system):
    service, _, _ = system
    people(service)
    past = (date.today() - timedelta(days=1)).isoformat()
    data = dict(name='Old', start_date=past, goal_due_date=past, self_review_due_date=past, manager_review_due_date=past,
                end_date=past, approver_id='00000000-0000-0000-0000-0000000000aa',
                participants=[dict(employee_id=E1, calibrator_user_id='00000000-0000-0000-0000-0000000000bb')])
    with pytest.raises(AppError, match='already passed'):
        act(service, HR, 'new', 'create_cycle', data)


def test_each_step_shows_the_deadline_it_is_working_to(system):
    service, platform, _ = system
    review = open_cycle(system)
    platform.rows['cycle']['data']['goal_due_date'] = '2026-02-15'
    shown = next(r for r in service.dashboard(HR)['reviews'] if r['id'] == review)
    assert shown['due_date'] == '2026-02-15'


# PF-6: people who join later can be added
def test_hr_can_add_someone_to_an_open_cycle_once(system):
    service, platform, _ = system
    people(service)
    open_cycle(system)
    added = dict(participants=[dict(employee_id=E1, calibrator_user_id=HR2)])
    act(service, HR, 'cycle', 'add_participants', added, key='add-joiner')
    joiner = reviews(platform, 'employee-3')
    assert platform.rows[joiner]['state'] == 'goals_draft'
    assert [p['employee_name'] for p in platform.rows['cycle']['data']['participants']][-1] == 'Joiner'
    with pytest.raises(AppError, match='already in this cycle'):
        act(service, HR, 'cycle', 'add_participants', added, key='add-joiner-again')


# PF-7: a wrong goal can be removed
def test_an_employee_can_remove_a_goal_before_submitting(system):
    service, platform, _ = system
    review = open_cycle(system)
    goal(service, review)
    wrong = act(service, EMPLOYEE, review, 'add_goal', dict(title='Typo', measurement='x', weight=10,
                target_date='2026-12-01'), key='wrong-goal')['entity_id']
    with pytest.raises(AppError, match='100%'):
        act(service, EMPLOYEE, review, 'submit_goals')
    act(service, EMPLOYEE, wrong, 'remove_goal')
    act(service, EMPLOYEE, review, 'submit_goals', key='submit-after-removal')
    assert platform.rows[review]['state'] == 'goals_pending'
    assert [g['data']['title'] for g in service.dashboard(EMPLOYEE)['reviews'][0]['goals']] == ['Delivery']


# PF-8: who assesses someone without a manager, and manager changes mid-cycle
def test_someone_without_a_reporting_manager_needs_an_assessor_chosen(system):
    service, _, _ = system
    people(service)
    options = service.options(HR)
    with pytest.raises(AppError, match='Choose who assesses Chief'):
        service.participants(options, [dict(employee_id=E2, calibrator_user_id='hr')])
    [chief] = service.participants(options, [dict(employee_id=E2, calibrator_user_id='hr', manager_user_id=CHIEF_ASSESSOR)])
    assert chief['manager_user_id'] == CHIEF_ASSESSOR


def directory(service, status='active', manager_code='BOSS'):
    rows = [dict(entity_id='employee-record', data=dict(employment_status=status, platform_user_id='employee',
                                                         reports_to_employee_code=manager_code)),
            dict(entity_id='boss-record', data=dict(employee_code='BOSS', platform_user_id=NEW_BOSS, employment_status='active'))]
    service.hrms.employees = lambda: rows


def test_a_new_reporting_manager_takes_over_open_manager_steps(system):
    service, platform, _ = system
    people(service)
    review = open_cycle(system)
    directory(service)
    service.sync_employee(HR, 'employee-record')
    assert platform.rows[review]['data']['manager_user_id'] == NEW_BOSS


def test_a_leavers_reviews_are_withdrawn_and_feedback_asked_of_them_cancelled(system):
    service, platform, _ = system
    people(service)
    feedback_requested(system)
    review = reviews(platform)
    directory(service, status='offboarded')
    platform.rows['feedback']['data']['reviewer_user_id'] = 'employee'  # the leaver was also asked for feedback
    service.sync_employee(HR, 'employee-record')
    assert platform.rows[review]['data']['withdrawal_reason'] == 'Left the company'
    assert platform.rows['feedback']['data']['cancel_reason'] == 'Reviewer left the company'


# PF-9: a published rating can be corrected, and the employee sees and acknowledges the change
def test_hr_can_correct_a_published_rating(system):
    service, platform, _ = system
    review = to_published(system)
    act(service, EMPLOYEE, review, 'acknowledge', dict(comment='Seen'))
    act(service, HR, review, 'correct_rating', dict(rating=4, comment='Calibration data entry error'))
    own = service.dashboard(EMPLOYEE)['reviews'][0]
    assert own['data']['final_rating'] == 4 and own['actions'] == ['acknowledge_correction']
    act(service, EMPLOYEE, review, 'acknowledge_correction', dict(comment='Thanks'))
    assert platform.rows[review]['data']['reacknowledge_required'] is None
    assert platform.rows[review]['data']['previous_final_rating'] == 3


def test_ratings_are_final_once_the_cycle_closes(system):
    service, _, _ = system
    review = to_published(system)
    act(service, HR, 'cycle', 'close')
    with pytest.raises(AppError):
        act(service, HR, review, 'correct_rating', dict(rating=4, comment='Too late'))


# PF-10: any HR can finish a colleague's draft; the approver can be changed while waiting
def test_another_hr_can_submit_a_colleagues_draft_but_neither_can_approve_it(system):
    service, platform, _ = system
    people(service)
    act(service, OTHER_HR, 'cycle', 'submit')
    assert platform.rows['cycle']['data']['submitted_by'] == HR2
    with pytest.raises(AppError, match='did not create or submit'):
        act(service, HR, 'cycle', 'change_approver', dict(approver_id=HR2, comment='Admin is away'))


def test_the_approver_can_be_changed_while_the_cycle_waits(system):
    service, platform, _ = system
    people(service)
    act(service, HR, 'cycle', 'submit')
    act(service, HR, 'cycle', 'change_approver', dict(approver_id=HR2, comment='Admin is away'))
    assert platform.rows['cycle']['data']['approver_id'] == HR2
    assert 'approve' in service.dashboard(OTHER_HR)['cycles'][0]['actions']
