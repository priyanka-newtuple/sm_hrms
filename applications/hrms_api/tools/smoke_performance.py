"""End-to-end local performance test. Keeps one explicitly named review cycle."""
import os

import httpx

from hrms_app.platform import PlatformClient


def main():
    assert os.environ.get('HRMS_LOCAL_SMOKE') == 'true', 'Local stack only'
    app = httpx.Client(base_url='http://hrms-app:8000/v1/api', timeout=180)

    def login(email, password):
        response = app.post('/auth/login', json=dict(email=email, password=password))
        assert response.status_code == 200, f'Login failed for {email}: {response.status_code}'
        return {'Authorization': 'Bearer ' + response.json()['access_token']}

    admin = login(os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    hr = login('kavya.menon@newtuple.com', os.environ['HRMS_DEMO_EMPLOYEE_PASSWORD'])
    employee = login('hrms.boundary.employee@newtuple.com', os.environ['HRMS_DEMO_EMPLOYEE_PASSWORD'])
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    rows = api.records('HRMS.Employee', ['work_email', 'platform_user_id', 'employee_code', 'reports_to_employee_code'])
    person = next(r for r in rows if r['data'].get('work_email') == 'hrms.boundary.employee@newtuple.com')
    manager_record = next(r for r in rows if r['data'].get('employee_code') == person['data']['reports_to_employee_code'])
    manager = login(manager_record['data']['work_email'], os.environ['HRMS_DEMO_MANAGER_PASSWORD'])
    hr_id = app.get('/auth/me', headers=hr).json()['id']
    admin_id = app.get('/auth/me', headers=admin).json()['id']

    def action(headers, target, trigger, data=None, suffix=''):
        body = dict(action=trigger, data=data or {}, idempotency_key=f'performance-smoke-v1-{trigger}{suffix}')
        path = '/hrms/performance/cycles' if target == 'new' else f'/hrms/performance/{target}/actions'
        response = app.post(path, headers=headers, json=body)
        assert response.status_code == 200, f'{trigger}: {response.status_code} {response.text}'
        repeat = app.post(path, headers=headers, json=body)
        assert repeat.status_code == 200 and repeat.json() == response.json(), f'{trigger}: retry changed result'
        return response.json()['entity_id']

    options = app.get('/hrms/performance/options', headers=hr)
    assert options.status_code == 200, options.text
    assert any(e['id'] == person['entity_id'] for e in options.json()['employees'])
    cycle = action(hr, 'new', 'create_cycle', dict(name='Local performance verification',
        description='Named integration-test fixture; not a real employee assessment.',
        start_date='2042-01-01', goal_due_date='2042-02-01', self_review_due_date='2042-10-01',
        manager_review_due_date='2042-11-01', end_date='2042-12-31', approver_id=admin_id,
        participants=[dict(employee_id=person['entity_id'], calibrator_user_id=hr_id)]))
    action(hr, cycle, 'submit')
    action(admin, cycle, 'approve')
    board = app.get('/hrms/performance', headers=employee)
    assert board.status_code == 200, board.text
    review = next(r for r in board.json()['reviews'] if r['data']['cycle_id'] == cycle)['id']
    action(employee, review, 'add_goal', dict(title='Local test goal', measurement='Verify state-machine integration',
                                            weight=100, target_date='2042-10-01'))
    action(employee, review, 'submit_goals')
    denied = app.post(f'/hrms/performance/{review}/actions', headers=employee, json=dict(
        action='approve_goals', data={}, idempotency_key='performance-smoke-self-approval-denied'))
    assert denied.status_code == 403, denied.text
    action(manager, review, 'approve_goals')
    action(hr, cycle, 'start_reviews')
    action(employee, review, 'submit_self', dict(summary='Integration test self review', rating=4))
    feedback = action(manager, review, 'request_feedback', dict(project_reference='Local verification project', reviewer_user_id=hr_id))
    action(hr, feedback, 'submit_feedback', dict(rating=4, contribution='Integration test feedback'))
    action(manager, review, 'submit_manager', dict(summary='Integration test manager review', rating=4))
    current = next(r for r in app.get('/hrms/performance', headers=employee).json()['reviews'] if r['id'] == review)
    # The test can be rerun against its completed fixture, in which case publication is already visible.
    if current['state'] not in {'published', 'acknowledged'}:
        assert 'manager_rating' not in current['data'] and current['feedback'] == []
    action(hr, cycle, 'start_calibration')
    action(hr, review, 'calibrate', dict(rating=4, comment='Private integration test calibration'))
    action(hr, cycle, 'publish')
    current = next(r for r in app.get('/hrms/performance', headers=employee).json()['reviews'] if r['id'] == review)
    assert current['data']['final_rating'] == 4 and 'calibration_comment' not in current['data']
    action(employee, review, 'acknowledge', dict(comment='Integration test acknowledgement'))
    action(hr, cycle, 'close')
    assert api.states('hrms_performancecycle')[cycle] == 'closed'
    assert api.states('hrms_performancereview')[review] == 'acknowledged'
    assert app.get('/hrms/performance/pending-actions', headers=hr).json() == []
    workflow_rows = app.get('/hrms/workflows', headers=employee)
    assert workflow_rows.status_code == 200, workflow_rows.text
    assert any(r['entity_id'] == review and r['title'] == 'Boundary Test Employee' for r in workflow_rows.json())
    assert app.post(f'/entities/{review}/transitions', headers=admin, json={'trigger': 'publish'}).status_code == 403
    print('PASS: native cycle/goals/review/feedback lifecycle, separation of duties, privacy, retries, workflow projection and mutation boundary')
    print('Retained fixture: Local performance verification (Boundary Test Employee)')


if __name__ == '__main__':
    main()
