"""Performance orchestration over public native APIs; no core imports or SQL."""
from datetime import UTC, datetime
import hashlib

from pydantic import ValidationError

from .catalog import pack_by_type
from .errors import AppError
from .performance_contracts import (Assessment, Calibration, Comment, CycleInput,
                                    FeedbackInput, FeedbackRequest, GoalInput, Reassignment)
from .policy import role_capabilities, capabilities, require
from .service import name

CYCLE = 'HRMS.PerformanceCycle'
REVIEW = 'HRMS.PerformanceReview'
GOAL = 'HRMS.PerformanceGoal'
FEEDBACK = 'HRMS.ProjectFeedback'
TYPES = (CYCLE, REVIEW, GOAL, FEEDBACK)


def check(condition, message, status=409):
    if not condition:
        raise AppError(status, message)


def parse(model, data):
    try:
        return model.model_validate(data).model_dump(mode='json')
    except ValidationError as exc:
        raise AppError(422, '; '.join(e['msg'] for e in exc.errors())) from exc


class PerformanceService:
    def __init__(self, hrms):
        self.hrms, self.platform, self.journal = hrms, hrms.platform, hrms.journal

    def records(self, kind):
        pack = pack_by_type(kind)
        states = self.platform.states(pack.machine_name)
        return [{**r, 'kind': kind, 'state': states.get(r['entity_id'], 'not_enrolled')}
                for r in self.platform.records(kind, ['identifier', 'hrms_operation_key',
                                                      *[f['field'] for f in pack.fields]])]

    def snapshot(self):
        return {kind: self.records(kind) for kind in TYPES}

    def pending(self, actor):
        with self.journal.lock(actor.organization_id) as db:
            rows = db.execute("SELECT operation_key, progress FROM operations WHERE organization_id=%s AND actor_id=%s AND result IS NULL AND progress ? 'performance_request' ORDER BY updated_at",
                              (actor.organization_id, actor.user_id)).fetchall()
            return [dict(idempotency_key=key, **progress['performance_request']) for key, progress in rows]

    def user_options(self, project_policy=None):
        users = []
        for user in self.platform.users():
            if user.get('status') != 'active' or user.get('email') == self.platform.email:
                continue
            roles = self.platform.call('GET', f"/roles/users/{user['id']}/roles")
            caps = set().union(*(role_capabilities(r['role_name'], project_policy) for r in roles
                                if r['organization_id'] == self.platform.org))
            if any(r['organization_id'] == self.platform.org for r in roles):
                users.append({'id': user['id'], 'name': user['full_name'], 'email': user['email'], 'capabilities': sorted(caps)})
        return users

    def options(self, actor):
        require(actor, 'performance:manage')
        users = self.user_options()
        active = {u['id'] for u in users}
        employees = self.hrms.employees()
        result = []
        for row in employees:
            d = row['data']
            managers = [m for m in employees if d.get('reports_to_employee_code')
                        and m['data'].get('employee_code') == d['reports_to_employee_code']]
            manager = managers[0] if len(managers) == 1 else None
            if d.get('employment_status', '').lower() != 'active' or d.get('platform_user_id') not in active:
                continue
            manager_id = manager['data'].get('platform_user_id') if manager else None
            if manager_id not in active or manager_id == d['platform_user_id']:
                continue
            result.append(dict(id=row['entity_id'], name=name(row), employee_user_id=d['platform_user_id'],
                               manager_user_id=manager_id, manager_name=name(manager)))
        return dict(employees=result, users=users,
                    approvers=[u for u in users if 'performance:approve_cycle' in u['capabilities'] and u['id'] != actor.user_id],
                    calibrators=[u for u in users if 'performance:manage' in u['capabilities']])

    @staticmethod
    def children(snap, kind, field, value):
        return [r for r in snap[kind] if r['data'].get(field) == value]

    @staticmethod
    def find(snap, entity_id):
        row = next((r for rows in snap.values() for r in rows if r['entity_id'] == entity_id), None)
        check(row is not None, 'Performance record was not found', 404)
        return row

    def allowed(self, actor, row, snap):
        d, state = row['data'], row['state']
        manage = 'performance:manage' in capabilities(actor)
        if row['kind'] == CYCLE:
            actions = []
            if manage and d['created_by'] == actor.user_id and state == 'draft':
                actions += ['edit_cycle', 'submit']
            if (state == 'pending_approval' and actor.user_id == d['approver_id']
                    and actor.user_id != d['created_by'] and 'performance:approve_cycle' in capabilities(actor)):
                actions += ['approve', 'request_changes']
            if manage:
                actions += {'open': ['start_reviews'], 'review': ['start_calibration'],
                            'calibration': ['publish'], 'published': ['close']}.get(state, [])
            return actions
        if row['kind'] == FEEDBACK:
            review = self.find(snap, d['review_id'])
            cycle = self.find(snap, review['data']['cycle_id'])
            return ['submit_feedback'] if (actor.user_id == d['reviewer_user_id'] and state == 'pending'
                                           and cycle['state'] in {'review', 'calibration'} and review['state'] == 'manager_review') else []
        if row['kind'] == GOAL:
            review = self.find(snap, d['review_id'])
            return ['edit_goal'] if 'add_goal' in self.allowed(actor, review, snap) else []
        cycle = self.find(snap, d['cycle_id'])
        if cycle['state'] in {'draft', 'pending_approval', 'closed'}:
            return []
        actions = []
        if manage and actor.user_id != d['employee_user_id'] and state not in {'published', 'acknowledged'}:
            actions += ['reassign']
        if actor.user_id == d['employee_user_id']:
            if state == 'goals_draft' and cycle['state'] == 'open':
                actions += ['add_goal', 'submit_goals']
            if state == 'self_review' and cycle['state'] in {'review', 'calibration'}:
                actions += ['submit_self']
            if state == 'published' and cycle['state'] == 'published':
                actions += ['acknowledge']
        if actor.user_id == d['manager_user_id'] and actor.user_id != d['employee_user_id']:
            if state == 'goals_pending' and cycle['state'] == 'open':
                actions += ['approve_goals', 'return_goals']
            if state == 'manager_review' and cycle['state'] in {'review', 'calibration'}:
                actions += ['submit_manager', 'return_self', 'request_feedback']
        if (manage and actor.user_id == d['calibrator_user_id'] and actor.user_id != d['employee_user_id']
                and state == 'calibration' and cycle['state'] == 'calibration'):
            actions += ['calibrate', 'return_manager']
        return actions

    def dashboard(self, actor):
        snap = self.snapshot()
        manage = 'performance:manage' in capabilities(actor)
        reviews = []
        for row in snap[REVIEW]:
            d = row['data']
            own = d['employee_user_id'] == actor.user_id
            if not (manage or own or actor.user_id in (d['manager_user_id'], d['calibrator_user_id'])):
                continue
            cycle = self.find(snap, d['cycle_id'])
            if cycle['state'] in {'draft', 'pending_approval'}:
                continue
            data = {k: v for k, v in d.items() if k not in {'hrms_operation_key'}}
            # Own-review confidentiality takes precedence over any HR role held by the employee.
            if own and (row['state'] not in {'published', 'acknowledged'} or cycle['state'] not in {'published', 'closed'}):
                for field in ('manager_summary', 'manager_rating', 'calibrated_rating', 'final_rating'):
                    data.pop(field, None)
            if own:
                data.pop('calibration_comment', None)
            goals = [dict(id=g['entity_id'], state=g['state'], data={k: v for k, v in g['data'].items()
                       if k not in {'hrms_operation_key'}}, actions=self.allowed(actor, g, snap))
                     for g in self.children(snap, GOAL, 'review_id', row['entity_id'])]
            feedback = [] if own else [dict(id=f['entity_id'], state=f['state'], data={k:v for k,v in f['data'].items()
                        if k != 'hrms_operation_key'}) for f in self.children(snap, FEEDBACK, 'review_id', row['entity_id'])]
            reviews.append(dict(id=row['entity_id'], kind=REVIEW, state=row['state'], data=data,
                                cycle_name=cycle['data']['name'], actions=self.allowed(actor, row, snap),
                                goals=goals, feedback=feedback))
        visible_cycles = {r['data']['cycle_id'] for r in reviews}
        cycles = []
        for row in snap[CYCLE]:
            d = row['data']
            if not (manage or d['approver_id'] == actor.user_id or row['entity_id'] in visible_cycles):
                continue
            data = {k: v for k, v in d.items() if k not in {'hrms_operation_key', 'participants'}}
            if manage or d['approver_id'] == actor.user_id:
                data['participants'] = d['participants']
            cycles.append(dict(id=row['entity_id'], kind=CYCLE, state=row['state'], data=data,
                               actions=self.allowed(actor, row, snap)))
        assigned = []
        for row in snap[FEEDBACK]:
            if row['data']['reviewer_user_id'] == actor.user_id:
                review = self.find(snap, row['data']['review_id'])
                assigned.append(dict(id=row['entity_id'], kind=FEEDBACK, state=row['state'],
                    data={k:v for k,v in row['data'].items() if k != 'hrms_operation_key'},
                    employee_name=review['data']['employee_name'], actions=self.allowed(actor, row, snap)))
        return dict(cycles=cycles, reviews=reviews, assigned_feedback=assigned, can_manage=manage)

    def workflows(self, actor):
        board = self.dashboard(actor)
        return [dict(entity_id=r['id'], entity_type=r['kind'],
                     title=r['data'].get('employee_name') or r['data'].get('name') or r.get('employee_name'),
                     identifier=r['data'].get('identifier', ''), current_state=r['state'],
                     workflow_label=pack_by_type(r['kind']).label,
                     owner_name=self.owner(r), next_action=', '.join(a.replace('_', ' ') for a in r['actions']) or
                         ('Complete' if r['state'] in {'closed', 'acknowledged', 'submitted'} else 'Waiting for assigned owner'),
                     progress=r.get('cycle_name', ''), due_date=None, leave=None, leave_view=None)
                for r in [*board['cycles'], *board['reviews'], *board['assigned_feedback']]]

    @staticmethod
    def owner(row):
        d = row['data']
        if row['kind'] == REVIEW and row['state'] == 'publish_ready':
            return 'HR publication'
        key = {'goals_pending': 'manager_name', 'manager_review': 'manager_name',
               'calibration': 'calibrator_name', 'pending_approval': 'approver_name'}.get(row['state'], 'employee_name')
        return d.get(key) or d.get('reviewer_name') or 'HR'

    def cycle_data(self, actor, data):
        require(actor, 'performance:manage')
        parsed = parse(CycleInput, data)
        options = self.options(actor)
        approver = next((u for u in options['approvers'] if u['id'] == parsed['approver_id']), None)
        check(approver is not None, 'Select a different authorized cycle approver', 422)
        participants = []
        for item in parsed['participants']:
            employee = next((e for e in options['employees'] if e['id'] == item['employee_id']), None)
            calibrator = next((u for u in options['calibrators'] if u['id'] == item['calibrator_user_id']), None)
            check(employee and calibrator, 'Every participant needs an active employee, manager and HR calibrator', 422)
            check(calibrator['id'] != employee['employee_user_id'], 'Employees cannot calibrate their own review', 422)
            participants.append(dict(employee_id=employee['id'], employee_name=employee['name'],
                employee_user_id=employee['employee_user_id'], manager_user_id=employee['manager_user_id'],
                manager_name=employee['manager_name'], calibrator_user_id=calibrator['id'], calibrator_name=calibrator['name']))
        check(len({p['employee_user_id'] for p in participants}) == len(participants), 'Duplicate employee login links need correction', 422)
        return {**parsed, 'participants': participants, 'created_by': actor.user_id, 'approver_name': approver['name']}

    def plan(self, actor, target, action, data, snap):
        ops = []
        def create(kind, values, owner, alias):
            ops.append(dict(op='create', kind=kind, data=values, owner=owner, target=alias))
        def patch(row, values):
            ops.append(dict(op='patch', target=row['entity_id'], data=values))
        def transition(row, trigger):
            ops.append(dict(op='transition', target=row['entity_id'], trigger=trigger))
        if action == 'create_cycle':
            check(target == 'new', 'Use the cycle creation endpoint', 422)
            create(CYCLE, self.cycle_data(actor, data), actor.user_id, 'created')
            return ops
        row = self.find(snap, target)
        check(action in self.allowed(actor, row, snap), 'You cannot perform this action at the current stage', 403)
        d = row['data']
        if action == 'edit_cycle':
            patch(row, self.cycle_data(actor, data))
        elif row['kind'] == CYCLE:
            reviews = self.children(snap, REVIEW, 'cycle_id', target)
            if action == 'approve':
                for index, participant in enumerate(d['participants']):
                    create(REVIEW, {**participant, 'cycle_id': target}, participant['employee_user_id'], f'review-{index}')
            elif action == 'request_changes':
                patch(row, {'decision_comment': parse(Comment, data)['comment']})
            elif action == 'start_reviews':
                check(reviews and all(r['state'] == 'self_review' for r in reviews), 'Every participant needs approved goals first')
            elif action == 'start_calibration':
                check(reviews and all(r['state'] == 'calibration' for r in reviews), 'All manager reviews must be submitted first')
            elif action == 'publish':
                check(reviews and all(r['state'] == 'publish_ready' for r in reviews), 'All reviews must be calibrated before publishing')
                for review in reviews:
                    patch(review, {'final_rating': review['data']['calibrated_rating'], 'published_at': datetime.now(UTC).isoformat()})
                    transition(review, 'publish')
            elif action == 'close':
                check(reviews and all(r['state'] == 'acknowledged' for r in reviews), 'Every employee must acknowledge before closing')
            transition(row, action)
        elif action in {'add_goal', 'edit_goal'}:
            review = row if row['kind'] == REVIEW else self.find(snap, d['review_id'])
            cycle = self.find(snap, review['data']['cycle_id'])
            goal = parse(GoalInput, data)
            check(cycle['data']['start_date'] <= goal['target_date'] <= cycle['data']['end_date'], 'Goal target must be inside cycle dates', 422)
            if action == 'add_goal':
                create(GOAL, {**goal, 'review_id': target}, actor.user_id, 'created')
            else:
                patch(row, goal)
        elif row['kind'] == FEEDBACK:
            patch(row, parse(FeedbackInput, data))
            transition(row, 'submit')
        else:
            goals = self.children(snap, GOAL, 'review_id', target)
            if action == 'reassign':
                assignment = parse(Reassignment, data)
                users = {u['id']: u for u in self.user_options()}
                manager = users.get(assignment['manager_user_id'])
                calibrator = users.get(assignment['calibrator_user_id'])
                check(manager and calibrator and 'performance:manage' in calibrator['capabilities'], 'Choose an active manager and HR calibrator', 422)
                check(d['employee_user_id'] not in {manager['id'], calibrator['id']}, 'Employees cannot assess or calibrate their own review', 422)
                patch(row, dict(manager_user_id=manager['id'], manager_name=manager['name'],
                                calibrator_user_id=calibrator['id'], calibrator_name=calibrator['name']))
                ops[-1]['previous_assignment'] = {key: d[key] for key in ('manager_user_id', 'manager_name', 'calibrator_user_id', 'calibrator_name')}
                return ops
            if action in {'submit_goals', 'approve_goals'}:
                check(goals and sum(g['data']['weight'] for g in goals) == 100, 'Goal weights must total exactly 100%')
                expected = {'draft', 'changes_requested'} if action == 'submit_goals' else {'pending_approval'}
                check(all(g['state'] in expected for g in goals), 'Goals are not in the expected stage')
                for goal in goals:
                    transition(goal, 'submit' if action == 'submit_goals' else 'approve')
            elif action == 'return_goals':
                comment = parse(Comment, data)['comment']
                for goal in goals:
                    patch(goal, {'manager_comment': comment})
                    transition(goal, 'request_changes')
                patch(row, {'return_comment': comment})
            elif action in {'return_self', 'return_manager'}:
                field = 'calibration_comment' if action == 'return_manager' else 'return_comment'
                patch(row, {field: parse(Comment, data)['comment']})
            elif action in {'submit_self', 'submit_manager'}:
                assessment = parse(Assessment, data)
                if action == 'submit_self':
                    check(goals and all(g['state'] == 'approved' for g in goals), 'Approved goals are required')
                else:
                    feedback = self.children(snap, FEEDBACK, 'review_id', target)
                    check(all(f['state'] == 'submitted' for f in feedback), 'Requested project feedback is still pending')
                prefix = 'self' if action == 'submit_self' else 'manager'
                patch(row, {f'{prefix}_summary': assessment['summary'], f'{prefix}_rating': assessment['rating']})
            elif action == 'request_feedback':
                request = parse(FeedbackRequest, data)
                reviewer = next((u for u in self.user_options() if u['id'] == request['reviewer_user_id']), None)
                check(reviewer and reviewer['id'] != d['employee_user_id'], 'Select an active reviewer other than the employee', 422)
                check(not any(f['data']['reviewer_user_id'] == reviewer['id'] and f['data']['project_reference'] == request['project_reference']
                              for f in self.children(snap, FEEDBACK, 'review_id', target)), 'Feedback was already requested')
                create(FEEDBACK, {**request, 'review_id': target, 'reviewer_name': reviewer['name']}, reviewer['id'], 'created')
                return ops
            elif action == 'calibrate':
                value = parse(Calibration, data)
                patch(row, {'calibrated_rating': value['rating'], 'calibration_comment': value['comment']})
            elif action == 'acknowledge':
                check(set(data) <= {'comment'}, 'Only an acknowledgement comment is accepted', 422)
                comment = data.get('comment', '')
                check(isinstance(comment, str) and len(comment) <= 4000, 'Invalid comment', 422)
                patch(row, {'employee_comment': comment, 'acknowledged_at': datetime.now(UTC).isoformat()})
            transition(row, action)
        return ops

    def execute(self, actor, target, request):
        check(actor.organization_id == self.platform.org, 'Wrong organization', 403)
        if request.action in {'create_cycle', 'edit_cycle', 'submit', 'start_reviews', 'start_calibration', 'publish', 'close', 'calibrate', 'return_manager', 'reassign'}:
            require(actor, 'performance:manage')
        if request.action in {'approve', 'request_changes'}:
            require(actor, 'performance:approve_cycle')
        payload = request.model_dump(mode='json')
        key = request.idempotency_key
        with self.journal.lock(actor.organization_id) as db:
            operation = self.journal.operation(db, actor, key, {'target': target, **payload})
            if operation.result is not None:
                return operation.result
            # Never let another action interleave with an incompletely applied multi-record plan.
            pending = db.execute("SELECT operation_key FROM operations WHERE organization_id=%s AND operation_key<>%s AND result IS NULL AND progress ? 'performance_plan' LIMIT 1",
                                 (actor.organization_id, key)).fetchone()
            check(not pending, 'A performance action needs recovery. Retry its original request before continuing.', 409)
            if 'performance_plan' not in operation.progress:
                plan = self.plan(actor, target, request.action, request.data, self.snapshot())
                operation.checkpoint(performance_plan=plan, performance_request={'target': target, 'action': request.action, 'data': request.data}, step=0, refs={})
            plan = operation.progress['performance_plan']
            refs = operation.progress['refs']
            for index in range(operation.progress['step'], len(plan)):
                step = plan[index]
                marker = hashlib.sha256(f'{actor.organization_id}:{key}:{index}'.encode()).hexdigest()
                if step['op'] == 'create':
                    rows = self.platform.records(step['kind'], ['hrms_operation_key'])
                    matches = [r for r in rows if r['data'].get('hrms_operation_key') == marker]
                    check(len(matches) <= 1, 'Duplicate operation records need reconciliation')
                    if matches:
                        entity_id = matches[0]['entity_id']
                    else:
                        check(operation.progress.get('creating') != index, 'Creation result is uncertain; an administrator must reconcile before retrying')
                        operation.checkpoint(creating=index)
                        record = self.platform.create_record(step['kind'], {**step['data'], 'hrms_operation_key': marker}, step['owner'])
                        entity_id = record['entity_id']
                    self.platform.enroll(entity_id, pack_by_type(step['kind']).machine_name)
                    refs[step['target']] = entity_id
                elif step['op'] == 'patch':
                    record = self.platform.record(step['target'])
                    self.platform.call('PUT', f"/entity-records/{step['target']}", json={'data': {**record['data'], **step['data']}})
                else:
                    self.platform.call('POST', f"/entities/{step['target']}/transitions", json={
                        'entity_id': step['target'], 'trigger': step['trigger'], 'idempotency_key': marker,
                        'inputs': {'hrms_actor_id': actor.user_id, 'hrms_operation_key': key}})
                operation.checkpoint(step=index + 1, refs=refs, creating=None)
            result = {'entity_id': refs.get('created', target), 'action': request.action}
            self.journal.audit(db, actor, f'performance:{request.action}', result['entity_id'], operation_key=key)
            operation.finish(result)
            return result
